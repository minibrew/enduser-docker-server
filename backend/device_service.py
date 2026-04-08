"""
Device state enrichment.

DeviceService fetches the raw breweryoverview from the MiniBrew API and
transforms it into an "intelligence" payload that the frontend can render
directly without needing to know MiniBrew's raw field names or codes.

Enrichment includes:
  - process_state label (e.g. 31 → "MASHING")
  - phase name (e.g. 80 → "FERMENTATION")
  - failure flag (71, 84, 93, 109 → True)
  - user_action label (e.g. 12 → "Needs cleaning")
  - allowed command types for the current user_action
  - null-coalesced fields that may be absent on idle devices

This is the canonical enricher – called both on WebSocket connect
(initial_state) and on every poll cycle (device_update) so the store
always holds the enriched view.
"""

from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store
from state_engine import build_state_intelligence


class DeviceService:
    """
    Fetches raw breweryoverview data and enriches it with human-readable
    labels and structured metadata via the state engine.
    """

    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client

    async def sync_device(self, device_id: str = "default") -> dict[str, Any]:
        """
        Fetch the latest breweryoverview, enrich it, and store the result.

        The breweryoverview response is a dict keyed by operational bucket:
          brew_clean_idle, fermenting, serving, brew_acid_clean_idle.
        We take the first device from the first non-empty bucket.

        Args:
            device_id:  Identifies which device slot to store under.
                        Defaults to "default" (the primary/only device).

        Returns:
            The enriched device state dict (same as what is stored).
        """
        store = get_state_store()

        brew_data: dict[str, Any] | None = None
        uuid: str | None = None

        # Try to get a live view; if the API is down keep the last known state.
        try:
            overview = await self._client.verify()
            for key in ("brew_clean_idle", "fermenting", "serving", "brew_acid_clean_idle"):
                devices: list[dict[str, Any]] = overview.get(key, [])
                if devices:
                    brew_data = devices[0]
                    # breweryoverview uses "uuid" or "serial_number".
                    uuid = brew_data.get("uuid") or brew_data.get("serial_number")
                    break
        except Exception:
            pass

        # Enrich raw fields with structured intelligence.
        intelligence = build_state_intelligence(
            state=brew_data.get("process_state", 0) if brew_data else 0,
            user_action=brew_data.get("user_action", 0) if brew_data else 0,
            current_state=brew_data.get("current_state", 0) if brew_data else 0,
        )

        # Build the final device state – null-coalesced fields so the
        # frontend always has something to display (or a known null).
        device_state: dict[str, Any] = {
            **intelligence,
            "uuid":               uuid,
            # breweryoverview uses "title"; v1/devices uses "custom_name".
            "custom_name":        brew_data.get("title") if brew_data else None,
            # breweryoverview uses "stage"; v1/devices uses "text".
            "stage":              brew_data.get("stage") if brew_data else None,
            "software_version":   brew_data.get("software_version") if brew_data else None,
            "online":             brew_data.get("online", False) if brew_data else False,
            "updating":           brew_data.get("updating", False) if brew_data else False,
            "beer_name":          brew_data.get("beer_name") if brew_data else None,
            "beer_style":         brew_data.get("beer_style") if brew_data else None,
            "current_temp":       brew_data.get("current_temp") if brew_data else None,
            "target_temp":        brew_data.get("target_temp") if brew_data else None,
            "_raw":               brew_data,   # Preserved for debug/raw view in UI.
        }

        store.set_device_state(device_id, device_state)
        return device_state

    def get_device(self, device_id: str = "default") -> dict[str, Any]:
        """
        Return the cached enriched device state without hitting the API.
        Use this when you need the last known state without a fresh fetch.
        """
        return get_state_store().get_device_state(device_id)
