"""
Audit logging service.

Logs all user actions (command dispatches, session lifecycle, auth events)
to an append-only SQLite audit log at /app/data/audit.db.

Schema:
  audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,   -- ISO 8601 UTC
    user_id      INTEGER,           -- NULL for system-initiated actions
    username     TEXT,               -- denormalised for readability
    action_type  TEXT NOT NULL,     -- session_command | keg_command | session_create |
                                     -- session_delete | auth_login | auth_register | ...
    resource_type TEXT NOT NULL,     -- session | keg | device | auth | system
    resource_id  TEXT,              -- session_id, keg_uuid, etc.
    command      TEXT,              -- NEXT_STEP, CHANGE_TEMPERATURE, etc.
    device_uuid  TEXT,
    result       TEXT,              -- success | error | blocked
    details      TEXT,              -- JSON blob with extra context
    result_code  INTEGER           -- HTTP status code if applicable
  )

Indices:
  - idx_timestamp   ON (timestamp DESC)
  - idx_user       ON (user_id, timestamp DESC)
  - idx_resource   ON (resource_type, resource_id)
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

DATA_DIR = Path("/app/data")
AUDIT_DB = DATA_DIR / "audit.db"

_init_done = False
_init_lock = asyncio.Lock()


async def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(AUDIT_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT    NOT NULL,
                user_id      INTEGER,
                username     TEXT,
                action_type  TEXT    NOT NULL,
                resource_type TEXT  NOT NULL,
                resource_id  TEXT,
                command      TEXT,
                device_uuid  TEXT,
                result       TEXT,
                details      TEXT,
                result_code  INTEGER
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user ON audit_log(user_id, timestamp DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_resource ON audit_log(resource_type, resource_id)")
        await db.commit()


async def ensure_started() -> None:
    global _init_done
    if _init_done:
        return
    async with _init_lock:
        if _init_done:
            return
        await init_db()
        _init_done = True


async def log_action(
    action_type: str,
    resource_type: str,
    resource_id: str | None = None,
    command: str | None = None,
    device_uuid: str | None = None,
    result: str = "success",
    details: dict[str, Any] | None = None,
    user_id: int | None = None,
    username: str | None = None,
    result_code: int | None = None,
) -> None:
    """
    Append a single audit log entry.

    Args:
        action_type:   session_command | keg_command | session_create | session_delete |
                      auth_login | auth_register | auth_logout | token_refresh | system_event
        resource_type: session | keg | device | auth | system
        resource_id:   session_id, keg_uuid, etc.
        command:       Named MiniBrew command if applicable.
        device_uuid:   MiniBrew device UUID.
        result:        success | error | blocked | pending
        details:       Extra context as a flat dict (serialised to JSON).
        user_id:       Authenticated user id (None for system actions).
        username:      Denormalised username string.
        result_code:   HTTP status code if applicable.
    """
    await ensure_started()
    now = datetime.now(timezone.utc).isoformat()
    details_json = json.dumps(details) if details else None
    async with aiosqlite.connect(AUDIT_DB) as db:
        await db.execute(
            """
            INSERT INTO audit_log
                (timestamp, user_id, username, action_type, resource_type,
                 resource_id, command, device_uuid, result, details, result_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, user_id, username, action_type, resource_type,
             resource_id, command, device_uuid, result, details_json, result_code),
        )
        await db.commit()


async def get_logs(
    limit: int = 100,
    offset: int = 0,
    user_id: int | None = None,
    action_type: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    result: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve audit log entries with optional filters.

    Returns newest-first (timestamp DESC).
    """
    await ensure_started()
    conditions = []
    params: list[Any] = []

    if user_id is not None:
        conditions.append("user_id = ?")
        params.append(user_id)
    if action_type:
        conditions.append("action_type = ?")
        params.append(action_type)
    if resource_type:
        conditions.append("resource_type = ?")
        params.append(resource_type)
    if resource_id:
        conditions.append("resource_id = ?")
        params.append(resource_id)
    if result:
        conditions.append("result = ?")
        params.append(result)
    if start_time:
        conditions.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        conditions.append("timestamp <= ?")
        params.append(end_time)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT id, timestamp, user_id, username, action_type, resource_type,
               resource_id, command, device_uuid, result, details, result_code
        FROM audit_log
        {where}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    async with aiosqlite.connect(AUDIT_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_log_count(
    user_id: int | None = None,
    action_type: str | None = None,
    resource_type: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> int:
    """Return total count of matching entries (for pagination)."""
    await ensure_started()
    conditions = []
    params: list[Any] = []

    if user_id is not None:
        conditions.append("user_id = ?")
        params.append(user_id)
    if action_type:
        conditions.append("action_type = ?")
        params.append(action_type)
    if resource_type:
        conditions.append("resource_type = ?")
        params.append(resource_type)
    if start_time:
        conditions.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        conditions.append("timestamp <= ?")
        params.append(end_time)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    async with aiosqlite.connect(AUDIT_DB) as db:
        async with db.execute(f"SELECT COUNT(*) FROM audit_log {where}", params) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0
