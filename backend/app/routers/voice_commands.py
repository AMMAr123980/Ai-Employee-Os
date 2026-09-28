"""
The voice command API.

Three things shape this router:

1. **It returns immediately.** Transcription plus planning can take the better
   part of a minute on a long voice note, and holding a worker that long is how
   you get gateway timeouts. The upload is accepted, a row is created QUEUED, a
   background task does the work, and the client polls `GET /{id}`.
   `sync=true` keeps the blocking behaviour for short clips and tests.

2. **It executes a plan, not an action.** `_execute_plan()` walks the steps in
   order, feeds each result into the next step's `$prev.` references, and rolls
   the step statuses up into the command status: EXECUTED, PARTIALLY_EXECUTED or
   FAILED. One failed step doesn't abandon the rest unless a later step depended
   on it, in which case that step fails with a message naming the field it
   needed.

3. **Permission and quota are checked before anything is spent.** Quota is
   reserved before the paid call and released if it fails. Permission is checked
   per step at execution time, not just at planning time, so a role change
   between planning and confirming is respected.
"""
import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import (
    models, usage_metering, voice_context, voice_i18n, voice_permissions, voice_storage, voice_time,
)
from app import voice_schemas as schemas
from app.auth import get_current_user
from app.database import get_db
from app.voice_actions import (
    AUTO_EXECUTE, CONFIRM_REQUIRED, READ_ONLY_INTENTS, VOICE_ACTION_REGISTRY,
    ActionContext, VoiceActionError, requires_confirmation, resolve_step_config,
)
from app.voice_intent import INTENT_CATALOG, IntentParsingError, VoicePlan, parse_voice_command
from app.voice_models import (
    VoiceCommand, VoiceCommandSource, VoiceCommandStatus, VoiceCommandStep, VoiceStepStatus,
)
from app.voice_transcription import (
    TranscriptionError, estimate_duration_seconds, transcribe_audio,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice-commands", tags=["voice"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------

def _loads(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _step_out(step: VoiceCommandStep) -> schemas.VoiceStepOut:
    return schemas.VoiceStepOut(
        id=step.id,
        position=step.position,
        intent=step.intent,
        config=_loads(step.config_json, {}),
        summary=step.summary,
        confidence=step.confidence,
        missing_info=_loads(step.missing_info_json, []),
        requires_confirmation=step.requires_confirmation,
        read_only=step.intent in READ_ONLY_INTENTS,
        status=step.status,
        result=_loads(step.result_json, None),
        error=step.error,
        executed_at=step.executed_at,
    )


def _out(command: VoiceCommand, *, with_audio: bool = False) -> schemas.VoiceCommandOut:
    audio_url = None
    if with_audio and command.audio_key:
        if not command.audio_expires_at or command.audio_expires_at > datetime.utcnow():
            # Relative path; the client fetches it with its auth header and
            # turns the bytes into a blob URL (same trick as the PDF views).
            audio_url = f"/api/voice-commands/{command.id}/audio"

    return schemas.VoiceCommandOut(
        id=command.id,
        source=command.source,
        detected_language=command.detected_language,
        locale=command.locale,
        timezone=command.timezone,
        transcript=command.transcript or "",
        intent=command.intent,
        confidence=command.confidence,
        summary=command.summary,
        missing_info=_loads(command.missing_info_json, []),
        status=command.status,
        result=_loads(command.result_json, None),
        error=command.error,
        steps=[_step_out(s) for s in sorted(command.steps, key=lambda s: s.position)],
        audio_url=audio_url,
        audio_duration_seconds=command.audio_duration_seconds,
        created_at=command.created_at,
        executed_at=command.executed_at,
    )


def _owned(db: Session, user: models.User, command_id: str) -> VoiceCommand:
    command = (
        db.query(VoiceCommand)
        .filter(VoiceCommand.id == command_id, VoiceCommand.company_id == user.company_id)
        .first()
    )
    if not command:
        raise HTTPException(404, "Voice command not found")
    return command


def _quota_error(exc: usage_metering.QuotaExceeded) -> HTTPException:
    return HTTPException(402, {
        "message": voice_i18n.t("quota_exceeded", "en"),
        "metric": exc.metric,
        "limit": exc.limit,
        "used": exc.current,
        "plan": exc.plan,
    })


# --------------------------------------------------------------------------
# Planning and execution
# --------------------------------------------------------------------------

def _persist_plan(db: Session, command: VoiceCommand, plan: VoicePlan, *,
                  hold_everything: bool = False) -> None:
    for position, step in enumerate(plan.steps):
        if step.intent == "unclear":
            continue
        db.add(VoiceCommandStep(
            command_id=command.id,
            position=position,
            intent=step.intent,
            config_json=json.dumps(step.config, ensure_ascii=False, default=str),
            summary=step.summary,
            confidence=step.confidence,
            missing_info_json=json.dumps(step.missing_info),
            # A step with missing slots is held even if its intent is normally
            # automatic: running a half-filled action is worse than asking.
            requires_confirmation=(
                hold_everything or requires_confirmation(step.intent) or bool(step.missing_info)
            ),
            status=VoiceStepStatus.PENDING,
        ))

    actionable = [s for s in plan.steps if s.intent != "unclear"]
    command.intent = (
        "multi_step" if len(actionable) > 1
        else (actionable[0].intent if actionable else "unclear")
    )
    command.action_json = json.dumps(
        {"steps": [{"type": s.intent, "config": s.config} for s in actionable]},
        ensure_ascii=False, default=str,
    )
    command.summary = plan.summary
    command.confidence = plan.confidence
    command.missing_info_json = json.dumps(plan.missing_info)
    command.locale = plan.locale
    command.timezone = plan.timezone
    db.flush()


def _fail_step(db: Session, step: VoiceCommandStep, message: str) -> None:
    """Record a failed step after rolling back its half-finished work.

    The rollback is what makes a partial write impossible — an action that
    raised midway leaves nothing behind — and the row has to be re-fetched
    afterwards because the rollback expires the session's identity map.
    """
    db.rollback()
    fresh = db.get(VoiceCommandStep, step.id)
    if fresh is None:
        return
    fresh.status = VoiceStepStatus.FAILED
    fresh.error = message
    db.commit()


def _execute_plan(db: Session, command: VoiceCommand, user: models.User, *,
                  step_overrides: Optional[dict[str, dict[str, Any]]] = None) -> None:
    """Run every pending step that isn't waiting on a confirmation.

    Results accumulate into `previous_results`, which is what makes
    "$prev.quotation_number" resolvable a step later.
    """
    step_overrides = step_overrides or {}
    previous_results: dict[str, Any] = {}
    locale = command.locale or voice_i18n.DEFAULT_LOCALE
    tz_name = command.timezone or voice_time.DEFAULT_TIMEZONE

    for step in sorted(command.steps, key=lambda s: s.position):
        if step.status == VoiceStepStatus.EXECUTED:
            previous_results.update(_loads(step.result_json, {}) or {})
            continue
        if step.status != VoiceStepStatus.PENDING or step.requires_confirmation:
            continue

        config = _loads(step.config_json, {}) or {}
        config.update(step_overrides.get(step.id, {}))

        try:
            voice_permissions.require(db, user, step.intent)
            config = resolve_step_config(config, previous_results)

            handler = VOICE_ACTION_REGISTRY.get(step.intent)
            if handler is None:
                raise VoiceActionError(f"No handler is registered for {step.intent}.")

            result = handler(ActionContext(
                db=db,
                company_id=command.company_id,
                user_id=user.id,
                config=config,
                tz_name=tz_name,
                locale=locale,
                command_id=command.id,
                step_id=step.id,
            ))
            step.status = VoiceStepStatus.EXECUTED
            step.result_json = json.dumps(result, ensure_ascii=False, default=str)
            step.executed_at = datetime.utcnow()
            previous_results.update(result or {})
            # Committed per step, not once at the end: step 1's work is already
            # durable by the time step 2 runs, so a rollback from a later
            # failure can't erase the record of what actually happened.
            db.commit()

        except voice_permissions.PermissionDenied as exc:
            _fail_step(db, step, voice_i18n.t("not_permitted", locale, intent=exc.intent))
        except VoiceActionError as exc:
            _fail_step(db, step, str(exc))
        except usage_metering.QuotaExceeded:
            _fail_step(db, step, voice_i18n.t("quota_exceeded", locale))
        except Exception:
            # A broken action must never surface as a 500. The user gets a step
            # they can retry; the stack trace goes to the log.
            logger.exception("Voice step %s (%s) failed", step.id, step.intent)
            _fail_step(
                db, step,
                "Something went wrong running that step. Try again, or do it by hand.",
            )

    db.refresh(command)
    _rollup(db, command, previous_results)
    db.commit()


def _rollup(db: Session, command: VoiceCommand, results: dict[str, Any]) -> None:
    steps = list(command.steps)
    statuses = {s.status for s in steps}

    if not steps:
        command.status = VoiceCommandStatus.NO_ACTION
    elif any(s.requires_confirmation and s.status == VoiceStepStatus.PENDING for s in steps):
        command.status = VoiceCommandStatus.AWAITING_CONFIRMATION
    elif statuses == {VoiceStepStatus.EXECUTED}:
        command.status = VoiceCommandStatus.EXECUTED
        command.executed_at = datetime.utcnow()
    elif VoiceStepStatus.EXECUTED in statuses and VoiceStepStatus.FAILED in statuses:
        command.status = VoiceCommandStatus.PARTIALLY_EXECUTED
        command.executed_at = datetime.utcnow()
    elif statuses <= {VoiceStepStatus.CANCELLED}:
        command.status = VoiceCommandStatus.CANCELLED
    elif VoiceStepStatus.FAILED in statuses:
        command.status = VoiceCommandStatus.FAILED
        command.error = next((s.error for s in steps if s.error), None)
    else:
        command.status = VoiceCommandStatus.AWAITING_CONFIRMATION

    command.result_json = json.dumps(
        {
            "steps": [_loads(s.result_json, None) for s in sorted(steps, key=lambda s: s.position)],
            "merged": results,
        },
        ensure_ascii=False, default=str,
    )
    db.flush()


def plan_and_execute(db: Session, command: VoiceCommand, user: models.User, *,
                     dry_run: bool = False) -> None:
    """Transcript -> plan -> execute. Shared by the audio path and the text
    path, so both behave identically."""
    locale = command.locale or voice_i18n.DEFAULT_LOCALE
    context = voice_context.build_context(
        db, company_id=command.company_id, user_id=user.id, thread_id=command.thread_id)
    allowed = voice_permissions.allowed_intents(db, user, list(INTENT_CATALOG))

    try:
        usage_metering.consume(db, command.company_id, usage_metering.AI_REQUESTS, 1)
    except usage_metering.QuotaExceeded:
        command.status = VoiceCommandStatus.FAILED
        command.error = voice_i18n.t("quota_exceeded", locale)
        db.commit()
        return

    try:
        plan = parse_voice_command(
            command.transcript,
            allowed_intents=allowed,
            context_block=context.as_prompt_block(),
            tz_name=command.timezone or voice_time.DEFAULT_TIMEZONE,
            locale=locale,
        )
    except IntentParsingError as exc:
        usage_metering.release(db, command.company_id, usage_metering.AI_REQUESTS, 1)
        command.status = VoiceCommandStatus.FAILED
        command.error = f"Heard the words, but couldn't work out the action: {exc}"
        db.commit()
        return

    # Context backfill, per step, and only where the speaker actually used a
    # referring expression. Anything filled this way is named in the summary, so
    # a wrong resolution is visible before it runs rather than after.
    for step in plan.steps:
        step.config, filled = voice_context.backfill_from_context(
            step.config, context, command.transcript, step.intent)
        if filled:
            step.summary = f"{step.summary} (using the {', '.join(filled)} from your last command)"

    _persist_plan(db, command, plan, hold_everything=dry_run)
    usage_metering.consume(db, command.company_id, usage_metering.VOICE_COMMANDS, 1)

    if not plan.is_actionable:
        command.status = VoiceCommandStatus.NO_ACTION
        command.summary = command.summary or voice_i18n.t("nothing_understood", locale)
        db.commit()
        return

    db.commit()
    db.refresh(command)

    if dry_run:
        command.status = VoiceCommandStatus.AWAITING_CONFIRMATION
        db.commit()
        return

    _execute_plan(db, command, user)


def _transcribe_onto(db: Session, command: VoiceCommand, audio_bytes: bytes, filename: str) -> None:
    seconds = estimate_duration_seconds(len(audio_bytes))
    usage_metering.check(db, command.company_id, usage_metering.TRANSCRIPTION_SECONDS, seconds)
    usage_metering.consume(db, command.company_id, usage_metering.AI_REQUESTS, 1)

    # Always use Gemini AI multimodal audio transcription for maximum accuracy across Urdu, English & Roman Urdu.
    # Browser Web Speech API often mis-transcribes non-English accents/languages into random English sentences.
    try:
        transcription = transcribe_audio(audio_bytes, filename=filename)
        transcription_text = transcription.text
        duration_sec = transcription.duration_seconds or seconds
        lang = transcription.language or "en"
    except TranscriptionError:
        if command.transcript:
            logger.info("Remote transcription failed, using frontend live transcript fallback.")
            transcription_text = command.transcript
            duration_sec = seconds
            lang = "en"
        else:
            usage_metering.release(db, command.company_id, usage_metering.AI_REQUESTS, 1)
            raise

    usage_metering.consume(
        db, command.company_id, usage_metering.TRANSCRIPTION_SECONDS,
        duration_sec,
    )

    stored = voice_storage.save_audio(
        audio_bytes, company_id=command.company_id, filename=filename)
    if stored:
        usage_metering.consume(
            db, command.company_id, usage_metering.STORAGE_BYTES, stored.size_bytes)
        command.audio_key = stored.key
        command.audio_bytes = stored.size_bytes
        command.audio_expires_at = stored.expires_at

    command.transcript = transcription_text
    command.detected_language = lang
    command.locale = voice_i18n.normalize_locale(lang)
    command.audio_duration_seconds = duration_sec
    command.status = VoiceCommandStatus.TRANSCRIBED
    db.commit()


def _background_process(command_id: str, user_id: str, audio_bytes: bytes, filename: str) -> None:
    """Runs outside the request, so it owns its own session — a background task
    must never touch the request's session, which FastAPI closes the moment the
    response is sent."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        command = db.get(VoiceCommand, command_id)
        user = db.get(models.User, user_id)
        if command is None or user is None:
            return

        command.status = VoiceCommandStatus.PROCESSING
        db.commit()

        try:
            _transcribe_onto(db, command, audio_bytes, filename)
        except TranscriptionError as exc:
            command.status = VoiceCommandStatus.FAILED
            command.error = f"{voice_i18n.t('transcription_failed', 'en')} ({exc})"
            db.commit()
            return
        except usage_metering.QuotaExceeded:
            command.status = VoiceCommandStatus.FAILED
            command.error = voice_i18n.t("quota_exceeded", "en")
            db.commit()
            return

        plan_and_execute(db, command, user)
    except Exception:
        logger.exception("Background processing failed for command %s", command_id)
        try:
            db.rollback()
            command = db.get(VoiceCommand, command_id)
            if command and command.status in (
                VoiceCommandStatus.QUEUED, VoiceCommandStatus.PROCESSING,
            ):
                command.status = VoiceCommandStatus.FAILED
                command.error = "Something went wrong processing that recording."
                db.commit()
        except Exception:
            logger.exception("Could not even mark command %s failed", command_id)
    finally:
        db.close()


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@router.get("/intents/catalog")
def get_intent_catalog(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Feeds the "try saying..." examples. Scoped to what this user may actually
    do, so nobody is shown an example that would be refused."""
    allowed = set(voice_permissions.allowed_intents(db, current_user, list(INTENT_CATALOG)))
    return {
        "intents": {k: v for k, v in INTENT_CATALOG.items() if k in allowed and k != "unclear"},
        "read_only": sorted(READ_ONLY_INTENTS & allowed),
        "requires_confirmation": sorted(CONFIRM_REQUIRED & allowed),
        "auto_execute": sorted(AUTO_EXECUTE & allowed),
    }


@router.get("/usage", response_model=schemas.UsageOut)
def get_usage(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """What the plan allows and what's been used. The mic UI reads this so it can
    grey the button out *before* someone records thirty seconds they can't
    spend."""
    return usage_metering.usage_snapshot(db, current_user.company_id)


@router.get("", response_model=list[schemas.VoiceCommandOut])
def list_voice_commands(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    commands = (
        db.query(VoiceCommand)
        .filter(VoiceCommand.company_id == current_user.company_id)
        .order_by(VoiceCommand.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [_out(c) for c in commands]


@router.get("/{command_id}", response_model=schemas.VoiceCommandOut)
def get_voice_command(
    command_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Poll target while a command is QUEUED or PROCESSING."""
    return _out(_owned(db, current_user, command_id), with_audio=True)


@router.post("", response_model=schemas.VoiceCommandOut)
async def submit_voice_command(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    timezone: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None),
    sync: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The mic-button endpoint. Returns QUEUED and does the work in the
    background; pass `sync=true` to block until it's done."""
    logger.info("=== submit_voice_command called ===")
    logger.info("  transcript from frontend: %r", transcript)
    logger.info("  audio filename: %s, timezone: %s", audio.filename, timezone)
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "The recording was empty.")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "That recording is too long — keep commands under about 20 minutes.")

    try:
        usage_metering.check(db, current_user.company_id, usage_metering.AI_REQUESTS, 2)
        usage_metering.check(
            db, current_user.company_id, usage_metering.TRANSCRIPTION_SECONDS,
            estimate_duration_seconds(len(audio_bytes)),
        )
    except usage_metering.QuotaExceeded as exc:
        raise _quota_error(exc)

    tz_name = voice_time.company_timezone(
        user=current_user, company=current_user.company, client_timezone=timezone)

    command = VoiceCommand(
        company_id=current_user.company_id,
        user_id=current_user.id,
        source=VoiceCommandSource.APP,
        transcript=(transcript or "").strip(),
        timezone=tz_name,
        thread_id=voice_context.current_thread_id(
            db, company_id=current_user.company_id, user_id=current_user.id),
        status=VoiceCommandStatus.QUEUED,
    )
    db.add(command)
    db.commit()
    db.refresh(command)

    filename = audio.filename or "voice-note.webm"
    if sync:
        try:
            _transcribe_onto(db, command, audio_bytes, filename)
        except TranscriptionError as exc:
            command.status = VoiceCommandStatus.FAILED
            command.error = f"{voice_i18n.t('transcription_failed', 'en')} ({exc})"
            db.commit()
            return _out(command)
        plan_and_execute(db, command, current_user)
        db.refresh(command)
        return _out(command, with_audio=True)

    background_tasks.add_task(
        _background_process, command.id, current_user.id, audio_bytes, filename)
    return _out(command)


@router.post("/text", response_model=schemas.VoiceCommandOut)
def submit_text_command(
    payload: schemas.TextCommandRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Same pipeline, typed. `dry_run` plans without running anything — a "what
    would you do?" button."""
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "Nothing to act on.")

    tz_name = voice_time.company_timezone(
        user=current_user, company=current_user.company, client_timezone=payload.timezone)

    command = VoiceCommand(
        company_id=current_user.company_id,
        user_id=current_user.id,
        source=VoiceCommandSource.TEXT,
        transcript=text,
        timezone=tz_name,
        locale=voice_i18n.DEFAULT_LOCALE,
        thread_id=voice_context.current_thread_id(
            db, company_id=current_user.company_id, user_id=current_user.id),
        status=VoiceCommandStatus.TRANSCRIBED,
    )
    db.add(command)
    db.commit()
    db.refresh(command)

    plan_and_execute(db, command, current_user, dry_run=payload.dry_run)
    db.refresh(command)
    return _out(command)


@router.post("/{command_id}/confirm", response_model=schemas.VoiceCommandOut)
def confirm_voice_command(
    command_id: str,
    payload: schemas.ConfirmCommandRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Release held steps and run them.

    `only_steps` allows approving part of a plan — "yes to the quotation, no to
    the email" — which matters once one command can contain several
    customer-facing actions.
    """
    command = _owned(db, current_user, command_id)
    if command.status != VoiceCommandStatus.AWAITING_CONFIRMATION:
        raise HTTPException(
            400, f"This command is '{command.status.value}', not awaiting confirmation.")

    approved = payload.only_steps
    for step in command.steps:
        if step.status != VoiceStepStatus.PENDING:
            continue
        if approved is not None and step.id not in approved:
            step.status = VoiceStepStatus.CANCELLED
            continue
        step.requires_confirmation = False
        if payload.overrides:
            config = _loads(step.config_json, {}) or {}
            config.update(payload.overrides)
            step.config_json = json.dumps(config, ensure_ascii=False, default=str)
    db.flush()

    _execute_plan(db, command, current_user, step_overrides=payload.step_overrides)
    db.refresh(command)
    return _out(command)


@router.post("/{command_id}/cancel", response_model=schemas.VoiceCommandOut)
def cancel_voice_command(
    command_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import voice_followups

    command = _owned(db, current_user, command_id)
    if command.status != VoiceCommandStatus.AWAITING_CONFIRMATION:
        raise HTTPException(
            400, f"This command is '{command.status.value}', not awaiting confirmation.")

    for step in command.steps:
        if step.status == VoiceStepStatus.PENDING:
            step.status = VoiceStepStatus.CANCELLED

    # A discarded plan must not leave a conditional follow-up behind to nag
    # about something that never happened.
    voice_followups.cancel_followups_for_command(db, command.id)

    _rollup(db, command, {})
    db.commit()
    db.refresh(command)
    return _out(command)


@router.get("/{command_id}/audio")
def get_command_audio(
    command_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Re-listen to what was actually said. This endpoint is what makes the
    command log an audit trail rather than a transcript the same AI produced."""
    command = _owned(db, current_user, command_id)
    if not command.audio_key:
        raise HTTPException(404, "No audio was retained for this command.")
    if command.audio_expires_at and command.audio_expires_at <= datetime.utcnow():
        raise HTTPException(410, "The recording has passed its retention period.")

    audio = voice_storage.load_audio(command.audio_key)
    if audio is None:
        raise HTTPException(404, "That recording is no longer in storage.")
    return Response(content=audio, media_type="audio/webm")
