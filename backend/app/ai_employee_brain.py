"""
Turns a plain-language brief into a structured action for one employee.

Runs on the same OpenAI client the rest of this codebase uses
(`ai_assistant.py`, `crm_assistant.py`, `email_assistant.py`) — one API key,
one model setting, one place to swap providers. The module-level `_client`
with a lazy `_get_client()` is copied from those files deliberately rather
than reinvented.

Three functions, and the split between them is the design:

- `plan()` — classification and slot extraction. JSON mode, strict shape,
  no prose. Runs on every brief.
- `write()` — long-form generation: job descriptions, contract drafts,
  campaign copy, support replies. Prose out, no JSON.
- `review_json()` — structured findings: clause risk, expense categories,
  message triage. A JSON array out.

Keeping them apart matters. A single call that both decides what to do and
writes 800 words of contract does neither well, and it makes the action
registry impossible to test. `plan()` is cheap and runs constantly; `write()`
is expensive and only runs after an intent is settled.

**No API key configured** is a first-class case, not a crash. `plan()` falls
back to keyword matching against the employee's own intent list — enough to
demo the routing, the confirmation gate and every non-AI action (stock
movements, POs, leave, expenses, all the reports) with `OPENAI_API_KEY`
empty. Only the text-generating actions genuinely need the key, and they say
so plainly when it's missing.

What is NOT sent to the model: `_redact()` strips salary figures and
credential-shaped keys from every context dict before it goes into a prompt.
The HR employee can tell you who's on probation without knowing what anyone
earns, and it should stay that way.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from openai import OpenAI, OpenAIError

from app.config import settings
from app.ai_employee_registry import INTENT_SLOTS, get_employee

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None

_SENSITIVE_KEY = re.compile(
    r"salary|wage|payroll|compensation|password|token|api_key|secret|cnic|ssn|iban|card_number",
    re.IGNORECASE,
)


def _get_client() -> Optional[OpenAI]:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


class EmployeeBrainError(Exception):
    """The model call failed or came back unusable. The router turns this
    into a FAILED run whose `error` is shown to the user, so keep messages
    short and tell them what to do about it."""


@dataclass
class EmployeePlan:
    intent: str
    confidence: float
    config: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    missing_info: list[str] = field(default_factory=list)


_PLAN_SYSTEM = """{persona}

You convert a typed instruction into JSON. Respond with ONLY a JSON object.

Today's date is {today}.

The ONLY actions you can take are these. Pick exactly one:
{catalog}

Rules:
- If the instruction doesn't match any action above, use "unclear". Do not stretch \
a request to fit — a different colleague handles work outside this list, and guessing \
wrong is worse than saying so.
- Fill every slot you can infer. Leave a slot out of "config" entirely if it wasn't \
stated or clearly implied. Never invent names, dates, quantities or amounts.
- Resolve relative dates ("next Tuesday", "end of the month") against today's date and \
output ISO 8601 (YYYY-MM-DD). If a date is genuinely ambiguous, omit it.
- "confidence" is your own 0.0-1.0 estimate that both the action and the slots are right.
- "summary" is one accurate sentence describing exactly what will happen if this runs. \
It is shown to a human for approval, so it must mention every value that will be \
written — names, amounts, dates.
- "missing_info" lists required slot names (those NOT marked optional) that the \
instruction didn't supply.

