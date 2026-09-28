import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    starts_at = Column(DateTime, nullable=False, index=True)
    ends_at = Column(DateTime, nullable=False)

    location = Column(String, nullable=True)
    meeting_link = Column(String, nullable=True)
    provider = Column(String, default="google", nullable=False)  # "google", "microsoft", "ical"
    external_event_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer")
    user = relationship("User")
