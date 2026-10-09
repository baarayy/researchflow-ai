"""Deterministic, offline stand-in for an LLM (demo mode and tests).

It implements the same `ResearchModel` interface with simple rules over the raw `context`:
keyword overlap for evidence extraction, templates for plans and reports. Its output is only
as good as those rules; it exists so the full workflow can run without API keys.
"""

import re
import uuid
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import ToolCall
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.ai.models import ResearchModel
from app.ai.rag.embeddings import tokenize
from app.ai.schemas import (
    ComparisonTable,
    CriticAssessment,
    EvidenceAnalysis,
    ExtractedClaim,
    GapQuery,
    GroundedAnswer,
    PlannedTask,
    ReportDraft,
    ReportFinding,
    ResearchPlan,
    TaskCoverage,
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_ASPECT_LEAD = re.compile(
    r"\b(?:evaluate|evaluating|including|assess|assessing|regarding)\b([^.?!]+)", re.I
)
_LEAD_VERB = re.compile(
    r"^(?:compare|explain|describe|evaluate|summari[sz]e|what (?:is|are)|how (?:do|does|can))\s+",
    re.I,
)


# Words the mock's own question templates add; they say nothing about the topic.
_TEMPLATE_WORDS = frozenset(
    tokenize(
        "evidence say does about context exist look specific data sources current landscape "
        "background reviewer request"
    )
)


def _sentences(text: str) -> list[str]:
    prose = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return [s.strip() for s in _SENTENCE.split(prose) if len(s.strip()) > 20]


def _overlap(a: str, b: str) -> int:
    return len((set(tokenize(a)) & set(tokenize(b))) - _TEMPLATE_WORDS)


def _core(question: str) -> str:
    """First sentence without its leading verb: 'Compare X for Y.' -> 'X for Y'."""
    first = _SENTENCE.split(question.strip())[0].rstrip(".?!")
    return _LEAD_VERB.sub("", first)[:200]


def _aspects(question: str) -> list[str]:
    match = _ASPECT_LEAD.search(question)
    if not match:
        return []
    parts = re.split(r",|\band\b", match.group(1))
    cleaned = [re.sub(r"^\s*(their|the|its)\s+", "", p.strip(), flags=re.I) for p in parts]
    return [c for c in cleaned if len(c) > 2][:4]


class MockResearchModel(ResearchModel):
    name = "mock"

    async def structured[T: BaseModel](
        self,
        schema: type[T],
        prompt: ChatPromptTemplate,
        inputs: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> T:
        handlers = {
            ResearchPlan: self._plan,
            EvidenceAnalysis: self._analyze,
            CriticAssessment: self._critic,
            ReportDraft: self._report,
            GroundedAnswer: self._grounded,
        }
        if schema not in handlers:
            raise NotImplementedError(f"Mock model has no handler for {schema.__name__}")
        return handlers[schema](context or {})  # type: ignore[return-value]

    async def tool_calls(
        self,
        prompt: ChatPromptTemplate,
        inputs: dict[str, Any],
        tools: Sequence[type[BaseModel]],
        *,
        context: dict[str, Any] | None = None,
    ) -> list[ToolCall]:
        ctx = context or {}
        names = {t.__name__ for t in tools}
        calls: list[ToolCall] = []
        for task in ctx.get("tasks", []):
            for pref, tool in (("web", "WebSearch"), ("documents", "DocumentSearch")):
                if pref in task["preferred_sources"] and tool in names:
                    calls.append(
                        ToolCall(
                            name=tool,
                            args={"query": task["question"], "task_id": task["id"]},
                            id=str(uuid.uuid4()),
                        )
                    )
        return calls

    # --- handlers ---------------------------------------------------------------------

    def _plan(self, ctx: dict[str, Any]) -> ResearchPlan:
        question = ctx["question"]
        core = _core(question)
        prefs: list[Any] = ["web", "documents"] if ctx.get("documents_available") else ["web"]
        tasks = [
            PlannedTask(
                question=f"What is the current landscape and background for: {core}?",
                rationale="Establishes context and key terms.",
                evidence_type="background overview",
                preferred_sources=prefs,
            )
        ]
        tasks += [
            PlannedTask(
                question=f"What does the evidence say about {a}? (context: {core})",
                rationale=f"The question explicitly asks about {a}.",
                evidence_type="specific data or analysis",
                preferred_sources=prefs,
            )
            for a in _aspects(question)
        ]
        tasks.append(
            PlannedTask(
                question=f"What limitations, risks or open questions exist for: {core}?",
                rationale="Surfaces uncertainty and caveats.",
                evidence_type="critical analysis",
                preferred_sources=prefs,
            )
        )
        tasks += [
            PlannedTask(
                question=f"Reviewer request: {fb}",
                rationale="Added from reviewer feedback.",
                evidence_type="reviewer request",
                preferred_sources=prefs,
            )
            for fb in ctx.get("feedback", [])
            if fb
        ]
        return ResearchPlan(objective=f"Answer: {core}", tasks=tasks[:8])

    def _analyze(self, ctx: dict[str, Any]) -> EvidenceAnalysis:
        tasks = {t["id"]: t for t in ctx.get("tasks", [])}
        sources = ctx.get("sources", {})
        claims: list[ExtractedClaim] = []
        answered: set[str] = set()
        # Score each task on what makes it distinct, not on context words every task shares.
        token_sets = [set(tokenize(t["question"])) for t in tasks.values()]
        shared = set.intersection(*token_sets) if len(token_sets) > 1 else set()
        for item in ctx.get("inbox", []):
            source, task = sources.get(item["source_id"]), tasks.get(item["task_id"])
            if not source or not task:
                continue
            own = set(tokenize(task["question"])) - _TEMPLATE_WORDS
            focus = (own - shared) or own  # a pure-context task (e.g. background) keeps its words

            def score(sentence: str, focus: set[str] = focus) -> int:
                return len(set(tokenize(sentence)) & focus)

            ranked = sorted(_sentences(source["content"]), key=score, reverse=True)
            for sentence in [s for s in ranked if score(s) >= 1][:2]:
                claims.append(
                    ExtractedClaim(
                        source_id=item["source_id"],
                        task_id=item["task_id"],
                        claim=sentence,
                        quote=sentence,
                        confidence=0.7 if source["content_kind"] != "snippet" else 0.6,
                    )
                )
                answered.add(item["task_id"])
        gaps = [
            f"No evidence found for: {t['question']}"
            for tid, t in tasks.items()
            if t["status"] == "in_progress" and tid not in answered
        ]
        return EvidenceAnalysis(
            claims=claims,
            gaps=gaps,
            summary=f"Extracted {len(claims)} claim(s) from {len(sources)} source(s).",
        )

    def _critic(self, ctx: dict[str, Any]) -> CriticAssessment:
        tasks, evidence = ctx.get("tasks", []), ctx.get("evidence", [])
        covered = {e["task_id"] for e in evidence}
        coverage = len([t for t in tasks if t["id"] in covered]) / max(len(tasks), 1)
        quality = "high" if coverage >= 0.9 else "medium" if coverage >= 0.5 else "low"
        gaps = [
            GapQuery(
                question=f"{t['question']} Look for specific data and sources.",
                rationale="No evidence was found for this subquestion.",
            )
            for t in tasks
            if t["id"] not in covered and t["origin"] == "plan"
        ][:4]
        return CriticAssessment(
            task_coverage=[
                TaskCoverage(task_id=t["id"], covered=t["id"] in covered) for t in tasks
            ],
            evidence_quality=quality,
            citation_completeness=1.0 if evidence else 0.0,
            remaining_gaps=gaps,
            needs_more_research=bool(gaps),
            summary=f"{len(covered & {t['id'] for t in tasks})} of {len(tasks)} subquestions have evidence.",
        )

    def _report(self, ctx: dict[str, Any]) -> ReportDraft:
        tasks, evidence = ctx["tasks"], ctx["evidence"]
        findings = []
        for t in tasks:
            items = [e for e in evidence if e["task_id"] == t["id"]][:3]
            if items:
                findings.append(
                    ReportFinding(
                        heading=t["question"],
                        statement=" ".join(e["claim"] for e in items),
                        evidence_ids=[e["id"] for e in items],
                        kind="fact",
                    )
                )
        answered = len(findings)
        findings.append(
            ReportFinding(
                heading="Overall assessment",
                statement=f"The collected sources address {answered} of {len(tasks)} subquestions; "
                "conclusions beyond the cited claims would need further research.",
                kind="inference",
            )
        )
        table = None
        if re.search(r"\b(compare|comparison|versus|vs\.?)\b", ctx["question"], re.I):
            table = ComparisonTable(
                title="Evidence by subquestion",
                columns=["Subquestion", "Evidence items", "Sources"],
                rows=[
                    [
                        t["question"],
                        str(len([e for e in evidence if e["task_id"] == t["id"]])),
                        str(len({e["source_id"] for e in evidence if e["task_id"] == t["id"]})),
                    ]
                    for t in tasks
                ],
            )
        return ReportDraft(
            executive_summary=f"This report compiles {len(evidence)} evidence item(s) from "
            f"{len({e['source_id'] for e in evidence})} source(s) across {len(tasks)} subquestions.",
            methodology="The question was decomposed into subquestions; each was searched with the "
            "enabled tools, and sentences matching the subquestion were extracted as evidence.",
            findings=findings,
            comparison_table=table,
            contradictions_and_uncertainties=[],
            limitations=[
                f"No evidence found for: {t['question']}"
                for t in tasks
                if not any(e["task_id"] == t["id"] for e in evidence)
            ],
            conclusions="The findings above are limited to what the retrieved sources state.",
        )

    def _grounded(self, ctx: dict[str, Any]) -> GroundedAnswer:
        question, passages = ctx["question"], ctx.get("passages", [])
        best: list[tuple[int, str, str]] = []
        for p in passages:
            for s in _sentences(p["text"]) or [p["text"]]:
                if (score := _overlap(s, question)) >= 1:
                    best.append((score, s, p["id"]))
        best.sort(key=lambda x: x[0], reverse=True)
        if not best:
            return GroundedAnswer(
                answer="The documents do not contain enough information to answer this question.",
                sufficient_evidence=False,
            )
        top = best[:3]
        return GroundedAnswer(
            answer=" ".join(s for _, s, _ in top),
            cited_passage_ids=list(dict.fromkeys(pid for _, _, pid in top)),
            sufficient_evidence=True,
        )
