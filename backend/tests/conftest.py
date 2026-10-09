"""Shared fixtures.

Unit and graph tests need nothing external. Tests marked `db` use the Postgres+pgvector test
database (docker compose creates `researchflow_test`); they are skipped if it is unreachable.
Everything runs with mock providers: no API keys, deterministic results.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Configure before any app module reads settings.
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://researchflow:researchflow@localhost:5433/researchflow_test",
)
os.environ.update(
    APP_ENV="test",
    DATABASE_URL=TEST_DB_URL,
    LLM_PROVIDER="mock",
    EMBEDDING_PROVIDER="mock",
    SEARCH_PROVIDER="mock",
    UPLOAD_DIR=tempfile.mkdtemp(prefix="researchflow-test-"),
    RATE_LIMIT_PER_MINUTE="1000",
)

import psycopg  # noqa: E402
import pytest  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _db_available() -> bool:
    try:
        with psycopg.connect(get_settings().checkpoint_database_url, connect_timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def migrated_db() -> str:
    if not _db_available():
        pytest.skip("Test database unavailable (run `docker compose up -d db`)")
    # Run the real Alembic migrations, so tests also verify them.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        check=True,
        env={**os.environ, "DATABASE_URL": TEST_DB_URL},
        capture_output=True,
    )
    return TEST_DB_URL


@pytest.fixture
async def clean_db(migrated_db):
    from sqlalchemy import text

    from app.db.session import dispose_engine, get_engine

    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE workflow_events, reports, evidence_items, sources, research_tasks, "
                "research_sessions, document_chunks, documents CASCADE"
            )
        )
    yield
    await dispose_engine()
