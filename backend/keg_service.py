"""
Keg management – listing, commands, and display name updates.

KegService wraps the MiniBrew keg API (GET /v1/kegs/, POST /v1/kegs/{uuid}/,
PATCH /v1/kegs/{uuid}/) and keeps the local StateStore in sync after
each mutation so the dashboard reflects the latest state immediately.

Supported keg commands:
  - PUT_INTO_SERVING_MODE  – start serving from this keg
  - SET_KEG_TEMPERATURE    – adjust target temperature
  - RESET_KEG              – mark keg as empty / reset state

The display_name is the user-facing label shown on the keg card in the
dashboard (e.g. "IPA Batch 42").  It is persisted on the MiniBrew API
via a PATCH call.
"""

from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store


class KegService:
    """
    All keg operations.  Each mutating method (serving mode, temperature,
    reset, display name) updates the local StateStore after the API call
    succeeds so the WebSocket push shows the new state without waiting
    for the next poll cycle.
    """

    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client

    async def put_into_serving_mode(self, keg_uuid: str) -> dict[str, Any]:
        """
        Transition a keg to serving mode.

        After the API call succeeds we re-fetch the keg to get its
        updated state and store it locally.
        """
        result = await self._client.send_keg_command(keg_uuid, "PUT_INTO_SERVING_MODE")
        keg_data = await self._client.get_keg(keg_uuid)
        get_state_store().set_keg(keg_uuid, keg_data)
        return result

    async def set_keg_temperature(
        self,
        keg_uuid: str,
        temperature: float,
    ) -> dict[str, Any]:
        """
        Set the target temperature for a keg.

        Args:
            keg_uuid:    Target keg UUID.
            temperature: Temperature in degrees Celsius.
        """
        result = await self._client.send_keg_command(
            keg_uuid,
            "SET_KEG_TEMPERATURE",
            {"temperature": temperature},
        )
        keg_data = await self._client.get_keg(keg_uuid)
        get_state_store().set_keg(keg_uuid, keg_data)
        return result

    async def reset_keg(self, keg_uuid: str) -> dict[str, Any]:
        """
        Reset a keg (e.g. after it has been emptied and cleaned).
        The keg returns to a known default state on the MiniBrew device.
        """
        result = await self._client.send_keg_command(keg_uuid, "RESET_KEG")
        keg_data = await self._client.get_keg(keg_uuid)
        get_state_store().set_keg(keg_uuid, keg_data)
        return result

    async def update_display_name(
        self,
        keg_uuid: str,
        display_name: str,
    ) -> dict[str, Any]:
        """
        Set a custom display name on a keg.

        The PATCH /v1/kegs/{uuid} endpoint persists this against the
        MiniBrew API so it survives across sessions and device reboots.

        Args:
            keg_uuid:      Target keg UUID.
            display_name:  Human-readable label (e.g. "IPA Batch 42").
        """
        result = await self._client.update_keg(keg_uuid, {"display_name": display_name})
        get_state_store().set_keg(keg_uuid, result)
        return result

    # ── State store access ──────────────────────────────────────────────

    def list_kegs(self) -> list[dict[str, Any]]:
        """
        Return all kegs from the local cache.
        Populated by PollingWorker on every poll cycle.
        """
        return get_state_store().list_kegs()

    def get_keg(self, keg_uuid: str) -> dict[str, Any] | None:
        """
        Return a cached keg by UUID without hitting the API.
        Returns None if the keg has not been seen yet.
        """
        return get_state_store().get_keg(keg_uuid)
