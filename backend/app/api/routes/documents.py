import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Response, UploadFile, status

from app.ai.rag.answer import answer_from_documents
from app.ai.rag.retrieval import RetrievalFilters
from app.api.deps import ContainerDep, DbDep
from app.core.errors import PayloadTooLarge
from app.core.security import CurrentUser, rate_limit
from app.repositories import documents as repo
from app.schemas.common import ErrorResponse, Page
from app.schemas.documents import (
    AskRequest,
    AskResponse,
    DocumentOut,
    PassageCitation,
    UploadResponse,
)
from app.services.document_service import DocumentService

router = APIRouter(
    prefix="/documents", tags=["documents"], responses={404: {"model": ErrorResponse}}
)


def _service(db: DbDep, container: ContainerDep) -> DocumentService:
    return DocumentService(db, container.storage, container.settings)


ServiceDep = Annotated[DocumentService, Depends(_service)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadResponse,
    dependencies=[Depends(rate_limit)],
    responses={413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def upload_document(
    user: CurrentUser,
    service: ServiceDep,
    container: ContainerDep,
    background: BackgroundTasks,
    response: Response,
    file: Annotated[UploadFile, File(description="PDF, TXT or Markdown")],
) -> UploadResponse:
    """Validates and extracts text synchronously (bad files fail fast with 422), then chunks and
    embeds in the background. Poll the document's `status` until it is `ready`."""
    limit = container.settings.max_upload_bytes
    data = await file.read(limit + 1)  # bounded read: never buffer more than the limit
    if len(data) > limit:
        raise PayloadTooLarge(f"File exceeds the {container.settings.max_upload_mb} MB limit.")
    doc, extracted = await service.upload(user, file.filename or "upload", file.content_type, data)
    if extracted is None:
        response.status_code = status.HTTP_200_OK
        return UploadResponse(document=DocumentOut.model_validate(doc), duplicate=True)
    background.add_task(container.indexer.index, doc.id, extracted)
    return UploadResponse(document=DocumentOut.model_validate(doc), duplicate=False)


@router.get("", response_model=Page[DocumentOut])
async def list_documents(
    user: CurrentUser,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[DocumentOut]:
    rows, total = await repo.list_documents(db, user, limit=limit, offset=offset)
    return Page(
        items=[DocumentOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID, user: CurrentUser, service: ServiceDep
) -> DocumentOut:
    return DocumentOut.model_validate(await service.get(user, document_id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, user: CurrentUser, service: ServiceDep
) -> Response:
    """Deletes the document, its stored file, and all chunks/embeddings (cascade)."""
    await service.delete(user, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ask", response_model=AskResponse, dependencies=[Depends(rate_limit)])
async def ask_documents(
    body: AskRequest, user: CurrentUser, container: ContainerDep
) -> AskResponse:
    """Single-shot grounded Q&A over your documents (basic RAG, no research workflow)."""
    result = await answer_from_documents(
        container.llm,
        container.retriever,
        body.question,
        RetrievalFilters(owner_id=user, document_ids=body.document_ids),
        top_k=body.top_k,
    )
    return AskResponse(
        answer=result.answer,
        sufficient_evidence=result.sufficient_evidence,
        citations=[
            PassageCitation(
                passage_id=pid,
                document_id=p.document_id,
                filename=p.filename,
                page_number=p.page_number,
                excerpt=p.text[:500],
                score=round(p.score, 4),
            )
            for pid, p in result.cited
        ],
    )
