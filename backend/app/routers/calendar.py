import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Customer
from app.calendar_models import CalendarEvent
from app.calendar_service import (
    create_calendar_event, generate_ics_file_content,
    generate_google_calendar_url, generate_outlook_calendar_url
)

logger = logging.getLogger("routers.calendar")
router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class CalendarEventCreateSchema(BaseModel):
    title: str
    description: Optional[str] = None
    starts_at: datetime
    duration_minutes: int = 30
    customer_id: Optional[str] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    provider: str = "google"


@router.get("/events")
def list_calendar_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    events = db.query(CalendarEvent).filter(
        CalendarEvent.company_id == current_user.company_id
    ).order_by(CalendarEvent.starts_at.asc()).all()

    return [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "starts_at": e.starts_at.isoformat(),
            "ends_at": e.ends_at.isoformat(),
            "location": e.location,
            "meeting_link": e.meeting_link,
            "provider": e.provider,
            "customer_id": e.customer_id,
            "customer_name": e.customer.name if e.customer else None,
            "google_url": generate_google_calendar_url(e),
            "outlook_url": generate_outlook_calendar_url(e),
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.post("/events")
def create_event_route(
    payload: CalendarEventCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    event = create_calendar_event(
        db=db,
        company_id=current_user.company_id,
        user_id=current_user.id,
        data=payload.dict()
    )

    return {
        "status": "created",
        "event_id": event.id,
        "title": event.title,
        "google_url": generate_google_calendar_url(event),
        "outlook_url": generate_outlook_calendar_url(event),
        "ics_export_url": f"/api/calendar/events/{event.id}/export.ics"
    }


@router.get("/events/{event_id}/export.ics")
def export_event_ics(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    event = db.query(CalendarEvent).filter(
        CalendarEvent.company_id == current_user.company_id,
        CalendarEvent.id == event_id
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    ics_content = generate_ics_file_content(event)
    filename = f"event_{event.id}.ics"

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
