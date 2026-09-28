"""
The two periodic jobs the voice features need.

Same in-process APScheduler pattern as followup_scheduler.py and
recurring_invoices.py — no separate worker, no extra terminal, and it stops
cleanly with the app.

1. **Conditional follow-up sweep.** Every `VOICE_FOLLOWUP_CHECK_INTERVAL_MINUTES`,
   evaluate every follow-up whose deadline has arrived: fire a reminder task if
   the thing you were waiting for still hasn't happened, quietly resolve it if it
   has. Runs across all companies; the manual "check now" endpoint calls the same
   function scoped to one.

2. **Audio retention sweep.** Deletes recordings past their retention window and
   hands the storage quota back. Runs twice a day by default, because retention
   is measured in months and a tighter loop would just be I/O for its own sake.

Both jobs are wrapped so an exception is logged and swallowed. A failing sweep
must not take the scheduler thread down with it, or the *other* job silently
stops too — which is the kind of failure nobody notices for a month.
"""
import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def run_followup_sweep() -> dict:
    from app import voice_followups

    db = SessionLocal()
    try:
        return voice_followups.sweep_followups(db)
    except Exception:
        logger.exception("Voice follow-up sweep failed")
        return {"checked": 0, "fired": 0, "resolved": 0, "errors": 1}
    finally:
        db.close()


def run_audio_sweep() -> dict:
    from app import voice_storage

    db = SessionLocal()
    try:
        return voice_storage.sweep_expired_audio(db)
    except Exception:
        logger.exception("Voice audio retention sweep failed")
        return {"deleted": 0}
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        run_followup_sweep,
        "interval",
        minutes=settings.voice_followup_check_interval_minutes,
        id="voice_followup_sweep",
        replace_existing=True,
    )
    _scheduler.add_job(
        run_audio_sweep,
        "interval",
        minutes=settings.voice_audio_sweep_interval_minutes,
        id="voice_audio_sweep",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Voice scheduler started (follow-ups every %s min, audio retention every %s min)",
        settings.voice_followup_check_interval_minutes,
        settings.voice_audio_sweep_interval_minutes,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
