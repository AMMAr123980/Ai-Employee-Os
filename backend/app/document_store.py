"""
Company Knowledge Base — extraction, chunking, embedding and search.

The pipeline is deliberately the dumbest thing that works:

    upload -> extract text -> chunk -> embed each chunk -> store
    ask     -> embed the question -> cosine-similarity over stored chunks
             -> hand the top few to the model with the question -> answer

No vector database, no background job queue: extraction and embedding happen
synchronously in the request for anything under EMBED_INLINE_MAX_CHARS, and
in a plain background task (FastAPI's BackgroundTasks, not a new worker)
above that — the same "no new services" rule the voice module holds itself
to. A company uploading a 200-page manual waits for a spinner, not a queue.

Running without an OpenAI key: extraction and storage still work, and search
falls back to a case-insensitive keyword match over chunk text instead of
cosine similarity. It's a worse search, not a broken feature, and
`ask_documents` says which mode answered.

Scanned PDFs: a page with no text layer is rendered to an image and OCR'd
(PyMuPDF + pytesseract) instead of the whole upload being rejected. See
`_ocr_pages`. Contract-specific clause extraction — finding and labelling
termination, liability, auto-renewal etc. clauses rather than just answering
free-text questions — lives in `contract_analysis.py`, which reuses this
module's chunks as its input.
"""
import io
import json
import logging
import math
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.document_models import Document, DocumentChunk, DocumentStatus

logger = logging.getLogger(__name__)

EMBED_INLINE_MAX_CHARS = 200_000   # ~ a 40-50 page document; above this, chunk/embed in the background
CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150
TOP_K = 5
EMBEDDING_MODEL = "text-embedding-3-small"


class DocumentStoreError(Exception):
    """Raised for problems the caller can act on: unreadable file, empty
    document, no matching document for a name. Message is shown as-is."""


_client = None


def _get_client():
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def extract_text(filename: str, content_type: Optional[str], data: bytes) -> tuple[str, bool]:
    """Best-effort text extraction. Unsupported binary formats raise rather
    than silently indexing garbage bytes as "text". Returns (text, ocr_used)
    — ocr_used is always False except for a PDF that needed OCR for at
    least one page."""
    name = (filename or "").lower()

    if name.endswith(".pdf") or content_type == "application/pdf":
        return _extract_pdf(data)

    if name.endswith((".txt", ".md", ".markdown", ".csv")) or (content_type or "").startswith("text/"):
        for encoding in ("utf-8", "latin-1"):
            try:
                return data.decode(encoding), False
            except UnicodeDecodeError:
                continue
        raise DocumentStoreError(f"Couldn't decode '{filename}' as text.")

    if name.endswith(".docx"):
        return _extract_docx(data), False

    raise DocumentStoreError(
        f"Unsupported file type for '{filename}'. Supported: PDF, DOCX, TXT, Markdown, CSV."
    )


