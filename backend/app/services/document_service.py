"""Document upload → validation → extraction → storage → chunking → embedding → pgvector."""

import asyncio
import hashlib
import logging
import uuid
from pathlib import PurePath

from langchain_core.embeddings import Embeddings
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.rag.chunking import chunk_pages
from app.ai.rag.ingestion import ExtractedDocument, IngestionError, extract_text, validate_upload
from app.core.config import Settings
from app.core.errors import NotFoundError, PayloadTooLarge, ValidationFailed
from app.models import Document, DocumentChunk
from app.repositories import documents as repo
from app.storage.base import FileStorage

logger = logging.getLogger(__name__)
EMBED_BATCH = 64


def safe_display_name(filename: str) -> str:
    """Keep only the base name, printable and bounded; used for display, never as a path."""
    name = PurePath(filename.replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:255] or "upload"


class DocumentIndexer:
    """Chunks + embeds a document and stores vectors. Runs in the background after upload."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        embeddings: Embeddings,
        storage: FileStorage,
        settings: Settings,
    ):
        self.sessionmaker = sessionmaker
        self.embeddings = embeddings
        self.storage = storage
        self.settings = settings

    async def index(
        self, document_id: uuid.UUID, extracted: ExtractedDocument | None = None
    ) -> None:
        async with self.sessionmaker() as db:
            doc = await db.get(Document, document_id)
            if doc is None:
                return
            try:
                if extracted is None:  # e.g. re-indexing after a restart
                    data = await self.storage.read(doc.storage_key)
                    extracted = await asyncio.to_thread(
                        extract_text, data, PurePath(doc.storage_key).suffix
                    )
                chunks = chunk_pages(
                    extracted.pages,
                    chunk_size=self.settings.chunk_size,
                    chunk_overlap=self.settings.chunk_overlap,
                    markdown=doc.storage_key.endswith((".md", ".markdown")),
                )
                vectors: list[list[float]] = []
                for i in range(0, len(chunks), EMBED_BATCH):
                    vectors += await self.embeddings.aembed_documents(
                        [c.text for c in chunks[i : i + EMBED_BATCH]]
                    )
                # Replace any partial chunks from an earlier attempt, then insert in one transaction.
                await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
                db.add_all(
                    DocumentChunk(
                        document_id=doc.id,
                        chunk_index=c.index,
                        page_number=c.page_number,
                        content=c.text,
                        embedding=v,
                    )
                    for c, v in zip(chunks, vectors, strict=True)
                )
                doc.status, doc.chunk_count, doc.error = "ready", len(chunks), None
                await db.commit()
            except Exception as exc:
                logger.exception("Indexing failed for document %s", document_id)
                await db.rollback()
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        status="failed",
                        error=f"Indexing failed ({type(exc).__name__}). Try uploading again.",
                    )
                )
                await db.commit()

    async def recover(self) -> None:
        async with self.sessionmaker() as db:
            stuck = await repo.documents_with_status(db, "indexing")
        for doc in stuck:
            await self.index(doc.id)


class DocumentService:
    def __init__(self, db: AsyncSession, storage: FileStorage, settings: Settings):
        self.db = db
        self.storage = storage
        self.settings = settings

    async def upload(
        self, owner_id: str, filename: str, content_type: str | None, data: bytes
    ) -> tuple[Document, ExtractedDocument | None]:
        """Validate and store. Returns (document, extracted) — extracted is None for duplicates."""
        if len(data) > self.settings.max_upload_bytes:
            raise PayloadTooLarge(f"File exceeds the {self.settings.max_upload_mb} MB limit.")
        name = safe_display_name(filename)
        try:
            ext = validate_upload(name, content_type, len(data), self.settings.max_upload_bytes)
            extracted = await asyncio.to_thread(extract_text, data, ext)
        except IngestionError as exc:
            raise ValidationFailed(str(exc)) from exc

        sha = hashlib.sha256(data).hexdigest()
        if existing := await repo.get_by_sha(self.db, owner_id, sha):
            if existing.status != "failed":
                return existing, None  # identical file already uploaded: don't index twice
            await self.delete(owner_id, existing.id)

        key = f"{uuid.uuid4().hex}{ext}"
        await self.storage.save(key, data)
        doc = Document(
            owner_id=owner_id,
            filename=name,
            content_type=(content_type or "application/octet-stream")[:100],
            size_bytes=len(data),
            sha256=sha,
            storage_key=key,
            status="indexing",
            page_count=extracted.page_count,
        )
        self.db.add(doc)
        try:
            await self.db.commit()
        except Exception:
            await self.storage.delete(key)
            raise
        return doc, extracted

    async def get(self, owner_id: str, document_id: uuid.UUID) -> Document:
        doc = await repo.get_document(self.db, document_id, owner_id)
        if doc is None:
            raise NotFoundError("Document not found")
        return doc

    async def delete(self, owner_id: str, document_id: uuid.UUID) -> None:
        doc = await self.get(owner_id, document_id)
        key = doc.storage_key
        await repo.delete_document(self.db, doc.id)
        await self.db.commit()
        await self.storage.delete(key)  # after commit: a failed DB delete never orphans metadata
