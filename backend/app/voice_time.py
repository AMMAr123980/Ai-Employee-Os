"""
Turning "Friday at 3 PM" into a real timestamp.

v1 told the model to assume UTC. For a company in Asia/Karachi that put
every spoken meeting five hours out — quietly, with no error, which is the
worst kind of wrong. The fix is two-sided and both sides live here:

1. `company_timezone()` resolves the IANA zone to use for a command, in
   priority order: the value the client sent with the recording (the
   browser knows its own zone) -> the user's saved zone -> the company's
   -> the server default. Whatever wins is stored on the VoiceCommand row,
   so a wrong timestamp can be explained later instead of guessed at.

2. `prompt_now()` gives the planner the current local date, time, weekday
   and zone, and the planner is told to emit a *local* ISO datetime with no
   offset. `to_utc()` then converts it once, here, at a single call site.

The model is deliberately not asked to do timezone arithmetic. It resolves
"Friday" against a date it was told; Python converts. Models are reliable at
the first and erratic at the second.

`parse_local_iso()` is forgiving about what comes back — a bare date, a
datetime with or without seconds, or an already-offset-aware string — and
returns None rather than raising, because a bad timestamp should downgrade
a step to "missing_info", not crash a request.
"""
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Optional

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - ancient runtimes only
    ZoneInfo = None  # type: ignore

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "UTC"


def _zone(name: Optional[str]):
    if not name or ZoneInfo is None:
        return dt_timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        logger.warning("Unknown timezone %r, falling back to UTC", name)
        return dt_timezone.utc


def company_timezone(user: Any = None, company: Any = None, client_timezone: Optional[str] = None) -> str:
    """Pick the IANA zone this command's dates should be read in.

    Client first on purpose: a salesperson in Dubai using a company
    registered in Lahore means "3 PM" in Dubai. The browser is the only
    thing that knows where the words were actually spoken.
    """
    for candidate in (
        client_timezone,
        getattr(user, "timezone", None),
        getattr(company, "timezone", None),
        getattr(user, "company", None) and getattr(user.company, "timezone", None),
    ):
        if candidate and _is_valid(candidate):
            return candidate
    return DEFAULT_TIMEZONE


def _is_valid(name: str) -> bool:
    if ZoneInfo is None:
        return name == "UTC"
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def now_local(tz_name: str) -> datetime:
    return datetime.now(_zone(tz_name))


def prompt_now(tz_name: str) -> str:
    """The date/time block injected into the planning prompt.

    Includes the weekday spelled out because "next Friday" is ambiguous
    without knowing what today is, and the offset because a model that sees
    +05:00 is less likely to helpfully convert to UTC on its own.
    """
    local = now_local(tz_name)
    return (
        f"Current local date and time: {local.strftime('%A, %d %B %Y, %H:%M')} "
        f"({tz_name}, UTC{local.strftime('%z')[:3]}:{local.strftime('%z')[3:]}). "
        f"Today is {local.strftime('%A')}; tomorrow is {(local + timedelta(days=1)).strftime('%A')}."
    )


def parse_local_iso(value: Any, tz_name: str) -> Optional[datetime]:
    """Parse whatever the model produced into a timezone-aware datetime.

    Returns None on anything unparseable — callers treat that as "the time
    wasn't captured" and ask the user, which is always better than storing
    a plausible-looking wrong time.
    """
    if value in (None, "", False):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = None
        for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            logger.info("Could not parse spoken datetime %r", value)
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_zone(tz_name))
    return dt


def to_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Columns in this codebase store naive UTC (`datetime.utcnow`), so the
    conversion has to strip tzinfo after converting — otherwise SQLAlchemy
    happily stores an offset-aware value next to naive ones and every
    comparison afterwards is wrong.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(dt_timezone.utc).replace(tzinfo=None)


def resolve_spoken_datetime(value: Any, tz_name: str) -> Optional[datetime]:
    """The one function actions should call: spoken value -> naive UTC."""
    return to_utc_naive(parse_local_iso(value, tz_name))


def format_for_user(dt: Optional[datetime], tz_name: str) -> str:
    """Naive-UTC back to a sentence a human recognises, for confirmation
    text. The confirmation must show the time in the zone the person spoke
    in, or they can't tell it's wrong."""
    if dt is None:
        return "no date"
    aware = dt.replace(tzinfo=dt_timezone.utc) if dt.tzinfo is None else dt
    return aware.astimezone(_zone(tz_name)).strftime("%a %d %b %Y, %H:%M")
