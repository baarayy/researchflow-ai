"""Research session tables.

The LangGraph checkpoint (managed by langgraph-checkpoint-postgres in its own tables) is the
source of truth for a running workflow. These tables are a queryable projection of it, written
by the workflow runner after every node, plus the event log the UI streams.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk, utcnow


class ResearchSession(UUIDPk, Timestamps, Base):
    """One research run. `id` doubles as the LangGraph thread_id."""

    __tablename__ = "research_sessions"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_research_sessions_idem"),
        Index("ix_research_sessions_owner_created", "owner_id", "created_at"),
    )

    owner_id: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    # queued | running | awaiting_approval | completed | partial | failed
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stage: Mapped[str | None] = mapped_column(String(64))
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    max_iterations: Mapped[int] = mapped_column(Integer)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    pending_approval: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    critic_feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    tasks: Mapped[list["ResearchTask"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="ResearchTask.task_key"
    )
    report: Mapped["Report | None"] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class ResearchTask(UUIDPk, Timestamps, Base):
    __tablename__ = "research_tasks"
    __table_args__ = (UniqueConstraint("session_id", "task_key", name="uq_research_tasks_key"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), index=True
    )
    task_key: Mapped[str] = mapped_column(String(16))
    question: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_type: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(16), default="plan")
    iteration_added: Mapped[int] = mapped_column(Integer, default=0)


class Source(UUIDPk, Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("session_id", "source_key", name="uq_sources_key"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), index=True
    )
    source_key: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))  # web | document
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    # Documents may be deleted after research; keep the citation, drop the link.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    page_number: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content_kind: Mapped[str] = mapped_column(String(16))  # snippet | full_text | passage
    published_date: Mapped[str | None] = mapped_column(String(32))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    possibly_outdated: Mapped[bool] = mapped_column(default=False)


class EvidenceItem(UUIDPk, Base):
    __tablename__ = "evidence_items"
    __table_args__ = (UniqueConstraint("session_id", "evidence_key", name="uq_evidence_key"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), index=True
    )
    evidence_key: Mapped[str] = mapped_column(String(32))
    source_key: Mapped[str] = mapped_column(String(32))
    task_key: Mapped[str | None] = mapped_column(String(16))
    claim: Mapped[str] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text)
    quote_verified: Mapped[bool] = mapped_column(default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(UUIDPk, Timestamps, Base):
    __tablename__ = "reports"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(32))  # complete | partial | insufficient_evidence
    markdown: Mapped[str] = mapped_column(Text)
    # Structured form (findings, citations, bibliography, warnings) for the UI.
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (Index("ix_workflow_events_session_id_id", "session_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(32))  # node | interrupt | status | error
    node: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
