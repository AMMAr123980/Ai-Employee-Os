"""
AI CRM Assistant — the "AI customer summaries / relationship insights" feature from
the product spec's AI CRM module. Looks at a customer's quotations, invoices, and
activity log and produces a short human-readable relationship summary.
"""
import logging
from typing import Optional

from openai import OpenAI, OpenAIError

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> Optional[OpenAI]:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _fallback_summary(stats: dict) -> str:
    parts = [
        f"{stats['quotation_count']} quotation(s)",
        f"{stats['invoice_count']} invoice(s)",
        f"{stats['paid_invoice_count']} paid",
    ]
    if stats["outstanding_total"] > 0:
        parts.append(f"{stats['currency']} {stats['outstanding_total']:,.2f} outstanding")
    if stats["email_count"] > 0:
        parts.append(f"{stats['email_count']} email(s) sent")
    return "Relationship snapshot: " + ", ".join(parts) + "."


SUMMARY_SYSTEM_PROMPT = """You write short relationship-insight summaries for a sales/ops \
tool. Given structured facts about a customer's quotations, invoices, and communication \
history, write a 2-4 sentence summary a salesperson could read in 5 seconds before a call. \
Mention: overall relationship health, payment behavior if relevant, and anything notable \
(frequent discount requests, slow replies, high value, etc.) — but ONLY based on the facts \
given, never invent numbers or events not present in the input. Output plain text only, no \
markdown, no headers."""


def generate_customer_summary(*, customer_name: str, stats: dict, recent_activity: str) -> dict:
    """stats is a dict of counts/totals; recent_activity is a short text digest of
    recent notes/emails. Returns {"summary": str}. Falls back to a factual one-liner
    built directly from stats if no API key is configured or the call fails."""
    client = _get_client()
    if client is None:
        return {"summary": _fallback_summary(stats)}

    facts = (
        f"Customer: {customer_name}\n"
        f"Quotations sent: {stats['quotation_count']}\n"
        f"Invoices issued: {stats['invoice_count']} ({stats['paid_invoice_count']} paid)\n"
        f"Outstanding balance: {stats['currency']} {stats['outstanding_total']:,.2f}\n"
        f"Emails sent to this customer: {stats['email_count']}\n"
        f"Current pipeline stage: {stats['pipeline_stage']}\n"
        f"Recent activity:\n{recent_activity or 'none recorded'}"
    )
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=250,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": facts},
            ],
        )
        summary = (resp.choices[0].message.content or "").strip()
        if not summary:
            raise ValueError("empty summary")
        return {"summary": summary}
    except (OpenAIError, ValueError) as exc:
        logger.warning("AI generate_customer_summary fell back to factual snapshot: %s", exc)
        return {"summary": _fallback_summary(stats)}
