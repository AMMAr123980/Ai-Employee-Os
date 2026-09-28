import logging
from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from app.models import (
    Customer, EmailMessage, EmailStatus, FollowUpStatus,
    InboundEmailConfig, CustomerNote, NoteType
)
from app.email_assistant import classify_email_thread

logger = logging.getLogger("inbound_email_sync")


def mock_fetch_inbox_messages(config: InboundEmailConfig) -> List[Dict[str, Any]]:
    """Fetches messages from Gmail/Outlook REST API or simulated driver."""
    # Simulated incoming email inbox driver for dev mode when OAuth tokens aren't configured
    if not config.access_token:
        logger.info(f"[SIMULATED INBOX SYNC] Account: {config.email_address or 'company@inbox.com'}")
        return []

    # In production, uses google-api-python-client / O365 library to pull unread messages
    return []


def sync_company_inbox(db: Session, company_id: str) -> Dict[str, Any]:
    """Syncs incoming emails, auto-links to customers, resolves follow-ups, and auto-classifies threads."""
    config = db.query(InboundEmailConfig).filter(InboundEmailConfig.company_id == company_id).first()

    if not config:
        config = InboundEmailConfig(
            company_id=company_id,
            email_address="sales@company.com",
            provider="gmail",
            auto_sync_enabled=True,
            auto_classify=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    fetched_messages = mock_fetch_inbox_messages(config)

    synced_count = 0
    followups_resolved = 0

    for msg_data in fetched_messages:
        from_email = msg_data.get("from_email")
        subject = msg_data.get("subject", "No Subject")
        body = msg_data.get("body", "")
        msg_id = msg_data.get("message_id", f"msg_{datetime.utcnow().timestamp()}")

        # Check if already processed
        existing = db.query(EmailMessage).filter(
            EmailMessage.company_id == company_id,
            EmailMessage.inbound_message_id == msg_id
        ).first()

        if existing:
            continue

        # Find or create customer
        customer = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.email.ilike(from_email)
        ).first()

        if not customer:
            sender_name = msg_data.get("from_name") or from_email.split("@")[0].capitalize()
            customer = Customer(
                company_id=company_id,
                name=sender_name,
                email=from_email,
                notes="Auto-created via inbound email sync"
            )
            db.add(customer)
            db.flush()

        # Save Inbound EmailMessage
        inbound_msg = EmailMessage(
            company_id=company_id,
            user_id=None,
            customer_id=customer.id,
            direction="inbound",
            inbound_message_id=msg_id,
            to_email=config.email_address or "inbox@company.com",
            subject=subject,
            body=body,
            status=EmailStatus.SENT,
            auto_generated=False
        )
        db.add(inbound_msg)
        synced_count += 1

        # Auto-resolve pending follow-up nudges for this customer!
        pending_followups = db.query(EmailMessage).filter(
            EmailMessage.company_id == company_id,
            EmailMessage.customer_id == customer.id,
            EmailMessage.follow_up_status == FollowUpStatus.PENDING
        ).all()

        for fup in pending_followups:
            fup.follow_up_status = FollowUpStatus.DONE
            fup.dismissed = True
            followups_resolved += 1

        # Auto-classify thread if enabled
        if config.auto_classify:
            try:
                clf = classify_email_thread(f"Subject: {subject}\n\n{body}")
                if clf.get("priority") in ["high", "urgent"] or clf.get("category") == "complaint":
                    note = CustomerNote(
                        company_id=company_id,
                        customer_id=customer.id,
                        user_id=None,
                        note_type=NoteType.NOTE,
                        content=f"⚠️ [Inbound Email Flagged - Priority: {clf.get('priority').upper()}, Category: {clf.get('category').upper()}]\nSubject: {subject}\nReasoning: {clf.get('reasoning')}"
                    )
                    db.add(note)
            except Exception as e:
                logger.error(f"Error classifying inbound email: {e}")

    config.last_synced_at = datetime.utcnow()
    db.commit()

    return {
        "synced_count": synced_count,
        "followups_resolved": followups_resolved,
        "last_synced_at": config.last_synced_at.isoformat()
    }
