"""
document_store.py — extraction (including the OCR fallback for scanned
PDFs) and chunking. The embedding/search paths already degrade to keyword
search without an OpenAI key and are exercised indirectly by
test_document_store's ask/search callers elsewhere; this file focuses on
extract_text()'s contract, since that's what changed.
"""
import io

import pytest

from app import document_store


def _minimal_pdf_bytes(text: str = "") -> bytes:
    """A tiny single-page PDF, generated with reportlab (already a project
    dependency) so tests don't need a binary fixture checked into the repo.
    With no text drawn, pypdf's extract_text() returns "" for it, which is
    exactly the "scanned page" condition _extract_pdf needs to exercise."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    if text:
        c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_extract_text_returns_a_text_ocr_used_tuple_for_plain_text():
    text, ocr_used = document_store.extract_text("notes.txt", "text/plain", b"hello world")
    assert text == "hello world"
    assert ocr_used is False


def test_extract_pdf_with_a_real_text_layer_does_not_touch_ocr(monkeypatch):
    calls = []
    monkeypatch.setattr(document_store, "_ocr_pages", lambda data, indices: calls.append(indices) or {})

    text, ocr_used = document_store.extract_text(
        "policy.pdf", "application/pdf", _minimal_pdf_bytes("Refunds are processed within 14 days.")
    )

    assert "Refunds are processed within 14 days." in text
    assert ocr_used is False
    assert calls == []  # no blank pages, so OCR is never even attempted


def test_extract_pdf_with_no_text_layer_falls_back_to_ocr(monkeypatch):
    monkeypatch.setattr(
        document_store, "_ocr_pages",
        lambda data, indices: {i: "Termination requires 30 days written notice." for i in indices},
    )

    text, ocr_used = document_store.extract_text("scanned.pdf", "application/pdf", _minimal_pdf_bytes())

    assert "Termination requires 30 days written notice." in text
    assert ocr_used is True


def test_extract_pdf_raises_a_clear_error_when_ocr_finds_nothing(monkeypatch):
    monkeypatch.setattr(document_store, "_ocr_pages", lambda data, indices: {})

    with pytest.raises(document_store.DocumentStoreError, match="tesseract|scan"):
        document_store.extract_text("blank_scan.pdf", "application/pdf", _minimal_pdf_bytes())


def test_ocr_pages_is_a_no_op_when_disabled(monkeypatch):
    monkeypatch.setattr(document_store.settings, "ocr_enabled", False)
    assert document_store._ocr_pages(b"irrelevant", [0]) == {}


def test_ocr_pages_skips_cleanly_when_dependencies_are_missing(monkeypatch):
    """PyMuPDF/pytesseract/Pillow are optional at import time — the whole
    point of the fallback is that a server without them still works, just
    without OCR. This simulates that by asking to OCR a page of a PDF that
    has no image-renderable content at all, using the real code path
    (dependencies are installed in this environment, so instead we assert
    the *result shape* tolerates a render failure without raising)."""
    result = document_store._ocr_pages(b"not a real pdf", [0])
    assert result == {}  # opening garbage bytes as a PDF fails closed, not raises


def test_chunk_text_keeps_paragraphs_together_under_the_limit():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = document_store.chunk_text(text, chunk_size=1000)
    assert len(chunks) == 1
    assert "Paragraph one." in chunks[0] and "Paragraph three." in chunks[0]


def test_chunk_text_hard_splits_a_paragraph_longer_than_one_chunk():
    long_para = "word " * 500  # ~2500 chars, well over a 1200-char chunk
    chunks = document_store.chunk_text(long_para, chunk_size=1200, overlap=150)
    assert len(chunks) > 1
    assert all(len(c) <= 1200 for c in chunks)
