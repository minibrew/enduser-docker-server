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

Device state is stored per breweryoverview bucket (brew_clean_idle,
fermenting, serving, brew_acid_clean_idle) so the frontend can enumerate
all devices and let the user switch between them.
"""

from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store, BREWERY_BUCKETS
from state_engine import build_state_intelligence


class DeviceService:
    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client

    async def sync_device(self, bucket: str | None = None) -> dict[str, Any]:
        """
        Fetch the latest breweryoverview, enrich all buckets, and store results.

        Args:
            bucket:  Optional bucket key to return as "selected" device.
                     If omitted, returns the first enriched device found.

        Returns:
            The enriched device state dict for the selected bucket.
        """
        store = get_state_store()
        brew_data: dict[str, Any] | None = None
        selected_bucket = bucket or store.get_selected_bucket()

        try:
            overview = await self._client.verify()
            store.set_brewery_overview(overview)

            for key in BREWERY_BUCKETS:
                devices: list[dict[str, Any]] = overview.get(key, [])
                if devices and not brew_data:
                    brew_data = devices[0]
                    # Auto-select first non-empty bucket.
                    if not store.get_selected_bucket():
                        store.select_bucket(key)

            # Build enriched state per bucket.
            for key in BREWERY_BUCKETS:
                devs = overview.get(key, [])
                if not devs:
                    continue
                d = devs[0]
                intelligence = build_state_intelligence(
                    state=d.get("process_state", 0),
                    user_action=d.get("user_action", 0),
                    current_state=d.get("current_state", 0),
                )
                device_state: dict[str, Any] = {
                    **intelligence,
                    "uuid": d.get("uuid") or d.get("serial_number"),
                    "custom_name": d.get("title"),
                    "stage": d.get("stage"),
                    "sub_title": d.get("sub_title"),
                    "software_version": d.get("software_version"),
                    "online": d.get("online", False),
                    "updating": d.get("updating", False),
                    "beer_name": d.get("beer_name"),
                    "beer_style": d.get("beer_style"),
                    "current_temp": d.get("current_temp"),
                    "target_temp": d.get("target_temp"),
                    "gravity": d.get("gravity"),
                    "session_id": d.get("session_id"),
                    "active_session": d.get("session_id"),
                    "image": d.get("image"),
                    "_raw": d,
                    "_bucket": key,
                }
                store.set_device_state(key, device_state)

        except Exception:
            pass

        return store.get_device_state(selected_bucket)

    def get_device(self, bucket: str = "default") -> dict[str, Any]:
        return get_state_store().get_device_state(bucket)

    def get_all_devices(self) -> list[dict[str, Any]]:
        """Return all devices across all buckets with their bucket key."""
        return get_state_store().get_all_devices()

    def get_brewery_overview(self) -> dict[str, Any]:
        return get_state_store().get_brewery_overview()
