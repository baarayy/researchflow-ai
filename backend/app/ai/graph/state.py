"""Typed state for the research graph.

LangGraph merges each node's returned dict into the state. A field without a reducer is simply
overwritten; a field annotated `Annotated[T, reducer]` is combined with `reducer(old, new)`.
Reducers matter here because web and document researchers run in parallel and both write
`sources` and `inbox` in the same step.
"""

import operator
from typing import Annotated, Any, Literal, NotRequired, TypedDict

TaskStatus = Literal["pending", "in_progress", "done", "no_evidence", "dropped"]


class TaskState(TypedDict):
    id: str  # "T1", "T2", ...
    question: str
    rationale: str
    evidence_type: str
    preferred_sources: list[str]
    status: TaskStatus
    origin: Literal["plan", "critic", "human"]
    iteration_added: int
    attempts: int


class SourceRecord(TypedDict):
    id: str  # "W-<hash>" for web, "D-<hash>" for document chunks; stable across iterations
    kind: Literal["web", "document"]
    title: str
    url: str | None
    document_id: str | None
    chunk_id: str | None
    page_number: int | None
    content: str  # the exact text the analyzer saw (truncated)
    content_kind: Literal["snippet", "full_text", "passage"]
    published_date: str | None
    retrieved_at: str
    possibly_outdated: bool


class EvidenceRecord(TypedDict):
    id: str  # "E-<hash>"
    source_id: str
    task_id: str
    claim: str
    quote: str | None
    quote_verified: bool
    confidence: float
    iteration: int


class InboxItem(TypedDict):
    """A source a researcher found this iteration that the analyzer has not processed yet."""

    task_id: str
    source_id: str
    query: str


class ToolCallRecord(TypedDict):
    tool: Literal["web_search", "document_search"]
    query: str
    task_id: str


class SearchLogEntry(TypedDict):
    tool: str
    query: str
    task_id: str
    iteration: int
    status: Literal["ok", "empty", "error"]
    result_count: int
    error: NotRequired[str]


class ErrorRecord(TypedDict):
    node: str
    message: str
    recoverable: bool


class Limits(TypedDict):
    max_iterations: int
    max_tool_calls: int
    max_tasks: int
    coverage_threshold: float


class ResearchOptions(TypedDict):
    use_web: bool
    use_documents: bool
    document_ids: list[str] | None  # None = all of the user's ready documents
    require_plan_approval: bool
    require_report_approval: bool


# --- reducers -------------------------------------------------------------------------


def merge_by_id(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upsert list items by their "id", preserving first-seen order."""
    merged = {item["id"]: item for item in left or []}
    for item in right or []:
        merged[item["id"]] = {**merged.get(item["id"], {}), **item}
    return list(merged.values())


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**(left or {}), **(right or {})}


def inbox_reducer(left: list[InboxItem], right: list[InboxItem] | None) -> list[InboxItem]:
    """Append; a node returns `None` to clear the inbox once it has been processed."""
    if right is None:
        return []
    return (left or []) + right


# --- the state ------------------------------------------------------------------------


class ResearchState(TypedDict, total=False):
    # Inputs (set once when the run starts)
    session_id: str
    owner_id: str
    question: str
    options: ResearchOptions
    limits: Limits

    # Planning
    objective: str
    tasks: Annotated[list[TaskState], merge_by_id]
    plan_revisions: int
    plan_approved: bool

    # Research loop
    iteration: int
    planned_calls: list[ToolCallRecord]  # set by dispatcher, consumed by the fan-out edge
    tool_calls_used: int
    search_log: Annotated[list[SearchLogEntry], operator.add]
    inbox: Annotated[list[InboxItem], inbox_reducer]
    sources: Annotated[dict[str, SourceRecord], merge_dicts]
    evidence: Annotated[list[EvidenceRecord], merge_by_id]
    summaries: Annotated[list[str], operator.add]
    contradictions: list[dict[str, Any]]
    knowledge_gaps: list[str]
    critic: dict[str, Any] | None

    # Human-in-the-loop
    human_feedback: Annotated[list[str], operator.add]
    report_approved: bool

    # Output
    final_report: dict[str, Any] | None
    errors: Annotated[list[ErrorRecord], operator.add]
    status: Literal["running", "failed", "completed"]