def _extract_pdf(data: bytes) -> tuple[str, bool]:
    """Text-layer extraction first, page by page. Any page that comes back
    blank — the signature of a scanned image with no text layer — is handed
    to `_ocr_pages` instead of just being dropped. A PDF that's part typed,
    part scanned (a contract with a hand-signed signature page) gets both:
    real text where it exists, OCR text where it doesn't."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentStoreError(
            "PDF support needs the 'pypdf' package — add it to requirements.txt and reinstall."
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise DocumentStoreError(f"Couldn't read that PDF: {exc}") from exc

    blank_indices = [i for i, p in enumerate(pages) if not p.strip()]
    ocr_used = False
    if blank_indices:
        ocr_text_by_page = _ocr_pages(data, blank_indices)
        for i, ocr_text in ocr_text_by_page.items():
            if ocr_text.strip():
                pages[i] = ocr_text
                ocr_used = True

    text = "\n\n".join(p for p in pages if p.strip())
    if not text.strip():
        reason = (
            "the scan may be too low quality to read, or OCR isn't set up on this server "
            "(needs the tesseract-ocr binary installed alongside the Python packages)"
            if blank_indices else
            "it may be a scanned image without a text layer"
        )
        raise DocumentStoreError(f"No extractable text found in that PDF — {reason}.")
    return text, ocr_used


def _ocr_pages(data: bytes, page_indices: list[int]) -> dict[int, str]:
    """OCRs the given 0-based page indices of a PDF and returns {index: text}.

    Rendering uses PyMuPDF (fitz) rather than pdf2image/poppler so this has
    no external system dependency beyond the OCR engine itself. Missing
    packages, a missing tesseract binary, or a corrupt render are all
    non-fatal here — the caller just keeps whatever text-layer pages it
    already had, same "worse, not broken" fallback philosophy as search()
    running without an OpenAI key."""
    if not settings.ocr_enabled or not page_indices:
        return {}
    if len(page_indices) > settings.ocr_max_pages:
        logger.info(
            "OCR skipped: %d blank pages exceeds ocr_max_pages=%d for an inline request.",
            len(page_indices), settings.ocr_max_pages,
        )
        return {}

    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.info("OCR skipped: PyMuPDF/pytesseract/Pillow not installed.")
        return {}

    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.warning("OCR skipped: couldn't open PDF for rendering: %s", exc)
        return {}

    results: dict[int, str] = {}
    zoom = 2.0  # ~144 DPI — enough for OCR accuracy without huge intermediate images
    try:
        for i in page_indices:
            if i >= pdf.page_count:
                continue
            try:
                pix = pdf.load_page(i).get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                results[i] = pytesseract.image_to_string(image, lang=settings.ocr_language)
            except pytesseract.pytesseract.TesseractNotFoundError:
                logger.warning(
                    "OCR skipped: the 'tesseract' binary isn't installed on this server "
                    "(the Python package alone isn't enough — see README)."
                )
                break
            except Exception as exc:
                logger.warning("OCR failed for page %d: %s", i, exc)
                continue
    finally:
        pdf.close()
    return results


def _extract_docx(data: bytes) -> str:
    try:
        import docx  # python-docx
    except ImportError as exc:
        raise DocumentStoreError(
            "DOCX support needs the 'python-docx' package — add it to requirements.txt and reinstall."
        ) from exc
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentStoreError(f"Couldn't read that DOCX: {exc}") from exc
    return "\n\n".join(p.text for p in document.paragraphs if p.text.strip())


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Paragraph-aware fixed-size chunking with a small overlap, so a fact
    split across a chunk boundary is still fully present in at least one
    chunk. Splitting purely on paragraphs would produce wildly uneven chunk
    sizes (a one-line heading next to a 3-page clause), which makes cosine
    similarity less meaningful — long chunks dilute their own embedding."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []

    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        candidate = f"{buffer}\n\n{para}" if buffer else para
        if len(candidate) <= chunk_size:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
        if len(para) <= chunk_size:
            buffer = para
        else:
            # A single paragraph longer than one chunk (a wall-of-text
            # contract clause) gets hard-split with overlap.
            start = 0
            while start < len(para):
                end = start + chunk_size
                chunks.append(para[start:end])
                start = end - overlap
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks


# --------------------------------------------------------------------------
# Embedding
# --------------------------------------------------------------------------

def embed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    """Returns one embedding per input text, or a list of Nones if no OpenAI
    key is configured — callers fall back to keyword search in that case."""
    client = _get_client()
    if client is None or not texts:
        return [None] * len(texts)
    try:
        # The API accepts a batch in one call; chunking that batch further
        # would only matter past a few thousand chunks, well beyond this
        # MVP's expected document volume.
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in response.data]
    except Exception as exc:
        logger.warning("Embedding call failed, falling back to keyword search: %s", exc)
        return [None] * len(texts)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------

def process_document(db: Session, document: Document, text: str) -> None:
    """Chunks, embeds and stores. Runs inline for small documents, or from a
    background task for large ones — either way it's the same function, so
    there's exactly one code path to test."""
    try:
        pieces = chunk_text(text)
        if not pieces:
            raise DocumentStoreError("That document appears to be empty.")

        embeddings = embed_texts(pieces)
        for index, (piece, embedding) in enumerate(zip(pieces, embeddings)):
            db.add(DocumentChunk(
                company_id=document.company_id,
                document_id=document.id,
                chunk_index=index,
                content=piece,
                embedding_json=json.dumps(embedding) if embedding is not None else None,
            ))

        document.chunk_count = len(pieces)
        document.char_count = len(text)
        document.status = DocumentStatus.READY
        document.processed_at = datetime.utcnow()
        document.error = None
        db.commit()
    except Exception as exc:
        db.rollback()
        document.status = DocumentStatus.FAILED
        document.error = str(exc)[:1000]
        db.commit()
        logger.warning("Document processing failed for %s: %s", document.id, exc)


