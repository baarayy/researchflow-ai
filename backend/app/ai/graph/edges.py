"""Routing rules for conditional edges.

Every routing decision is a small pure function of the state, so it can be unit-tested without
running a model. The LLM never returns a node name: the critic returns structured scores, the
critic node turns them into `critic["sufficient"]` with explicit thresholds, and these functions
combine that with hard limits (iterations, tool-call budget).
"""

from typing import Literal

from langgraph.graph import END
from langgraph.types import Send

from app.ai.graph.state import ResearchState

ResearchOutcome = Literal[
    "sufficient", "needs_more", "iteration_limit", "budget_exhausted", "no_open_tasks"
]


def research_outcome(state: ResearchState) -> ResearchOutcome:
    """Where the research stands after the critic. Also used to qualify the final report."""
    critic = state.get("critic") or {}
    if critic.get("sufficient"):
        return "sufficient"
    if not any(t["status"] == "pending" for t in state.get("tasks", [])):
        return "no_open_tasks"
    limits = state["limits"]
    if state.get("iteration", 0) >= limits["max_iterations"]:
        return "iteration_limit"
    if state.get("tool_calls_used", 0) >= limits["max_tool_calls"]:
        return "budget_exhausted"
    return "needs_more"


def route_after_planner(state: ResearchState) -> str:
    return END if state.get("status") == "failed" else "plan_review"


def route_after_plan_review(state: ResearchState) -> Literal["dispatcher", "planner"]:
    return "dispatcher" if state.get("plan_approved") else "planner"


def fan_out_research(state: ResearchState) -> list[Send] | Literal["evidence_analyzer"]:
    """Map step: one parallel researcher invocation per planned tool call (LangGraph Send API)."""
    calls = state.get("planned_calls") or []
    if not calls:
        return "evidence_analyzer"
    options = state["options"]
    return [
        Send(
            "web_researcher" if call["tool"] == "web_search" else "document_researcher",
            {
                "call": call,
                "owner_id": state["owner_id"],
                "document_ids": options.get("document_ids"),
                "iteration": state.get("iteration", 0),
            },
        )
        for call in calls
    ]


def route_after_critic(
    state: ResearchState,
) -> Literal["dispatcher", "report_review", "report_generator"]:
    if research_outcome(state) == "needs_more":
        return "dispatcher"
    if state["options"].get("require_report_approval") and not state.get("report_approved"):
        return "report_review"
    return "report_generator"


def route_after_report_review(
    state: ResearchState,
) -> Literal["dispatcher", "report_generator"]:
    if state.get("report_approved"):
        return "report_generator"
    # The reviewer asked for more research: honour it only while limits allow.
    return "dispatcher" if research_outcome(state) == "needs_more" else "report_generator"
