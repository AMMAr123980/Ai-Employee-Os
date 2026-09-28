"""
Company Knowledge Base API.

Upload a policy, price list, contract template or handbook; ask questions
against it later. This is the document store VOICE_AND_MEETINGS.md said
didn't exist yet — building it is what turns on the `ask_documents` voice
intent in voice_actions.py.

Small files are chunked and embedded inline, before the response is sent, so
"upload then immediately ask" works without a poll. Larger files fall back to
a background task, same shape as the meeting pipeline, with `status` on the
row as the progress indicator.

Two ways to get answers out of what's uploaded: `/ask` for a free-text
question over one or all documents (document_store.py), and
`/{id}/contract-analysis` for a structured, clause-by-clause read of one
document as a contract (contract_analysis.py) — termination, liability,
auto-renewal and the rest, plus which of those are conspicuously absent.
"""
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app import contract_analysis, document_schemas as schemas
from app import document_store, models
from app.auth import get_current_user
from app.database import get_db
from app.document_models import Document, DocumentStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["knowledge-base"])

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024  # 25 MB — generous for policies/contracts, not a video store


def _out(db: Session, document: Document) -> schemas.DocumentOut:
    uploader = db.get(models.User, document.uploaded_by_user_id) if document.uploaded_by_user_id else None
    return schemas.DocumentOut(
        id=document.id,
        title=document.title,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        category=document.category,
        status=document.status,
        error=document.error,
        chunk_count=document.chunk_count,
        char_count=document.char_count,
        ocr_used=document.ocr_used,
        uploaded_by_name=uploader.name if uploader else None,
        created_at=document.created_at,
        processed_at=document.processed_at,
    )


def _owned(db: Session, company_id: str, document_id: str) -> Document:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.company_id == company_id)
        .first()
    )
    if not document:
        raise HTTPException(404, "Document not found")
    return document


def _process_in_background(document_id: str, text: str) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document:
            document_store.process_document(db, document, text)
    finally:
        db.close()


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(Document).filter(Document.company_id == current_user.company_id)
    if category:
        query = query.filter(Document.category == category)
    rows = query.order_by(Document.created_at.desc()).limit(300).all()
    return [_out(db, d) for d in rows]


@router.post("", response_model=schemas.DocumentOut)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    category: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = await file.read()
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(413, f"File too large — the limit is {MAX_DOCUMENT_BYTES // (1024*1024)} MB.")

    try:
        text, ocr_used = document_store.extract_text(file.filename or "upload", file.content_type, data)
    except document_store.DocumentStoreError as exc:
        raise HTTPException(400, str(exc)) from exc

    document = Document(
        company_id=current_user.company_id,
        uploaded_by_user_id=current_user.id,
        title=(title or file.filename or "Untitled document").strip(),
        filename=file.filename or "upload",
        content_type=file.content_type,
        size_bytes=len(data),
        category=category,
        status=DocumentStatus.PROCESSING,
        ocr_used=ocr_used,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    if len(text) <= document_store.EMBED_INLINE_MAX_CHARS:
        document_store.process_document(db, document, text)
        db.refresh(document)
    else:
        background_tasks.add_task(_process_in_background, document.id, text)

    return _out(db, document)


@router.get("/{document_id}", response_model=schemas.DocumentOut)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _out(db, _owned(db, current_user.company_id, document_id))


@router.patch("/{document_id}", response_model=schemas.DocumentOut)
def update_document(
    document_id: str,
    payload: schemas.DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    document = _owned(db, current_user.company_id, document_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    db.commit()
    db.refresh(document)
    return _out(db, document)


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    document = _owned(db, current_user.company_id, document_id)
    db.delete(document)  # cascades to chunks
    db.commit()
    return {"ok": True}


@router.post("/ask", response_model=schemas.AskResponse)
def ask_documents(
    payload: schemas.AskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if payload.document_id:
        _owned(db, current_user.company_id, payload.document_id)  # 404s if not this company's
    if not payload.question.strip():
        raise HTTPException(400, "Ask something.")

    result = document_store.answer_question(
        db, current_user.company_id, payload.question, document_id=payload.document_id
    )
    return schemas.AskResponse(**result)


@router.post("/{document_id}/contract-analysis", response_model=schemas.ContractAnalysisResponse)
def analyze_contract(
    document_id: str,
    refresh: bool = Query(False, description="Re-run the analysis instead of using the cached result."),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Reads a document as a contract: finds and labels clauses against a
    fixed taxonomy (termination, liability, auto-renewal, ...) and reports
    which of those are missing — a different job from `/ask`, which only
    answers free-text questions against whatever it happens to retrieve."""
    _owned(db, current_user.company_id, document_id)  # 404s if not this company's
    try:
        result = contract_analysis.analyze(db, current_user.company_id, document_id, force=refresh)
    except contract_analysis.ContractAnalysisError as exc:
        raise HTTPException(400, str(exc)) from exc
    return schemas.ContractAnalysisResponse(**result)


@router.get("/{document_id}/contract-analysis", response_model=schemas.ContractAnalysisResponse)
def get_contract_analysis(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Convenience read-only fetch of the cached analysis, if any has been
    run — lets the UI show a previous result without triggering a new one."""
    document = _owned(db, current_user.company_id, document_id)
    if not document.contract_analysis_json:
        raise HTTPException(404, "This document hasn't been analyzed as a contract yet.")
    cached = json.loads(document.contract_analysis_json)
    cached["cached"] = True
    return schemas.ContractAnalysisResponse(**cached)
