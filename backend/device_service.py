from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store
from state_engine import build_state_intelligence, USER_ACTION_LABELS


class DeviceService:
    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client

    async def sync_device(self, device_id: str = "default") -> dict[str, Any]:
        store = get_state_store()

        brew_data = None
        uuid = None

        try:
            overview = await self._client.verify()
            for key in ("brew_clean_idle", "fermenting", "serving", "brew_acid_clean_idle"):
                devices = overview.get(key, [])
                if devices:
                    brew_data = devices[0]
                    uuid = brew_data.get("uuid") or brew_data.get("serial_number")
                    break
        except Exception:
            pass

        intelligence = build_state_intelligence(
            state=brew_data.get("process_state", 0) if brew_data else 0,
            user_action=brew_data.get("user_action", 0) if brew_data else 0,
            current_state=brew_data.get("current_state", 0) if brew_data else 0,
        )

        device_state = {
            **intelligence,
            "uuid": uuid,
            "custom_name": brew_data.get("title") if brew_data else None,
            "stage": brew_data.get("stage") if brew_data else None,
            "software_version": brew_data.get("software_version") if brew_data else None,
            "online": brew_data.get("online") if brew_data else False,
            "updating": brew_data.get("updating") if brew_data else False,
            "beer_name": brew_data.get("beer_name") if brew_data else None,
            "beer_style": brew_data.get("beer_style") if brew_data else None,
            "current_temp": brew_data.get("current_temp") if brew_data else None,
            "target_temp": brew_data.get("target_temp") if brew_data else None,
            "_raw": brew_data,
        }

        store.set_device_state(device_id, device_state)
        return device_state

    def get_device(self, device_id: str = "default") -> dict[str, Any]:
        return get_state_store().get_device_state(device_id)