"""Optional checks against real, paid providers. Skipped unless RUN_LIVE_TESTS=1.

RUN_LIVE_TESTS=1 OPENAI_API_KEY=... TAVILY_API_KEY=... pytest -m live
"""

import os

import pytest

from app.ai.models import build_research_model
from app.ai.prompts import PLANNER
from app.ai.schemas import ResearchPlan
from app.ai.tools.web_search import TavilySearchProvider
from app.core.config import Settings

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1"),
]


async def test_openai_structured_plan():
    settings = Settings(llm_provider="openai")
    model = build_research_model(settings)
    plan = await model.structured(
        ResearchPlan,
        PLANNER,
        {"question": "What is pgvector?", "documents_available": "no", "feedback": "(none)"},
    )
    assert 1 <= len(plan.tasks) <= 8


async def test_tavily_search_returns_results():
    provider = TavilySearchProvider(Settings(search_provider="tavily"))
    results = await provider.search("pgvector PostgreSQL extension", 3)
    assert results and all(r.url.startswith("http") for r in results)
