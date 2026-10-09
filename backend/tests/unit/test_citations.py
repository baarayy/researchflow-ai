from app.ai.schemas import ComparisonTable, ReportDraft, ReportFinding
from app.services.citation_service import build_report, insufficient_evidence_report


def src(sid: str, url: str, kind: str = "web", content_kind: str = "snippet") -> dict:
    return {
        "id": sid,
        "kind": kind,
        "title": f"Title {sid}",
        "url": url,
        "document_id": None,
        "chunk_id": None,
        "page_number": 4 if kind == "document" else None,
        "content": "...",
        "content_kind": content_kind,
        "published_date": None,
        "retrieved_at": "2026-01-01T00:00:00Z",
        "possibly_outdated": False,
    }


def ev(eid: str, sid: str) -> dict:
    return {
        "id": eid,
        "source_id": sid,
        "task_id": "T1",
        "claim": f"claim {eid}",
        "quote": "q",
        "quote_verified": True,
        "confidence": 0.8,
        "iteration": 1,
    }


SOURCES = {"W-1": src("W-1", "https://a.example/1"), "D-1": src("D-1", None, "document", "passage")}
EVIDENCE = [ev("E-aaaaaa01", "W-1"), ev("E-aaaaaa02", "D-1")]


def draft(**kw) -> ReportDraft:
    base = dict(
        executive_summary="Summary.", methodology="Method.", findings=[], conclusions="Done."
    )
    return ReportDraft(**{**base, **kw})


def test_valid_citations_are_numbered_by_first_use():
    d = draft(
        findings=[
            ReportFinding(heading="H1", statement="S1", evidence_ids=["E-aaaaaa02"], kind="fact"),
            ReportFinding(
                heading="H2", statement="S2", evidence_ids=["E-aaaaaa01", "E-aaaaaa02"], kind="fact"
            ),
        ]
    )
    r = build_report(
        question="Q?", draft=d, evidence=EVIDENCE, sources=SOURCES, outcome="sufficient"
    )
    assert r["status"] == "complete" and r["warnings"] == []
    assert [f["citations"] for f in r["findings"]] == [[1], [1, 2]]
    assert [b["source_id"] for b in r["bibliography"]] == ["D-1", "W-1"]
    assert "[[1]](#ref-1)" in r["markdown"] and "p. 4" in r["markdown"]


def test_unknown_evidence_is_removed_and_fact_downgraded():
    d = draft(
        findings=[
            ReportFinding(heading="H", statement="S", evidence_ids=["E-deadbeef"], kind="fact")
        ]
    )
    r = build_report(
        question="Q?", draft=d, evidence=EVIDENCE, sources=SOURCES, outcome="sufficient"
    )
    f = r["findings"][0]
    assert f["kind"] == "inference" and f["citations"] == [] and r["bibliography"] == []
    assert any("unknown evidence" in w for w in r["warnings"])
    assert "Interpretation" in r["markdown"]


def test_free_text_urls_and_numeric_citations_are_sanitized():
    d = draft(
        executive_summary="See https://evil.example/x and https://a.example/1 per [3]; also E-aaaaaa01 and E-ffffffff.",
    )
    r = build_report(
        question="Q?", draft=d, evidence=EVIDENCE, sources=SOURCES, outcome="sufficient"
    )
    s = r["executive_summary"]
    assert "evil.example" not in s and "[link removed]" in s
    assert "https://a.example/1" in s  # URL of a collected source is kept
    assert "[3]" not in s and "E-ffffffff" not in s
    assert "[[1]](#ref-1)" in s  # inline evidence id resolved to a citation


def test_partial_outcome_and_table_padding():
    d = draft(comparison_table=ComparisonTable(title="T", columns=["a", "b"], rows=[["x"]]))
    r = build_report(
        question="Q?",
        draft=d,
        evidence=EVIDENCE,
        sources=SOURCES,
        outcome="iteration_limit",
        demo_mode=True,
    )
    assert r["status"] == "partial"
    assert r["comparison_table"]["rows"] == [["x", ""]]
    assert any("iteration limit" in limitation for limitation in r["limitations"])
    assert "Demo mode" in r["markdown"] and "Partial report" in r["markdown"]


def test_insufficient_evidence_report_has_no_findings():
    r = insufficient_evidence_report(
        question="Q?",
        outcome="no_open_tasks",
        tasks=[{"question": "q1", "status": "no_evidence"}],
        errors=[],
        demo_mode=False,
    )
    assert (
        r["status"] == "insufficient_evidence" and r["findings"] == [] and r["bibliography"] == []
    )
