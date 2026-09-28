"""
AI Meeting Assistant — transcription, speaker turns, summary, action items,
deadline extraction.

Pipeline, with the status written at each stage so a 40-minute recording isn't
an opaque spinner:

    QUEUED -> TRANSCRIBING -> SUMMARIZING -> COMPLETED

Speaker identification deserves a straight answer rather than a feature bullet.
Whisper returns text and timings and nothing about who spoke, so this module
supports three levels and records which one produced the labels, in
`speaker_method`:

- **"provided"** — a human named the speakers afterwards (the /speakers
  endpoint). This is the accurate one.
- **"diarized"** — an external diarization service is configured
  (`diarization_url`, any endpoint returning `{start, end, speaker}` spans).
- **"heuristic"** — the fallback. Turns are inferred from gaps between segments,
  producing "Speaker 1", "Speaker 2". It detects that someone stopped talking,
  not who started; the same person speaking twice with someone in between gets
  two different labels. The UI says "estimated from pauses" because presenting
  this as voice identification would be a lie.

Action items become real Tasks, assigned where the spoken owner matches a
colleague by name. That's the part that makes the feature pay for itself: a
summary you read once is a nice-to-have, a task list in your queue is the
product. Name matching is deliberately conservative — one unambiguous match or
nothing, because a task assigned to the wrong colleague is worse than an
unassigned one, since unassigned is visible and misassigned isn't.
"""
import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models, usage_metering, voice_i18n, voice_storage, voice_time
from app.config import settings
from app.task_models import Task, TaskPriority, TaskSource
from app.voice_models import MeetingSession, MeetingStatus
from app.voice_summarizer import SummarizerError, summarize_meeting
from app.voice_transcription import (
    Segment, TranscriptionError, estimate_duration_seconds, transcribe_long_audio,
)

logger = logging.getLogger(__name__)

SPEAKER_GAP_SECONDS = 1.6   # a pause longer than this is treated as a possible turn change
MAX_SPEAKERS = 8


def quota_preflight(db: Session, company_id: str, audio_size: int) -> None:
    """Meetings are the expensive path — an hour of audio is several Whisper
    chunks plus a long summarisation call. Check before reading the upload,
    not after."""
    seconds = estimate_duration_seconds(audio_size)
    usage_metering.check(db, company_id, usage_metering.TRANSCRIPTION_SECONDS, seconds)
    usage_metering.check(db, company_id, usage_metering.AI_REQUESTS, 2)
    usage_metering.check(db, company_id, usage_metering.STORAGE_BYTES, audio_size)


def store_meeting_audio(db: Session, meeting: MeetingSession, audio_bytes: bytes,
                        filename: str) -> None:
    stored = voice_storage.save_audio(
        audio_bytes, company_id=meeting.company_id, filename=filename, kind="meetings")
    if stored:
        meeting.audio_key = stored.key
        meeting.audio_bytes = stored.size_bytes
        usage_metering.consume(db, meeting.company_id, usage_metering.STORAGE_BYTES,
                               stored.size_bytes)
        db.commit()


def process_meeting(db: Session, meeting_id: str, audio_bytes: bytes, *,
                    filename: str = "meeting.m4a",
                    tz_name: str = voice_time.DEFAULT_TIMEZONE) -> None:
    """Run the whole pipeline. Called from a background task, so it owns its own
    error handling: every exit path leaves the row in a terminal status with
    something a human can read in `error`."""
    meeting = db.get(MeetingSession, meeting_id)
    if meeting is None:
        logger.error("Meeting %s vanished before processing", meeting_id)
        return

    try:
        meeting.status = MeetingStatus.TRANSCRIBING
        db.commit()

        seconds_estimate = estimate_duration_seconds(len(audio_bytes))
        usage_metering.consume(db, meeting.company_id, usage_metering.AI_REQUESTS, 1)
        transcription = transcribe_long_audio(audio_bytes, filename=filename)
        usage_metering.consume(
            db, meeting.company_id, usage_metering.TRANSCRIPTION_SECONDS,
            transcription.duration_seconds or seconds_estimate,
        )

        segments, method = _label_speakers(audio_bytes, transcription.segments)

        meeting.transcript = transcription.text
        meeting.segments_json = json.dumps(
            [
                {"start": round(s.start, 2), "end": round(s.end, 2),
                 "speaker": s.speaker, "text": s.text}
                for s in segments
            ],
            ensure_ascii=False,
        )
        meeting.speaker_method = method
        meeting.duration_seconds = transcription.duration_seconds
        meeting.detected_language = transcription.language
        meeting.status = MeetingStatus.SUMMARIZING
        db.commit()

        locale = voice_i18n.normalize_locale(transcription.language)
        usage_metering.consume(db, meeting.company_id, usage_metering.AI_REQUESTS, 1)
        summary = summarize_meeting(
            _transcript_with_speakers(segments) or transcription.text,
            today=voice_time.now_local(tz_name).date().isoformat(),
            locale=locale,
            title=meeting.title,
        )

        items = _attach_owners(db, meeting, summary.get("action_items") or [])
        created = _create_tasks(db, meeting, items, tz_name)

        meeting.summary = summary.get("summary", "")
        meeting.decisions_json = json.dumps(summary.get("decisions") or [], ensure_ascii=False)
        meeting.action_items_json = json.dumps(created, ensure_ascii=False)
        meeting.deadlines_json = json.dumps(summary.get("deadlines") or [], ensure_ascii=False)
        meeting.open_questions_json = json.dumps(
            summary.get("open_questions") or [], ensure_ascii=False)
        meeting.status = MeetingStatus.COMPLETED
        meeting.completed_at = datetime.utcnow()
        db.commit()

    except (TranscriptionError, SummarizerError) as exc:
        logger.warning("Meeting %s failed: %s", meeting_id, exc)
        db.rollback()
        meeting = db.get(MeetingSession, meeting_id)
        if meeting:
            meeting.status = MeetingStatus.FAILED
            meeting.error = str(exc)
            db.commit()
    except Exception:
        logger.exception("Meeting %s failed unexpectedly", meeting_id)
        db.rollback()
        meeting = db.get(MeetingSession, meeting_id)
        if meeting:
            meeting.status = MeetingStatus.FAILED
            meeting.error = "Something went wrong processing this recording."
            db.commit()


