"""
Unit and integration tests for Authentication, JWT tokens, SSO, and MFA (TOTP).
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import hash_password, verify_password, create_access_token, decode_access_token
from app import models, sso_auth

client = TestClient(app)


def test_password_hashing():
    pwd = "SecretPassword123!"
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_encode_decode():
    token = create_access_token("usr_test123", "cmp_test456")
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "usr_test123"
    assert decoded["company_id"] == "cmp_test456"


def test_signup_and_login_flow(db):
    signup_payload = {
        "company_name": "Acme Software Ltd",
        "email": "ceo@acme.com",
        "password": "Password123!",
        "name": "Jane Doe",
    }
    resp = client.post("/api/auth/signup", json=signup_payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "ceo@acme.com"

    # Test login
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "ceo@acme.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


def test_invalid_login_rejection(db):
    resp = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@acme.com", "password": "Password123!"},
    )
    assert resp.status_code in (400, 401)


def test_totp_mfa_flow(db, user):
    secret = sso_auth.generate_totp_secret()
    otpauth = sso_auth.get_totp_qr_uri(user.email, secret)
    assert len(secret) == 16
    assert "otpauth://" in otpauth

    # Generate current valid code and verify
    code = sso_auth.generate_totp_code(secret)
    assert sso_auth.verify_totp_code(secret, code) is True
    assert sso_auth.verify_totp_code(secret, "000000") is False
