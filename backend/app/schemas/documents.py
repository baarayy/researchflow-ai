import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    error: str | None
    page_count: int | None
    chunk_count: int
    created_at: datetime


class UploadResponse(BaseModel):
    document: DocumentOut
    duplicate: bool = Field(description="True if this exact file was already uploaded.")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    top_k: int | None = Field(default=None, ge=1, le=20)


class PassageCitation(BaseModel):
    passage_id: str
    document_id: uuid.UUID
    filename: str
    page_number: int | None
    excerpt: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sufficient_evidence: bool
    citations: list[PassageCitation]
