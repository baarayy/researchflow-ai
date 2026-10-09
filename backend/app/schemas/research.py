import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateResearchRequest(BaseModel):
    question: str = Field(min_length=10, max_length=2000)
    use_web: bool = True
    use_documents: bool = True
    document_ids: list[uuid.UUID] | None = Field(
        default=None,
        max_length=50,
        description="Restrict document search; null = all your documents.",
    )
    require_plan_approval: bool = True
    require_report_approval: bool = False
    max_iterations: int | None = Field(default=None, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("Question must be at least 10 non-blank characters")
        return v


class ApprovalDecision(BaseModel):
    """Value passed to LangGraph's Command(resume=...)."""

    action: Literal["approve", "revise"]
    feedback: str | None = Field(default=None, max_length=2000)


class ApproveRequest(BaseModel):
    feedback: str | None = Field(default=None, max_length=2000)


class ReviseRequest(BaseModel):
    feedback: str = Field(min_length=3, max_length=2000)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SessionSummary(ORMModel):
    id: uuid.UUID
    question: str
    status: str
    stage: str | None
    iteration: int
    max_iterations: int
    created_at: datetime
    updated_at: datetime


class TaskOut(ORMModel):
    task_key: str
    question: str
    rationale: str
    evidence_type: str
    status: str
    origin: str
    iteration_added: int


class SourceOut(ORMModel):
    source_key: str
    kind: str
    title: str
    url: str | None
    document_id: uuid.UUID | None
    page_number: int | None
    excerpt: str
    content_kind: str
    published_date: str | None
    retrieved_at: datetime
    possibly_outdated: bool


class EvidenceOut(ORMModel):
    evidence_key: str
    source_key: str
    task_key: str | None
    claim: str
    quote: str | None
    quote_verified: bool
    confidence: float


class SessionDetail(SessionSummary):
    options: dict[str, Any]
    pending_approval: dict[str, Any] | None
    critic_feedback: dict[str, Any] | None
    error: str | None
    tasks: list[TaskOut]
    sources: list[SourceOut]
    evidence: list[EvidenceOut]
    has_report: bool


class ReportOut(BaseModel):
    session_id: uuid.UUID
    status: str
    markdown: str
    content: dict[str, Any]
    created_at: datetime


class EventOut(ORMModel):
    id: int
    type: str
    node: str | None
    payload: dict[str, Any]
    created_at: datetime
