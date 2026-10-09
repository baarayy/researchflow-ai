import asyncio

import pymupdf
import pytest
from sqlalchemy import func, select

from app.models import DocumentChunk

pytestmark = pytest.mark.db

MD = (
    b"# Inference hardware\n\nRunning a 70B model at 16-bit precision needs about 140 GB of GPU memory.\n\n"
    b"# Licensing\n\nApache 2.0 permits commercial use.\n"
)


def pdf_bytes() -> bytes:
    doc = pymupdf.open()
    for text in (
        "Page one is about licensing and Apache terms.",
        "Page two explains GPU memory budgets.",
    ):
        doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


async def upload(client, name, data, ctype, headers=None):
    return await client.post(
        "/api/v1/documents", files={"file": (name, data, ctype)}, headers=headers or {}
    )


async def wait_ready(client, doc_id, headers=None):
    for _ in range(100):
        doc = (await client.get(f"/api/v1/documents/{doc_id}", headers=headers or {})).json()
        if doc["status"] in ("ready", "failed"):
            return doc
        await asyncio.sleep(0.05)
    raise AssertionError("document never indexed")


async def test_upload_index_list_delete(client, container):
    r = await upload(client, "notes.md", MD, "text/markdown")
    assert r.status_code == 201, r.text
    doc = await wait_ready(client, r.json()["document"]["id"])
    assert doc["status"] == "ready" and doc["chunk_count"] >= 1

    listing = (await client.get("/api/v1/documents")).json()
    assert listing["total"] == 1 and listing["items"][0]["filename"] == "notes.md"

    async with container.sessionmaker() as db:
        count = (
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == doc["id"])
        )
        assert (await db.execute(count)).scalar_one() == doc["chunk_count"]
        assert (await client.delete(f"/api/v1/documents/{doc['id']}")).status_code == 204
        assert (await db.execute(count)).scalar_one() == 0  # chunks + embeddings removed by cascade
    assert (await client.get(f"/api/v1/documents/{doc['id']}")).status_code == 404


async def test_duplicate_upload_is_not_reindexed(client):
    first = await upload(client, "a.md", MD, "text/markdown")
    await wait_ready(client, first.json()["document"]["id"])
    second = await upload(client, "renamed.md", MD, "text/markdown")
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert second.json()["document"]["id"] == first.json()["document"]["id"]


async def test_pdf_pages_and_grounded_answer_with_citations(client):
    r = await upload(client, "guide.pdf", pdf_bytes(), "application/pdf")
    doc = await wait_ready(client, r.json()["document"]["id"])
    assert doc["page_count"] == 2

    ans = (
        await client.post(
            "/api/v1/documents/ask", json={"question": "What about GPU memory budgets?"}
        )
    ).json()
    assert ans["sufficient_evidence"] is True
    assert (
        ans["citations"][0]["filename"] == "guide.pdf" and ans["citations"][0]["page_number"] == 2
    )

    none = (
        await client.post("/api/v1/documents/ask", json={"question": "medieval pottery glazes"})
    ).json()
    assert none["sufficient_evidence"] is False and none["citations"] == []


@pytest.mark.parametrize(
    ("name", "data", "ctype", "status"),
    [
        ("x.exe", b"MZ....", "application/octet-stream", 422),
        ("x.pdf", b"not a pdf at all", "application/pdf", 422),
        ("empty.txt", b"", "text/plain", 422),
        ("x.txt", b"tiny", "text/plain", 422),
    ],
)
async def test_invalid_uploads_rejected(client, name, data, ctype, status):
    r = await upload(client, name, data, ctype)
    assert r.status_code == status and r.json()["error"]["message"]


async def test_oversized_upload_rejected(client, container, monkeypatch):
    monkeypatch.setattr(container.settings, "max_upload_mb", 1)
    r = await upload(client, "big.txt", b"a" * (1024 * 1024 + 10), "text/plain")
    assert r.status_code == 413


async def test_documents_are_isolated_per_user(client):
    r = await upload(client, "notes.md", MD, "text/markdown")
    await wait_ready(client, r.json()["document"]["id"])
    other = {"X-User-Id": "intruder"}
    assert (await client.get("/api/v1/documents", headers=other)).json()["total"] == 0
    assert (
        await client.delete(f"/api/v1/documents/{r.json()['document']['id']}", headers=other)
    ).status_code == 404
    ans = (
        await client.post("/api/v1/documents/ask", json={"question": "GPU memory"}, headers=other)
    ).json()
    assert ans["citations"] == []
