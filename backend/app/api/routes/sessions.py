from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.core.security import CurrentUser
from app.repositories import research as repo
from app.schemas.common import Page
from app.schemas.research import SessionSummary

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=Page[SessionSummary])
async def list_sessions(
    user: CurrentUser,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> Page[SessionSummary]:
    rows, total = await repo.list_sessions(db, user, limit=limit, offset=offset, status=status)
    return Page(
        items=[SessionSummary.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
