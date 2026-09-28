"""
Contract clause extraction: the keyword fallback (no OpenAI key), the LLM
path (mocked), missing-clause detection, and result caching on the Document
row. The LLM call itself is stubbed — what's under test is this module's
handling of the response, same spirit as test_voice_intent.py.
"""
import json

import pytest

from app import contract_analysis
from app.document_models import Document, DocumentChunk, DocumentStatus


@pytest.fixture()
def contract_document(db, company):
    document = Document(
        company_id=company.id,
        title="Vendor MSA",
        filename="vendor_msa.pdf",
        content_type="application/pdf",
        size_bytes=1234,
        status=DocumentStatus.READY,
        chunk_count=2,
        char_count=500,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    db.add_all([
        DocumentChunk(
            company_id=company.id, document_id=document.id, chunk_index=0,
            content=(
                "Either party may terminate this Agreement for convenience upon 30 days "
                "written notice to the other party."
            ),
        ),
        DocumentChunk(
            company_id=company.id, document_id=document.id, chunk_index=1,
            content=(
                "This Agreement shall automatically renew for successive one-year terms "
                "unless either party provides notice of non-renewal at least 60 days before "
                "the end of the then-current term."
            ),
        ),
    ])
    db.commit()
    return document


def test_analysis_without_a_document_raises(db, company):
    with pytest.raises(contract_analysis.ContractAnalysisError):
        contract_analysis.analyze(db, company.id, "does-not-exist")


def test_analysis_of_an_unprocessed_document_raises(db, company):
    document = Document(
        company_id=company.id, title="Empty", filename="x.pdf",
        status=DocumentStatus.PROCESSING,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    with pytest.raises(contract_analysis.ContractAnalysisError, match="no indexed text"):
        contract_analysis.analyze(db, company.id, document.id)


def test_keyword_fallback_finds_clauses_without_an_openai_key(db, company, contract_document):
    # conftest sets OPENAI_API_KEY="" for the whole test session.
    result = contract_analysis.analyze(db, company.id, contract_document.id)

    assert result["mode"] == "keyword_fallback"
    types_found = {c["clause_type"] for c in result["clauses"]}
    assert "termination" in types_found
    assert "auto_renewal" in types_found
    assert all(c["risk_level"] == "unreviewed" for c in result["clauses"])
    # Clause types with no keyword hit at all (e.g. force_majeure) are absent
    # from the document and should show up as missing.
    missing_types = {m["clause_type"] for m in result["missing_clause_types"]}
    assert "force_majeure" in missing_types
    assert "termination" not in missing_types


def test_result_is_cached_on_the_document_row(db, company, contract_document):
    contract_analysis.analyze(db, company.id, contract_document.id)
    db.refresh(contract_document)

    assert contract_document.contract_analysis_json is not None
    assert contract_document.contract_analyzed_at is not None

    cached = json.loads(contract_document.contract_analysis_json)
    assert cached["document_id"] == contract_document.id


def test_second_call_returns_cached_result_without_recomputing(db, company, contract_document, monkeypatch):
    contract_analysis.analyze(db, company.id, contract_document.id)

    monkeypatch.setattr(
        contract_analysis, "_keyword_fallback",
        lambda chunks: (_ for _ in ()).throw(AssertionError("should not recompute")),
    )
    result = contract_analysis.analyze(db, company.id, contract_document.id)
    assert result["cached"] is True


def test_force_refresh_recomputes(db, company, contract_document):
    first = contract_analysis.analyze(db, company.id, contract_document.id)
    assert first["cached"] is False

    second = contract_analysis.analyze(db, company.id, contract_document.id, force=True)
    assert second["cached"] is False


def test_llm_path_parses_structured_clauses_and_flags_risk(db, company, contract_document, monkeypatch):
    fake_clauses = [
        {
            "clause_type": "termination",
            "label": "Termination",
            "title": "30-day termination for convenience",
            "excerpt": "Either party may terminate this Agreement for convenience upon 30 days written notice.",
            "plain_english": "Either side can walk away with a month's notice, no reason needed.",
            "risk_level": "standard",
            "chunk_id": None,
        },
        {
            "clause_type": "auto_renewal",
            "label": "Auto-Renewal",
            "title": "Auto-renews yearly with a narrow opt-out window",
            "excerpt": "This Agreement shall automatically renew for successive one-year terms unless notice is given 60 days prior.",
            "plain_english": "You're locked in for another year unless you cancel 60 days ahead of time.",
            "risk_level": "attention",
            "chunk_id": None,
        },
    ]
    monkeypatch.setattr(contract_analysis, "_get_client", lambda: object())
    monkeypatch.setattr(contract_analysis, "_run_llm_extraction", lambda text, truncated: fake_clauses)

    result = contract_analysis.analyze(db, company.id, contract_document.id)

    assert result["mode"] == "answered"
    assert len(result["clauses"]) == 2
    risk_by_type = {c["clause_type"]: c["risk_level"] for c in result["clauses"]}
    assert risk_by_type["auto_renewal"] == "attention"
    # Best-effort chunk attribution should find the matching source chunk.
    termination_clause = next(c for c in result["clauses"] if c["clause_type"] == "termination")
    assert termination_clause["chunk_id"] is not None


def test_llm_failure_falls_back_to_keywords_instead_of_erroring(db, company, contract_document, monkeypatch):
    monkeypatch.setattr(contract_analysis, "_get_client", lambda: object())

    def _boom(*args, **kwargs):
        raise RuntimeError("model call failed")

    monkeypatch.setattr(contract_analysis, "_run_llm_extraction", _boom)

    result = contract_analysis.analyze(db, company.id, contract_document.id)
    assert result["mode"] == "keyword_fallback"
    assert result["error"] is not None
    assert len(result["clauses"]) > 0
