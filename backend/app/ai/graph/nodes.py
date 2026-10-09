"""Graph nodes. Each node reads the state and returns a partial update.

Nodes are methods on `ResearchNodes` so they share injected dependencies (model, search
provider, retriever, settings) without globals. Provider failures are caught and recorded as
recoverable errors; the workflow degrades (e.g. fewer sources, fallback report) rather than
crashing. Only a planner failure ends the run, since nothing useful can happen without a plan.
"""

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, TypedDict

from langgraph.types import interrupt

from app.ai.graph.edges import research_outcome
from app.ai.graph.state import (
    EvidenceRecord,
    InboxItem,
    ResearchState,
    SearchLogEntry,
    SourceRecord,
    TaskState,
    ToolCallRecord,
)
from app.ai.models import ResearchModel
from app.ai.prompts import (
    ANALYZER,
    CRITIC,
    DISPATCHER,
    PLANNER,
    REPORT,
    fence,
    render_list,
    render_tasks,
)
from app.ai.rag.retrieval import DocumentRetriever, RetrievalFilters
from app.ai.schemas import (
    CriticAssessment,
    EvidenceAnalysis,
    ReportDraft,
    ReportFinding,
    ResearchPlan,
)
from app.ai.tools.document_search import DocumentSearch
from app.ai.tools.web_search import SearchProvider, WebSearch
from app.core.config import Settings
from app.core.retry import call_with_retries
from app.services import citation_service

logger = logging.getLogger(__name__)

MAX_PLAN_REVISIONS = 3
MAX_TASK_ATTEMPTS = 2
SOURCE_TEXT_LIMIT = 3000
ToolName = Literal["web_search", "document_search"]
TOOL_NAMES: dict[str, ToolName] = {"WebSearch": "web_search", "DocumentSearch": "document_search"}


@dataclass
class ResearchDeps:
    llm: ResearchModel
    search: SearchProvider
    retriever: DocumentRetriever
    settings: Settings


class ResearcherInput(TypedDict):
    """Payload of a `Send` to a researcher node (not the full graph state)."""

    call: ToolCallRecord
    owner_id: str
    document_ids: list[str] | None
    iteration: int


# --- small helpers ----------------------------------------------------------------------


def short_hash(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:10]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def active_tasks(state: ResearchState) -> list[TaskState]:
    return [t for t in state.get("tasks", []) if t["status"] != "dropped"]


def is_outdated(published: str | None, max_age_days: int) -> bool:
    if not published:
        return False
    try:
        published_on = date.fromisoformat(published[:10])
    except ValueError:
        return False
    return published_on < date.today() - timedelta(days=max_age_days)


def _filters(owner_id: str, document_ids: list[str] | None) -> RetrievalFilters:
    ids = [uuid.UUID(d) for d in document_ids] if document_ids is not None else None
    return RetrievalFilters(owner_id=owner_id, document_ids=ids)


def _error(node: str, message: str, recoverable: bool = True) -> dict[str, Any]:
    return {"node": node, "message": message, "recoverable": recoverable}


