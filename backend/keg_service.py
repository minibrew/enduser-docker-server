from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store


class KegService:
    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client

    async def put_into_serving_mode(self, keg_uuid: str) -> dict[str, Any]:
        result = await self._client.post_keg_command(keg_uuid, "PUT_INTO_SERVING_MODE")
        store = get_state_store()
        keg_data = await self._client.get_keg(keg_uuid)
        store.set_keg(keg_uuid, keg_data)
        return result

    async def set_keg_temperature(self, keg_uuid: str, temperature: float) -> dict[str, Any]:
        result = await self._client.post_keg_command(keg_uuid, "SET_KEG_TEMPERATURE", {"temperature": temperature})
        store = get_state_store()
        keg_data = await self._client.get_keg(keg_uuid)
        store.set_keg(keg_uuid, keg_data)
        return result

    async def reset_keg(self, keg_uuid: str) -> dict[str, Any]:
        result = await self._client.post_keg_command(keg_uuid, "RESET_KEG")
        store = get_state_store()
        keg_data = await self._client.get_keg(keg_uuid)
        store.set_keg(keg_uuid, keg_data)
        return result

    async def update_display_name(self, keg_uuid: str, display_name: str) -> dict[str, Any]:
        result = await self._client.patch_keg(keg_uuid, {"display_name": display_name})
        store = get_state_store()
        store.set_keg(keg_uuid, result)
        return result

    def list_kegs(self) -> list[dict[str, Any]]:
        return get_state_store().list_kegs()

    def get_keg(self, keg_uuid: str) -> dict[str, Any] | None:
        return get_state_store().get_keg(keg_uuid)