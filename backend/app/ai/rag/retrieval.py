"""Top-k semantic retrieval over pgvector, scoped to one user's ready documents."""

import uuid
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Document, DocumentChunk


@dataclass(frozen=True)
class RetrievalFilters:
    owner_id: str
    document_ids: list[uuid.UUID] | None = None  # None = all of the owner's documents
    page_from: int | None = None
    page_to: int | None = None


@dataclass(frozen=True)
class RetrievedPassage:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int | None
    chunk_index: int
    text: str
    score: float  # cosine similarity in [-1, 1]


async def search_chunks(
    db: AsyncSession,
    query_embedding: list[float],
    filters: RetrievalFilters,
    *,
    top_k: int,
    min_score: float = 0.0,
) -> list[RetrievedPassage]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(DocumentChunk, Document.filename, distance.label("distance"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.owner_id == filters.owner_id, Document.status == "ready")
        .order_by(distance)
        .limit(top_k)
    )
    if filters.document_ids is not None:
        stmt = stmt.where(Document.id.in_(filters.document_ids))
    if filters.page_from is not None:
        stmt = stmt.where(DocumentChunk.page_number >= filters.page_from)
    if filters.page_to is not None:
        stmt = stmt.where(DocumentChunk.page_number <= filters.page_to)

    rows = (await db.execute(stmt)).all()
    passages = [
        RetrievedPassage(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            text=chunk.content,
            score=1.0 - float(dist),
        )
        for chunk, filename, dist in rows
    ]
    return [p for p in passages if p.score >= min_score]


class DocumentRetriever:
    """Embeds the query, then searches. Owns its DB sessions so graph nodes can call it."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        embeddings: Embeddings,
        *,
        top_k: int,
        min_score: float,
    ):
        self.sessionmaker = sessionmaker
        self.embeddings = embeddings
        self.top_k = top_k
        self.min_score = min_score

    async def retrieve(
        self, query: str, filters: RetrievalFilters, top_k: int | None = None
    ) -> list[RetrievedPassage]:
        vector = await self.embeddings.aembed_query(query)
        async with self.sessionmaker() as db:
            return await search_chunks(
                db, vector, filters, top_k=top_k or self.top_k, min_score=self.min_score
            )

    async def has_documents(self, filters: RetrievalFilters) -> bool:
        stmt = select(Document.id).where(
            Document.owner_id == filters.owner_id, Document.status == "ready"
        )
        if filters.document_ids is not None:
            stmt = stmt.where(Document.id.in_(filters.document_ids))
        async with self.sessionmaker() as db:
            return (await db.execute(stmt.limit(1))).first() is not None
