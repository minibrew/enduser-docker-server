import json
import os
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


DATA_DIR = Path("/app/data")
SETTINGS_FILE = DATA_DIR / "settings.json"
MASTER_KEY_FILE = DATA_DIR / ".master.key"


def _get_fernet() -> Fernet:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if MASTER_KEY_FILE.exists():
        key = MASTER_KEY_FILE.read_bytes()
    else:
        key = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"minibrew-session-orchestrator-v1",
            iterations=480000,
        ).derive(b"minibrew-token-store")
        key = base64.urlsafe_b64encode(key)
        MASTER_KEY_FILE.write_bytes(key)
    return Fernet(key)


def get_token() -> str | None:
    if not SETTINGS_FILE.exists():
        return None
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        encrypted = base64.b64decode(data["encrypted_token"])
        return _get_fernet().decrypt(encrypted).decode()
    except Exception:
        return None


def get_env_token() -> str | None:
    return os.environ.get("MINIBREW_API_KEY") or None


def save_token(token: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = _get_fernet().encrypt(token.encode())
    SETTINGS_FILE.write_text(json.dumps({"encrypted_token": base64.b64encode(encrypted).decode()}))
    _hot_reload_client_token(token)


def delete_token() -> None:
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()
    from minibrew_client import _reset_to_env_token
    _reset_to_env_token()


def is_token_set() -> tuple[bool, str | None]:
    stored = get_token()
    if stored:
        return True, "stored"
    env_token = get_env_token()
    if env_token:
        return True, "env"
    return False, None


def _hot_reload_client_token(token: str) -> None:
    from minibrew_client import _set_runtime_token
    _set_runtime_token(token)
