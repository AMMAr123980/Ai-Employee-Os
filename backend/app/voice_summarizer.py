"""
The long-form model calls, kept apart from the planner.

Same split `ai_employee_brain` makes between plan() and write(), for the same
reason: a call that both decides what to do and writes 400 words does neither
well. voice_intent classifies; this module reads and writes prose.

Two consumers:

- `summarize_email_activity()` — the AI Email Assistant asked by voice. This
  app logs outbound mail, so the honest framing is "what you've sent and what
  hasn't come back", not "your inbox". The prompt says so explicitly, because a
  model handed a list of sent emails will otherwise write as though it read the
  replies.
- `summarize_meeting()` — summary, decisions, action items with owners and
  dates, deadlines, open questions.

Both take a `locale` and write their prose in it, for the same reason
voice_i18n exists: an Urdu meeting shouldn't produce an English summary.
"""
import logging
from typing import Any, Optional

from app import voice_i18n, voice_llm

logger = logging.getLogger(__name__)

SummarizerError = voice_llm.LLMError


def _language_line(locale: str) -> str:
    locale = voice_i18n.normalize_locale(locale)
    if locale == voice_i18n.DEFAULT_LOCALE:
        return ""
    name = voice_i18n.LANGUAGE_NAMES.get(locale, locale)
    return f"\nWrite all prose in {name}. Keep names, numbers and reference codes exactly as they are."


_EMAIL_SYSTEM = """You summarise a business's recent OUTBOUND email activity. Output ONLY a JSON object.

These are emails the company SENT. You cannot see replies — do not write as though you can. \
A message flagged awaiting_followup is one where no reply has been recorded yet.

Rules:
- Group by what the reader must DO next, not by recipient.
- "needs_chasing" is for messages that have gone quiet and matter (quotations, invoices, \
anything with money attached). Be strict: if everything is urgent, nothing is.
- Never invent a recipient, subject or amount that isn't in the input.
- Keep each item to one line.{language}

Shape:
{{"summary": "<2-3 sentences>", \
"needs_chasing": [{{"customer": "...", "subject": "...", "why": "..."}}], \
"failed": [{{"customer": "...", "subject": "...", "why": "..."}}], \
"fyi": ["..."]}}
"""


def summarize_email_activity(messages: list[dict[str, Any]], *, locale: str = "en") -> dict[str, Any]:
    import json

    system = _EMAIL_SYSTEM.format(language=_language_line(locale))
    user = json.dumps(messages, ensure_ascii=False)[:60_000]
    return voice_llm.plan_json(system, user, max_tokens=1200)


_MEETING_SYSTEM = """You write up a meeting from its transcript. Output ONLY a JSON object.

Today's date is {today}.

Rules:
- "summary": what was discussed and concluded, in 4-8 sentences. Neutral, no filler.
- "decisions": only things actually decided. An argument with no conclusion is not a decision.
- "action_items": each needs an owner and, where one was stated or clearly implied, a due date \
resolved to ISO (YYYY-MM-DD) against today's date. Use the speaker label from the transcript if \
no name was said, and "unassigned" if nobody took it. Omit the date rather than guessing it.
- "deadlines": dates mentioned that constrain the business (delivery, renewal, payment), \
separate from action items.
- "open_questions": things raised and left unresolved.
- Never invent an owner, a date or a commitment.{language}

Shape:
{{"summary": "...", "decisions": ["..."], \
"action_items": [{{"owner": "...", "title": "...", "due_date": "YYYY-MM-DD or null"}}], \
"deadlines": [{{"what": "...", "date": "YYYY-MM-DD"}}], "open_questions": ["..."]}}
"""


def summarize_meeting(transcript: str, *, today: str, locale: str = "en",
                      title: Optional[str] = None) -> dict[str, Any]:
    system = _MEETING_SYSTEM.format(today=today, language=_language_line(locale))
    header = f"Meeting title: {title}\n\n" if title else ""
    # Transcripts run long, and the tail of a meeting carries the commitments,
    # so when trimming is needed keep the end rather than the beginning.
    body = (header + transcript)[-100_000:]
    return voice_llm.plan_json(system, body, max_tokens=2500)
