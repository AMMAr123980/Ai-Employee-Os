"""
Making the pricing page true.

Basic is $19/month for 500 AI requests. A single voice command costs two
paid API calls (Whisper, then Claude) and v1 counted neither, so a Basic
seat recording forty voice notes a day cost more than it paid. This module
is the meter.

Design notes that matter more than the code:

- **Reserve before spending, release on failure.** `consume()` is called
  *before* the API call, not after. The alternative — bill what you used —
  means a company that's over its limit still gets to make the expensive
  call. If the call then fails, `release()` gives the unit back, so a
  Whisper timeout doesn't eat someone's quota.
- **One counter row per (company, metric, period), updated under a row
  lock.** Two voice notes submitted at the same instant must not both read
  499 and both write 500. `SELECT ... FOR UPDATE` where the database
  supports it; SQLite ignores it and is single-writer anyway.
- **Limits live in `PLAN_LIMITS`**, keyed by the plan names on the pricing
  page, with `None` meaning unlimited-under-fair-use. Fair use is not
  "infinite": `FAIR_USE_CEILING` is a soft ceiling that logs loudly rather
  than blocking, so an unlimited plan being abused is visible before it's
  a bill.
- **Unknown plan -> the most generous limits, not the least.** A billing
  bug must never lock a paying customer out of their own data. It should
  page you, which is what the warning log is for.

`QuotaExceeded` carries the metric, the limit and the current value so the
router can turn it into a 402 the UI can render as "you've used 500 of 500 —
upgrade" rather than a generic error.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.voice_models import UsageCounter

logger = logging.getLogger(__name__)

# --- metrics -------------------------------------------------------------
AI_REQUESTS = "ai_requests"                 # any billed model call (Whisper, Claude, embeddings)
TRANSCRIPTION_SECONDS = "transcription_seconds"
STORAGE_BYTES = "storage_bytes"
VOICE_COMMANDS = "voice_commands"           # not capped; tracked for the usage screen
INVOICES_PER_MONTH = "invoices_per_month"   # invoice count cap
QUOTATIONS_PER_MONTH = "quotations_per_month" # quotation count cap
USER_SEATS = "user_seats"                   # user seat cap

MONTHLY_METRICS = {AI_REQUESTS, TRANSCRIPTION_SECONDS, VOICE_COMMANDS, INVOICES_PER_MONTH, QUOTATIONS_PER_MONTH}
LIFETIME_METRICS = {STORAGE_BYTES, USER_SEATS}
METRICS = MONTHLY_METRICS | LIFETIME_METRICS

_GB = 1024 ** 3

# --- limits, straight off the pricing page -------------------------------
PLAN_LIMITS: dict[str, dict[str, Optional[float]]] = {
    "basic": {
        AI_REQUESTS: 500,
        TRANSCRIPTION_SECONDS: 3 * 3600,      # ~3 hours of audio a month
        STORAGE_BYTES: 1 * _GB,
        INVOICES_PER_MONTH: 30,
        QUOTATIONS_PER_MONTH: 30,
        USER_SEATS: 3,
    },
    "pro": {
        AI_REQUESTS: 10_000,
        TRANSCRIPTION_SECONDS: 40 * 3600,
        STORAGE_BYTES: 20 * _GB,
        INVOICES_PER_MONTH: 500,
        QUOTATIONS_PER_MONTH: 500,
        USER_SEATS: 15,
    },
    "business": {
        AI_REQUESTS: None,                    # unlimited (fair use)
        TRANSCRIPTION_SECONDS: None,
        STORAGE_BYTES: 200 * _GB,             # storage is a real cost; still capped
        INVOICES_PER_MONTH: None,
        QUOTATIONS_PER_MONTH: None,
        USER_SEATS: None,
    },
}

# Soft ceiling for "unlimited (fair use)" plans. Logged, never blocked.
FAIR_USE_CEILING: dict[str, float] = {
    AI_REQUESTS: 200_000,
    TRANSCRIPTION_SECONDS: 500 * 3600,
}

_MOST_GENEROUS = "business"


class QuotaExceeded(Exception):
    def __init__(self, metric: str, limit: float, current: float, plan: str):
        self.metric = metric
        self.limit = limit
        self.current = current
        self.plan = plan
        super().__init__(f"{metric} quota exceeded for plan {plan}: {current:.0f}/{limit:.0f}")


def _period(metric: str) -> str:
    return "lifetime" if metric in LIFETIME_METRICS else datetime.utcnow().strftime("%Y-%m")


def plan_for_company(db: Session, company_id: str) -> str:
    """Read the plan off the company row, defensively.

    The attribute is looked up rather than assumed because this module ships
    into a codebase whose Company model isn't in front of it — `plan`,
    `plan_name` and `subscription_tier` are all plausible names, so all
    three are tried before giving up.
    """
    from app import models

    company = db.get(models.Company, company_id)
    for attr in ("plan", "plan_name", "subscription_tier", "tier"):
        raw = getattr(company, attr, None)
        if raw:
            value = getattr(raw, "value", raw)
            key = str(value).strip().lower()
            if key in PLAN_LIMITS:
                return key
    logger.warning("Company %s has no recognisable plan; assuming %s limits", company_id, _MOST_GENEROUS)
    return _MOST_GENEROUS


def limit_for(plan: str, metric: str) -> Optional[float]:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS[_MOST_GENEROUS]).get(metric)


def _counter(db: Session, company_id: str, metric: str, *, lock: bool = False) -> UsageCounter:
    period = _period(metric)
    query = db.query(UsageCounter).filter(
        UsageCounter.company_id == company_id,
        UsageCounter.metric == metric,
        UsageCounter.period == period,
    )
    if lock:
        try:
            query = query.with_for_update()
        except Exception:  # backend without row locking (SQLite) — single writer anyway
            pass
    counter = query.first()
    if counter is None:
        counter = UsageCounter(company_id=company_id, metric=metric, period=period, value=0)
        db.add(counter)
        db.flush()
    return counter


def current_usage(db: Session, company_id: str, metric: str) -> float:
    return float(_counter(db, company_id, metric).value or 0)


def check(db: Session, company_id: str, metric: str, amount: float = 1) -> None:
    """Would spending `amount` breach the plan? Raises QuotaExceeded if so.

    Separate from consume() so an endpoint can refuse a 20 MB upload before
    reading the body, rather than after.
    """
    plan = plan_for_company(db, company_id)
    limit = limit_for(plan, metric)
    if limit is None:
        return
    current = current_usage(db, company_id, metric)
    if current + amount > limit:
        raise QuotaExceeded(metric, limit, current, plan)


def consume(db: Session, company_id: str, metric: str, amount: float = 1) -> float:
    """Check and increment atomically. Call this immediately *before* the
    billed operation; call release() if the operation then fails."""
    plan = plan_for_company(db, company_id)
    limit = limit_for(plan, metric)
    counter = _counter(db, company_id, metric, lock=True)
    current = float(counter.value or 0)

    if limit is not None and current + amount > limit:
        raise QuotaExceeded(metric, limit, current, plan)

    ceiling = FAIR_USE_CEILING.get(metric)
    if limit is None and ceiling and current + amount > ceiling:
        logger.warning(
            "Company %s past fair-use ceiling for %s: %.0f (ceiling %.0f) — not blocked",
            company_id, metric, current + amount, ceiling,
        )

    counter.value = current + amount
    counter.updated_at = datetime.utcnow()
    db.flush()
    return counter.value


def release(db: Session, company_id: str, metric: str, amount: float = 1) -> None:
    """Hand back a reserved unit. Clamped at zero — a double release must
    not manufacture free quota."""
    if amount <= 0:
        return
    counter = _counter(db, company_id, metric, lock=True)
    counter.value = max(0.0, float(counter.value or 0) - amount)
    counter.updated_at = datetime.utcnow()
    db.flush()


def usage_snapshot(db: Session, company_id: str) -> dict:
    """Everything the usage screen needs in one call: what's been used, what
    the cap is, and how close to it they are."""
    plan = plan_for_company(db, company_id)
    out = {"plan": plan, "period": datetime.utcnow().strftime("%Y-%m"), "metrics": {}}
    for metric in sorted(METRICS):
        limit = limit_for(plan, metric)
        used = current_usage(db, company_id, metric)
        out["metrics"][metric] = {
            "used": used,
            "limit": limit,
            "unlimited": limit is None,
            "percent": None if limit is None else round(min(100.0, used / limit * 100), 1),
        }
    return out
