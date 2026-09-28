"""
AI Email Assistant — the "draft emails / summarize / classify" features from the
product spec's Email Assistant module. Sending itself lives in email_sender.py;
this module is purely the OpenAI-backed language logic.
"""
import json
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


def _fallback_draft(customer_name: str, context: str, instructions: Optional[str]) -> dict:
    subject = "Following up"
    body = (
        f"Hi {customer_name},\n\n"
        f"{context}\n\n"
        f"{instructions or ''}\n\n"
        f"Best regards,\n{settings.company_name}"
    ).strip()
    return {"subject": subject, "body": body}


DRAFT_EMAIL_SYSTEM_PROMPT = """You are the AI Email Assistant inside a business operations \
tool. Given context about a customer and (optionally) a quotation or invoice, write a short, \
professional, friendly business email. Respond with ONLY a JSON object matching exactly:

{"subject": "string", "body": "string"}

Rules:
- body should read like a real email: greeting, 2-4 short sentences, sign-off with the \
sender's company name.
- Do not invent numbers, prices, or dates that weren't given in the context.
- Keep it concise — this is a business email, not a newsletter.
"""


def draft_email(
    *,
    customer_name: str,
    company_name: str,
    context: str,
    instructions: Optional[str] = None,
) -> dict:
    """Returns {"subject": ..., "body": ...}. Falls back to a templated email if no
    API key is configured or the call fails, so sending still works either way."""
    client = _get_client()
    if client is None:
        return _fallback_draft(customer_name, context, instructions)

    user_prompt = (
        f"Sender company: {company_name}\n"
        f"Recipient: {customer_name}\n"
        f"Context: {context}\n"
        f"Extra instructions from the sender: {instructions or 'none'}"
    )
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=600,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": DRAFT_EMAIL_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        subject = str(data.get("subject", "")).strip()
        body = str(data.get("body", "")).strip()
        if not subject or not body:
            raise ValueError("empty subject/body")
        return {"subject": subject, "body": body}
    except (OpenAIError, json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("AI draft_email fell back to template: %s", exc)
        return _fallback_draft(customer_name, context, instructions)


FOLLOWUP_SYSTEM_PROMPT = """You are the AI Email Assistant inside a business operations \
tool. The sender emailed a customer and hasn't heard back after several days. Write a \
short, polite, low-pressure follow-up email referencing the original message. Respond \
with ONLY a JSON object matching exactly:

{"subject": "string", "body": "string"}

Rules:
- Keep it brief — 2-4 sentences. Assume the customer is busy, not uninterested.
- Reference the original subject/topic naturally, don't just repeat it verbatim.
- Do not invent new offers, numbers, or deadlines not in the original context.
- Sign off with the sender's company name.
"""


def _fallback_followup(customer_name: str, original_subject: str, days_since: int) -> dict:
    subject = f"Following up: {original_subject}"
    body = (
        f"Hi {customer_name},\n\n"
        f"Just following up on my email from {days_since} day(s) ago"
        f"{' (' + original_subject + ')' if original_subject else ''} — "
        f"wanted to check if you had any questions or thoughts.\n\n"
        f"Best regards,\n{settings.company_name}"
    ).strip()
    return {"subject": subject, "body": body}


def draft_followup_email(
    *,
    customer_name: str,
    company_name: str,
    original_subject: str,
    original_body: str,
    days_since: int,
) -> dict:
    """Returns {"subject": ..., "body": ...} for a nudge follow-up email. Falls back
    to a simple template if no API key is configured or the call fails."""
    client = _get_client()
    if client is None:
        return _fallback_followup(customer_name, original_subject, days_since)

    user_prompt = (
        f"Sender company: {company_name}\n"
        f"Recipient: {customer_name}\n"
        f"Original email sent {days_since} day(s) ago.\n"
        f"Original subject: {original_subject}\n"
        f"Original body:\n{original_body[:1000]}"
    )
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=400,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": FOLLOWUP_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        subject = str(data.get("subject", "")).strip()
        body = str(data.get("body", "")).strip()
        if not subject or not body:
            raise ValueError("empty subject/body")
        return {"subject": subject, "body": body}
    except (OpenAIError, json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("AI draft_followup_email fell back to template: %s", exc)
        return _fallback_followup(customer_name, original_subject, days_since)


SUMMARIZE_SYSTEM_PROMPT = """You summarize email threads for a busy business user. Respond \
with ONLY a JSON object matching exactly:

{"summary": "string", "action_items": ["string", ...]}

summary: 2-3 sentences capturing what the thread is about and where it stands.
action_items: concrete next steps implied by the thread (empty list if none).
"""


def summarize_thread(text: str) -> dict:
    client = _get_client()
    if client is None:
        return {"summary": text[:280] + ("…" if len(text) > 280 else ""), "action_items": []}

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=500,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return {
            "summary": str(data.get("summary", "")).strip() or "No summary available.",
            "action_items": [str(a) for a in data.get("action_items", [])],
        }
    except (OpenAIError, json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("AI summarize_thread fell back to truncation: %s", exc)
        return {"summary": text[:280] + ("…" if len(text) > 280 else ""), "action_items": []}


CLASSIFY_SYSTEM_PROMPT = """You triage inbound business emails. Respond with ONLY a JSON \
object matching exactly:

{"category": "sales|support|billing|complaint|spam|other", "priority": \
"low|normal|high|urgent", "reasoning": "string"}

reasoning: one short sentence explaining the classification.
"""


def classify_email(text: str) -> dict:
    client = _get_client()
    if client is None:
        return {"category": "other", "priority": "normal", "reasoning": "AI classification unavailable (no API key configured)."}

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        category = str(data.get("category", "other")).strip().lower()
        priority = str(data.get("priority", "normal")).strip().lower()
        if category not in {"sales", "support", "billing", "complaint", "spam", "other"}:
            category = "other"
        if priority not in {"low", "normal", "high", "urgent"}:
            priority = "normal"
        return {
            "category": category,
            "priority": priority,
            "reasoning": str(data.get("reasoning", "")).strip(),
        }
    except (OpenAIError, json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("AI classify_email fell back to default: %s", exc)
        return {"category": "other", "priority": "normal", "reasoning": "Classification failed; defaulted."}
