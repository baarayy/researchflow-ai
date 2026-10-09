"""Assemble the research StateGraph.

START → planner ─┬→ plan_review ─┬→ dispatcher ─(Send…)→ web_researcher ──────┐
                 └→ END (failed) └→ planner (revise)    → document_researcher ─┤
                                                                               ↓
      report_generator ←─ report_review ←─ critic ←──────────── evidence_analyzer
            ↓              (optional)        └→ dispatcher (more research, bounded)
           END
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from app.ai.graph import edges
from app.ai.graph.nodes import ResearchDeps, ResearchNodes
from app.ai.graph.state import ResearchState


def build_workflow(deps: ResearchDeps, checkpointer: Checkpointer = None) -> CompiledStateGraph:
    n = ResearchNodes(deps)
    g = StateGraph(ResearchState)

    g.add_node("planner", n.planner)
    g.add_node("plan_review", n.plan_review)
    g.add_node("dispatcher", n.dispatcher)
    # Researchers receive a Send payload (ResearcherInput), not the graph state.
    g.add_node("web_researcher", n.web_researcher)  # type: ignore[arg-type]
    g.add_node("document_researcher", n.document_researcher)  # type: ignore[arg-type]
    g.add_node("evidence_analyzer", n.evidence_analyzer)
    g.add_node("critic", n.critic)
    g.add_node("report_review", n.report_review)
    g.add_node("report_generator", n.report_generator)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", edges.route_after_planner, ["plan_review", END])
    g.add_conditional_edges("plan_review", edges.route_after_plan_review, ["dispatcher", "planner"])
    # Fan-out: one Send per tool call; both researcher types run in the same parallel step.
    g.add_conditional_edges(
        "dispatcher",
        edges.fan_out_research,
        ["web_researcher", "document_researcher", "evidence_analyzer"],
    )
    # Fan-in: the analyzer runs once, after every researcher in the step has finished.
    g.add_edge("web_researcher", "evidence_analyzer")
    g.add_edge("document_researcher", "evidence_analyzer")
    g.add_edge("evidence_analyzer", "critic")
    g.add_conditional_edges(
        "critic", edges.route_after_critic, ["dispatcher", "report_review", "report_generator"]
    )
    g.add_conditional_edges(
        "report_review", edges.route_after_report_review, ["dispatcher", "report_generator"]
    )
    g.add_edge("report_generator", END)

    return g.compile(checkpointer=checkpointer)
