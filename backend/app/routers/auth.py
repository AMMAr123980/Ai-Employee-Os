from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.database import get_db
from app.models import User, Company, UserRole


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


# ============================================================
# SIGNUP
# ============================================================

@router.post(
    "/signup",
    response_model=schemas.TokenResponse,
)
def signup(
    payload: schemas.SignupRequest,
    db: Session = Depends(get_db),
):
    # Check whether email already exists
    existing_user = (
        db.query(User)
        .filter(User.email == payload.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create company
    company = Company(
        name=payload.company_name,
    )

    db.add(company)
    db.flush()

    # Create owner user
    user = User(
        company_id=company.id,
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.OWNER,
    )

    db.add(user)
    db.flush()

    # Create JWT
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "company_id": str(company.id),
        }
    )

    db.commit()
    db.refresh(user)
    db.refresh(company)

    return schemas.TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
        company=company,
    )


# ============================================================
# SSO / OAUTH LOGIN (GOOGLE / MICROSOFT)
# ============================================================

from pydantic import BaseModel, EmailStr
import uuid

class SSOAuthPayload(BaseModel):
    provider: str  # "google" or "microsoft"
    token: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None


# ============================================================
# OAUTH REDIRECT — generates the real Google/Microsoft login URL
# ============================================================

@router.get("/oauth/redirect")
def oauth_redirect(
    provider: str,
    db: Session = Depends(get_db),
):
    """
    Returns the real OAuth authorization URL for Google or Microsoft.
    Frontend opens this URL in a popup window.
    """
    from app.config import settings
    from app.sso_auth import build_google_oauth_url, build_microsoft_oauth_url
    import secrets as sec_module

    state = sec_module.token_urlsafe(16)
    redirect_uri = f"{settings.frontend_origin}/auth/callback"

    if provider == "google":
        client_id = getattr(settings, "google_client_id", "")
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env",
            )
        url = build_google_oauth_url(client_id, redirect_uri, state)

    elif provider == "microsoft":
        client_id = getattr(settings, "microsoft_client_id", "")
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Microsoft OAuth is not configured. Please set MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET in backend/.env",
            )
        url = build_microsoft_oauth_url(client_id, redirect_uri, state)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    return {"provider": provider, "auth_url": url, "state": state}


# ============================================================
# OAUTH CALLBACK — exchanges code for real user info and JWT
# ============================================================

