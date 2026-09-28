import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from app.calendar_models import CalendarEvent


def format_iso_utc(dt: datetime) -> str:
    return dt.strftime('%Y%m%dT%H%M%SZ')


def generate_ics_file_content(event: CalendarEvent) -> str:
    """Generates standard RFC 5545 iCalendar (.ics) format."""
    now_str = format_iso_utc(datetime.utcnow())
    start_str = format_iso_utc(event.starts_at)
    end_str = format_iso_utc(event.ends_at)

    summary = (event.title or "Meeting").replace("\n", " ")
    description = (event.description or "").replace("\n", "\\n")
    location = (event.meeting_link or event.location or "").replace("\n", " ")

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AI Employee OS//Calendar Module//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:event_{event.id}@aiemployeeos.local",
        f"DTSTAMP:{now_str}",
        f"DTSTART:{start_str}",
        f"DTEND:{end_str}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{location}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(ics_lines)


def generate_google_calendar_url(event: CalendarEvent) -> str:
    """Generates a direct Google Calendar 'Add to Calendar' web URL."""
    start_str = format_iso_utc(event.starts_at)
    end_str = format_iso_utc(event.ends_at)
    title_enc = urllib.parse.quote(event.title or "Meeting")
    details_enc = urllib.parse.quote(event.description or "")
    loc_enc = urllib.parse.quote(event.meeting_link or event.location or "")

    return (
        f"https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={title_enc}&dates={start_str}/{end_str}&details={details_enc}&location={loc_enc}"
    )


def generate_outlook_calendar_url(event: CalendarEvent) -> str:
    """Generates a direct Outlook / Microsoft 365 web 'Add to Calendar' URL."""
    start_str = event.starts_at.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = event.ends_at.strftime('%Y-%m-%dT%H:%M:%SZ')
    title_enc = urllib.parse.quote(event.title or "Meeting")
    details_enc = urllib.parse.quote(event.description or "")
    loc_enc = urllib.parse.quote(event.meeting_link or event.location or "")

    return (
        f"https://outlook.live.com/calendar/0/deeplink/compose?path=/calendar/action/compose"
        f"&rru=addevent&subject={title_enc}&startdt={start_str}&enddt={end_str}&body={details_enc}&location={loc_enc}"
    )


def create_calendar_event(
    db: Session,
    company_id: str,
    user_id: Optional[str],
    data: Dict[str, Any]
) -> CalendarEvent:
    """Creates a new calendar event record."""
    starts_at = data.get("starts_at")
    if isinstance(starts_at, str):
        starts_at = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    elif not starts_at:
        starts_at = datetime.utcnow() + timedelta(days=1)

    ends_at = data.get("ends_at")
    if isinstance(ends_at, str):
        ends_at = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
    elif not ends_at:
        ends_at = starts_at + timedelta(minutes=data.get("duration_minutes", 30))

    event = CalendarEvent(
        company_id=company_id,
        user_id=user_id,
        customer_id=data.get("customer_id"),
        title=data.get("title", "Meeting"),
        description=data.get("description", ""),
        starts_at=starts_at,
        ends_at=ends_at,
        location=data.get("location"),
        meeting_link=data.get("meeting_link") or f"https://meet.jit.si/ai_os_{company_id[:6]}_{datetime.utcnow().timestamp()}",
        provider=data.get("provider", "google"),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
