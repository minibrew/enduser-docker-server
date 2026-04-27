"""
JWT authentication service (Simplified).

Handles token creation and validation without a backing database.
Used for multi-user session management if enabled, currently bypassed for single-user mode.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from jose import jwt, JWTError

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

_jwt_secret: str | None = None

def _get_jwt_secret() -> str:
    global _jwt_secret
    if _jwt_secret is None:
        _jwt_secret = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
    return _jwt_secret

async def ensure_started() -> None:
    """No-op. Database removed."""
    pass

def create_access_token(payload: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = dict(payload)
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    return jwt.encode(to_encode, _get_jwt_secret(), algorithm=ALGORITHM)

def create_refresh_token(payload: dict[str, Any]) -> str:
    to_encode = dict(payload)
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    return jwt.encode(to_encode, _get_jwt_secret(), algorithm=ALGORITHM)

def verify_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    # Always return a default admin user
    return {"id": 1, "username": "admin", "is_active": 1}

def make_tokens_for_user(user: dict[str, Any]) -> dict[str, str]:
    payload = {"sub": str(user["id"]), "username": user["username"]}
    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "token_type": "bearer",
    }

async def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    # Any credentials work in bypassed mode, or we can just not call this.
    return {"id": 1, "username": "admin"}

async def create_user(username: str, password: str) -> dict[str, Any]:
    # No-op registration
    return {"id": 1, "username": username}
