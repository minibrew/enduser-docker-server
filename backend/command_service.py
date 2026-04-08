from typing import Any

from minibrew_client import MiniBrewClient
from session_service import SessionService
from keg_service import KegService
from state_engine import get_allowed_commands


class CommandService:
    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client
        self._session_svc: SessionService | None = None
        self._keg_svc: KegService | None = None

    def set_session_service(self, svc: SessionService) -> None:
        self._session_svc = svc

    def set_keg_service(self, svc: KegService) -> None:
        self._keg_svc = svc

    async def execute_session_command(self, session_id: str, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._session_svc:
            return {"error": "SessionService not configured"}

        session = self._session_svc.get_session(session_id)
        if not session:
            session = await self._session_svc.get_session(session_id)

        user_action = session.get("user_action", 0) if session else 0
        allowed = get_allowed_commands(int(user_action))

        type_map = {
            "END_SESSION": None,
            "NEXT_STEP": 3,
            "BYPASS_USER_ACTION": 3,
            "CHANGE_TEMPERATURE": 6,
            "GO_TO_MASH": 3,
            "GO_TO_BOIL": 3,
            "FINISH_BREW_SUCCESS": 3,
            "FINISH_BREW_FAILURE": 3,
            "CLEAN_AFTER_BREW": 3,
            "BYPASS_CLEAN": 3,
        }
        cmd_type = type_map.get(command)

        if cmd_type is not None and cmd_type not in allowed:
            return {"error": f"Command type {cmd_type} not allowed for user_action {user_action}", "allowed": allowed}

        if command == "CHANGE_TEMPERATURE":
            return await self._session_svc.update_recipe(session_id,
                serving_temperature=params.get("serving_temperature") if params else None,
                recipe=params.get("beer_recipe") if params else None)

        if cmd_type is None:
            return await self._session_svc.delete_session(session_id)

        return await self._session_svc.send_command(session_id, cmd_type, params)

    async def execute_keg_command(self, keg_uuid: str, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._keg_svc:
            return {"error": "KegService not configured"}

        if command == "PUT_INTO_SERVING_MODE":
            return await self._keg_svc.put_into_serving_mode(keg_uuid)
        if command == "SET_KEG_TEMPERATURE":
            return await self._keg_svc.set_keg_temperature(keg_uuid, params.get("temperature") if params else 0)
        if command == "RESET_KEG":
            return await self._keg_svc.reset_keg(keg_uuid)
        return {"error": f"Unknown keg command: {command}"}