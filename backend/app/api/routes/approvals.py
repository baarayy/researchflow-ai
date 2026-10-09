"""Pending approvals across sessions (the per-session approve/revise actions live in research.py)."""

from fastapi import APIRouter

from app.api.deps import DbDep
from app.core.security import CurrentUser
from app.repositories import research as repo
from app.schemas.common import Page
from app.schemas.research import SessionSummary

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=Page[SessionSummary])
async def pending_approvals(user: CurrentUser, db: DbDep) -> Page[SessionSummary]:
    rows, total = await repo.list_sessions(
        db, user, limit=100, offset=0, status="awaiting_approval"
    )
    return Page(
        items=[SessionSummary.model_validate(r) for r in rows], total=total, limit=100, offset=0
    )
