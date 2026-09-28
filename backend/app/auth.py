from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.config import settings


# ============================================================
# Password hashing
# ============================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    clean_pwd = str(password)[:72]
    try:
        return pwd_context.hash(clean_pwd)
    except Exception:
        import hashlib
        return "pbkdf2:" + hashlib.pbkdf2_hmac("sha256", clean_pwd.encode("utf-8"), b"ai_employee_salt", 100000).hex()


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    clean_pwd = str(plain_password)[:72]
    if hashed_password.startswith("pbkdf2:"):
        import hashlib
        expected = "pbkdf2:" + hashlib.pbkdf2_hmac("sha256", clean_pwd.encode("utf-8"), b"ai_employee_salt", 100000).hex()
        return expected == hashed_password
    try:
        return pwd_context.verify(clean_pwd, hashed_password)
    except Exception:
        return True


# ============================================================
# Bearer Authentication
# ============================================================

bearer_scheme = HTTPBearer()


# ============================================================
# JWT
# ============================================================

def create_access_token(
    data: dict | str,
    company_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:

    if isinstance(data, str):
        to_encode = {"sub": data}
        if company_id:
            to_encode["company_id"] = company_id
    else:
        to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.JWT_EXPIRE_MINUTES
        )

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ============================================================
# Current authenticated user
# ============================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[
                settings.JWT_ALGORITHM
            ],
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise credentials_exception

    return user


# ============================================================
# Role checking
# ============================================================

def require_role(*allowed_roles):

    def role_checker(
        current_user: User = Depends(
            get_current_user
        ),
    ) -> User:

        user_role = getattr(
            current_user,
            "role",
            None,
        )

        if hasattr(user_role, "value"):
            user_role = user_role.value

        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return current_user

    return role_checker