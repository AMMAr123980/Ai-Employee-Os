"""
The model calls behind the voice features, routed through the unified LLM provider.

Supports Google Gemini, Groq, OpenAI, Anthropic, and smart local contextual fallback.
"""
import json
import logging
import re
from typing import Any, Optional

from app.config import settings
from app.llm_provider import complete_text, smart_contextual_fallback

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the model call fails or returns something unusable."""


def available() -> bool:
    """Voice features are always available via Gemini, Groq, OpenAI, Anthropic, or Smart Fallback."""
    return True


def plan_json(system_prompt: str, user_content: str, *, max_tokens: int = 1500) -> dict[str, Any]:
    """One structured JSON call."""
    prompt = f"{user_content}\n\nRespond with strictly valid JSON only."
    try:
        raw = complete_text(prompt=prompt, system_prompt=system_prompt)
    except Exception as exc:
        logger.warning("Voice LLM call error: %s, using fallback", exc)
        raw = smart_contextual_fallback(prompt=prompt, system_prompt=system_prompt)

    # Clean markdown code blocks if model wrapped json in ```json ... ```
    raw_cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw_cleaned = re.sub(r"\s*```$", "", raw_cleaned.strip())

    try:
        parsed = json.loads(raw_cleaned)
    except json.JSONDecodeError:
        # Try finding json bracket pattern
        match = re.search(r"(\{.*\})", raw_cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
            except Exception:
                parsed = None
        else:
            parsed = None

    if not isinstance(parsed, dict):
        # Graceful default JSON dict structure
        logger.warning("Voice planner output was non-JSON dict: %r", raw[:200])
        parsed = json.loads(smart_contextual_fallback(prompt=prompt, system_prompt=system_prompt))

    return parsed


def write_text(system_prompt: str, user_content: str, *, max_tokens: int = 800) -> str:
    """Generate prose text."""
    try:
        return complete_text(prompt=user_content, system_prompt=system_prompt)
    except Exception as exc:
        logger.warning("Voice text generation failed: %s, using fallback", exc)
        return smart_contextual_fallback(prompt=user_content, system_prompt=system_prompt)
