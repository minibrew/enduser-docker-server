"""
In-memory singleton store for all active application state.

StateStore holds the current view of:
  - sessions:  {session_id → session_data}   (from v1/sessions polling)
  - kegs:      {keg_uuid  → keg_data}       (from v1/kegs polling)
  - device:   {device_id → device_state}   (from breweryoverview + enrichment)
  - commands:  {session_id → command_state} (used to track in-flight commands)

All data is ephemeral – it disappears when the backend restarts.
The PollingWorker repopulates it within one poll cycle (~2 s).

Swap-ready: replace get_state_store() with a Redis-backed implementation
to persist state across restarts and support horizontal scaling.
"""

from typing import Any


class StateStore:
    """
    Singleton in-memory store.  All StateStore() calls return the same
    instance so any service can read/write without passing references around.
    """

    _instance: "StateStore | None" = None

    def __new__(cls) -> "StateStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        # Skip re-initialisation on repeated construction.
        if self._initialized:
            return
        self._sessions: dict[str, dict[str, Any]] = {}
        self._kegs: dict[str, dict[str, Any]] = {}
        self._device_state: dict[str, Any] = {}
        # Tracks in-flight command states per session_id.
        # Values: "pending", "success", "error"
        self._command_states: dict[str, str] = {}
        self._initialized = True

    # ── Sessions ──────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return the stored data for a session, or None if not in store."""
        return self._sessions.get(session_id)

    def set_session(self, session_id: str, data: dict[str, Any]) -> None:
        """
        Upsert a session record.  Called by PollingWorker on every poll
        cycle to keep the local cache fresh.
        """
        self._sessions[session_id] = data

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return all session records as a list."""
        return list(self._sessions.values())

    def remove_session(self, session_id: str) -> None:
        """
        Delete a session from the store.  Called after DELETE /sessions/{id}
        succeeds so the session disappears from the UI immediately.
        """
        self._sessions.pop(session_id, None)

    # ── Kegs ────────────────────────────────────────────────────────────

    def get_keg(self, keg_uuid: str) -> dict[str, Any] | None:
        return self._kegs.get(keg_uuid)

    def set_keg(self, keg_uuid: str, data: dict[str, Any]) -> None:
        """Upsert a keg record."""
        self._kegs[keg_uuid] = data

    def list_kegs(self) -> list[dict[str, Any]]:
        return list(self._kegs.values())

    # ── Device ─────────────────────────────────────────────────────────

    def get_device_state(self, device_id: str = "default") -> dict[str, Any]:
        """
        Return the enriched device state for a device.
        Enrichment (phase, labels, failure flag) is done by DeviceService
        before calling set_device_state – this returns exactly what was stored.
        """
        return self._device_state.get(device_id, {})

    def set_device_state(self, device_id: str, data: dict[str, Any]) -> None:
        """
        Store the enriched device state.  Overwrites any previous state
        for this device_id.
        """
        self._device_state[device_id] = data

    # ── Command state ──────────────────────────────────────────────────

    def get_command_state(self, session_id: str) -> str | None:
        """
        Return the command state for a session: "pending", "success", or None.
        Used by the UI to show feedback after sending a command.
        """
        return self._command_states.get(session_id)

    def set_command_state(self, session_id: str, state: str) -> None:
        """Mark a command as pending/success/error for a session."""
        self._command_states[session_id] = state

    def clear_command_state(self, session_id: str) -> None:
        """Reset command state after it has been consumed by the UI."""
        self._command_states.pop(session_id, None)


def get_state_store() -> StateStore:
    """Return the singleton StateStore instance."""
    return StateStore()