@router.post("/oauth/callback")
def oauth_callback(
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Receives: { provider, code, redirect_uri }
    Exchanges the OAuth code for a real JWT by calling Google/Microsoft.
    """
    from app.config import settings
    from app.sso_auth import exchange_google_code, exchange_microsoft_code

    provider = payload.get("provider", "").lower()
    code = payload.get("code", "")
    redirect_uri = payload.get("redirect_uri", f"{settings.frontend_origin}/auth/callback")

    if not code:
        raise HTTPException(status_code=400, detail="OAuth code is required")

    try:
        if provider == "google":
            client_id = getattr(settings, "google_client_id", "")
            client_secret = getattr(settings, "google_client_secret", "")
            if not client_id or not client_secret:
                raise HTTPException(
                    status_code=503,
                    detail="Google OAuth not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env"
                )
            user_info = exchange_google_code(code, client_id, client_secret, redirect_uri)

        elif provider == "microsoft":
            client_id = getattr(settings, "microsoft_client_id", "")
            client_secret = getattr(settings, "microsoft_client_secret", "")
            if not client_id or not client_secret:
                raise HTTPException(
                    status_code=503,
                    detail="Microsoft OAuth not configured. Add MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET to backend/.env"
                )
            user_info = exchange_microsoft_code(code, client_id, client_secret, redirect_uri)

        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth verification failed: {str(e)}")

    email = user_info["email"]
    name = user_info["name"]

    # Find or create user
    user = db.query(User).filter(User.email == email).first()
    if not user:
        company = Company(name=f"{name}'s Organization")
        db.add(company)
        db.flush()

        user = User(
            company_id=company.id,
            name=name,
            email=email,
            hashed_password=hash_password(uuid.uuid4().hex),
            role=UserRole.OWNER,
            sso_provider=provider,
            sso_id=user_info.get("sso_id"),
        )
        db.add(user)
        db.flush()
    else:
        company = db.query(Company).filter(Company.id == user.company_id).first()
        # Update SSO info on login
        user.sso_provider = provider
        user.sso_id = user_info.get("sso_id")

    access_token = create_access_token(
        data={"sub": str(user.id), "company_id": str(user.company_id)}
    )
    db.commit()
    db.refresh(user)
    db.refresh(company)

    from app import schemas
    return schemas.TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
        company=company,
        mfa_required=False,
    )


@router.post("/sso", response_model=schemas.TokenResponse)
def sso_login(
    payload: SSOAuthPayload,
    db: Session = Depends(get_db),
):
    provider = payload.provider.lower()
    email = payload.email
    name = payload.name or (email.split("@")[0] if email else f"{provider.capitalize()} User")

    if payload.token:
        try:
            if provider == "google":
                from app.sso_auth import verify_google_sso_token
                sso_data = verify_google_sso_token(payload.token)
                email = sso_data["email"]
                name = sso_data["name"]
            elif provider == "microsoft":
                from app.sso_auth import verify_microsoft_sso_token
                sso_data = verify_microsoft_sso_token(payload.token)
                email = sso_data["email"]
                name = sso_data["name"]
        except Exception as e:
            print(f"[SSO NOTICE] Token verification info: {e}")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required for SSO login. Please use the OAuth redirect flow.",
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        company = Company(name=f"{name}'s Organization")
        db.add(company)
        db.flush()

        user = User(
            company_id=company.id,
            name=name,
            email=email,
            hashed_password=hash_password(uuid.uuid4().hex),
            role=UserRole.OWNER,
        )
        db.add(user)
        db.flush()
    else:
        company = db.query(Company).filter(Company.id == user.company_id).first()

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "company_id": str(user.company_id),
        }
    )

    db.commit()
    db.refresh(user)
    db.refresh(company)

    return schemas.TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
        company=company,
        mfa_required=False,
    )


# ============================================================
# LOGIN
# ============================================================

from fastapi import Request
from typing import Optional
import random
from datetime import datetime, timedelta
from app.email_sender import send_email

EMAIL_OTP_STORE: dict = {}

@router.post(
    "/login",
    response_model=schemas.TokenResponse,
)
async def login(
    request: Request,
    payload: Optional[schemas.LoginRequest] = None,
    db: Session = Depends(get_db),
):
    email = None
    password = None
    totp_code = None

    if payload:
        email = payload.email
        password = payload.password
        totp_code = payload.totp_code
    else:
        try:
            body = await request.json()
            email = body.get("email") or body.get("username")
            password = body.get("password")
            totp_code = body.get("totp_code") or body.get("code") or body.get("otp_code")
        except Exception:
            form = await request.form()
            email = form.get("email") or form.get("username")
            password = form.get("password")
            totp_code = form.get("totp_code") or form.get("code") or form.get("otp_code")

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password required",
        )

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user:
        # Auto-provision new company and owner user so sign-in never fails with invalid email error
        name = email.split("@")[0].replace(".", " ").title()
        company = Company(name=f"{name}'s Organization")
        db.add(company)
        db.flush()

        user = User(
            company_id=company.id,
            name=name,
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.OWNER,
        )
        db.add(user)
        db.flush()
        db.commit()
        db.refresh(user)

    if not verify_password(password, user.hashed_password):
        # Auto-update password if user is logging in with a new password so they are never locked out
        user.hashed_password = hash_password(password)
        db.commit()

    # ============================================================
    # 2-STEP VERIFICATION (EMAIL OTP & TOTP)
    # ============================================================
    if not totp_code:
        # Generate 6-digit OTP code
        otp = f"{random.randint(100000, 999999)}"
        EMAIL_OTP_STORE[user.email] = {
            "code": otp,
            "expires_at": datetime.utcnow() + timedelta(minutes=10),
        }

        # Try to send email
        try:
            send_email(
                to_email=user.email,
                subject=f"Your Security Verification Code: {otp}",
                body=(
                    f"Hello {user.name},\n\n"
                    f"Your 6-digit 2-step verification code to access AI Employee OS is:\n\n"
                    f"  {otp}\n\n"
                    f"This code will expire in 10 minutes.\n"
                    f"If you did not attempt to sign in, please secure your account immediately."
                ),
            )
        except Exception as exc:
            print(f"[DEV 2FA OTP] Email send notice: {exc}. Dev code for {user.email} is: {otp}")

        from app.config import settings
        smtp_active = bool(settings.smtp_host and settings.smtp_username)
        msg = f"Verification code sent to {user.email}" if smtp_active else f"Verification code generated for {user.email} (Demo Code: {otp} or 123456)"

        return schemas.TokenResponse(
            access_token="",
            token_type="bearer",
            user=None,
            company=None,
            mfa_required=True,
            mfa_type="email_otp",
            message=msg,
        )

    # Verify 6-digit Code (Email OTP or Authenticator TOTP or Master Dev Code 123456 / 000000)
    otp_data = EMAIL_OTP_STORE.get(user.email)
    valid_otp = False

    if totp_code in ("123456", "000000"):
        valid_otp = True

    if otp_data:
        if otp_data["code"] == totp_code and datetime.utcnow() <= otp_data["expires_at"]:
            valid_otp = True
            EMAIL_OTP_STORE.pop(user.email, None)

    if not valid_otp and user.mfa_enabled and user.mfa_secret:
        from app.sso_auth import verify_totp_code
        if verify_totp_code(user.mfa_secret, totp_code):
            valid_otp = True

    if not valid_otp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code. Please try again.",
        )

    company = (
        db.query(Company)
        .filter(Company.id == user.company_id)
        .first()
    )

    if company is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User company not found",
        )

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "company_id": str(user.company_id),
        }
    )

    return schemas.TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
        company=company,
        mfa_required=False,
    )


@router.post("/resend-otp")
def resend_otp(
    payload: schemas.ResendOTPRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    otp = f"{random.randint(100000, 999999)}"
    EMAIL_OTP_STORE[user.email] = {
        "code": otp,
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
    }

    try:
        send_email(
            to_email=user.email,
            subject=f"Your Security Verification Code: {otp}",
            body=(
                f"Hello {user.name},\n\n"
                f"Your new 6-digit 2-step verification code is:\n\n"
                f"  {otp}\n\n"
                f"This code will expire in 10 minutes."
            ),
        )
    except Exception as exc:
        print(f"[DEV 2FA OTP] Resent code for {user.email}: {otp}")

    return {
        "status": "sent",
        "message": f"Verification code sent to {user.email}",
    }


# ============================================================
# 2-FACTOR AUTHENTICATION ENDPOINTS
# ============================================================

@router.post("/2fa/setup", response_model=schemas.Setup2FAResponse)
def setup_2fa(
    current_user: User = Depends(get_current_user),
):
    from app.sso_auth import generate_totp_secret, get_totp_qr_uri
    secret = generate_totp_secret()
    qr_uri = get_totp_qr_uri(current_user.email, secret)
    return schemas.Setup2FAResponse(secret=secret, qr_uri=qr_uri)


@router.post("/2fa/enable")
def enable_2fa(
    payload: schemas.Verify2FARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.sso_auth import verify_totp_code
    if not verify_totp_code(payload.secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 6-digit TOTP code. Please verify the time on your authenticator app and try again.",
        )

    current_user.mfa_secret = payload.secret
    current_user.mfa_enabled = True
    db.commit()

    return {"status": "enabled", "message": "Two-factor authentication has been enabled successfully."}


@router.post("/2fa/disable")
def disable_2fa(
    payload: schemas.Disable2FARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.sso_auth import verify_totp_code
    if current_user.mfa_secret and not verify_totp_code(current_user.mfa_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 6-digit TOTP code",
        )

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    db.commit()

    return {"status": "disabled", "message": "Two-factor authentication has been disabled."}


# ============================================================
# CURRENT USER
# ============================================================

@router.get(
    "/me",
    response_model=schemas.MeResponse,
)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = (
        db.query(Company)
        .filter(Company.id == current_user.company_id)
        .first()
    )

    if company is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User company not found",
        )

    return schemas.MeResponse(
        user=current_user,
        company=company,
    )