# --------------------------------------------------------------------------
# Search & ask
# --------------------------------------------------------------------------

def search(
    db: Session, company_id: str, query: str, *,
    top_k: int = TOP_K, document_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Returns the top_k most relevant chunks, each with its document title
    so an answer can be attributed to a source document."""
    chunk_query = db.query(DocumentChunk).filter(DocumentChunk.company_id == company_id)
    if document_id:
        chunk_query = chunk_query.filter(DocumentChunk.document_id == document_id)
    chunks = chunk_query.all()
    if not chunks:
        return []

    [query_embedding] = embed_texts([query])
    scored: list[tuple[float, DocumentChunk]] = []

    if query_embedding is not None:
        for chunk in chunks:
            if not chunk.embedding_json:
                continue
            score = _cosine(query_embedding, json.loads(chunk.embedding_json))
            scored.append((score, chunk))

    if not scored:
        # No key configured, or nothing had an embedding yet — fall back to a
        # plain keyword match rather than returning nothing.
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
        for chunk in chunks:
            lowered = chunk.content.lower()
            score = sum(lowered.count(term) for term in terms)
            if score > 0:
                scored.append((float(score), chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:top_k]

    documents_by_id = {d.id: d for d in db.query(Document).filter(Document.company_id == company_id).all()}
    return [
        {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "document_title": documents_by_id.get(chunk.document_id).title
            if documents_by_id.get(chunk.document_id) else "Unknown document",
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": round(score, 4),
        }
        for score, chunk in top
    ]


def answer_question(db: Session, company_id: str, question: str, *, document_id: Optional[str] = None) -> dict[str, Any]:
    """Retrieval-augmented answer. If no OpenAI key is configured, returns the
    raw matching passages instead of a synthesised answer — still useful,
    just not summarised."""
    matches = search(db, company_id, question, document_id=document_id)
    if not matches:
        return {
            "answer": "Nothing in the knowledge base looks related to that question.",
            "sources": [],
            "mode": "no_match",
        }

    client = _get_client()
    if client is None:
        return {
            "answer": None,
            "sources": matches,
            "mode": "passages_only",
        }

    context = "\n\n---\n\n".join(
        f"From \"{m['document_title']}\":\n{m['content']}" for m in matches
    )
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": (
                    "Answer the question using ONLY the excerpts below, which are the company's "
                    "own documents. If the excerpts don't contain the answer, say so plainly rather "
                    "than guessing or using outside knowledge. Be concise. Mention which document "
                    "the answer came from when it matters."
                )},
                {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {question}"},
            ],
            temperature=0.1,
            max_tokens=600,
        )
        answer = response.choices[0].message.content
    except Exception as exc:
        logger.warning("ask_documents synthesis failed, returning passages: %s", exc)
        return {"answer": None, "sources": matches, "mode": "passages_only", "error": str(exc)}

    return {"answer": answer, "sources": matches, "mode": "answered"}
