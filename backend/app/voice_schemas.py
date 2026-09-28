"""
Wire shapes for the voice, meeting and task endpoints.

`VoiceCommandOut` deliberately carries both the rollup (`intent`, `summary`,
`status`) and the detail (`steps`). A client that only wants to show "what did
it do" reads the rollup; the confirmation sheet reads the steps. `intent` on a
multi-step plan is the literal string "multi_step".
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.task_models import TaskPriority, TaskSource, TaskStatus
from app.voice_models import (
    FollowupStatus, MeetingStatus, VoiceCommandSource, VoiceCommandStatus, VoiceStepStatus,
)


# --------------------------------------------------------------------------
# Voice commands
# --------------------------------------------------------------------------

class VoiceStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    position: int
    intent: str
    config: dict[str, Any] = {}
    summary: Optional[str] = None
    confidence: Optional[float] = None
    missing_info: list[str] = []
    requires_confirmation: bool = False
    read_only: bool = False
    status: VoiceStepStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    executed_at: Optional[datetime] = None


class VoiceCommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source: VoiceCommandSource
    detected_language: Optional[str] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None
    transcript: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    summary: Optional[str] = None
    missing_info: list[str] = []
    status: VoiceCommandStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    steps: list[VoiceStepOut] = []
    audio_url: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    created_at: datetime
    executed_at: Optional[datetime] = None


class TextCommandRequest(BaseModel):
    """The same pipeline without a microphone: useful on a desktop, and the
    cheap way to iterate on prompts without spending Whisper calls."""
    text: str
    timezone: Optional[str] = None
    dry_run: bool = False


class ConfirmCommandRequest(BaseModel):
    """Lets the confirmation screen patch a slot before running — the model
    heard "Jon" but meant a specific customer, and the app fills that in rather
    than making someone re-record.

    `only_steps` is what makes partial approval possible: yes to the quotation,
    no to the email, without discarding the whole plan.
    """
    overrides: dict[str, Any] = {}
    step_overrides: dict[str, dict[str, Any]] = {}
    only_steps: Optional[list[str]] = Field(
        default=None,
        description="Step ids to run. Omit to run everything pending.",
    )


class UsageOut(BaseModel):
    plan: str
    period: str
    metrics: dict[str, Any]


# --------------------------------------------------------------------------
# Meetings
# --------------------------------------------------------------------------

class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: Optional[str] = None
    customer_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    detected_language: Optional[str] = None
    status: MeetingStatus
    transcript: Optional[str] = None
    segments: list[dict[str, Any]] = []
    speaker_method: Optional[str] = None
    summary: Optional[str] = None
    decisions: list[str] = []
    action_items: list[dict[str, Any]] = []
    deadlines: list[dict[str, Any]] = []
    open_questions: list[str] = []
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class SpeakerMapRequest(BaseModel):
    """Put names to the estimated labels. Once a human has done this the labels
    aren't a guess any more, so `speaker_method` flips to "provided"."""
    speaker_map: dict[str, str]


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------

class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus
    priority: TaskPriority
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    assignee_name: Optional[str] = None
    source: TaskSource
    created_at: datetime


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.NORMAL
    due_date: Optional[datetime] = None
    customer_id: Optional[str] = None
    assigned_to_user_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[datetime] = None
    assigned_to_user_id: Optional[str] = None


class FollowupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    condition_type: str
    reminder_title: str
    due_at: datetime
    status: FollowupStatus
    resolved_reason: Optional[str] = None
    fired_task_id: Optional[str] = None
    created_at: datetime
