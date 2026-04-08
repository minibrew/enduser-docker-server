from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store


USER_ACTION_LABELS: dict[int, str] = {
    0: "None",
    2: "Prepare cleaning",
    3: "Add cleaning agent",
    4: "Fill water",
    5: "Ready to clean",
    12: "Needs cleaning",
    13: "Needs acid cleaning",
    21: "Start brewing",
    22: "Add ingredients",
    23: "Mash in",
    24: "Heat to mash",
    25: "Mash done",
    26: "Prepare fermentation",
    27: "Cool to fermentation",
    28: "Add yeast",
    30: "Fermentation complete",
    31: "Transfer to serving",
    32: "Start cleaning",
    33: "Rinse",
    34: "Acid clean",
    35: "Sanitize",
    36: "Finished cleaning",
    37: "CIP Finished",
}


class SessionService:
    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client

    async def create_brew_session(self, minibrew_uuid: str, beer_recipe: dict[str, Any] | None = None) -> dict[str, Any]:
        data = {
            "minibrew_uuid": minibrew_uuid,
            "session_type": 0,
            "beer_recipe": beer_recipe or {},
        }
        result = await self._client.create_session(data)
        session_id = result.get("id") or result.get("session_id")
        if session_id:
            store = get_state_store()
            store.set_session(str(session_id), result)
        return result

    async def create_clean_session(self, minibrew_uuid: str) -> dict[str, Any]:
        data = {
            "minibrew_uuid": minibrew_uuid,
            "session_type": "clean_minibrew",
        }
        result = await self._client.create_session(data)
        session_id = result.get("id") or result.get("session_id")
        if session_id:
            store = get_state_store()
            store.set_session(str(session_id), result)
        return result

    async def create_acid_clean_session(self, minibrew_uuid: str) -> dict[str, Any]:
        data = {
            "minibrew_uuid": minibrew_uuid,
            "session_type": "acid_clean_minibrew",
        }
        result = await self._client.create_session(data)
        session_id = result.get("id") or result.get("session_id")
        if session_id:
            store = get_state_store()
            store.set_session(str(session_id), result)
        return result

    async def send_command(self, session_id: str, command_type: int, params: dict[str, Any] | None = None) -> dict[str, Any]:
        result = await self._client.send_session_command(session_id, command_type, params)
        store = get_state_store()
        store.set_session(str(session_id), result)
        return result

    async def wake_device(self, session_id: str) -> dict[str, Any]:
        return await self.send_command(session_id, command_type=2)

    async def generic_command(self, session_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.send_command(session_id, command_type=3, params=params)

    async def update_recipe(self, session_id: str, serving_temperature: float | None = None, recipe: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if serving_temperature is not None:
            params["serving_temperature"] = serving_temperature
        if recipe:
            params["beer_recipe"] = recipe
        return await self.send_command(session_id, command_type=6, params=params if params else None)

    async def get_user_action_details(self, session_id: str, action_id: int) -> dict[str, Any]:
        return await self._client.get_user_action(session_id, action_id)

    async def get_session(self, session_id: str) -> dict[str, Any]:
        result = await self._client.get_session(session_id)
        store = get_state_store()
        store.set_session(str(session_id), result)
        return result

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        result = await self._client.delete_session(session_id)
        store = get_state_store()
        store.remove_session(str(session_id))
        return result

    def list_sessions(self) -> list[dict[str, Any]]:
        return get_state_store().list_sessions()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return get_state_store().get_session(session_id)


def user_action_label(action_id: int) -> str:
    return USER_ACTION_LABELS.get(action_id, f"Action {action_id}")