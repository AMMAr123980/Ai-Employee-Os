"""Schemas for the AI employees API.

`AIEmployeeRunOut` deliberately mirrors voice_schemas.VoiceCommandOut field
for field (intent / confidence / action / summary / missing_info / status /
result / error). The confirmation screen the voice module already needs —
"here's what I'm about to do, approve or cancel" — then renders an employee
run with no new component.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.ai_employee_models import AIEmployeeRunStatus, AIEmployeeRunTrigger


class BriefRequest(BaseModel):
    """What the user typed or said into an employee's panel."""
    brief: str
    trigger: AIEmployeeRunTrigger = AIEmployeeRunTrigger.USER
    # Skips execution and returns the plan only — for a "what would you do?"
    # preview button, and for testing a prompt without writing rows.
    dry_run: bool = False


class AIEmployeeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_key: str
    trigger: AIEmployeeRunTrigger
    brief: str
    intent: Optional[str]
    confidence: Optional[float]
    action: Optional[dict[str, Any]] = None  # from action_json, filled in the router
    summary: Optional[str]
    missing_info: list[str] = []
    status: AIEmployeeRunStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str]
    created_at: datetime
    executed_at: Optional[datetime]


class ConfirmRunRequest(BaseModel):
    """Lets the confirmation screen patch a slot before executing — the model
    heard "Zenith" and meant supplier_id of "Zenith Traders (Lahore)", or the
    approver wants to change a quantity. Same contract as
    voice_schemas.ConfirmVoiceCommandRequest."""
    overrides: dict[str, Any] = {}


class EmployeeConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    display_name: Optional[str] = None
    autonomy_level: Optional[str] = None  # "standard" | "cautious"
    instructions: Optional[str] = None


class EmployeeOut(BaseModel):
    key: str
    label: str
    department: str
    description: str
    intents: list[str]
    examples: list[str] = []
    enabled: bool = True
    display_name: Optional[str] = None
    autonomy_level: str = "standard"
    instructions: Optional[str] = None
