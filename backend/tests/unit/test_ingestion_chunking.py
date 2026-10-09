import pymupdf
import pytest

from app.ai.rag.chunking import chunk_pages
from app.ai.rag.ingestion import IngestionError, PageText, extract_text, validate_upload

MB = 1024 * 1024


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    return doc.tobytes()


@pytest.mark.parametrize(
    ("name", "ctype", "size", "message"),
    [
        ("a.exe", "application/octet-stream", 10, "Unsupported file type"),
        ("a", None, 10, "Unsupported file type"),
        ("a.pdf", "text/html", 10, "does not match"),
        ("a.txt", "text/plain", 0, "empty"),
        ("a.txt", "text/plain", 30 * MB, "limit"),
    ],
)
def test_validate_upload_rejects(name, ctype, size, message):
    with pytest.raises(IngestionError, match=message):
        validate_upload(name, ctype, size, 20 * MB)


def test_validate_upload_accepts_generic_content_type():
    assert validate_upload("Notes.MD", "application/octet-stream", 10, MB) == ".md"


def test_pdf_extraction_keeps_page_numbers():
    doc = extract_text(
        make_pdf(["First page about licensing terms.", "", "Third page on GPU memory needs."]),
        ".pdf",
    )
    assert doc.page_count == 3
    assert [p.page_number for p in doc.pages] == [1, 3]  # blank page skipped, numbering kept


def test_pdf_without_text_is_rejected():
    with pytest.raises(IngestionError, match="OCR"):
        extract_text(make_pdf(["", ""]), ".pdf")


def test_corrupt_pdf_is_rejected():
    with pytest.raises(IngestionError):
        extract_text(b"%PDF-1.7 garbage that is not a pdf", ".pdf")
    with pytest.raises(IngestionError, match="not a valid PDF"):
        extract_text(b"hello world, definitely not a pdf", ".pdf")


def test_binary_text_file_is_rejected():
    with pytest.raises(IngestionError, match="binary"):
        extract_text(b"abc\x00def" * 10, ".txt")


def test_chunking_preserves_pages_and_overlap():
    long = " ".join(f"sentence{i} about topic." for i in range(200))
    chunks = chunk_pages(
        [PageText(1, long), PageText(2, "short page two text")], chunk_size=300, chunk_overlap=50
    )
    assert all(len(c.text) <= 300 for c in chunks)
    assert chunks[-1].page_number == 2 and chunks[-1].text == "short page two text"
    assert {c.page_number for c in chunks[:-1]} == {1}  # no chunk spans pages
    assert [c.index for c in chunks] == list(range(len(chunks)))
    # Overlap: the end of one chunk reappears at the start of the next.
    assert chunks[0].text.split()[-1] in chunks[1].text


def test_markdown_chunking_prefers_headings():
    md = "# A\n\n" + "alpha " * 60 + "\n\n# B\n\n" + "beta " * 60
    chunks = chunk_pages([PageText(None, md)], chunk_size=400, chunk_overlap=0, markdown=True)
    assert chunks[0].text.startswith("# A") and any(c.text.startswith("# B") for c in chunks)