Respond with exactly this shape:
{{"intent": "<one of the actions above>", "confidence": <0.0-1.0>, \
"config": {{...slots...}}, "summary": "<one sentence>", "missing_info": [...]}}
"""


def _redact(context: dict[str, Any]) -> dict[str, Any]:
    """Drop anything that looks like pay or a credential before it reaches
    the model. Recursive, and applied to every context dict — it's cheap, and
    the alternative is remembering to do it at a dozen call sites."""
    clean: dict[str, Any] = {}
    for key, value in context.items():
        if _SENSITIVE_KEY.search(str(key)):
            continue
        if isinstance(value, dict):
            clean[key] = _redact(value)
        elif isinstance(value, list):
            clean[key] = [_redact(v) if isinstance(v, dict) else v for v in value]
        else:
            clean[key] = value
    return clean


def _catalog_for_prompt(employee_key: str) -> str:
    return "\n".join(
        f"- {intent}: slots = {INTENT_SLOTS.get(intent, [])}"
        for intent in get_employee(employee_key)["intents"]
    )


def _chat(system: str, user: str, *, max_tokens: int, json_mode: bool) -> str:
    from app.llm_provider import complete_text, smart_contextual_fallback

    prompt = f"{user}\n\nRespond with strictly valid JSON only." if json_mode else user
    try:
        raw = complete_text(prompt=prompt, system_prompt=system)
        raw_cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw_cleaned = re.sub(r"\s*```$", "", raw_cleaned.strip())
        return raw_cleaned
    except Exception as exc:
        logger.exception("AI employee model call failed")
        return smart_contextual_fallback(prompt=prompt, system_prompt=system)


def _keyword_fallback(employee_key: str, brief: str) -> EmployeePlan:
    """Used when there's no API key. Scores each of this employee's intents
    by how many of its own name-words appear in the brief. Crude on purpose:
    it exists so the app is demonstrable without a key, not to be clever.
    Confidence is capped low and no slots are filled, so anything it picks
    lands in the confirmation gate rather than running."""
    text = brief.lower()
    best, best_score = "unclear", 0
    for intent in get_employee(employee_key)["intents"]:
        words = [w for w in intent.split("_") if len(w) > 3]
        score = sum(1 for w in words if w in text)
        if score > best_score:
            best, best_score = intent, score
    if best_score == 0:
        return EmployeePlan(
            intent="unclear", confidence=0.0,
            summary="No AI key configured, and the instruction didn't obviously match an action.",
        )
    return EmployeePlan(
        intent=best, confidence=0.3, config={},
        summary=f"Best guess without an AI key: {best.replace('_', ' ')}. "
                f"Fill in the details before confirming.",
    )


def plan(
    employee_key: str,
    brief: str,
    *,
    context: dict[str, Any] | None = None,
    extra_instructions: str | None = None,
) -> EmployeePlan:
    """`context` is whatever the router looked up that might help slot
    filling — existing supplier names, stock item names, open PO numbers.
    Supplying it is what turns "raise a PO to Zenith" into a match against
    the supplier that exists, rather than a string the action layer then has
    to guess at."""
    employee = get_employee(employee_key)

    has_llm = bool(settings.openai_api_key or settings.gemini_api_key or getattr(settings, "groq_api_key", "") or settings.anthropic_api_key)
    if not has_llm:
        return _keyword_fallback(employee_key, brief)

    persona = employee["system_prompt"]
    if extra_instructions:
        # AIEmployeeConfig.instructions — company context like "our week runs
        # Sunday to Thursday" or "always quote in PKR".
        persona = f"{persona}\n\nCompany-specific context: {extra_instructions.strip()}"

    system = _PLAN_SYSTEM.format(
        persona=persona,
        today=date.today().isoformat(),
        catalog=_catalog_for_prompt(employee_key),
    )

    user = brief
    if context:
        user = (
            f"{brief}\n\n---\nExisting records you may match against (use exact names "
            f"from here where they clearly correspond):\n"
            f"{json.dumps(_redact(context), default=str)[:4000]}"
        )

    raw = _chat(system, user, max_tokens=800, json_mode=True)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("AI employee planner returned non-JSON: %r", raw[:500])
        raise EmployeeBrainError("Couldn't work out what to do with that — try rephrasing it.") from exc

    intent = parsed.get("intent", "unclear")
    if intent not in employee["intents"]:
        # Covers both "unclear" and an intent hallucinated from another
        # department. Either way this employee doesn't run it.
        intent = "unclear"

    return EmployeePlan(
        intent=intent,
        confidence=float(parsed.get("confidence", 0.0) or 0.0),
        config=parsed.get("config", {}) or {},
        summary=parsed.get("summary", ""),
        missing_info=parsed.get("missing_info", []) or [],
    )


def write(
    employee_key: str,
    task: str,
    *,
    context: dict[str, Any] | None = None,
    max_tokens: int = 2000,
    extra_instructions: str | None = None,
) -> str:
    """Long-form text: a JD, a contract body, campaign copy, a support reply.

    Everything this returns is a draft. Every caller writes it to a
    DRAFT-status row or returns it for display — none of them send it.
    Sending is always a separate, separately-confirmed intent.
    """
    system = get_employee(employee_key)["system_prompt"]
    if extra_instructions:
        system = f"{system}\n\nCompany-specific context: {extra_instructions.strip()}"
    system += (
        "\n\nWrite the requested document directly. No preamble, no 'here is', no "
        "closing offer to revise. Use [SQUARE BRACKETS] for any detail you weren't "
        "given rather than inventing a plausible-looking value."
    )

    user = task
    if context:
        user = f"{task}\n\n---\nContext:\n{json.dumps(_redact(context), default=str)[:6000]}"

    text = _chat(system, user, max_tokens=max_tokens, json_mode=False)
    if not text:
        raise EmployeeBrainError("The draft came back empty — try again with a bit more detail.")
    return text


def review_json(
    employee_key: str,
    task: str,
    *,
    context: dict[str, Any] | None = None,
    max_tokens: int = 2000,
) -> list[dict[str, Any]]:
    """Structured findings — clause review, expense categorisation, triage.

    Returns a list. An unparseable response raises rather than returning [],
    because "no risks found" and "the model broke" must not look the same to
    the person reading the result.

    JSON mode guarantees an object, not an array, so the prompt asks for
    {"items": [...]} and this unwraps it — the alternative is fighting the
    API's own contract.
    """
    system = (
        f"{get_employee(employee_key)['system_prompt']}\n\n"
        'Respond with ONLY a JSON object of the form {"items": [ ... ]}.'
    )
    user = task
    if context:
        user = f"{task}\n\n---\nContext:\n{json.dumps(_redact(context), default=str)[:12000]}"

    raw = _chat(system, user, max_tokens=max_tokens, json_mode=True)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Structured review returned non-JSON: %r", raw[:500])
        raise EmployeeBrainError("The review came back in an unreadable format — try again.") from exc

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value
    raise EmployeeBrainError("The review came back in an unexpected shape — try again.")
