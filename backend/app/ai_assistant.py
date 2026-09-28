"""
AI Quotation/Invoice Assistant.

Uses unified llm_provider for Gemini, Groq, OpenAI, Anthropic, and smart contextual fallback.
"""
import json
import logging
import re
from typing import List, Optional

from app.config import settings
from app.llm_provider import complete_text

logger = logging.getLogger(__name__)


DRAFT_ITEMS_SYSTEM_PROMPT = """You are the line-item drafting engine inside a business \
quotation tool. Given a plain-English request, respond with ONLY a JSON object matching \
this exact shape:

{"items": [{"description": "string", "quantity": number, "unit_price": number}], \
"suggested_notes": "string or null"}

Rules:
- Infer reasonable unit prices only if the user gives a hint; otherwise use 0 and let the \
human fill it in.
- Keep descriptions concise and professional (suitable for a client-facing PDF).
- suggested_notes is a single short sentence for the quotation notes field, or null.
"""


def draft_items_from_prompt(prompt: str) -> dict:
    """Returns a dict shaped like AIDraftItemsResponse."""
    try:
        text = complete_text(
            prompt=f"{prompt}\n\nRespond with strictly valid JSON only.",
            system_prompt=DRAFT_ITEMS_SYSTEM_PROMPT
        )
        text_cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        text_cleaned = re.sub(r"\s*```$", "", text_cleaned.strip())
        data = json.loads(text_cleaned)
        items = data.get("items") or []
        cleaned = [
            {
                "description": str(it.get("description", "")).strip() or "Item",
                "quantity": float(it.get("quantity", 1) or 1),
                "unit_price": float(it.get("unit_price", 0) or 0),
            }
            for it in items
        ]
        if not cleaned:
            raise ValueError("empty items")
        return {"items": cleaned, "suggested_notes": data.get("suggested_notes")}
    except Exception as exc:
        logger.warning("AI draft_items_from_prompt fell back to manual entry: %s", exc)
        return {
            "items": [{"description": prompt.strip()[:200], "quantity": 1, "unit_price": 0}],
            "suggested_notes": None,
        }


def summarize_quotation(customer_name: str, items: List[dict], total: float, currency: str) -> Optional[str]:
    """Short cover-note summary shown at the top of the quotation PDF."""
    item_lines = "\n".join(f"- {i['description']} x{i['quantity']}" for i in items)
    prompt = (
        f"Write a 1-2 sentence professional, friendly cover note for a quotation sent to "
        f"{customer_name}. Total: {currency} {total:,.2f}. Items:\n{item_lines}\n"
        "Output only the note text, no greeting/signature."
    )
    try:
        return complete_text(prompt=prompt).strip()
    except Exception as exc:
        logger.warning("AI summarize_quotation failed: %s", exc)
        return f"Thank you for requesting a quotation from {settings.company_name}. We look forward to serving you."
