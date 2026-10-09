"""Data access for research sessions and their projections (tasks, sources, evidence...)."""

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvidenceItem, Report, ResearchSession, ResearchTask, Source, WorkflowEvent

TERMINAL_STATUSES = ("completed", "partial", "failed")


async def get_session(
    db: AsyncSession, session_id: uuid.UUID, owner_id: str | None = None
) -> ResearchSession | None:
    stmt = select(ResearchSession).where(ResearchSession.id == session_id)
    if owner_id is not None:
        stmt = stmt.where(ResearchSession.owner_id == owner_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_by_idempotency_key(
    db: AsyncSession, owner_id: str, key: str
) -> ResearchSession | None:
    stmt = select(ResearchSession).where(
        ResearchSession.owner_id == owner_id, ResearchSession.idempotency_key == key
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_sessions(
    db: AsyncSession, owner_id: str, *, limit: int, offset: int, status: str | None = None
) -> tuple[list[ResearchSession], int]:
    base = select(ResearchSession).where(ResearchSession.owner_id == owner_id)
    if status:
        base = base.where(ResearchSession.status == status)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(
        base.order_by(ResearchSession.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars()), total


async def sessions_with_status(
    db: AsyncSession, statuses: tuple[str, ...]
) -> list[ResearchSession]:
    rows = await db.execute(select(ResearchSession).where(ResearchSession.status.in_(statuses)))
    return list(rows.scalars())


async def claim_for_resume(db: AsyncSession, session_id: uuid.UUID, owner_id: str) -> bool:
    """Atomically move awaiting_approval -> running. False if someone else already did."""
    result = await db.execute(
        update(ResearchSession)
        .where(
            ResearchSession.id == session_id,
            ResearchSession.owner_id == owner_id,
            ResearchSession.status == "awaiting_approval",
        )
        .values(status="running", pending_approval=None)
        .returning(ResearchSession.id)
    )
    await db.commit()
    return result.first() is not None


async def update_session(db: AsyncSession, session_id: uuid.UUID, **values: Any) -> None:
    await db.execute(
        update(ResearchSession).where(ResearchSession.id == session_id).values(**values)
    )


async def add_event(
    db: AsyncSession, session_id: uuid.UUID, type_: str, node: str | None, payload: dict[str, Any]
) -> None:
    db.add(WorkflowEvent(session_id=session_id, type=type_, node=node, payload=payload))


async def events_after(
    db: AsyncSession, session_id: uuid.UUID, after_id: int, limit: int = 200
) -> list[WorkflowEvent]:
    rows = await db.execute(
        select(WorkflowEvent)
        .where(WorkflowEvent.session_id == session_id, WorkflowEvent.id > after_id)
        .order_by(WorkflowEvent.id)
        .limit(limit)
    )
    return list(rows.scalars())


async def tasks_for(db: AsyncSession, session_id: uuid.UUID) -> list[ResearchTask]:
    rows = await db.execute(
        select(ResearchTask)
        .where(ResearchTask.session_id == session_id)
        .order_by(ResearchTask.created_at, ResearchTask.task_key)
    )
    return list(rows.scalars())


async def sources_for(db: AsyncSession, session_id: uuid.UUID) -> list[Source]:
    rows = await db.execute(
        select(Source).where(Source.session_id == session_id).order_by(Source.retrieved_at)
    )
    return list(rows.scalars())


async def evidence_for(db: AsyncSession, session_id: uuid.UUID) -> list[EvidenceItem]:
    rows = await db.execute(
        select(EvidenceItem)
        .where(EvidenceItem.session_id == session_id)
        .order_by(EvidenceItem.created_at)
    )
    return list(rows.scalars())


async def report_for(db: AsyncSession, session_id: uuid.UUID) -> Report | None:
    return (
        await db.execute(select(Report).where(Report.session_id == session_id))
    ).scalar_one_or_none()


# --- projection upserts (idempotent: safe to repeat after every graph step) -------------


async def upsert_tasks(
    db: AsyncSession, session_id: uuid.UUID, tasks: list[dict[str, Any]]
) -> None:
    if not tasks:
        return
    rows = [
        {
            "id": uuid.uuid4(),
            "session_id": session_id,
            "task_key": t["id"],
            "question": t["question"],
            "rationale": t["rationale"],
            "evidence_type": t["evidence_type"],
            "status": t["status"],
            "origin": t["origin"],
            "iteration_added": t["iteration_added"],
        }
        for t in tasks
    ]
    stmt = insert(ResearchTask).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_research_tasks_key",
        set_={
            "status": stmt.excluded.status,
            "question": stmt.excluded.question,
            "rationale": stmt.excluded.rationale,
            "evidence_type": stmt.excluded.evidence_type,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)


async def upsert_sources(
    db: AsyncSession, session_id: uuid.UUID, sources: list[dict[str, Any]]
) -> None:
    if not sources:
        return
    rows = [
        {
            "id": uuid.uuid4(),
            "session_id": session_id,
            "source_key": s["id"],
            "kind": s["kind"],
            "title": s["title"],
            "url": s.get("url"),
            "document_id": uuid.UUID(s["document_id"]) if s.get("document_id") else None,
            "page_number": s.get("page_number"),
            "excerpt": s["content"][:1000],
            "content_kind": s["content_kind"],
            "published_date": s.get("published_date"),
            "possibly_outdated": s.get("possibly_outdated", False),
        }
        for s in sources
    ]
    stmt = insert(Source).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_sources_key", set_={"possibly_outdated": stmt.excluded.possibly_outdated}
    )
    await db.execute(stmt)


async def insert_evidence(
    db: AsyncSession, session_id: uuid.UUID, evidence: list[dict[str, Any]]
) -> None:
    if not evidence:
        return
    rows = [
        {
            "id": uuid.uuid4(),
            "session_id": session_id,
            "evidence_key": e["id"],
            "source_key": e["source_id"],
            "task_key": e["task_id"],
            "claim": e["claim"],
            "quote": e["quote"],
            "quote_verified": e["quote_verified"],
            "confidence": e["confidence"],
        }
        for e in evidence
    ]
    await db.execute(
        insert(EvidenceItem).values(rows).on_conflict_do_nothing(constraint="uq_evidence_key")
    )


async def save_report(db: AsyncSession, session_id: uuid.UUID, report: dict[str, Any]) -> None:
    content = {k: v for k, v in report.items() if k != "markdown"}
    stmt = insert(Report).values(
        id=uuid.uuid4(),
        session_id=session_id,
        status=report["status"],
        markdown=report["markdown"],
        content=content,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["session_id"],
        set_={
            "status": stmt.excluded.status,
            "markdown": stmt.excluded.markdown,
            "content": stmt.excluded.content,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
