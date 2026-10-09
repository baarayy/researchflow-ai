"""Test doubles for graph tests."""

import uuid
from typing import Any

from app.ai.mock import MockResearchModel
from app.ai.rag.retrieval import RetrievalFilters, RetrievedPassage
from app.ai.tools.web_search import WebResult


class ScriptedModel(MockResearchModel):
    """Mock model whose answers can be overridden per schema.

    `overrides[SchemaName]` is a list of results returned in order (the last one repeats); an
    Exception instance is raised instead of returned.
    """

    def __init__(self, **overrides: list[Any]):
        self.overrides = overrides
        self.calls: dict[str, int] = {}

    async def structured(self, schema, prompt, inputs, *, context=None):
        name = schema.__name__
        self.calls[name] = self.calls.get(name, 0) + 1
        if name in self.overrides:
            script = self.overrides[name]
            result = script[min(self.calls[name], len(script)) - 1]
            if isinstance(result, Exception):
                raise result
            if callable(result):
                return result(context or {})
            return result
        # Prompt must render with the inputs given (catches missing template variables).
        prompt.format_messages(**inputs)
        return await super().structured(schema, prompt, inputs, context=context)


class StaticSearch:
    name = "static"

    def __init__(self, results: list[WebResult] | None = None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.queries: list[str] = []

    async def search(self, query: str, max_results: int) -> list[WebResult]:
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.results[:max_results]


class FakeRetriever:
    def __init__(self, passages: list[RetrievedPassage] | None = None):
        self.passages = passages or []
        self.filters: list[RetrievalFilters] = []

    async def has_documents(self, filters: RetrievalFilters) -> bool:
        return bool(self.passages)

    async def retrieve(self, query: str, filters: RetrievalFilters, top_k: int | None = None):
        self.filters.append(filters)
        return self.passages


def passage(text: str, filename: str = "notes.pdf", page: int | None = 1) -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename=filename,
        page_number=page,
        chunk_index=0,
        text=text,
        score=0.9,
    )


def web(
    title: str, content: str, url: str | None = None, published: str | None = "2026-01-01"
) -> WebResult:
    return WebResult(
        title=title,
        url=url or f"https://example.org/{abs(hash(title))}",
        content=content,
        content_kind="snippet",
        published_date=published,
    )
