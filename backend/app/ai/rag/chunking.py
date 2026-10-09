"""Split extracted pages into overlapping chunks, keeping page numbers.

Chunks never span pages, so every chunk can be cited with an exact page.
"""

from dataclasses import dataclass

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from app.ai.rag.ingestion import PageText


@dataclass(frozen=True)
class Chunk:
    index: int
    page_number: int | None
    text: str


def make_splitter(
    chunk_size: int, chunk_overlap: int, markdown: bool
) -> RecursiveCharacterTextSplitter:
    if markdown:
        # Prefers splitting on headings, then paragraphs, then sentences.
        return RecursiveCharacterTextSplitter.from_language(
            Language.MARKDOWN, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def chunk_pages(
    pages: list[PageText], *, chunk_size: int, chunk_overlap: int, markdown: bool = False
) -> list[Chunk]:
    splitter = make_splitter(chunk_size, chunk_overlap, markdown)
    chunks: list[Chunk] = []
    for page in pages:
        for piece in splitter.split_text(page.text):
            if piece.strip():
                chunks.append(Chunk(len(chunks), page.page_number, piece.strip()))
    return chunks
