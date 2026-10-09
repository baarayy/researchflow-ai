"""Citation validation and report rendering.

The model never writes citation numbers or the bibliography. It returns a `ReportDraft` whose
findings reference evidence ids (E-...). This module:

1. drops evidence ids that are not in the evidence registry (hallucinated or mistyped);
2. downgrades "fact" findings left without valid evidence to "inference";
3. removes URLs and numeric citations the model wrote into free text, unless the URL belongs to
   a collected source;
4. numbers sources by first citation and renders Markdown plus a structured form for the UI.

Every citation in the output therefore points to a source the system actually retrieved, and to
an evidence item extracted from that source.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from app.ai.graph.state import EvidenceRecord, SourceRecord
from app.ai.schemas import ReportDraft

ReportStatus = Literal["complete", "partial", "insufficient_evidence"]

_EVIDENCE_ID = re.compile(r"\[?\b(E-[0-9a-f]{6,16})\b\]?")
_NUMERIC_CITATION = re.compile(r"\[(\d{1,3})\](?!\()")
_URL = re.compile(r"https?://[^\s)\]>\"']+")

OUTCOME_NOTES = {
    "sufficient": None,
    "iteration_limit": "The research iteration limit was reached before all questions were "
    "fully answered.",
    "budget_exhausted": "The tool-call budget for this session ran out before research finished.",
    "no_open_tasks": "Some research questions could not be answered with the sources found.",
    "needs_more": "Research ended before the critic considered the evidence sufficient.",
}


class CitationRegistry:
    """Assigns citation numbers to sources in order of first use."""

    def __init__(self, evidence: Mapping[str, EvidenceRecord], sources: Mapping[str, SourceRecord]):
        self.evidence = evidence
        self.sources = sources
        self.numbers: dict[str, int] = {}

    def number_for_evidence(self, evidence_id: str) -> int | None:
        ev = self.evidence.get(evidence_id)
        if ev is None or ev["source_id"] not in self.sources:
            return None
        return self.numbers.setdefault(ev["source_id"], len(self.numbers) + 1)

    def known_urls(self) -> set[str]:
        return {s["url"] for s in self.sources.values() if s["url"]}


def _cite(numbers: list[int]) -> str:
    return "".join(f"[[{n}]](#ref-{n})" for n in sorted(set(numbers)))


def clean_free_text(text: str, registry: CitationRegistry, warnings: list[str]) -> str:
    """Resolve inline evidence ids to citations and strip untrusted URLs / numbering."""

    def evidence_sub(match: re.Match[str]) -> str:
        number = registry.number_for_evidence(match.group(1))
        if number is None:
            warnings.append(f"Removed reference to unknown evidence id {match.group(1)}.")
            return ""
        return _cite([number])

    def url_sub(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,;")
        if url in registry.known_urls():
            return match.group(0)
        warnings.append("Removed a URL that does not belong to any collected source.")
        return "[link removed]"

    if _NUMERIC_CITATION.search(text):
        warnings.append(
            "Removed model-written numeric citations; citations are assigned by the system."
        )
        text = _NUMERIC_CITATION.sub("", text)
    text = _URL.sub(url_sub, text)
    return _EVIDENCE_ID.sub(evidence_sub, text).strip()


def build_report(
    *,
    question: str,
    draft: ReportDraft,
    evidence: list[EvidenceRecord],
    sources: Mapping[str, SourceRecord],
    outcome: str,
    extra_warnings: list[str] | None = None,
    demo_mode: bool = False,
) -> dict[str, Any]:
    evidence_by_id = {e["id"]: e for e in evidence}
    registry = CitationRegistry(evidence_by_id, sources)
    warnings: list[str] = list(extra_warnings or [])

    findings: list[dict[str, Any]] = []
    for f in draft.findings:
        numbers, valid_ids = [], []
        for eid in dict.fromkeys(f.evidence_ids):
            n = registry.number_for_evidence(eid)
            if n is None:
                warnings.append(f"Finding '{f.heading}' cited unknown evidence {eid}; removed.")
            else:
                numbers.append(n)
                valid_ids.append(eid)
        kind = f.kind
        if kind == "fact" and not valid_ids:
            kind = "inference"
            warnings.append(
                f"Finding '{f.heading}' had no valid supporting evidence; shown as an inference."
            )
        findings.append(
            {
                "heading": clean_free_text(f.heading, registry, warnings),
                "statement": clean_free_text(f.statement, registry, warnings),
                "kind": kind,
                "evidence_ids": valid_ids,
                "citations": sorted(set(numbers)),
            }
        )

    text = {
        "executive_summary": clean_free_text(draft.executive_summary, registry, warnings),
        "methodology": clean_free_text(draft.methodology, registry, warnings),
        "conclusions": clean_free_text(draft.conclusions, registry, warnings),
    }
    uncertainties = [
        clean_free_text(c, registry, warnings) for c in draft.contradictions_and_uncertainties
    ]
    limitations = [clean_free_text(c, registry, warnings) for c in draft.limitations]
    table = None
    if draft.comparison_table:
        t = draft.comparison_table
        width = len(t.columns)
        table = {
            "title": t.title,
            "columns": [clean_free_text(c, registry, warnings) for c in t.columns],
            "rows": [
                [clean_free_text(c, registry, warnings) for c in (row + [""] * width)[:width]]
                for row in t.rows
            ],
        }

    status: ReportStatus = "complete" if outcome == "sufficient" else "partial"
    auto_limitations = _automatic_limitations(outcome, sources, registry, demo_mode)

    bibliography = [
        _bib_entry(n, sources[sid])
        for sid, n in sorted(registry.numbers.items(), key=lambda x: x[1])
    ]
    supporting = _supporting_evidence(findings, evidence_by_id, registry)

    report = {
        "status": status,
        "outcome": outcome,
        "question": question,
        **text,
        "findings": findings,
        "comparison_table": table,
        "contradictions_and_uncertainties": uncertainties,
        "limitations": limitations + auto_limitations,
        "supporting_evidence": supporting,
        "bibliography": bibliography,
        "warnings": list(dict.fromkeys(warnings)),
        "demo_mode": demo_mode,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    report["markdown"] = render_markdown(report)
    return report


def insufficient_evidence_report(
    *,
    question: str,
    outcome: str,
    tasks: Sequence[Mapping[str, Any]],
    errors: list[str],
    demo_mode: bool,
) -> dict[str, Any]:
    """Deterministic report used when nothing citable was found. No LLM call, nothing to invent."""
    report = {
        "status": "insufficient_evidence",
        "outcome": outcome,
        "question": question,
        "executive_summary": "The research workflow did not find any evidence that could be cited "
        "for this question, so no findings are reported.",
        "methodology": "Planned subquestions were searched using the enabled tools: "
        + "; ".join(t["question"] for t in tasks if t["status"] != "dropped"),
        "findings": [],
        "comparison_table": None,
        "contradictions_and_uncertainties": [],
        "limitations": [
            "No relevant sources were retrieved. Try rephrasing the question, enabling web search, "
            "or uploading relevant documents.",
            *errors,
        ],
        "conclusions": "No conclusion can be drawn without evidence.",
        "supporting_evidence": [],
        "bibliography": [],
        "warnings": [],
        "demo_mode": demo_mode,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    report["markdown"] = render_markdown(report)
    return report


def _automatic_limitations(
    outcome: str, sources: Mapping[str, SourceRecord], registry: CitationRegistry, demo_mode: bool
) -> list[str]:
    notes = []
    if note := OUTCOME_NOTES.get(outcome):
        notes.append(note)
    cited = [sources[s] for s in registry.numbers]
    if any(s["content_kind"] == "snippet" for s in cited):
        notes.append(
            "Some web evidence comes from search-result snippets, not verified full pages."
        )
    if any(s.get("possibly_outdated") for s in cited):
        notes.append("Some cited sources may be outdated (marked in the bibliography).")
    if demo_mode:
        notes.append(
            "Demo mode: sources are synthetic fixtures and the analysis is rule-based, "
            "not a real model. Do not rely on this report."
        )
    return notes


def _bib_entry(n: int, s: SourceRecord) -> dict[str, Any]:
    return {
        "number": n,
        "source_id": s["id"],
        "kind": s["kind"],
        "title": s["title"],
        "url": s.get("url"),
        "document_id": s.get("document_id"),
        "page_number": s.get("page_number"),
        "content_kind": s["content_kind"],
        "published_date": s.get("published_date"),
        "retrieved_at": s.get("retrieved_at"),
        "possibly_outdated": s.get("possibly_outdated", False),
    }


def _supporting_evidence(
    findings: list[dict[str, Any]],
    evidence_by_id: Mapping[str, EvidenceRecord],
    registry: CitationRegistry,
) -> list[dict[str, Any]]:
    seen: dict[tuple[int, str], dict[str, Any]] = {}
    for f in findings:
        for eid in f["evidence_ids"]:
            ev = evidence_by_id[eid]
            # The same claim can support several tasks; list it once per source.
            seen.setdefault(
                (registry.numbers[ev["source_id"]], ev["claim"]),
                {
                    "evidence_id": eid,
                    "citation": registry.numbers[ev["source_id"]],
                    "claim": ev["claim"],
                    "quote": ev["quote"] if ev["quote_verified"] else None,
                },
            )
    return list(seen.values())


def _bib_line(b: dict[str, Any]) -> str:
    if b["kind"] == "web":
        line = f"{b['title']}. <{b['url']}>"
        if b.get("published_date"):
            line += f" (published {b['published_date']})"
        if b["content_kind"] == "snippet":
            line += " — search snippet"
    else:
        line = f"{b['title']} (uploaded document)"
        if b.get("page_number"):
            line += f", p. {b['page_number']}"
    if b.get("possibly_outdated"):
        line += " — possibly outdated"
    return f"{b['number']}. {line}"


def render_markdown(r: dict[str, Any]) -> str:
    out = [f"# Research report\n\n**Question:** {r['question']}\n"]
    if r["status"] != "complete":
        label = {"partial": "Partial report", "insufficient_evidence": "Insufficient evidence"}[
            r["status"]
        ]
        out.append(f"> **{label}.** {OUTCOME_NOTES.get(r['outcome']) or 'See limitations.'}\n")
    if r.get("demo_mode"):
        out.append("> **Demo mode:** synthetic sources and rule-based analysis.\n")
    out += [
        "## Executive summary\n",
        r["executive_summary"] + "\n",
        "## Methodology\n",
        r["methodology"] + "\n",
    ]

    out.append("## Main findings\n")
    if not r["findings"]:
        out.append("_No findings could be supported with evidence._\n")
    for f in r["findings"]:
        out.append(f"### {f['heading']}\n")
        if f["kind"] == "fact":
            out.append(f"{f['statement']} {_cite(f['citations'])}\n")
        else:
            out.append(
                f"> **Interpretation (model inference, not directly sourced):** {f['statement']}"
                f"{' ' + _cite(f['citations']) if f['citations'] else ''}\n"
            )

    if t := r.get("comparison_table"):
        out.append(f"## {t['title']}\n")
        out.append("| " + " | ".join(t["columns"]) + " |")
        out.append("|" + "---|" * len(t["columns"]))
        out += ["| " + " | ".join(c.replace("|", "\\|") for c in row) + " |" for row in t["rows"]]
        out.append("")

    if r["supporting_evidence"]:
        out.append("## Supporting evidence\n")
        for e in r["supporting_evidence"]:
            line = f"- {_cite([e['citation']])} {e['claim']}"
            if e.get("quote") and e["quote"] != e["claim"]:
                line += f'\n  *Quote: "{e["quote"]}"*'
            out.append(line)
        out.append("")

    for title, items in (
        ("Contradictions and uncertainties", r["contradictions_and_uncertainties"]),
        ("Limitations", r["limitations"]),
    ):
        if items:
            out.append(f"## {title}\n")
            out += [f"- {i}" for i in items]
            out.append("")

    out += ["## Conclusions\n", r["conclusions"] + "\n"]
    if r["bibliography"]:
        out.append("## Bibliography\n")
        out += [_bib_line(b) for b in r["bibliography"]]
    return "\n".join(out).strip() + "\n"
