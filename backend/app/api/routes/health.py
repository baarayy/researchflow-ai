from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import ContainerDep, DbDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: DbDep, container: ContainerDep) -> JSONResponse:
    s = container.settings
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "providers": {
            "llm": container.llm.name,
            "search": container.search.name,
            "embeddings": s.embedding_provider,
        },
        "demo_mode": s.demo_mode,
        "limits": {"max_iterations": s.max_research_iterations, "max_upload_mb": s.max_upload_mb},
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)
