from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.document_models import DocumentStatus


class DocumentOut(BaseModel):
    id: str
    title: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: int
    category: Optional[str] = None
    status: DocumentStatus
    error: Optional[str] = None
    chunk_count: int
    char_count: int
    ocr_used: bool = False
    uploaded_by_name: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None


class SourcePassage(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    chunk_index: int
    content: str
    score: float


class AskRequest(BaseModel):
    question: str
    document_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: Optional[str] = None
    sources: list[SourcePassage]
    mode: str
    error: Optional[str] = None


# --- Contract clause extraction ---
# A different shape of question than ask_documents: not "what does the
# contract say about X" but "read this whole contract and tell me what's in
# it, clause by clause, and what's conspicuously missing."

class ClauseOut(BaseModel):
    clause_type: str
    label: str
    title: Optional[str] = None
    excerpt: str
    plain_english: str
    risk_level: str  # "standard" | "attention" | "high_risk" | "unreviewed" (keyword fallback)
    chunk_id: Optional[str] = None


class MissingClauseType(BaseModel):
    clause_type: str
    label: str
    description: str


class ContractAnalysisResponse(BaseModel):
    document_id: str
    document_title: str
    mode: str  # "answered" | "keyword_fallback"
    truncated: bool
    clauses: list[ClauseOut]
    missing_clause_types: list[MissingClauseType]
    error: Optional[str] = None
    cached: bool = False
