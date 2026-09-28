"""
Contract clause extraction — the piece the general `ask_documents` Q&A in
document_store.py deliberately doesn't do.

Asking "what's our termination notice period?" already works today through
plain retrieval-augmented search: embed the question, find the closest
chunks, hand them to the model. That's fine when you know what to ask. It's
the wrong tool when what you actually want is "read this whole contract and
tell me what's in it" — termination terms, liability caps, auto-renewal,
governing law, all the clauses a lawyer or ops person would scan for, found
and labelled without having to know the twelve questions to ask first, plus
which of the standard ones are conspicuously *absent*.

So this module is a second, contract-shaped read of the same chunks:

    chunks (already stored by document_store) -> whole-document text
        -> classify against a fixed clause taxonomy -> structured clauses
        -> diff against the taxonomy -> "missing" list

Same fallback philosophy as the rest of the knowledge base: with no OpenAI
key configured, a keyword pass over the chunks still finds candidate clauses
(worse — no risk assessment, no summarisation — but not nothing). `mode` on
the result says which path ran, exactly like `answer_question`'s `mode`.

Results are cached on Document.contract_analysis_json so reopening a
contract doesn't re-spend a model call; pass force=True to redo it (e.g.
after the document was re-uploaded, or to retry after a failed LLM call).
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.document_models import Document, DocumentChunk

logger = logging.getLogger(__name__)

# How much of the document to hand the model in one call. A 40-page contract
# is roughly 80-100k characters; this covers the large majority of real
# contracts in a single inline request without a background job. Longer
# documents are still analyzed, just truncated, and the response says so.
MAX_ANALYSIS_CHARS = 100_000


class ContractAnalysisError(Exception):
    """Raised for problems the caller can act on (no chunks yet, document
    not found). Message is shown as-is."""


@dataclass(frozen=True)
class ClauseType:
    id: str
    label: str
    # A few surface strings that tend to appear near this clause. Only used
    # by the no-API-key keyword fallback — the LLM path gets the label and
    # a one-line description instead, since it can reason past exact wording.
    keywords: tuple[str, ...]
    description: str


# The fixed taxonomy both extraction paths classify against. Deliberately a
# closed list rather than "whatever the model feels like calling things" —
# a closed list is what makes "missing clauses" a meaningful, stable signal
# instead of an artifact of how one run happened to phrase things.
STANDARD_CLAUSE_TYPES: list[ClauseType] = [
    ClauseType("termination", "Termination", ("terminat",),
               "How and when either party can end the agreement, and required notice."),
    ClauseType("auto_renewal", "Auto-Renewal", ("automatically renew", "auto-renew", "renewal term"),
               "Whether the contract renews on its own unless someone acts, and the opt-out deadline."),
    ClauseType("payment_terms", "Payment Terms", ("net 30", "net 15", "invoice", "payment shall", "due within"),
               "Price, invoicing cadence, due dates, and late-payment consequences."),
    ClauseType("limitation_of_liability", "Limitation of Liability",
               ("limitation of liability", "in no event shall", "liable for"),
               "Caps or exclusions on what either party can be made to pay if something goes wrong."),
    ClauseType("indemnification", "Indemnification", ("indemnif", "hold harmless"),
               "Who covers whose losses, fines, or legal costs arising from the deal."),
    ClauseType("confidentiality", "Confidentiality", ("confidential information", "non-disclosure"),
               "What counts as confidential, and obligations to protect it."),
    ClauseType("ip_ownership", "Intellectual Property / Ownership",
               ("intellectual property", "work product", "ownership of"),
               "Who owns what's created or shared under the agreement."),
    ClauseType("non_compete", "Non-Compete / Non-Solicit", ("non-compete", "non-solicit", "restraint of trade"),
               "Restrictions on competing or poaching staff/customers after the deal ends."),
    ClauseType("governing_law", "Governing Law & Jurisdiction", ("governing law", "jurisdiction", "venue"),
               "Which country/state's law applies and where disputes are heard."),
    ClauseType("warranties", "Warranties & Disclaimers", ("warrant", "as is", "disclaims all warranties"),
               "Promises made (or explicitly not made) about quality, fitness, or performance."),
    ClauseType("force_majeure", "Force Majeure", ("force majeure", "act of god"),
               "Excuses for non-performance due to events outside either party's control."),
    ClauseType("dispute_resolution", "Dispute Resolution / Arbitration",
               ("arbitration", "dispute resolution", "mediation"),
               "How disagreements get resolved — courts, arbitration, mediation, and in what order."),
    ClauseType("assignment", "Assignment", ("assign this agreement", "assignment of this"),
               "Whether either party can transfer the contract to someone else."),
    ClauseType("data_protection", "Data Protection / Privacy", ("personal data", "gdpr", "data protection"),
               "Handling of personal or regulated data, and applicable privacy law."),
]

_CLAUSE_TYPES_BY_ID = {c.id: c for c in STANDARD_CLAUSE_TYPES}
_VALID_RISK_LEVELS = {"standard", "attention", "high_risk"}

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
# Input assembly
# --------------------------------------------------------------------------

def _document_text(db: Session, company_id: str, document_id: str) -> tuple[Document, list[DocumentChunk], str, bool]:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.company_id == company_id)
        .first()
    )
    if not document:
        raise ContractAnalysisError("Document not found.")

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    if not chunks:
        raise ContractAnalysisError(
            "This document has no indexed text yet — wait for it to finish processing (or check "
            "its error) before analyzing it as a contract."
        )

    # Chunks overlap slightly at their boundaries (see document_store.chunk_text);
    # rejoining them duplicates a sentence or two here and there, which is a
    # non-issue for a model read and cheaper than storing the raw text twice.
    full_text = "\n\n".join(c.content for c in chunks)
    truncated = len(full_text) > MAX_ANALYSIS_CHARS
    if truncated:
        full_text = full_text[:MAX_ANALYSIS_CHARS]
    return document, chunks, full_text, truncated


def _find_chunk_id(chunks: list[DocumentChunk], excerpt: str) -> Optional[str]:
    """Best-effort attribution: which stored chunk does this excerpt most
    resemble? Not exact-match (the model paraphrases), so this checks a
    meaningful slice of the excerpt as a substring first, and falls back to
    the chunk with the most shared words. Good enough to jump to "roughly
    here" in the source document — not meant to be a precise citation."""
    if not excerpt:
        return None
    needle = excerpt.strip()[:80].lower()
    if len(needle) >= 20:
        for chunk in chunks:
            if needle in chunk.content.lower():
                return chunk.id

    excerpt_words = set(excerpt.lower().split())
    if not excerpt_words:
        return None
    best_chunk, best_overlap = None, 0
    for chunk in chunks:
        overlap = len(excerpt_words & set(chunk.content.lower().split()))
        if overlap > best_overlap:
            best_chunk, best_overlap = chunk, overlap
    return best_chunk.id if best_chunk and best_overlap >= 4 else None


