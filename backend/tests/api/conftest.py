import httpx
import pytest

from app.container import build_container
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.main import create_app

pytestmark = pytest.mark.db


async def make_client(container):
    app = create_app()
    app.state.container = container  # lifespan isn't run by ASGITransport; wire it directly
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def container(clean_db):
    # Real Postgres checkpointer: these tests exercise durable interrupt/resume.
    c = await build_container(get_settings(), get_sessionmaker())
    yield c
    await c.close()


@pytest.fixture
async def client(container):
    async with await make_client(container) as c:
        yield c