# --------------------------------------------------------------------------
# Speakers
# --------------------------------------------------------------------------

def _label_speakers(audio_bytes: bytes, segments: list[Segment]) -> tuple[list[Segment], str]:
    if getattr(settings, "diarization_url", ""):
        diarized = _diarize(audio_bytes, segments)
        if diarized:
            return diarized, "diarized"
    return _heuristic_turns(segments), "heuristic"


def _heuristic_turns(segments: list[Segment]) -> list[Segment]:
    """Label turns from silence gaps. See the module docstring for what this
    can and can't do — the label is a reading aid, not identification."""
    speaker_index = 1
    previous_end = None
    for segment in segments:
        if previous_end is not None and (segment.start - previous_end) > SPEAKER_GAP_SECONDS:
            speaker_index = speaker_index % MAX_SPEAKERS + 1
        segment.speaker = f"Speaker {speaker_index}"
        previous_end = segment.end
    return segments


def _diarize(audio_bytes: bytes, segments: list[Segment]) -> Optional[list[Segment]]:
    """Call an external diarization service if one is configured.

    Behind a setting and a try/except because diarization is the piece most
    likely to be swapped. A failure degrades to the heuristic rather than
    failing the meeting — a transcript without reliable speaker labels is still
    most of the value.
    """
    import httpx  # only needed on this path

    url = settings.diarization_url
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.diarization_api_key}"}
            if settings.diarization_api_key else {},
            files={"file": ("meeting.audio", audio_bytes)},
            timeout=300,
        )
        resp.raise_for_status()
        spans = resp.json().get("segments") or []
    except Exception:
        logger.warning("Diarization service unavailable; using pause-based turns", exc_info=True)
        return None

    if not spans:
        return None

    for segment in segments:
        midpoint = (segment.start + segment.end) / 2
        segment.speaker = "Unknown"
        for span in spans:
            try:
                if float(span["start"]) <= midpoint <= float(span["end"]):
                    segment.speaker = str(span.get("speaker", "Speaker"))
                    break
            except (KeyError, TypeError, ValueError):
                continue
    return segments


def _transcript_with_speakers(segments: list[Segment]) -> str:
    """Collapse consecutive same-speaker segments into turns. The summarizer
    reads this rather than the flat text, because "who committed to what" is
    exactly what's lost without turn boundaries."""
    lines: list[str] = []
    current: Optional[str] = None
    buffer: list[str] = []

    for segment in segments:
        if segment.speaker != current:
            if buffer:
                lines.append(f"{current}: {' '.join(buffer).strip()}")
            current = segment.speaker
            buffer = []
        buffer.append(segment.text)
    if buffer:
        lines.append(f"{current}: {' '.join(buffer).strip()}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Action items
# --------------------------------------------------------------------------

def _attach_owners(db: Session, meeting: MeetingSession,
                   items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    users = (
        db.query(models.User)
        .filter(models.User.company_id == meeting.company_id)
        .limit(200).all()
    )
    by_name: dict[str, list[Any]] = {}
    for user in users:
        full = (user.name or "").strip().lower()
        if not full:
            continue
        by_name.setdefault(full, []).append(user)
        by_name.setdefault(full.split()[0], []).append(user)

    for item in items:
        owner = str(item.get("owner") or "").strip().lower()
        matches = by_name.get(owner, [])
        item["assigned_user_id"] = matches[0].id if len(matches) == 1 else None
    return items


def _create_tasks(db: Session, meeting: MeetingSession, items: list[dict[str, Any]],
                  tz_name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        due = voice_time.resolve_spoken_datetime(item.get("due_date"), tz_name)
        task = Task(
            company_id=meeting.company_id,
            created_by_user_id=meeting.user_id,
            assigned_to_user_id=item.get("assigned_user_id") or meeting.user_id,
            customer_id=meeting.customer_id,
            title=title,
            description=(
                f"From meeting: {meeting.title or 'untitled'} "
                f"(owner said: {item.get('owner') or 'unassigned'})"
            ),
            priority=TaskPriority.NORMAL,
            due_date=due,
            source=TaskSource.MEETING,
            source_ref=meeting.id,
        )
        db.add(task)
        db.flush()
        out.append({
            "task_id": task.id,
            "title": title,
            "owner": item.get("owner"),
            "assigned_user_id": item.get("assigned_user_id"),
            "due": voice_time.format_for_user(due, tz_name),
        })
    return out
