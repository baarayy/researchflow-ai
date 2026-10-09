"""pgvector retrieval: ordering, owner isolation and metadata filters."""

import uuid

import pytest

from app.ai.rag.embeddings import HashingEmbeddings
from app.ai.rag.retrieval import RetrievalFilters, search_chunks
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Document, DocumentChunk

pytestmark = pytest.mark.db


async def seed(db, owner, filename, pages, status="ready"):
    emb = HashingEmbeddings(get_settings().embedding_dim)
    doc = Document(
        owner_id=owner,
        filename=filename,
        content_type="text/plain",
        size_bytes=1,
        sha256=uuid.uuid4().hex,
        storage_key=f"{uuid.uuid4().hex}.txt",
        status=status,
    )
    db.add(doc)
    await db.flush()
    for i, (page, text) in enumerate(pages):
        db.add(
            DocumentChunk(
                document_id=doc.id,
                chunk_index=i,
                page_number=page,
                content=text,
                embedding=emb.embed_query(text),
            )
        )
    await db.commit()
    return doc


async def test_search_orders_filters_and_isolates(clean_db):
    emb = HashingEmbeddings(get_settings().embedding_dim)
    async with get_sessionmaker()() as db:
        mine = await seed(
            db, "alice", "gpu.txt", [(1, "GPU memory for inference"), (2, "license terms apache")]
        )
        other = await seed(db, "alice", "misc.txt", [(1, "GPU memory budgeting guide")])
        await seed(db, "bob", "bob.txt", [(1, "GPU memory for inference exactly")])
        await seed(db, "alice", "pending.txt", [(1, "GPU memory for inference")], status="indexing")

        q = emb.embed_query("GPU memory inference")
        results = await search_chunks(db, q, RetrievalFilters(owner_id="alice"), top_k=10)
        assert {r.filename for r in results} == {"gpu.txt", "misc.txt"}  # no bob, no unready docs
        assert results[0].text == "GPU memory for inference"
        assert results == sorted(results, key=lambda r: r.score, reverse=True)

        only = await search_chunks(
            db, q, RetrievalFilters(owner_id="alice", document_ids=[other.id]), top_k=10
        )
        assert {r.document_id for r in only} == {other.id}

        page2 = await search_chunks(
            db, q, RetrievalFilters(owner_id="alice", page_from=2), top_k=10
        )
        assert [r.page_number for r in page2] == [2] and page2[0].document_id == mine.id

        top1 = await search_chunks(db, q, RetrievalFilters(owner_id="alice"), top_k=1)
        assert len(top1) == 1
        strict = await search_chunks(
            db, q, RetrievalFilters(owner_id="alice"), top_k=10, min_score=0.99
        )
        assert all(r.score >= 0.99 for r in strict)
