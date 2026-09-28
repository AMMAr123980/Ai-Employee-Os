"""
Tests for Quotations, Invoices, Payment Recording, PDF generation, and Conversion.
"""
import pytest
from app import models
from app.auth import create_access_token


def get_auth_header(user):
    token = create_access_token(user.id, user.company_id)
    return {"Authorization": f"Bearer {token}"}


def test_create_quotation(db, user, customer, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    headers = get_auth_header(user)

    payload = {
        "customer_id": customer.id,
        "items": [
            {"description": "Web Development", "quantity": 10, "unit_price": 100.0},
            {"description": "UI Design", "quantity": 5, "unit_price": 80.0},
        ],
        "discount_percent": 10.0,
        "tax_percent": 5.0,
        "notes": "Valid for 30 days",
    }

    resp = client.post("/api/quotations", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["customer_id"] == customer.id
    assert len(data["items"]) == 2
    assert data["subtotal"] == 1400.0
    assert data["total"] == 1323.0


def test_convert_quotation_to_invoice_and_record_payment(db, user, customer):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    headers = get_auth_header(user)

    # 1. Create quotation
    q_resp = client.post(
        "/api/quotations",
        json={
            "customer_id": customer.id,
            "items": [{"description": "Consulting", "quantity": 2, "unit_price": 500.0}],
        },
        headers=headers,
    )
    quot_id = q_resp.json()["id"]

    # 2. Update status to approved
    client.patch(f"/api/quotations/{quot_id}/status", json={"status": "approved"}, headers=headers)

    # 3. Convert to invoice
    conv_resp = client.post(f"/api/quotations/{quot_id}/convert-to-invoice", json={}, headers=headers)
    assert conv_resp.status_code == 200
    inv = conv_resp.json()
    inv_id = inv["id"]
    assert inv["total"] == 1000.0
    assert inv["amount_paid"] == 0.0

    # 4. Record partial payment
    pay_resp = client.post(f"/api/invoices/{inv_id}/payments", json={"amount": 400.0}, headers=headers)
    assert pay_resp.status_code == 200
    updated_inv = pay_resp.json()
    assert updated_inv["amount_paid"] == 400.0
    assert updated_inv["status"] == "partially_paid"

    # 5. Pay remaining
    pay2_resp = client.post(f"/api/invoices/{inv_id}/payments", json={"amount": 600.0}, headers=headers)
    assert pay2_resp.status_code == 200
    assert pay2_resp.json()["status"] == "paid"