# --------------------------------------------------------------------------
# Keyword fallback (no OpenAI key configured)
# --------------------------------------------------------------------------

def _keyword_fallback(chunks: list[DocumentChunk]) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for clause_type in STANDARD_CLAUSE_TYPES:
        hit = None
        for chunk in chunks:
            lowered = chunk.content.lower()
            if any(kw in lowered for kw in clause_type.keywords):
                hit = chunk
                break
        if hit is None:
            continue
        excerpt = hit.content.strip()
        clauses.append({
            "clause_type": clause_type.id,
            "label": clause_type.label,
            "excerpt": excerpt[:500] + ("…" if len(excerpt) > 500 else ""),
            "plain_english": (
                f"Contains language matching \"{clause_type.label}\" — review manually. "
                "No OpenAI key is configured, so this is a keyword match, not a read summary."
            ),
            "risk_level": "unreviewed",
            "chunk_id": hit.id,
        })
    return clauses


# --------------------------------------------------------------------------
# LLM extraction
# --------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are reviewing a contract for a small business's ops/legal team. Read the excerpt and "
    "find every clause that matches one of the clause types listed below. For each clause you find:\n"
    "- clause_type: the exact id from the list, or \"other\" for something notable that doesn't fit\n"
    "- title: a short human title for this specific clause (e.g. \"90-day auto-renewal\")\n"
    "- excerpt: the actual contract text for this clause, verbatim, trimmed to the relevant sentences "
    "(under ~120 words)\n"
    "- plain_english: one or two plain-English sentences on what it means in practice\n"
    "- risk_level: \"standard\" (ordinary/expected terms), \"attention\" (one-sided, unusual, or worth "
    "double-checking), or \"high_risk\" (clearly disadvantageous — e.g. uncapped liability, silent "
    "auto-renewal with a narrow opt-out window, unilateral termination)\n\n"
    "Only extract clauses that are actually present in the text — never invent one. If the same clause "
    "type appears more than once (e.g. two different notice periods), return each occurrence separately. "
    "Respond with ONLY a JSON object: {\"clauses\": [...]}. No prose outside the JSON."
)


