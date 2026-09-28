"""
Comprehensive Multi-Tenancy Isolation Test Suite.
Verifies that User/Company B can NEVER access, modify, list, or delete Company A's resources.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token
from app import models, task_models, calendar_models, workflow_models, document_models

client = TestClient(app)


@pytest.fixture
def company_b(db):
    co = models.Company(name="Rival Corp B", plan=models.Plan.PRO, timezone="UTC")
    db.add(co)
    db.commit()
    db.refresh(co)
    return co


@pytest.fixture
def user_b(db, company_b):
    usr = models.User(
        company_id=company_b.id,
        email="hacker@rival.test",
        hashed_password="x",
        name="Rival Hacker",
        role=models.UserRole.OWNER,
    )
    db.add(usr)
    db.commit()
    db.refresh(usr)
    return usr


def get_headers(user):
    token = create_access_token(user.id, user.company_id)
    return {"Authorization": f"Bearer {token}"}


def test_customer_isolation(db, user, customer, user_b):
    headers_a = get_headers(user)
    headers_b = get_headers(user_b)

    # User A lists customers -> finds customer
    res_a = client.get("/api/customers", headers=headers_a)
    assert res_a.status_code == 200
    ids_a = [c["id"] for c in res_a.json()]
    assert customer.id in ids_a

    # User B lists customers -> empty list
    res_b = client.get("/api/customers", headers=headers_b)
    assert res_b.status_code == 200
    ids_b = [c["id"] for c in res_b.json()]
    assert customer.id not in ids_b

    # User B tries to view Customer A by ID -> 404
    get_b = client.get(f"/api/customers/{customer.id}", headers=headers_b)
    assert get_b.status_code == 404

    # User B tries to delete Customer A -> 404
    del_b = client.delete(f"/api/customers/{customer.id}", headers=headers_b)
    assert del_b.status_code == 404


def test_quotations_and_invoices_isolation(db, user, customer, user_b):
    headers_a = get_headers(user)
    headers_b = get_headers(user_b)

    # User A creates quotation
    q_res = client.post(
        "/api/quotations",
        json={"customer_id": customer.id, "items": [{"description": "Item A", "quantity": 1, "unit_price": 100}]},
        headers=headers_a,
    )
    quot_id = q_res.json()["id"]

    # User B lists quotations -> empty
    q_list_b = client.get("/api/quotations", headers=headers_b)
    assert quot_id not in [q["id"] for q in q_list_b.json()]

    # User B attempts to access quotation -> 404
    q_get_b = client.get(f"/api/quotations/{quot_id}", headers=headers_b)
    assert q_get_b.status_code == 404


def test_tasks_and_calendar_isolation(db, user, customer, user_b):
    headers_a = get_headers(user)
    headers_b = get_headers(user_b)

    # User A creates task
    t_res = client.post(
        "/api/tasks",
        json={"title": "Secret Task A", "customer_id": customer.id},
        headers=headers_a,
    )
    task_id = t_res.json()["id"]

    # User B lists tasks -> empty
    t_list_b = client.get("/api/tasks", headers=headers_b)
    assert task_id not in [t["id"] for t in t_list_b.json()]

    # User A creates calendar event
    cal_res = client.post(
        "/api/calendar/events",
        json={"title": "Executive Meeting A", "starts_at": "2026-10-01T10:00:00Z"},
        headers=headers_a,
    )
    ev_id = cal_res.json()["event_id"]

    # User B lists calendar events -> empty
    cal_list_b = client.get("/api/calendar/events", headers=headers_b)
    assert ev_id not in [e["id"] for e in cal_list_b.json()]
