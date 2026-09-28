import base64
import hashlib
import hmac
import json
import logging
import secrets
import struct
import time
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional

logger = logging.getLogger("sso_auth")


def generate_totp_secret() -> str:
    """Generates a random 16-character base32 secret for TOTP 2FA."""
    random_bytes = secrets.token_bytes(10)
    return base64.b32encode(random_bytes).decode("utf-8").replace("=", "")


def get_totp_qr_uri(email: str, secret: str) -> str:
    """Generates an otpauth:// URI compatible with Google Authenticator and Authy."""
    label = urllib.parse.quote(f"AI Employee OS:{email}")
    issuer = urllib.parse.quote("AI Employee OS")
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def generate_totp_code(secret: str, time_step: Optional[int] = None) -> str:
    """Calculates 6-digit TOTP code for a secret."""
    if time_step is None:
        time_step = int(time.time()) // 30

    # Ensure secret padding
    secret_bytes = base64.b32decode(secret + '=' * (-len(secret) % 8), casefold=True)
    msg = struct.pack(">Q", time_step)
    hmac_hash = hmac.new(secret_bytes, msg, hashlib.sha1).digest()

    offset = hmac_hash[-1] & 0x0F
    code_int = ((hmac_hash[offset] & 0x7F) << 24 |
                (hmac_hash[offset + 1] & 0xFF) << 16 |
                (hmac_hash[offset + 2] & 0xFF) << 8 |
                (hmac_hash[offset + 3] & 0xFF)) % 1000000

    return f"{code_int:06d}"


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """Validates 6-digit TOTP code with time window tolerance."""
    if not secret or not code:
        return False

    clean_code = str(code).strip()
    current_step = int(time.time()) // 30

    for step in range(current_step - window, current_step + window + 1):
        if generate_totp_code(secret, step) == clean_code:
            return True

    return False


# ============================================================
# GOOGLE OAUTH2 — Real Authorization Code Flow
# ============================================================

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_google_oauth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the real Google OAuth2 authorization URL."""
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    })
    return f"{GOOGLE_AUTH_URL}?{params}"


def exchange_google_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange authorization code for access token and get user info from Google."""
    # Step 1: Exchange code for tokens
    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(GOOGLE_TOKEN_URL, data=token_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=15) as resp:
        token_resp = json.loads(resp.read().decode("utf-8"))

    access_token = token_resp.get("access_token")
    if not access_token:
        raise ValueError("Google token exchange failed: no access_token returned")

    # Step 2: Get user info
    info_req = urllib.request.Request(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    with urllib.request.urlopen(info_req, timeout=15) as resp:
        user_data = json.loads(resp.read().decode("utf-8"))

    email = user_data.get("email")
    if not email:
        raise ValueError("Google did not return an email address")

    return {
        "email": email,
        "name": user_data.get("name", email.split("@")[0]),
        "sso_id": user_data.get("sub"),
        "picture": user_data.get("picture"),
        "provider": "google",
    }


# ============================================================
# MICROSOFT OAUTH2 — Real Authorization Code Flow
# ============================================================

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GRAPH_URL = "https://graph.microsoft.com/v1.0/me"


def build_microsoft_oauth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the real Microsoft OAuth2 authorization URL."""
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile User.Read",
        "prompt": "select_account",
        "state": state,
    })
    return f"{MS_AUTH_URL}?{params}"


def exchange_microsoft_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange authorization code for access token and get user info from Microsoft."""
    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": "openid email profile User.Read",
    }).encode("utf-8")

    req = urllib.request.Request(MS_TOKEN_URL, data=token_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=15) as resp:
        token_resp = json.loads(resp.read().decode("utf-8"))

    access_token = token_resp.get("access_token")
    if not access_token:
        raise ValueError("Microsoft token exchange failed: no access_token returned")

    # Get user profile from Microsoft Graph
    info_req = urllib.request.Request(
        MS_GRAPH_URL,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    with urllib.request.urlopen(info_req, timeout=15) as resp:
        user_data = json.loads(resp.read().decode("utf-8"))

    email = user_data.get("mail") or user_data.get("userPrincipalName")
    if not email:
        raise ValueError("Microsoft did not return an email address")

    return {
        "email": email,
        "name": user_data.get("displayName", email.split("@")[0]),
        "sso_id": user_data.get("id"),
        "provider": "microsoft",
    }


# ============================================================
# Legacy token verification (kept for fallback)
# ============================================================

def verify_google_sso_token(token: str) -> Dict[str, Any]:
    """Verifies Google OAuth2 ID Token or Access Token."""
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "email" in data:
                return {
                    "email": data["email"],
                    "name": data.get("name", data["email"].split("@")[0]),
                    "sso_id": data.get("sub"),
                    "provider": "google"
                }
    except Exception as e:
        logger.warning(f"Google ID token verification failed: {e}. Trying userinfo endpoint...")

    try:
        req = urllib.request.Request(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "email": data["email"],
                "name": data.get("name", data["email"].split("@")[0]),
                "sso_id": data.get("sub"),
                "provider": "google"
            }
    except Exception as exc:
        logger.error(f"Google SSO verification failed: {exc}")
        raise ValueError("Invalid Google OAuth token")


def verify_microsoft_sso_token(token: str) -> Dict[str, Any]:
    """Verifies Microsoft 365 / Azure AD OAuth Access Token."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        req = urllib.request.Request(MS_GRAPH_URL, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            email = data.get("mail") or data.get("userPrincipalName")
            return {
                "email": email,
                "name": data.get("displayName", email.split("@")[0]),
                "sso_id": data.get("id"),
                "provider": "microsoft"
            }
    except Exception as e:
        logger.error(f"Microsoft SSO verification failed: {e}")
        raise ValueError("Invalid Microsoft OAuth token")



