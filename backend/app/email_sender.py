"""
Actually sends the emails the AI Email Assistant drafts. Kept separate from
email_assistant.py (which is pure language logic) so sending can be swapped for a
provider API (SendGrid, SES, Gmail API) later without touching the AI drafting code.
"""
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import settings


class EmailSendError(Exception):
    pass


def send_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
) -> None:
    if not settings.smtp_host:
        raise EmailSendError(
            "SMTP is not configured (SMTP_HOST is empty). Set SMTP_* in backend/.env to send real emails."
        )

    from_name = settings.smtp_from_name or settings.company_name
    from_email = settings.smtp_from_email or settings.smtp_username

    msg = MIMEMultipart()
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_bytes and attachment_filename:
        part = MIMEApplication(attachment_bytes, Name=attachment_filename)
        part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
        msg.attach(part)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendError(str(exc)) from exc
