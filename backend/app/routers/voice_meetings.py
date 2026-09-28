"""
AI Meeting Assistant API.

Upload a recording, poll until it's done, read the summary — and find the action
items already sitting in the task list as real Tasks.

The work runs in a background task for the same reason voice commands do: an
hour of audio is minutes of processing, and a request that holds a worker that
long times out somewhere you don't control. The row's `status` is the progress
bar.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, usage_metering, voice_meetings, voice_storage, voice_time
from app import voice_schemas as schemas
from app.auth import get_current_user
from app.database import get_db
from app.voice_models import MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

MAX_MEETING_BYTES = 200 * 1024 * 1024   # roughly a couple of hours of compressed audio


def _loads(raw: Optional[str], default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _out(meeting: MeetingSession) -> schemas.MeetingOut:
    return schemas.MeetingOut(
        id=meeting.id,
        title=meeting.title,
        customer_id=meeting.customer_id,
        occurred_at=meeting.occurred_at,
        duration_seconds=meeting.duration_seconds,
        detected_language=meeting.detected_language,
        status=meeting.status,
        transcript=meeting.transcript,
        segments=_loads(meeting.segments_json, []),
        speaker_method=meeting.speaker_method,
        summary=meeting.summary,
        decisions=_loads(meeting.decisions_json, []),
        action_items=_loads(meeting.action_items_json, []),
        deadlines=_loads(meeting.deadlines_json, []),
        open_questions=_loads(meeting.open_questions_json, []),
        error=meeting.error,
        created_at=meeting.created_at,
        completed_at=meeting.completed_at,
    )


def _owned(db: Session, user: models.User, meeting_id: str) -> MeetingSession:
    meeting = (
        db.query(MeetingSession)
        .filter(MeetingSession.id == meeting_id, MeetingSession.company_id == user.company_id)
        .first()
    )
    if not meeting:
        raise HTTPException(404, "Meeting not found")
    return meeting


def _process(meeting_id: str, audio_bytes: bytes, filename: str, tz_name: str) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        meeting = db.get(MeetingSession, meeting_id)
        if meeting is None:
            return
        voice_meetings.store_meeting_audio(db, meeting, audio_bytes, filename)
        voice_meetings.process_meeting(
            db, meeting_id, audio_bytes, filename=filename, tz_name=tz_name)
    finally:
        db.close()


@router.post("", response_model=schemas.MeetingOut)
async def upload_meeting(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    title: Optional[str] = Form(None),
    customer_id: Optional[str] = Form(None),
    timezone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "The upload was empty.")
    if len(audio_bytes) > MAX_MEETING_BYTES:
        raise HTTPException(413, "That recording is too large — compress it or split it first.")

    try:
        voice_meetings.quota_preflight(db, current_user.company_id, len(audio_bytes))
    except usage_metering.QuotaExceeded as exc:
        raise HTTPException(402, {
            "message": "This plan's transcription allowance is used up.",
            "metric": exc.metric, "limit": exc.limit, "used": exc.current, "plan": exc.plan,
        })

    if customer_id:
        owned = (
            db.query(models.Customer)
            .filter(models.Customer.id == customer_id,
                    models.Customer.company_id == current_user.company_id)
            .first()
        )
        if not owned:
            raise HTTPException(404, "Customer not found")

    tz_name = voice_time.company_timezone(
        user=current_user, company=current_user.company, client_timezone=timezone)

    meeting = MeetingSession(
        company_id=current_user.company_id,
        user_id=current_user.id,
        customer_id=customer_id or None,
        title=title or (audio.filename or "Meeting"),
        occurred_at=datetime.utcnow(),
        status=MeetingStatus.QUEUED,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    background_tasks.add_task(
        _process, meeting.id, audio_bytes, audio.filename or "meeting.m4a", tz_name)
    return _out(meeting)


@router.get("", response_model=list[schemas.MeetingOut])
def list_meetings(
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(MeetingSession)
        .filter(MeetingSession.company_id == current_user.company_id)
        .order_by(MeetingSession.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    # The list view drops transcripts and segments — they're large and nobody
    # reads a full transcript from a list.
    out = []
    for row in rows:
        item = _out(row)
        item.transcript = None
        item.segments = []
        out.append(item)
    return out


@router.get("/{meeting_id}", response_model=schemas.MeetingOut)
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _out(_owned(db, current_user, meeting_id))


@router.post("/{meeting_id}/speakers", response_model=schemas.MeetingOut)
def rename_speakers(
    meeting_id: str,
    payload: schemas.SpeakerMapRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Put names to the estimated speaker labels.

    The summary isn't regenerated — that would cost another call, and names
    rarely change what was decided. Re-upload if you need that.
    """
    meeting = _owned(db, current_user, meeting_id)
    segments = _loads(meeting.segments_json, [])
    if not segments:
        raise HTTPException(400, "This meeting has no transcript segments yet.")

    for segment in segments:
        if segment.get("speaker") in payload.speaker_map:
            segment["speaker"] = payload.speaker_map[segment["speaker"]]

    meeting.segments_json = json.dumps(segments, ensure_ascii=False)
    meeting.speaker_map_json = json.dumps(payload.speaker_map, ensure_ascii=False)
    meeting.speaker_method = "provided"
    db.commit()
    db.refresh(meeting)
    return _out(meeting)


@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    meeting = _owned(db, current_user, meeting_id)
    if meeting.audio_key:
        voice_storage.delete_audio(meeting.audio_key)
        usage_metering.release(
            db, meeting.company_id, usage_metering.STORAGE_BYTES, meeting.audio_bytes or 0)
    db.delete(meeting)
    db.commit()
    return {"ok": True, "deleted": meeting_id}
