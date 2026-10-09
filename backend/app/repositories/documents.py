import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document


async def get_document(db: AsyncSession, document_id: uuid.UUID, owner_id: str) -> Document | None:
    stmt = select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_by_sha(db: AsyncSession, owner_id: str, sha256: str) -> Document | None:
    stmt = select(Document).where(Document.owner_id == owner_id, Document.sha256 == sha256)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_documents(
    db: AsyncSession, owner_id: str, *, limit: int, offset: int
) -> tuple[list[Document], int]:
    base = select(Document).where(Document.owner_id == owner_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = await db.execute(base.order_by(Document.created_at.desc()).limit(limit).offset(offset))
    return list(rows.scalars()), total


async def documents_with_status(db: AsyncSession, status: str) -> list[Document]:
    return list((await db.execute(select(Document).where(Document.status == status))).scalars())


async def count_owned(db: AsyncSession, owner_id: str, ids: list[uuid.UUID]) -> int:
    stmt = select(func.count()).where(Document.owner_id == owner_id, Document.id.in_(ids))
    return (await db.execute(stmt)).scalar_one()


async def delete_document(db: AsyncSession, document_id: uuid.UUID) -> None:
    # Chunks (and their embeddings) go with it via ON DELETE CASCADE.
    await db.execute(delete(Document).where(Document.id == document_id))
