"""Turn uploaded bytes into page-tagged text. Pure functions; no database access.

PDF extraction uses PyMuPDF. Extraction is CPU-bound, so callers run it in a worker thread.
"""

from dataclasses import dataclass
from pathlib import PurePath

import pymupdf

ALLOWED_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/x-markdown", "text/plain"},
    ".markdown": {"text/markdown", "text/x-markdown", "text/plain"},
}
# Browsers/curl often send a generic type; accept it and rely on extension + content sniffing.
GENERIC_TYPES = {"application/octet-stream", ""}


class IngestionError(ValueError):
    """The upload is invalid or has no usable text. Message is safe to show to users."""


@dataclass(frozen=True)
class PageText:
    page_number: int | None  # 1-based for PDFs; None for plain-text formats
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    pages: list[PageText]
    page_count: int | None

    @property
    def char_count(self) -> int:
        return sum(len(p.text) for p in self.pages)


def validate_upload(filename: str, content_type: str | None, size: int, max_bytes: int) -> str:
    """Return the normalized extension or raise IngestionError."""
    ext = PurePath(filename).suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise IngestionError(f"Unsupported file type '{ext or 'none'}'. Use PDF, TXT or Markdown.")
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in GENERIC_TYPES and ctype not in ALLOWED_TYPES[ext]:
        raise IngestionError(f"Content type '{ctype}' does not match extension '{ext}'.")
    if size == 0:
        raise IngestionError("The file is empty.")
    if size > max_bytes:
        raise IngestionError(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    return ext


def extract_text(data: bytes, ext: str) -> ExtractedDocument:
    doc = _extract_pdf(data) if ext == ".pdf" else _extract_plain(data)
    if doc.char_count < 20:
        raise IngestionError(
            "No extractable text found. Scanned PDFs need OCR before upload."
            if ext == ".pdf"
            else "The document contains no readable text."
        )
    return doc


def _extract_pdf(data: bytes) -> ExtractedDocument:
    if not data.startswith(b"%PDF"):
        raise IngestionError("File is not a valid PDF.")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise IngestionError("Password-protected PDFs are not supported.")
            pages = [PageText(i + 1, page.get_text("text").strip()) for i, page in enumerate(pdf)]
            return ExtractedDocument([p for p in pages if p.text], page_count=len(pages))
    except IngestionError:
        raise
    except Exception as exc:  # PyMuPDF raises various internal errors on corrupt files
        raise IngestionError("The PDF could not be read; it may be corrupt.") from exc


def _extract_plain(data: bytes) -> ExtractedDocument:
    if b"\x00" in data[:4096]:
        raise IngestionError("File looks binary, not text.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return ExtractedDocument([PageText(None, text.strip())], page_count=None)
