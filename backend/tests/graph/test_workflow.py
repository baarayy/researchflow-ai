"""End-to-end graph behaviour with an in-memory checkpointer and scripted doubles."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.ai.graph.nodes import ResearchDeps
from app.ai.graph.workflow import build_workflow
from app.ai.schemas import (
    CriticAssessment,
    EvidenceAnalysis,
    ExtractedClaim,
    GapQuery,
    TaskCoverage,
)
from app.ai.tools.demo_corpus import MockSearchProvider
from app.core.config import get_settings
from app.core.errors import ExternalServiceError
from tests.helpers import FakeRetriever, ScriptedModel, StaticSearch, passage, web

QUESTION = (
    "Compare open-source LLMs for building AI agents. Evaluate their reasoning, "
    "hardware requirements, licensing and suitability for production."
)


def initial(**options) -> dict:
    opts = {
        "use_web": True,
        "use_documents": True,
        "document_ids": None,
        "require_plan_approval": False,
        "require_report_approval": False,
        **options,
    }
    return {
        "session_id": "s",
        "owner_id": "user-1",
        "question": QUESTION,
        "options": opts,
        "limits": {
            "max_iterations": 3,
            "max_tool_calls": 40,
            "max_tasks": 12,
            "coverage_threshold": 0.75,
        },
        "iteration": 0,
        "tool_calls_used": 0,
    }


def make_graph(llm=None, search=None, retriever=None):
    deps = ResearchDeps(
        llm or ScriptedModel(),
        search or MockSearchProvider(),
        retriever or FakeRetriever(),
        get_settings(),
    )
    return build_workflow(deps, InMemorySaver())


async def run(graph, graph_input, thread="t1"):
    config = {"configurable": {"thread_id": thread}}
    nodes = []
    async for update in graph.astream(graph_input, config, stream_mode="updates"):
        nodes += list(update)
    snapshot = await graph.aget_state(config)
    return snapshot, nodes


def critic(needs_more: bool, gaps: list[str] | None = None, quality="medium"):
    return lambda ctx: CriticAssessment(
        task_coverage=[TaskCoverage(task_id=t["id"], covered=True) for t in ctx["tasks"]],
        evidence_quality=quality,
        citation_completeness=1.0,
        remaining_gaps=[GapQuery(question=g, rationale="gap") for g in (gaps or [])],
        needs_more_research=needs_more,
        summary="scripted",
    )


async def test_successful_research_produces_cited_report():
    graph = make_graph()
    snapshot, nodes = await run(graph, initial())
    values = snapshot.values
    assert snapshot.next == ()
    assert nodes[:2] == ["planner", "plan_review"] and nodes[-1] == "report_generator"
    assert values["iteration"] == 1 and values["critic"]["sufficient"]
    report = values["final_report"]
    assert report["status"] == "complete" and report["bibliography"]
    # Every cited evidence item points at a source the graph actually retrieved.
    for f in report["findings"]:
        for eid in f["evidence_ids"]:
            assert (
                next(e for e in values["evidence"] if e["id"] == eid)["source_id"]
                in values["sources"]
            )


async def test_web_and_document_research_run_in_parallel():
    retriever = FakeRetriever(
        [passage("Our licensing review preferred Apache 2.0 models for production.")]
    )
    snapshot, nodes = await run(make_graph(retriever=retriever), initial())
    first_dispatch = nodes.index("dispatcher")
    step = nodes[first_dispatch + 1 : nodes.index("evidence_analyzer")]
    assert {"web_researcher", "document_researcher"} <= set(step)
    assert any(
        s["kind"] == "document" and s["page_number"] == 1
        for s in snapshot.values["sources"].values()
    )
    assert retriever.filters[0].owner_id == "user-1"  # scope comes from state, not the model


async def test_plan_approval_interrupt_and_resume():
    graph = make_graph()
    snapshot, nodes = await run(graph, initial(require_plan_approval=True))
    assert nodes[-1] == "__interrupt__"
    assert snapshot.next == ("plan_review",)
    payload = snapshot.interrupts[0].value
    assert payload["kind"] == "plan_review" and len(payload["tasks"]) >= 3

    snapshot, _ = await run(graph, Command(resume={"action": "approve"}))
    assert snapshot.values["final_report"]["status"] == "complete"


async def test_plan_revision_replans_with_feedback():
    graph = make_graph()
    await run(graph, initial(require_plan_approval=True))
    snapshot, nodes = await run(
        graph, Command(resume={"action": "revise", "feedback": "Focus on GPU memory"})
    )
    assert nodes == ["plan_review", "planner", "__interrupt__"]
    questions = [t["question"] for t in snapshot.values["tasks"]]
    assert any("Focus on GPU memory" in q for q in questions)
    assert snapshot.values["plan_revisions"] == 1


async def test_insufficient_evidence_triggers_another_iteration():
    llm = ScriptedModel(
        CriticAssessment=[
            critic(True, ["What GPU memory do quantized models need?"]),
            critic(False),
        ]
    )
    snapshot, nodes = await run(make_graph(llm=llm), initial())
    values = snapshot.values
    assert nodes.count("dispatcher") == 2 and values["iteration"] == 2
    assert any(t["origin"] == "critic" for t in values["tasks"])
    assert values["final_report"]["status"] == "complete"


async def test_iteration_limit_stops_the_loop_with_partial_report():
    counter = iter(range(100))
    llm = ScriptedModel(
        CriticAssessment=[
            lambda ctx: critic(True, [f"New gap {next(counter)} about GPU memory"])(ctx)
        ]
    )
    snapshot, nodes = await run(make_graph(llm=llm), initial())
    values = snapshot.values
    assert values["iteration"] == 3 and nodes.count("critic") == 3
    assert values["final_report"]["status"] == "partial"
    assert values["final_report"]["outcome"] == "iteration_limit"


async def test_empty_search_results_yield_insufficient_evidence_report():
    snapshot, _ = await run(make_graph(search=StaticSearch([])), initial())
    report = snapshot.values["final_report"]
    assert report["status"] == "insufficient_evidence" and report["findings"] == []
    assert all(e["status"] == "empty" for e in snapshot.values["search_log"])


async def test_search_tool_failure_is_recorded_not_fatal():
    search = StaticSearch(error=ExternalServiceError("boom"))
    snapshot, _ = await run(make_graph(search=search), initial())
    values = snapshot.values
    assert values["final_report"]["status"] == "insufficient_evidence"
    assert any(e["node"] == "web_researcher" and e["recoverable"] for e in values["errors"])


async def test_report_failure_falls_back_to_partial_digest():
    llm = ScriptedModel(ReportDraft=[RuntimeError("model down")])
    snapshot, _ = await run(make_graph(llm=llm), initial())
    report = snapshot.values["final_report"]
    assert report["status"] == "partial"
    assert any("evidence digest" in w for w in report["warnings"])
    assert report["findings"] and all(f["citations"] for f in report["findings"])


async def test_planner_failure_ends_run():
    llm = ScriptedModel(ResearchPlan=[RuntimeError("model down")])
    snapshot, nodes = await run(make_graph(llm=llm), initial())
    assert nodes == ["planner"] and snapshot.values["status"] == "failed"
    assert snapshot.values["errors"][0]["recoverable"] is False


async def test_analyzer_drops_claims_for_unknown_sources_and_flags_bad_quotes():
    def analysis(ctx):
        sid = next(iter(ctx["sources"]))
        return EvidenceAnalysis(
            claims=[
                ExtractedClaim(
                    source_id="W-hallucinated", task_id="T1", claim="made up", confidence=0.9
                ),
                ExtractedClaim(
                    source_id=sid,
                    task_id="T1",
                    claim="real",
                    quote="this text is not in the source",
                    confidence=1.0,
                ),
            ]
        )

    search = StaticSearch([web("GPU", "GPU memory dominates inference cost.")])
    llm = ScriptedModel(EvidenceAnalysis=[analysis], CriticAssessment=[critic(False)])
    snapshot, _ = await run(make_graph(llm=llm, search=search), initial())
    values = snapshot.values
    claims = [e["claim"] for e in values["evidence"]]
    assert "made up" not in claims and "real" in claims
    real = next(e for e in values["evidence"] if e["claim"] == "real")
    assert real["quote_verified"] is False and real["confidence"] < 1.0
    assert any("unknown sources" in e["message"] for e in values["errors"])


async def test_report_review_interrupt_and_revision_adds_human_task():
    graph = make_graph()
    snapshot, nodes = await run(graph, initial(require_report_approval=True))
    assert snapshot.next == ("report_review",)
    assert snapshot.interrupts[0].value["kind"] == "report_review"

    snapshot, nodes = await run(
        graph, Command(resume={"action": "revise", "feedback": "Licensing of Apache models"})
    )
    assert any(t["origin"] == "human" for t in snapshot.values["tasks"])
    assert "dispatcher" in nodes and snapshot.next == (
        "report_review",
    )  # reviewed again after research

    snapshot, nodes = await run(graph, Command(resume={"action": "approve"}))
    assert nodes[-1] == "report_generator" and snapshot.values["final_report"]


async def test_repeated_queries_are_not_dispatched_twice():
    search = StaticSearch([])
    llm = ScriptedModel(CriticAssessment=[critic(True, [])])
    snapshot, _ = await run(make_graph(llm=llm, search=search), initial())
    assert len(search.queries) == len(set(search.queries))


@pytest.mark.parametrize("use_web", [False])
async def test_no_tools_available_still_finishes(use_web):
    snapshot, _ = await run(
        make_graph(), initial(use_web=use_web, use_documents=False), thread=str(uuid.uuid4())
    )
    assert snapshot.values["final_report"]["status"] == "insufficient_evidence"
    assert any(e["node"] == "dispatcher" for e in snapshot.values["errors"])
