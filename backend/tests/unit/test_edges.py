from langgraph.graph import END
from langgraph.types import Send

from app.ai.graph import edges

LIMITS = {"max_iterations": 3, "max_tool_calls": 10, "max_tasks": 8, "coverage_threshold": 0.75}
OPTIONS = {
    "use_web": True,
    "use_documents": True,
    "document_ids": None,
    "require_plan_approval": True,
    "require_report_approval": False,
}


def state(**kw):
    base = {
        "limits": LIMITS,
        "options": OPTIONS,
        "owner_id": "u",
        "iteration": 1,
        "tool_calls_used": 2,
        "tasks": [{"id": "T1", "status": "pending"}],
        "critic": {"sufficient": False},
    }
    return {**base, **kw}


def test_outcomes():
    assert edges.research_outcome(state(critic={"sufficient": True})) == "sufficient"
    assert edges.research_outcome(state()) == "needs_more"
    assert edges.research_outcome(state(iteration=3)) == "iteration_limit"
    assert edges.research_outcome(state(tool_calls_used=10)) == "budget_exhausted"
    assert edges.research_outcome(state(tasks=[{"id": "T1", "status": "done"}])) == "no_open_tasks"


def test_route_after_critic():
    assert edges.route_after_critic(state()) == "dispatcher"
    assert edges.route_after_critic(state(iteration=3)) == "report_generator"
    with_review = {**OPTIONS, "require_report_approval": True}
    assert edges.route_after_critic(state(iteration=3, options=with_review)) == "report_review"
    assert (
        edges.route_after_critic(state(iteration=3, options=with_review, report_approved=True))
        == "report_generator"
    )


def test_route_after_report_review():
    assert edges.route_after_report_review(state(report_approved=True)) == "report_generator"
    assert edges.route_after_report_review(state()) == "dispatcher"
    assert edges.route_after_report_review(state(iteration=3)) == "report_generator"


def test_planner_and_plan_review_routes():
    assert edges.route_after_planner({"status": "failed"}) == END
    assert edges.route_after_planner({"status": "running"}) == "plan_review"
    assert edges.route_after_plan_review({"plan_approved": True}) == "dispatcher"
    assert edges.route_after_plan_review({"plan_approved": False}) == "planner"


def test_fan_out_sends_one_per_call():
    calls = [
        {"tool": "web_search", "query": "q", "task_id": "T1"},
        {"tool": "document_search", "query": "q", "task_id": "T1"},
    ]
    sends = edges.fan_out_research(state(planned_calls=calls))
    assert [s.node for s in sends] == ["web_researcher", "document_researcher"]
    assert all(isinstance(s, Send) and s.arg["owner_id"] == "u" for s in sends)
    assert edges.fan_out_research(state(planned_calls=[])) == "evidence_analyzer"
