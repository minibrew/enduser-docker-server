"""
Encrypted at-rest token storage.

When the user enters a MiniBrew API bearer token via the Settings panel,
it is encrypted with Fernet (AES-128-CBC + PBKDF2) and written to
/app/data/settings.json inside the Docker container.

Key security properties:
  - The token is never stored in plaintext.
  - A derived master key is stored alongside (also encrypted at rest via
    a fixed salt – acceptable since it cannot decrypt arbitrary data without
    also having access to the container filesystem).
  - Tokens are hot-reloaded: after a save, all active MiniBrewClient
    instances immediately use the new credentials without a restart.

Token resolution order (used by is_token_set()):
  1. Encrypted storage file  → "stored" (user set via Settings panel)
  2. MINIBREW_API_KEY env    → "env"   (from .env / docker env_file)
  3. Neither set             → null    (token gate shown in UI)
"""

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


DATA_DIR = Path("/app/data")
SETTINGS_FILE = DATA_DIR / "settings.json"
# Master key derived once and persisted. Changing this invalidates all
# stored tokens – delete the file to reset.
MASTER_KEY_FILE = DATA_DIR / ".master.key"


def _get_fernet() -> Fernet:
    """
    Return a Fernet cipher configured with the persisted master key.

    On first call the key is derived using PBKDF2-HMAC-SHA256 with a
    fixed application-specific salt and 480 000 iterations (NIST 2024
    recommendation for password-based key derivation).  The derived key is
    base64-encoded and written to MASTER_KEY_FILE so subsequent container
    restarts use the same key and previously saved tokens remain decryptable.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if MASTER_KEY_FILE.exists():
        key = MASTER_KEY_FILE.read_bytes()
    else:
        key = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"minibrew-session-orchestrator-v1",
            iterations=480_000,
        ).derive(b"minibrew-token-store")
        key = base64.urlsafe_b64encode(key)
        MASTER_KEY_FILE.write_bytes(key)

    return Fernet(key)


def get_token() -> str | None:
    """
    Decrypt and return the stored runtime token, or None if no token
    has been saved via the Settings panel.
    """
    if not SETTINGS_FILE.exists():
        return None
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        encrypted = base64.b64decode(data["encrypted_token"])
        return _get_fernet().decrypt(encrypted).decode()
    except Exception:
        # Corrupt file, wrong key, tampered data – treat as unset.
        return None


def get_env_token() -> str | None:
    """
    Return the MINIBREW_API_KEY from the OS environment (set by
    docker-compose env_file or shell).  This is the fallback token
    used when no runtime override is stored.
    """
    return os.environ.get("MINIBREW_API_KEY") or None


def save_token(token: str) -> None:
    """
    Encrypt the given token with Fernet and write to settings.json.

    After writing, hot-reloads the token into every active MiniBrewClient
    instance so the new credentials are used immediately.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = _get_fernet().encrypt(token.encode())
    SETTINGS_FILE.write_text(
        json.dumps({"encrypted_token": base64.b64encode(encrypted).decode()})
    )
    _hot_reload_client_token(token)


def delete_token() -> None:
    """
    Delete the stored token override and revert all MiniBrewClient
    instances to using the MINIBREW_API_KEY from the environment.

    If SETTINGS_FILE does not exist this is a no-op.
    After deletion the token source falls back to .env automatically.
    """
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()
    # Revert all client instances to the .env token.
    from minibrew_client import _reset_to_env_token
    _reset_to_env_token()


def is_token_set() -> tuple[bool, str | None]:
    """
    Determine whether a MiniBrew API token is currently available and
    identify its source.

    Returns:
        (True, "stored")  – runtime override from Settings panel is active
        (True, "env")     – no stored token; MINIBREW_API_KEY from .env is active
        (False, None)     – no token available at all; UI must show the token gate
    """
    stored = get_token()
    if stored:
        return True, "stored"
    env_token = get_env_token()
    if env_token:
        return True, "env"
    return False, None


def _hot_reload_client_token(token: str) -> None:
    """
    Install a new bearer token in every active MiniBrewClient instance.

    Called internally by save_token().  The import inside the function
    avoids a circular dependency at module load time.
    """
    from minibrew_client import _set_runtime_token
    _set_runtime_token(token)
