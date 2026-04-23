"""
JWT authentication service.

Handles:
  - User registration with bcrypt password hashing
  - User authentication (username + password → JWT)
  - JWT creation and validation (HS256)
  - Access tokens (30 min expiry) and refresh tokens (7 days)
  - User store in SQLite (/app/data/users.db)

Protected routes receive the JWT via Authorization: Bearer <token> header.
The JWT payload contains: sub (user_id), username, exp, iat.
"""

import os
import secrets
import aiosqlite
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bcrypt
from jose import jwt, JWTError

DATA_DIR = Path("/app/data")
USERS_DB = DATA_DIR / "users.db"

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

_jwt_secret: str | None = None
_startup_done = False
_init_lock = asyncio.Lock()


def _get_jwt_secret() -> str:
    global _jwt_secret
    if _jwt_secret is None:
        _jwt_secret = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
    return _jwt_secret


async def init_db() -> None:
    """Create the users table if it doesn't exist. Safe to call multiple times."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(USERS_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.commit()


async def ensure_started() -> None:
    """Called at app startup to init the DB once."""
    global _startup_done
    if _startup_done:
        return
    async with _init_lock:
        if _startup_done:
            return
        await init_db()
        _startup_done = True


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


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


async def get_user_by_username(username: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(USERS_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, username, hashed_password, created_at, is_active FROM users WHERE username = ?",
            (username,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)


async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(USERS_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, username, created_at, is_active FROM users WHERE id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)


async def create_user(username: str, password: str) -> dict[str, Any]:
    """Create a new user. Returns the user dict or raises ValueError if username taken."""
    existing = await get_user_by_username(username)
    if existing:
        raise ValueError(f"Username '{username}' is already taken")
    hashed = hash_password(password)
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(USERS_DB) as db:
        async with db.execute(
            "INSERT INTO users (username, hashed_password, created_at) VALUES (?, ?, ?)",
            (username, hashed, now),
        ) as cur:
            await db.commit()
            user_id = cur.lastrowid
    return {"id": user_id, "username": username, "created_at": now, "is_active": 1}


async def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    user = await get_user_by_username(username)
    if not user or not user.get("is_active"):
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def make_tokens_for_user(user: dict[str, Any]) -> dict[str, str]:
    """Return access + refresh token pair for a user dict."""
    payload = {"sub": str(user["id"]), "username": user["username"]}
    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "token_type": "bearer",
    }
