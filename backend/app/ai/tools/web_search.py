"""Web search: the tool schema the model sees, and the providers that execute it.

The model only *proposes* a call (`WebSearch(query=..., task_id=...)`); the web_researcher
graph node executes it through a `SearchProvider` with timeouts and bounded retries.
"""

import logging
from typing import Literal, Protocol

from langchain_core.tools import ToolException
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import ExternalServiceError

logger = logging.getLogger(__name__)


class WebSearch(BaseModel):
    """Search the public web for recent, citable information."""

    query: str = Field(max_length=300, description="Search engine query.")
    task_id: str = Field(description="Id of the research task this search serves.")


class WebResult(BaseModel):
    title: str
    url: str
    content: str
    # A search snippet is partial text, not the verified full page.
    content_kind: Literal["snippet", "full_text"]
    published_date: str | None = None
    score: float | None = None


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int) -> list[WebResult]: ...


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, settings: Settings):
        from langchain_tavily import TavilySearch

        assert settings.tavily_api_key is not None  # guaranteed by Settings validation
        self._tool = TavilySearch(
            max_results=settings.search_max_results,
            tavily_api_key=settings.tavily_api_key.get_secret_value(),
            include_raw_content=False,
        )

    async def search(self, query: str, max_results: int) -> list[WebResult]:
        try:
            raw = await self._tool.ainvoke({"query": query})
        except ToolException as exc:
            # langchain-tavily raises ToolException("No search results found ...") on empty.
            if "no search results" in str(exc).lower():
                return []
            raise
        if isinstance(raw, dict) and raw.get("error"):
            raise ExternalServiceError(f"Tavily error: {type(raw['error']).__name__}")
        results = raw.get("results", []) if isinstance(raw, dict) else []
        return [
            WebResult(
                title=r.get("title") or r.get("url", "Untitled"),
                url=r["url"],
                content=(r.get("raw_content") or r.get("content") or "")[:4000],
                content_kind="full_text" if r.get("raw_content") else "snippet",
                published_date=r.get("published_date"),
                score=r.get("score"),
            )
            for r in results[:max_results]
            if r.get("url")
        ]


def build_search_provider(settings: Settings) -> SearchProvider:
    if settings.search_provider == "tavily":
        return TavilySearchProvider(settings)
    from app.ai.tools.demo_corpus import MockSearchProvider

    return MockSearchProvider()
