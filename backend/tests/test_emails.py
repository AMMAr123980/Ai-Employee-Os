"""
Tests for AI Email Assistant drafting, sending, thread classification, and inbox sync.
"""
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token
from app import models

client = TestClient(app)


def get_headers(user):
    token = create_access_token(user.id, user.company_id)
    return {"Authorization": f"Bearer {token}"}


def test_draft_and_send_email(db, user, customer):
    headers = get_headers(user)

    # 1. Draft email
    draft_resp = client.post(
        "/api/emails/draft",
        json={"customer_id": customer.id, "instructions": "Offer 15% discount on upcoming order"},
        headers=headers,
    )
    assert draft_resp.status_code == 200
    draft = draft_resp.json()
    assert draft["to_email"] == customer.email
    assert len(draft["subject"]) > 0

    # 2. Send email
    send_resp = client.post(
        "/api/emails/send",
        json={
            "customer_id": customer.id,
            "to_email": customer.email,
            "subject": draft["subject"],
            "body": draft["body"],
            "follow_up_in_days": 3,
        },
        headers=headers,
    )
    assert send_resp.status_code == 200
    sent = send_resp.json()
    assert sent["status"] in ("sent", "draft", "failed")


def test_classify_and_summarize(db, user):
    headers = get_headers(user)

    text = "We are interested in purchasing 50 enterprise seats. Please send us your pricing tier matrix."

    summary_resp = client.post("/api/emails/summarize", json={"text": text}, headers=headers)
    assert summary_resp.status_code == 200
    assert "summary" in summary_resp.json()

    classify_resp = client.post("/api/emails/classify", json={"text": text}, headers=headers)
    assert classify_resp.status_code == 200
    assert "category" in classify_resp.json()


def test_inbox_sync_simulation(db, user, customer):
    headers = get_headers(user)

    # Create pending follow-up email message for customer
    fup_msg = models.EmailMessage(
        company_id=user.company_id,
        user_id=user.id,
        customer_id=customer.id,
        to_email=customer.email,
        subject="Re: Quotation Q-1001",
        body="Following up on quotation",
        status=models.EmailStatus.SENT,
        follow_up_at=datetime.utcnow() - timedelta(days=1),
        follow_up_status=models.FollowUpStatus.PENDING,
        auto_generated=True,
        dismissed=False,
    )
    db.add(fup_msg)
    db.commit()

    # Simulate inbound reply email from customer
    inbound_payload = {
        "from_email": customer.email,
        "from_name": customer.name,
        "subject": "Re: Quotation Q-1001 - Approved!",
        "body": "Hi, we accept the proposal. Please send invoice.",
    }
    sync_resp = client.post("/api/emails/simulate-inbound", json=inbound_payload, headers=headers)
    assert sync_resp.status_code == 200
    res = sync_resp.json()
    assert res["status"] in ("synced", "inbound_simulated")
    assert res["followups_auto_resolved"] >= 1

    # Verify follow-up was marked dismissed
    db.expire_all()
    db.refresh(fup_msg)
    assert fup_msg.dismissed is True
