import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sse_starlette import EventSourceResponse

from app.api.deps import ContainerDep, DbDep
from app.core.errors import NotFoundError
from app.core.security import CurrentUser, rate_limit
from app.repositories import research as repo
from app.schemas.common import ErrorResponse
from app.schemas.research import (
    ApprovalDecision,
    ApproveRequest,
    CreateResearchRequest,
    EventOut,
    EvidenceOut,
    ReportOut,
    ReviseRequest,
    SessionDetail,
    SessionSummary,
    SourceOut,
    TaskOut,
)
from app.services.research_service import ResearchService

router = APIRouter(prefix="/research", tags=["research"], responses={404: {"model": ErrorResponse}})

IdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
]


def _service(db: DbDep, container: ContainerDep) -> ResearchService:
    return ResearchService(db, container.runner, container.settings)


ServiceDep = Annotated[ResearchService, Depends(_service)]


async def _detail(db: DbDep, session) -> SessionDetail:
    return SessionDetail(
        **SessionSummary.model_validate(session).model_dump(),
        options=session.options,
        pending_approval=session.pending_approval,
        critic_feedback=session.critic_feedback,
        error=session.error,
        tasks=[TaskOut.model_validate(t) for t in await repo.tasks_for(db, session.id)],
        sources=[SourceOut.model_validate(s) for s in await repo.sources_for(db, session.id)],
        evidence=[EvidenceOut.model_validate(e) for e in await repo.evidence_for(db, session.id)],
        has_report=await repo.report_for(db, session.id) is not None,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionSummary,
    dependencies=[Depends(rate_limit)],
    summary="Create a research session and start the workflow",
)
async def create_research(
    body: CreateResearchRequest,
    user: CurrentUser,
    service: ServiceDep,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> SessionSummary:
    session, created = await service.create(user, body, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK  # replay of an earlier request
    return SessionSummary.model_validate(session)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_research(
    session_id: uuid.UUID, user: CurrentUser, service: ServiceDep, db: DbDep
) -> SessionDetail:
    return await _detail(db, await service.get(user, session_id))


@router.post(
    "/{session_id}/approve",
    response_model=SessionSummary,
    responses={409: {"model": ErrorResponse}},
)
async def approve(
    session_id: uuid.UUID, body: ApproveRequest, user: CurrentUser, service: ServiceDep
) -> SessionSummary:
    """Approve the pending checkpoint (plan review or pre-report review) and resume the graph."""
    decision = ApprovalDecision(action="approve", feedback=body.feedback)
    return SessionSummary.model_validate(await service.resume(user, session_id, decision))


@router.post(
    "/{session_id}/revise", response_model=SessionSummary, responses={409: {"model": ErrorResponse}}
)
async def revise(
    session_id: uuid.UUID, body: ReviseRequest, user: CurrentUser, service: ServiceDep
) -> SessionSummary:
    """Send feedback instead of approving: replans (plan review) or researches more (report review)."""
    decision = ApprovalDecision(action="revise", feedback=body.feedback)
    return SessionSummary.model_validate(await service.resume(user, session_id, decision))


@router.get("/{session_id}/report", response_model=ReportOut)
async def get_report(
    session_id: uuid.UUID, user: CurrentUser, service: ServiceDep, db: DbDep
) -> ReportOut:
    await service.get(user, session_id)
    report = await repo.report_for(db, session_id)
    if report is None:
        raise NotFoundError("Report is not available yet")
    return ReportOut(
        session_id=session_id,
        status=report.status,
        markdown=report.markdown,
        content=report.content,
        created_at=report.created_at,
    )


@router.get("/{session_id}/events", summary="Server-Sent Events stream of workflow progress")
async def stream_events(
    session_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    service: ServiceDep,
    container: ContainerDep,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Streams persisted `workflow_events` rows (replayable via `after` / Last-Event-ID).

    The stream closes after the session reaches a terminal status. Events are read from the
    database, so any API instance can serve the stream for any run.
    """
    await service.get(user, session_id)
    cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    async def generator():
        nonlocal cursor
        while not await request.is_disconnected():
            async with container.sessionmaker() as db:
                events = await repo.events_after(db, session_id, cursor)
                session = await repo.get_session(db, session_id)
            for e in events:
                cursor = e.id
                yield {
                    "id": str(e.id),
                    "event": e.type,
                    "data": EventOut.model_validate(e).model_dump_json(),
                }
            if session is None or (session.status in repo.TERMINAL_STATUSES and not events):
                yield {
                    "event": "end",
                    "data": json.dumps({"status": session.status if session else "deleted"}),
                }
                return
            await asyncio.sleep(0.75)

    return EventSourceResponse(generator(), ping=15)
