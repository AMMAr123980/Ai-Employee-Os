"""
Tasks — the AI Task Manager from the product spec.

This table didn't exist before, and three features needed it badly enough that
adding it was the smaller change:

- **Voice commands.** "Remind me to call the supplier tomorrow" has to land
  somewhere. Before this, it could only become an email draft, which is not
  what was asked for.
- **Conditional follow-ups.** "Chase him if he doesn't reply in three days"
  fires a reminder — a reminder is a task, not an email.
- **Meeting action items.** The whole value of meeting notes is that the
  commitments end up in someone's queue.

Kept in its own module rather than appended to models.py for the same reason
ai_employee_models.py is separate: it's a self-contained feature that imports
cleanly with one line in main.py.

`source` records what created the task, because a task you don't remember
creating is unnerving unless the UI can say "from your voice command on
Tuesday" or "from the Acme kickoff meeting".
"""
import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models import gen_id


class TaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TaskSource(str, enum.Enum):
    MANUAL = "manual"
    VOICE = "voice"
    FOLLOWUP = "followup"
    MEETING = "meeting"
    AI_EMPLOYEE = "ai_employee"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)

    created_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    assigned_to_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.OPEN, nullable=False, index=True)
    priority = Column(Enum(TaskPriority), default=TaskPriority.NORMAL, nullable=False)

    # Stored naive UTC, like every other timestamp here. The voice layer
    # converts from the speaker's local time once, at the boundary
    # (voice_time.resolve_spoken_datetime), so nothing downstream has to think
    # about timezones.
    due_date = Column(DateTime, nullable=True, index=True)
    completed_at = Column(DateTime, nullable=True)

    source = Column(Enum(TaskSource), default=TaskSource.MANUAL, nullable=False)
    source_ref = Column(String, nullable=True)   # voice command id, meeting id, etc.

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer")
    assignee = relationship("User", foreign_keys=[assigned_to_user_id])