def _build_user_prompt(full_text: str, truncated: bool) -> str:
    taxonomy = "\n".join(f"- {c.id}: {c.label} — {c.description}" for c in STANDARD_CLAUSE_TYPES)
    note = (
        "\n\n(This document was truncated to fit one review pass — treat this as the first "
        "portion of a longer contract.)" if truncated else ""
    )
    return f"Clause types to look for:\n{taxonomy}\n\nContract text:\n{full_text}{note}"


def _run_llm_extraction(full_text: str, truncated: bool) -> list[dict[str, Any]]:
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4000,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(full_text, truncated)},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    raw_clauses = parsed.get("clauses") if isinstance(parsed, dict) else None
    if not isinstance(raw_clauses, list):
        raise ContractAnalysisError("The model's answer wasn't the expected shape.")

    clauses: list[dict[str, Any]] = []
    for item in raw_clauses:
        if not isinstance(item, dict):
            continue
        clause_type_id = item.get("clause_type") or "other"
        if clause_type_id not in _CLAUSE_TYPES_BY_ID and clause_type_id != "other":
            clause_type_id = "other"
        label = (
            _CLAUSE_TYPES_BY_ID[clause_type_id].label
            if clause_type_id in _CLAUSE_TYPES_BY_ID
            else (item.get("title") or "Other").strip()
        )
        risk_level = item.get("risk_level") if item.get("risk_level") in _VALID_RISK_LEVELS else "standard"
        excerpt = (item.get("excerpt") or "").strip()
        if not excerpt:
            continue
        clauses.append({
            "clause_type": clause_type_id,
            "label": label,
            "title": (item.get("title") or label).strip(),
            "excerpt": excerpt,
            "plain_english": (item.get("plain_english") or "").strip(),
            "risk_level": risk_level,
            "chunk_id": None,  # filled in by the caller, which has the chunk list
        })
    return clauses


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def analyze(db: Session, company_id: str, document_id: str, *, force: bool = False) -> dict[str, Any]:
    """Runs (or returns the cached) contract clause analysis for a document.
    Shape matches ContractAnalysisResponse in document_schemas.py."""
    document, chunks, full_text, truncated = _document_text(db, company_id, document_id)

    if not force and document.contract_analysis_json:
        cached = json.loads(document.contract_analysis_json)
        cached["cached"] = True
        return cached

    client = _get_client()
    error: Optional[str] = None
    if client is None:
        clauses = _keyword_fallback(chunks)
        mode = "keyword_fallback"
    else:
        try:
            clauses = _run_llm_extraction(full_text, truncated)
            for clause in clauses:
                clause["chunk_id"] = _find_chunk_id(chunks, clause["excerpt"])
            mode = "answered"
        except Exception as exc:
            logger.warning("Contract clause extraction failed for %s, falling back to keywords: %s",
                            document_id, exc)
            clauses = _keyword_fallback(chunks)
            mode = "keyword_fallback"
            error = str(exc)[:500]

    found_types = {c["clause_type"] for c in clauses}
    missing_clause_types = [
        {"clause_type": c.id, "label": c.label, "description": c.description}
        for c in STANDARD_CLAUSE_TYPES
        if c.id not in found_types
    ]

    result = {
        "document_id": document.id,
        "document_title": document.title,
        "mode": mode,
        "truncated": truncated,
        "clauses": clauses,
        "missing_clause_types": missing_clause_types,
        "error": error,
        "cached": False,
    }

    document.contract_analysis_json = json.dumps({k: v for k, v in result.items() if k != "cached"})
    document.contract_analyzed_at = datetime.utcnow()
    db.commit()

    return result
