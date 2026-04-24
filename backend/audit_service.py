"""
Audit logging service.

Logs all user actions (command dispatches, session lifecycle, etc.)
to an append-only JSONL log file at /app/data/audit.log.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path("./data")
AUDIT_LOG_FILE = DATA_DIR / "audit.log"

# Configure a standard logger for the audit log
_logger = logging.getLogger("audit")
_logger.setLevel(logging.INFO)

def _setup_file_handler():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(h, logging.FileHandler) for h in _logger.handlers):
        handler = logging.FileHandler(AUDIT_LOG_FILE)
        handler.setFormatter(logging.Formatter('%(message)s'))
        _logger.addHandler(handler)

async def ensure_started() -> None:
    """No-op for file-based logging, just ensures directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _setup_file_handler()

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
    Append a single audit log entry to the JSONL file.
    """
    _setup_file_handler()
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "username": username,
        "action_type": action_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "command": command,
        "device_uuid": device_uuid,
        "result": result,
        "details": details,
        "result_code": result_code
    }
    
    # Write as a single line of JSON
    _logger.info(json.dumps(entry))

async def get_logs(
    limit: int = 100,
    offset: int = 0,
    **kwargs
) -> list[dict[str, Any]]:
    """
    Retrieve audit log entries from the file.
    Returns newest-first by reading the file backwards.
    """
    if not AUDIT_LOG_FILE.exists():
        return []

    logs = []
    try:
        with open(AUDIT_LOG_FILE, "r") as f:
            lines = f.readlines()
            # Reverse and apply offset/limit
            target_lines = lines[::-1][offset:offset+limit]
            for line in target_lines:
                if line.strip():
                    logs.append(json.loads(line))
    except Exception:
        pass
    return logs

async def get_log_count(**kwargs) -> int:
    """Return total count of log entries."""
    if not AUDIT_LOG_FILE.exists():
        return 0
    try:
        with open(AUDIT_LOG_FILE, "r") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0
