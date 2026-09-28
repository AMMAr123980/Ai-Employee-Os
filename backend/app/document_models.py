"""
Company Knowledge Base — the piece VOICE_AND_MEETINGS.md names explicitly as
missing: "There's no document store to ask, so there's no `ask_documents`
intent." This module is that document store.

Kept separate from models.py for the same reason ai_employee_models.py and
task_models.py are: a self-contained feature that imports cleanly with one
line in main.py, and can be deleted wholesale if it's ever ripped out.

Two tables, on purpose rather than one with a JSON blob:

- `kb_documents` — one row per uploaded file. What the UI lists, what
  `document_id` on a chunk points back to, what "delete this document"
  operates on.
- `kb_document_chunks` — the unit search actually happens over. A whole
  document is too big to hand an LLM as context and too coarse to search
  well ("mentions pricing somewhere in this 40-page PDF" isn't an answer);
  a paragraph-sized chunk with its own embedding is both citable and
  searchable.

No vector extension. `embedding_json` is a JSON-encoded list of floats and
`document_store.py` does the cosine similarity in Python. That's the right
trade for the scale this app runs at (dozens to low hundreds of documents
per company, not millions) — adding pgvector or a hosted vector DB before
the data volume needs it is a dependency this MVP doesn't need yet.
"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models import gen_id


class DocumentStatus(str, enum.Enum):
    PROCESSING = "processing"   # uploaded, text extraction / embedding still running
    READY = "ready"              # chunked and embedded, searchable
    FAILED = "failed"            # extraction or embedding failed — see error


class Document(Base):
    __tablename__ = "kb_documents"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    uploaded_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)

    title = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)   # "application/pdf", "text/plain", ...
    size_bytes = Column(Integer, default=0, nullable=False)

    # A short label so "ask the finance policy" resolves without a filename —
    # free text, not a fixed enum, because companies file things differently.
    category = Column(String, nullable=True)

    status = Column(Enum(DocumentStatus), default=DocumentStatus.PROCESSING, nullable=False, index=True)
    error = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0, nullable=False)
    char_count = Column(Integer, default=0, nullable=False)

    # True if at least one page had no text layer and was read back via OCR
    # instead — see document_store._extract_pdf. Surfaced in the UI so a
    # scanned contract that came back thin/garbled doesn't look like a
    # silent failure.
    ocr_used = Column(Boolean, default=False, nullable=False)

    # Cached output of contract_analysis.analyze() — a JSON blob, same
    # shape as ContractAnalysisResponse. Nullable: most documents (price
    # lists, handbooks) are never analyzed as contracts. Recomputed on
    # demand via POST /api/documents/{id}/contract-analysis?refresh=true,
    # otherwise served from here so re-opening a contract doesn't re-spend
    # a model call.
    contract_analysis_json = Column(Text, nullable=True)
    contract_analyzed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    processed_at = Column(DateTime, nullable=True)

    uploaded_by = relationship("User")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "kb_document_chunks"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    document_id = Column(String, ForeignKey("kb_documents.id"), nullable=False, index=True)

    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    # JSON-encoded list[float]. Nullable so a chunk can exist (and still be
    # keyword-searched) even when no OpenAI key is configured — see
    # document_store.embed_query() falling back to keyword search.
    embedding_json = Column(Text, nullable=True)

    document = relationship("Document", back_populates="chunks")
