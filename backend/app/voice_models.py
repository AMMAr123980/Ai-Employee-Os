"""
Voice Commands & Voice Message Understanding — data model.

The shape of this file is the whole difference between "one command = one
action" and "one command = a plan":

- A `VoiceCommand` owns an ordered list of `VoiceCommandStep` rows. A
  single-action command is a plan of length 1, so simple commands behave
  exactly as you'd expect — but "draft a quotation for Acme for 25 laptops,
  email it to them, and remind me if they don't reply in three days" is three
  rows that run in order, each with its own status, result and error.
  `action_json` / `result_json` on the command are a rollup of the steps, so
  anything that only wants a summary doesn't have to join.
- `QUEUED` / `PROCESSING` exist because transcription and planning happen in a
  background task: the upload returns instantly and the client polls.
- Audio is retained (`audio_key`, `audio_expires_at`) rather than discarded,
  so a disputed transcript can be re-listened to. See voice_storage.py for the
  retention sweep.
- `timezone` and `locale` are captured per command. "Friday at 3 PM" spoken in
  Asia/Karachi resolves in Asia/Karachi (voice_time.py), not UTC, and the
  confirmation sentence comes back in the language it was spoken in
  (voice_i18n.py).

Three more tables live here because the voice pipeline is the only thing that
writes them:

- `VoiceFollowup` — a condition plus a deadline. This is what makes "remind me
  *if* he doesn't reply" different from a plain dated reminder.
- `MeetingSession` — the AI Meeting Assistant: a long recording, its transcript
  with speaker turns, the summary, and action items that become real Tasks.
- `UsageCounter` — per-company metering, so the plan limits on the pricing page
  are numbers the system enforces rather than marketing copy.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.models import gen_id


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------

class VoiceCommandSource(str, enum.Enum):
    APP = "app"                               # recorded in-app (hold-to-talk)
    TEXT = "text"                             # typed into the same box; skips transcription
    WHATSAPP_TEAM = "whatsapp_team"           # reserved: team member's voice note to the company number
    WHATSAPP_CUSTOMER = "whatsapp_customer"   # reserved: inbound customer voice note — never auto-executed


class VoiceCommandStatus(str, enum.Enum):
    QUEUED = "queued"                                # accepted, background task not started
    PROCESSING = "processing"                        # transcribing and/or planning
    TRANSCRIBED = "transcribed"                      # speech-to-text done, not yet planned
    NO_ACTION = "no_action"                          # nothing actionable was said
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # at least one step needs a human tap
    EXECUTED = "executed"                            # every step ran
    PARTIALLY_EXECUTED = "partially_executed"        # some ran, at least one failed
    FAILED = "failed"
    CANCELLED = "cancelled"


class VoiceStepStatus(str, enum.Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class FollowupStatus(str, enum.Enum):
    WAITING = "waiting"          # deadline not reached
    FIRED = "fired"              # deadline passed, condition still unmet -> reminder created
    RESOLVED = "resolved"        # the thing we were waiting for happened
    CANCELLED = "cancelled"


class MeetingStatus(str, enum.Enum):
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


# --------------------------------------------------------------------------
# Voice commands
# --------------------------------------------------------------------------

class VoiceCommand(Base):
    __tablename__ = "voice_commands"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True)

    source = Column(Enum(VoiceCommandSource), nullable=False)

    # --- audio + transcript ---
    audio_duration_seconds = Column(Float, nullable=True)
    audio_key = Column(String, nullable=True)        # object key in the audio store, null if not retained
    audio_bytes = Column(Integer, nullable=True)     # counted against the plan's storage quota
    audio_expires_at = Column(DateTime, nullable=True)
    detected_language = Column(String, nullable=True)   # ISO 639-1, e.g. "en", "ur"
    transcript = Column(Text, nullable=False, default="")

    # --- how it was interpreted ---
    timezone = Column(String, nullable=True)         # IANA zone the relative dates were resolved in
    locale = Column(String, nullable=True)           # language the summary/errors were written in
    confidence = Column(Float, nullable=True)        # lowest step confidence — the weakest link
    summary = Column(Text, nullable=True)
    missing_info_json = Column(Text, nullable=True)

    intent = Column(String, nullable=True)           # single intent, or "multi_step"
    action_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)

    status = Column(Enum(VoiceCommandStatus), default=VoiceCommandStatus.QUEUED, nullable=False, index=True)
    error = Column(Text, nullable=True)

    # Commands issued close together by the same person form a thread, so
    # "email it to them" can resolve what "it" and "them" mean.
    thread_id = Column(String, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)

    user = relationship("User")
    customer = relationship("Customer")
    steps = relationship(
        "VoiceCommandStep",
        back_populates="command",
        order_by="VoiceCommandStep.position",
        cascade="all, delete-orphan",
    )


class VoiceCommandStep(Base):
    """One action inside a command's plan.

    `position` is execution order and it's semantic: step 2 may depend on what
    step 1 created (draft a quotation, then email *that* quotation). The
    executor feeds each step's result into the next step's `$prev.` references
    — see voice_actions.resolve_step_config.
    """
    __tablename__ = "voice_command_steps"

    id = Column(String, primary_key=True, default=gen_id)
    command_id = Column(String, ForeignKey("voice_commands.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)

    intent = Column(String, nullable=False)
    config_json = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    missing_info_json = Column(Text, nullable=True)

    requires_confirmation = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(VoiceStepStatus), default=VoiceStepStatus.PENDING, nullable=False)
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    executed_at = Column(DateTime, nullable=True)

    command = relationship("VoiceCommand", back_populates="steps")


Index("ix_voice_steps_command_position", VoiceCommandStep.command_id, VoiceCommandStep.position)


# --------------------------------------------------------------------------
# Conditional follow-ups
# --------------------------------------------------------------------------

class VoiceFollowup(Base):
    """"...and remind me if he doesn't reply within three days."

    A dated reminder can't express that: it fires whether or not the customer
    replied. This row holds the *condition* as well as the deadline, and
    voice_followups.sweep_followups() checks the condition when the deadline
    arrives — creating the reminder only if it's still unmet, and quietly
    resolving the row if the customer did get in touch.

    `condition_type` is a small closed set rather than free text, because each
    value maps to one checker function. An unknown condition can't silently
    evaluate to "true, fire it".
    """
    __tablename__ = "voice_followups"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)

    voice_command_id = Column(String, ForeignKey("voice_commands.id"), nullable=True)
    step_id = Column(String, ForeignKey("voice_command_steps.id"), nullable=True)

    condition_type = Column(String, nullable=False)   # see voice_followups.CONDITION_CHECKERS
    condition_config_json = Column(Text, nullable=True)
    reminder_title = Column(Text, nullable=False)

    due_at = Column(DateTime, nullable=False, index=True)
    status = Column(Enum(FollowupStatus), default=FollowupStatus.WAITING, nullable=False, index=True)
    resolved_reason = Column(Text, nullable=True)
    fired_task_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    checked_at = Column(DateTime, nullable=True)

    customer = relationship("Customer")


# --------------------------------------------------------------------------
# Meeting assistant
# --------------------------------------------------------------------------

class MeetingSession(Base):
    """A recorded meeting: transcript with speaker turns, summary, decisions,
    action items and deadlines.

    Speaker labels are honest about what they are. Whisper returns no
    diarization, so `speaker_method` records how turns were attributed:
    "provided" (a human named them), "diarized" (an external service), or
    "heuristic" (pause detection — a guess, and the UI says so).
    """
    __tablename__ = "voice_meetings"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True)

    title = Column(String, nullable=True)
    occurred_at = Column(DateTime, nullable=True)

    audio_key = Column(String, nullable=True)
    audio_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    detected_language = Column(String, nullable=True)

    transcript = Column(Text, nullable=True)
    segments_json = Column(Text, nullable=True)        # [{start, end, speaker, text}, ...]
    speaker_method = Column(String, nullable=True)     # provided | diarized | heuristic
    speaker_map_json = Column(Text, nullable=True)

    summary = Column(Text, nullable=True)
    decisions_json = Column(Text, nullable=True)
    action_items_json = Column(Text, nullable=True)    # [{owner, title, due, task_id}, ...]
    deadlines_json = Column(Text, nullable=True)
    open_questions_json = Column(Text, nullable=True)

    status = Column(Enum(MeetingStatus), default=MeetingStatus.QUEUED, nullable=False, index=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)

    customer = relationship("Customer")


# --------------------------------------------------------------------------
# Metering
# --------------------------------------------------------------------------

class UsageCounter(Base):
    """One row per (company, metric, period), incremented before any paid call.

    `period` is "YYYY-MM" for monthly metrics and the literal "lifetime" for
    ones that don't reset (storage), so the usage screen is a single query.
    """
    __tablename__ = "voice_usage_counters"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    metric = Column(String, nullable=False)     # see usage_metering.METRICS
    period = Column(String, nullable=False)     # "2026-09" | "lifetime"
    value = Column(Float, nullable=False, default=0)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Index(
    "ix_usage_company_metric_period",
    UsageCounter.company_id, UsageCounter.metric, UsageCounter.period,
    unique=True,
)


class VoiceRolePermission(Base):
    """Per-company override of the default role -> permission map in
    voice_permissions.py.

    Exists because companies disagree about who may email a customer. Absence
    of a row means "use the default for this role" — this is an override list,
    not a source of truth, so an empty table is a fully working system.
    """
    __tablename__ = "voice_role_permissions"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    permission = Column(String, nullable=False)
    allowed = Column(Boolean, nullable=False, default=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Index(
    "ix_voice_role_perm",
    VoiceRolePermission.company_id, VoiceRolePermission.role, VoiceRolePermission.permission,
    unique=True,
)