class ResearchNodes:
    def __init__(self, deps: ResearchDeps):
        self.deps = deps
        self.llm = deps.llm
        self.settings = deps.settings

    async def _documents_available(self, state: ResearchState) -> bool:
        options = state["options"]
        if not options.get("use_documents"):
            return False
        try:
            return await self.deps.retriever.has_documents(
                _filters(state["owner_id"], options.get("document_ids"))
            )
        except Exception:
            logger.exception("Could not check document availability")
            return False

    # --- A. Planner ---------------------------------------------------------------------

    async def planner(self, state: ResearchState) -> dict[str, Any]:
        docs_available = await self._documents_available(state)
        feedback = state.get("human_feedback", [])
        try:
            plan = await self.llm.structured(
                ResearchPlan,
                PLANNER,
                {
                    "question": state["question"],
                    "documents_available": "yes" if docs_available else "no",
                    "feedback": render_list(feedback),
                },
                context={
                    "question": state["question"],
                    "feedback": feedback,
                    "documents_available": docs_available,
                },
            )
        except Exception as exc:
            logger.exception("Planner failed")
            return {
                "status": "failed",
                "errors": [
                    _error(
                        "planner",
                        f"Could not create a research plan ({type(exc).__name__}).",
                        False,
                    )
                ],
            }

        max_tasks = state["limits"]["max_tasks"]
        tasks: list[TaskState] = []
        for i, t in enumerate(plan.tasks[:max_tasks], start=1):
            prefs: list[str] = [
                p for p in t.preferred_sources if p != "documents" or docs_available
            ]
            tasks.append(
                {
                    "id": f"T{i}",
                    "question": t.question.strip(),
                    "rationale": t.rationale.strip(),
                    "evidence_type": t.evidence_type.strip(),
                    "preferred_sources": prefs or ["web"],
                    "status": "pending",
                    "origin": "plan",
                    "iteration_added": 0,
                    "attempts": 0,
                }
            )
        # On a revision, tasks from the previous plan that are not replaced are dropped.
        new_ids = {t["id"] for t in tasks}
        dropped = [
            {**t, "status": "dropped"} for t in state.get("tasks", []) if t["id"] not in new_ids
        ]
        return {
            "objective": plan.objective,
            "tasks": tasks + dropped,
            "plan_approved": False,
            "status": "running",
            "iteration": state.get("iteration", 0),
            "tool_calls_used": state.get("tool_calls_used", 0),
        }

    # --- H1. Human approval of the plan -------------------------------------------------

    def plan_review(self, state: ResearchState) -> dict[str, Any]:
        if not state["options"].get("require_plan_approval"):
            return {"plan_approved": True}
        # interrupt() pauses the graph here and persists the checkpoint. When resumed with
        # Command(resume=decision), this node re-runs from the top and interrupt() returns it.
        decision = interrupt(
            {
                "kind": "plan_review",
                "objective": state.get("objective", ""),
                "tasks": active_tasks(state),
                "revision": state.get("plan_revisions", 0),
            }
        )
        if decision.get("action") == "approve":
            return {"plan_approved": True}
        revisions = state.get("plan_revisions", 0) + 1
        feedback = str(decision.get("feedback") or "").strip()[:2000]
        if revisions > MAX_PLAN_REVISIONS:
            return {
                "plan_approved": True,
                "errors": [
                    _error(
                        "plan_review", "Revision limit reached; continuing with the current plan."
                    )
                ],
            }
        return {"plan_approved": False, "plan_revisions": revisions, "human_feedback": [feedback]}

    # --- B. Research dispatcher ---------------------------------------------------------

    async def dispatcher(self, state: ResearchState) -> dict[str, Any]:
        iteration = state.get("iteration", 0) + 1
        pending = [t for t in state.get("tasks", []) if t["status"] == "pending"]
        options = state["options"]
        allowed: dict[str, type] = {}
        if options.get("use_web"):
            allowed["web_search"] = WebSearch
        if await self._documents_available(state):
            allowed["document_search"] = DocumentSearch

        update: dict[str, Any] = {"iteration": iteration, "planned_calls": []}
        if not pending or not allowed:
            if not allowed:
                update["errors"] = [
                    _error(
                        "dispatcher",
                        "No research tools are available (web search disabled and no ready documents).",
                    )
                ]
            update["tasks"] = [
                {**t, "status": "no_evidence", "attempts": t["attempts"] + 1} for t in pending
            ]
            return update

        used = {(e["tool"], normalize(e["query"])) for e in state.get("search_log", [])}
        try:
            proposed = await self.llm.tool_calls(
                DISPATCHER,
                {
                    "question": state["question"],
                    "tasks": render_tasks(pending),
                    "used": render_list(q for _, q in used),
                },
                list(allowed.values()),
                context={"tasks": pending, "allowed": list(allowed)},
            )
        except Exception as exc:
            logger.warning("Tool selection failed, using default routing: %s", exc)
            proposed = []
            update["errors"] = [
                _error("dispatcher", "Tool selection failed; used default routing.")
            ]

        pending_ids = {t["id"] for t in pending}
        calls: list[ToolCallRecord] = []
        for proposal in proposed:
            tool = TOOL_NAMES.get(proposal["name"])
            args = proposal.get("args") or {}
            query = str(args.get("query", "")).strip()[:300]
            task_id = str(args.get("task_id", ""))
            if tool in allowed and task_id in pending_ids and query:  # ignore anything else
                calls.append({"tool": tool, "query": query, "task_id": task_id})

        # Every pending task gets at least a default call, so one sloppy model reply can't stall it.
        covered = {c["task_id"] for c in calls}
        for t in pending:
            if t["id"] not in covered:
                for pref in t["preferred_sources"]:
                    default: ToolName = "web_search" if pref == "web" else "document_search"
                    if default in allowed:
                        calls.append(
                            {"tool": default, "query": t["question"][:300], "task_id": t["id"]}
                        )

        # Deduplicate against earlier iterations and within this batch; respect the budget.
        budget = state["limits"]["max_tool_calls"] - state.get("tool_calls_used", 0)
        unique: list[ToolCallRecord] = []
        for c in calls:
            key = (c["tool"], normalize(c["query"]))
            if key not in used and len(unique) < budget:
                used.add(key)
                unique.append(c)

        dispatched = {c["task_id"] for c in unique}
        update["planned_calls"] = unique
        update["tool_calls_used"] = state.get("tool_calls_used", 0) + len(unique)
        update["tasks"] = [
            {**t, "status": "in_progress", "attempts": t["attempts"] + 1}
            if t["id"] in dispatched
            else {**t, "status": "no_evidence", "attempts": t["attempts"] + 1}  # nothing new to try
            for t in pending
        ]
        return update

    # --- C. Web researcher --------------------------------------------------------------

    async def web_researcher(self, payload: ResearcherInput) -> dict[str, Any]:
        call, iteration = payload["call"], payload["iteration"]
        s = self.settings
        log: SearchLogEntry = {
            "tool": "web_search",
            "query": call["query"],
            "task_id": call["task_id"],
            "iteration": iteration,
            "status": "ok",
            "result_count": 0,
        }
        try:
            results = await call_with_retries(
                lambda: self.deps.search.search(call["query"], s.search_max_results),
                what="web search",
                timeout=s.search_timeout_seconds,
                retries=s.external_max_retries,
            )
        except Exception as exc:
            logger.warning("Web search failed for %r: %s", call["query"], exc)
            return {
                "search_log": [{**log, "status": "error", "error": str(exc)[:200]}],
                "errors": [
                    _error("web_researcher", f"Web search failed for '{call['query'][:80]}'.")
                ],
            }

        now = datetime.now(UTC).isoformat()
        sources: dict[str, SourceRecord] = {}
        inbox: list[InboxItem] = []
        for r in results:
            sid = f"W-{short_hash(r.url)}"
            sources[sid] = {
                "id": sid,
                "kind": "web",
                "title": r.title[:300],
                "url": r.url,
                "document_id": None,
                "chunk_id": None,
                "page_number": None,
                "content": r.content[:SOURCE_TEXT_LIMIT],
                "content_kind": r.content_kind,
                "published_date": r.published_date,
                "retrieved_at": now,
                "possibly_outdated": is_outdated(r.published_date, s.outdated_after_days),
            }
            inbox.append({"task_id": call["task_id"], "source_id": sid, "query": call["query"]})
        log["status"], log["result_count"] = ("ok" if results else "empty"), len(results)
        return {"sources": sources, "inbox": inbox, "search_log": [log]}

    # --- D. Document researcher ---------------------------------------------------------

    async def document_researcher(self, payload: ResearcherInput) -> dict[str, Any]:
        call, iteration = payload["call"], payload["iteration"]
        log: SearchLogEntry = {
            "tool": "document_search",
            "query": call["query"],
            "task_id": call["task_id"],
            "iteration": iteration,
            "status": "ok",
            "result_count": 0,
        }
        try:
            passages = await self.deps.retriever.retrieve(
                call["query"], _filters(payload["owner_id"], payload["document_ids"])
            )
        except Exception as exc:
            logger.exception("Document retrieval failed")
            return {
                "search_log": [{**log, "status": "error", "error": type(exc).__name__}],
                "errors": [_error("document_researcher", "Document retrieval failed.")],
            }

        now = datetime.now(UTC).isoformat()
        sources: dict[str, SourceRecord] = {}
        inbox: list[InboxItem] = []
        for p in passages:
            sid = f"D-{short_hash(str(p.chunk_id))}"
            sources[sid] = {
                "id": sid,
                "kind": "document",
                "title": p.filename,
                "url": None,
                "document_id": str(p.document_id),
                "chunk_id": str(p.chunk_id),
                "page_number": p.page_number,
                "content": p.text[:SOURCE_TEXT_LIMIT],
                "content_kind": "passage",
                "published_date": None,
                "retrieved_at": now,
                "possibly_outdated": False,
            }
            inbox.append({"task_id": call["task_id"], "source_id": sid, "query": call["query"]})
        log["status"], log["result_count"] = ("ok" if passages else "empty"), len(passages)
        return {"sources": sources, "inbox": inbox, "search_log": [log]}

    # --- E. Evidence analyzer -----------------------------------------------------------

    async def evidence_analyzer(self, state: ResearchState) -> dict[str, Any]:
        inbox = state.get("inbox") or []
        all_sources = state.get("sources", {})
        tasks = active_tasks(state)
        task_ids = {t["id"] for t in tasks}
        update: dict[str, Any] = {"inbox": None}  # None clears the inbox (see inbox_reducer)

        new_evidence: list[EvidenceRecord] = []
        if inbox:
            source_ids = list(dict.fromkeys(i["source_id"] for i in inbox))
            task_for_source = {i["source_id"]: i["task_id"] for i in inbox}
            batch = {sid: all_sources[sid] for sid in source_ids if sid in all_sources}
            rendered = "\n\n".join(
                fence(
                    sid,
                    s["content"],
                    kind=s["kind"],
                    title=s["title"],
                    content_kind=s["content_kind"],
                    published=s.get("published_date"),
                    task=task_for_source[sid],
                )
                for sid, s in batch.items()
            )
            try:
                analysis = await self.llm.structured(
                    EvidenceAnalysis,
                    ANALYZER,
                    {
                        "question": state["question"],
                        "tasks": render_tasks(tasks),
                        "today": date.today().isoformat(),
                        "sources": rendered,
                    },
                    context={"inbox": inbox, "sources": batch, "tasks": tasks},
                )
            except Exception as exc:
                logger.warning("Evidence analysis failed: %s", exc)
                analysis = EvidenceAnalysis()
                update["errors"] = [
                    _error("evidence_analyzer", "Evidence analysis failed for this batch.")
                ]

            iteration = state.get("iteration", 0)
            dropped = 0
            for c in analysis.claims:
                source = batch.get(c.source_id)
                if source is None:  # model cited a source it was not shown
                    dropped += 1
                    continue
                task_id = c.task_id if c.task_id in task_ids else task_for_source[c.source_id]
                quote = (c.quote or "").strip() or None
                verified = quote is not None and normalize(quote) in normalize(source["content"])
                eid = f"E-{short_hash(c.source_id, task_id, normalize(c.claim))}"
                new_evidence.append(
                    {
                        "id": eid,
                        "source_id": c.source_id,
                        "task_id": task_id,
                        "claim": c.claim.strip(),
                        "quote": quote,
                        "quote_verified": verified,
                        # Unverifiable quotes and snippets lower confidence.
                        "confidence": round(
                            c.confidence
                            * (1 if verified or not quote else 0.6)
                            * (0.8 if source["content_kind"] == "snippet" else 1),
                            2,
                        ),
                        "iteration": iteration,
                    }
                )
            if dropped:
                update.setdefault("errors", []).append(
                    _error(
                        "evidence_analyzer",
                        f"Dropped {dropped} claim(s) attributed to unknown sources.",
                    )
                )

            if outdated := [sid for sid in analysis.outdated_source_ids if sid in batch]:
                update["sources"] = {
                    sid: {**batch[sid], "possibly_outdated": True} for sid in outdated
                }
            update["contradictions"] = state.get("contradictions", []) + [
                {
                    "description": c.description,
                    "source_ids": [s for s in c.source_ids if s in all_sources],
                }
                for c in analysis.contradictions
            ]
            update["knowledge_gaps"] = analysis.gaps
            if analysis.summary:
                update["summaries"] = [analysis.summary]

        update["evidence"] = new_evidence
        evidence_tasks = {e["task_id"] for e in state.get("evidence", []) + new_evidence}
        update["tasks"] = [
            {**t, "status": "done" if t["id"] in evidence_tasks else "no_evidence"}
            for t in tasks
            if t["status"] == "in_progress"
        ]
        return update

    # --- F. Critic ----------------------------------------------------------------------

    async def critic(self, state: ResearchState) -> dict[str, Any]:
        limits = state["limits"]
        tasks = active_tasks(state)
        evidence = state.get("evidence", [])
        covered = {e["task_id"] for e in evidence}
        coverage = len([t for t in tasks if t["id"] in covered]) / max(len(tasks), 1)

        assessment: CriticAssessment | None = None
        try:
            assessment = await self.llm.structured(
                CriticAssessment,
                CRITIC,
                {
                    "question": state["question"],
                    "tasks": render_tasks(tasks),
                    "evidence": render_list(
                        f"[{e['task_id']}] {e['claim']}" for e in evidence[-60:]
                    ),
                    "gaps": render_list(state.get("knowledge_gaps", [])),
                    "iteration": state.get("iteration", 0),
                    "max_iterations": limits["max_iterations"],
                },
                context={"tasks": tasks, "evidence": evidence},
            )
        except Exception as exc:
            logger.warning("Critic failed, using coverage-only assessment: %s", exc)

        quality = assessment.evidence_quality if assessment else ("medium" if coverage else "low")
        # Explicit rule: the model's opinion can veto "sufficient" but cannot override coverage.
        sufficient = (
            coverage >= limits["coverage_threshold"]
            and quality != "low"
            and not (assessment and assessment.needs_more_research)
        )

        new_tasks: list[TaskState] = []
        if not sufficient:
            known = {normalize(t["question"]) for t in state.get("tasks", [])}
            room = limits["max_tasks"] - len(state.get("tasks", []))
            for gap in (assessment.remaining_gaps if assessment else [])[: max(room, 0)]:
                if normalize(gap.question) in known:
                    continue
                known.add(normalize(gap.question))
                new_tasks.append(
                    {
                        "id": f"T{len(state.get('tasks', [])) + len(new_tasks) + 1}",
                        "question": gap.question,
                        "rationale": gap.rationale,
                        "evidence_type": "gap follow-up",
                        "preferred_sources": ["web", "documents"],
                        "status": "pending",
                        "origin": "critic",
                        "iteration_added": state.get("iteration", 0),
                        "attempts": 0,
                    }
                )
            # Retry unanswered tasks once more (the dispatcher skips repeated queries).
            new_tasks += [
                {**t, "status": "pending"}
                for t in tasks
                if t["status"] == "no_evidence" and t["attempts"] < MAX_TASK_ATTEMPTS
            ]

        return {
            "critic": {
                "iteration": state.get("iteration", 0),
                "coverage": round(coverage, 2),
                "evidence_quality": quality,
                "citation_completeness": assessment.citation_completeness if assessment else None,
                "task_coverage": [tc.model_dump() for tc in assessment.task_coverage]
                if assessment
                else [],
                "remaining_gaps": [g.question for g in assessment.remaining_gaps]
                if assessment
                else [],
                "model_requested_more": bool(assessment and assessment.needs_more_research),
                "summary": assessment.summary
                if assessment
                else "Automatic coverage-based assessment.",
                "sufficient": sufficient,
            },
            "tasks": new_tasks,
        }

    # --- H2. Human approval before the report -------------------------------------------

    def report_review(self, state: ResearchState) -> dict[str, Any]:
        critic = state.get("critic") or {}
        decision = interrupt(
            {
                "kind": "report_review",
                "outcome": research_outcome(state),
                "coverage": critic.get("coverage"),
                "evidence_count": len(state.get("evidence", [])),
                "source_count": len(state.get("sources", {})),
                "critic_summary": critic.get("summary"),
                "remaining_gaps": critic.get("remaining_gaps", []),
            }
        )
        if decision.get("action") == "approve":
            return {"report_approved": True}
        feedback = str(decision.get("feedback") or "").strip()[:2000]
        tasks = state.get("tasks", [])
        human_task: TaskState = {
            "id": f"T{len(tasks) + 1}",
            "question": feedback or "Find additional supporting evidence",
            "rationale": "Requested by the human reviewer.",
            "evidence_type": "reviewer request",
            "preferred_sources": ["web", "documents"],
            "status": "pending",
            "origin": "human",
            "iteration_added": state.get("iteration", 0),
            "attempts": 0,
        }
        return {
            "report_approved": False,
            "human_feedback": [feedback],
            "tasks": [human_task] if len(tasks) < state["limits"]["max_tasks"] else [],
            "critic": {**critic, "sufficient": False},
        }

    # --- I. Report generator ------------------------------------------------------------

    async def report_generator(self, state: ResearchState) -> dict[str, Any]:
        outcome = research_outcome(state)
        evidence = state.get("evidence", [])
        sources = state.get("sources", {})
        tasks = active_tasks(state)
        demo = self.settings.demo_mode
        error_notes = [e["message"] for e in state.get("errors", [])][-5:]

        if not evidence:
            report = citation_service.insufficient_evidence_report(
                question=state["question"],
                outcome=outcome,
                tasks=tasks,
                errors=error_notes,
                demo_mode=demo,
            )
            return {"final_report": report, "status": "completed"}

        warnings: list[str] = []
        try:
            draft = await self.llm.structured(
                ReportDraft,
                REPORT,
                {
                    "question": state["question"],
                    "research_status": outcome,
                    "tasks": render_tasks(tasks),
                    "evidence": "\n\n".join(
                        fence(
                            e["id"],
                            f"{e['claim']}\nQuote: {e['quote'] or '(none)'}",
                            task=e["task_id"],
                            source=sources[e["source_id"]]["title"],
                            source_type=sources[e["source_id"]]["content_kind"],
                        )
                        for e in evidence
                        if e["source_id"] in sources
                    ),
                    "contradictions": render_list(
                        c["description"] for c in state.get("contradictions", [])
                    ),
                    "gaps": render_list((state.get("critic") or {}).get("remaining_gaps", [])),
                },
                context={
                    "question": state["question"],
                    "tasks": tasks,
                    "evidence": evidence,
                    "sources": sources,
                    "outcome": outcome,
                },
            )
        except Exception as exc:
            logger.warning("Report generation failed, using evidence digest: %s", exc)
            draft = evidence_digest(state["question"], tasks, evidence)
            warnings.append(
                "The report writer failed; this is an automatically assembled evidence digest."
            )
            outcome = outcome if outcome != "sufficient" else "needs_more"

        report = citation_service.build_report(
            question=state["question"],
            draft=draft,
            evidence=evidence,
            sources=sources,
            outcome=outcome,
            extra_warnings=warnings,
            demo_mode=demo,
        )
        return {"final_report": report, "status": "completed"}


def evidence_digest(
    question: str, tasks: list[TaskState], evidence: list[EvidenceRecord]
) -> ReportDraft:
    """Deterministic fallback report: lists evidence per task, makes no claims of its own."""
    findings = []
    for t in tasks:
        items = [e for e in evidence if e["task_id"] == t["id"]]
        if items:
            findings.append(
                ReportFinding(
                    heading=t["question"],
                    statement=" ".join(e["claim"] for e in items[:3]),
                    evidence_ids=[e["id"] for e in items[:3]],
                    kind="fact",
                )
            )
    return ReportDraft(
        executive_summary=f"Evidence collected for: {question}. No synthesis was performed.",
        methodology="Subquestions were researched with web search and document retrieval; "
        "claims below are listed as extracted from sources.",
        findings=findings,
        limitations=["No model-written synthesis is included in this digest."],
        conclusions="See the findings for the evidence collected.",
    )
