"""
In-memory singleton store for all active application state.

StateStore holds the current view of:
  - sessions:     {session_id → session_data}    (from v1/sessions polling)
  - kegs:         {keg_uuid  → keg_data}        (from v1/kegs polling)
  - overview:     full breweryoverview (all 4 buckets, set by PollingWorker)
  - device_state: {device_key → enriched_state}  (enriched breweryoverview per bucket)
  - recipes:      {recipe_id → recipe_data}
  - beers:        {beer_id → beer_data}
  - commands:     {session_id → command_state}  (in-flight command tracking)

All data is ephemeral – it disappears when the backend restarts.
The PollingWorker repopulates it within one poll cycle (~2 s).

Swap-ready: replace get_state_store() with a Redis-backed implementation
to persist state across restarts and support horizontal scaling.
"""

from typing import Any


# Brewery overview bucket names (in priority order for auto-selection).
BREWERY_BUCKETS = (
    "brew_clean_idle",
    "fermenting",
    "serving",
    "brew_acid_clean_idle",
)


class StateStore:
    """
    Singleton in-memory store.  All StateStore() calls return the same
    instance so any service can read/write without passing references around.
    """

    _instance: "StateStore | None" = None
    _initialized: bool = False

    def __new__(cls) -> "StateStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._sessions: dict[str, dict[str, Any]] = {}
        self._kegs: dict[str, dict[str, Any]] = {}
        # Full breweryoverview: {bucket_name: [device, ...], ...}
        self._brewery_overview: dict[str, Any] = {}
        # Enriched device state keyed by UUID
        self._device_state: dict[str, dict[str, Any]] = {}
        # Currently selected device UUID
        self._selected_device_uuid: str | None = None
        # Recipes and beers caches
        self._recipes: dict[str, dict[str, Any]] = {}
        self._beers: dict[str, dict[str, Any]] = {}
        # Tracks in-flight command states per session_id.
        self._command_states: dict[str, str] = {}
        self._initialized = True

    # ── Brewery overview ───────────────────────────────────────────────

    def set_brewery_overview(self, overview: dict[str, Any]) -> None:
        """Store the raw breweryoverview from the API (all 4 buckets)."""
        self._brewery_overview = overview

    def get_brewery_overview(self) -> dict[str, Any]:
        """Return the raw breweryoverview."""
        return self._brewery_overview

    def get_all_devices(self) -> list[dict[str, Any]]:
        """
        Flatten all devices across all buckets.
        Each device carries its bucket key in _bucket metadata.
        """
        devices = []
        for bucket in BREWERY_BUCKETS:
            for dev in self._brewery_overview.get(bucket, []):
                dev = dict(dev)
                dev["_bucket"] = bucket
                devices.append(dev)
        return devices

    def select_bucket(self, bucket: str) -> None:
        """Compatibility: select the first device in this bucket."""
        if bucket in BREWERY_BUCKETS:
            devices = self._brewery_overview.get(bucket, [])
            if devices:
                d = devices[0]
                uuid = d.get("uuid") or d.get("serial_number")
                if uuid:
                    self.select_device(uuid)

    def get_selected_bucket(self) -> str:
        """Compatibility: return the bucket of the selected device."""
        dev = self.get_selected_device()
        if dev:
            # Try to find which bucket this device is in
            for bucket in BREWERY_BUCKETS:
                for d in self._brewery_overview.get(bucket, []):
                    if (d.get("uuid") or d.get("serial_number")) == self._selected_device_uuid:
                        return bucket
        return "brew_clean_idle"

    def select_device(self, uuid: str) -> None:
        """Set the active device by UUID."""
        self._selected_device_uuid = uuid

    def get_selected_device_uuid(self) -> str | None:
        """Return the currently selected device UUID."""
        return self._selected_device_uuid

    def get_selected_device(self) -> dict[str, Any] | None:
        """Return the raw device data for the selected UUID."""
        if not self._selected_device_uuid:
            return None
        for bucket in BREWERY_BUCKETS:
            for d in self._brewery_overview.get(bucket, []):
                if (d.get("uuid") or d.get("serial_number")) == self._selected_device_uuid:
                    return d
        return None

    # ── Device state ───────────────────────────────────────────────────

    def get_device_state(self, uuid_or_bucket: str) -> dict[str, Any]:
        """Return the enriched device state for a UUID (or bucket for compatibility)."""
        if uuid_or_bucket in self._device_state:
            return self._device_state[uuid_or_bucket]
        # Fallback for bucket-based lookups
        for dev in self._device_state.values():
            if dev.get("_bucket") == uuid_or_bucket:
                return dev
        return {}

    def set_device_state(self, uuid: str, data: dict[str, Any]) -> None:
        """Store enriched device state for a UUID."""
        self._device_state[uuid] = data

    def get_any_enriched_device(self) -> dict[str, Any]:
        """Return the first non-empty enriched device state across all buckets."""
        for bucket in BREWERY_BUCKETS:
            state = self._device_state.get(bucket, {})
            if state.get("uuid"):
                return state
        return {}

    # ── Sessions ───────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)

    def set_session(self, session_id: str, data: dict[str, Any]) -> None:
        self._sessions[session_id] = data

    def list_sessions(self) -> list[dict[str, Any]]:
        return list(self._sessions.values())

    def remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    # ── Kegs ──────────────────────────────────────────────────────────

    def get_keg(self, keg_uuid: str) -> dict[str, Any] | None:
        return self._kegs.get(keg_uuid)

    def set_keg(self, keg_uuid: str, data: dict[str, Any]) -> None:
        self._kegs[keg_uuid] = data

    def list_kegs(self) -> list[dict[str, Any]]:
        return list(self._kegs.values())

    # ── Recipes ────────────────────────────────────────────────────────

    def set_recipe(self, recipe_id: str, data: dict[str, Any]) -> None:
        self._recipes[recipe_id] = data

    def get_recipe(self, recipe_id: str) -> dict[str, Any] | None:
        return self._recipes.get(recipe_id)

    def list_recipes(self) -> list[dict[str, Any]]:
        return list(self._recipes.values())

    # ── Beers ──────────────────────────────────────────────────────────

    def set_beer(self, beer_id: str, data: dict[str, Any]) -> None:
        self._beers[beer_id] = data

    def get_beer(self, beer_id: str) -> dict[str, Any] | None:
        return self._beers.get(beer_id)

    def list_beers(self) -> list[dict[str, Any]]:
        return list(self._beers.values())

    # ── Command state ──────────────────────────────────────────────────

    def get_command_state(self, session_id: str) -> str | None:
        return self._command_states.get(session_id)

    def set_command_state(self, session_id: str, state: str) -> None:
        self._command_states[session_id] = state

    def clear_command_state(self, session_id: str) -> None:
        self._command_states.pop(session_id, None)


def get_state_store() -> StateStore:
    return StateStore()
