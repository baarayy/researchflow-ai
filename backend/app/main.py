import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import approvals, documents, health, research, sessions
from app.container import Container, build_container
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # raises on invalid config: fail fast at startup
    configure_logging(settings.log_level)
    container: Container = getattr(app.state, "container", None) or await build_container(
        settings, get_sessionmaker()
    )
    app.state.container = container
    recovered = await container.runner.recover()
    background = asyncio.create_task(container.indexer.recover())
    logger.info(
        "ResearchFlow started (demo_mode=%s, recovered_runs=%d)", settings.demo_mode, recovered
    )
    try:
        yield
    finally:
        background.cancel()
        await container.close()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ResearchFlow AI",
        version="0.1.0",
        description="AI research assistant built with LangChain and LangGraph.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-User-Id", "Idempotency-Key", "Last-Event-ID"],
    )
    install_error_handlers(app)
    api = APIRouter(prefix="/api/v1")
    for module in (health, research, sessions, approvals, documents):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
