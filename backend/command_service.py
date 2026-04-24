"""
Command routing and state-aware validation.

CommandService is the gatekeeper for all commands sent to the MiniBrew
device.  Before dispatching any command it checks:

  1. Is a session selected in the UI?  (Guard: END_SESSION is always allowed)
  2. Is the command type permitted given the current user_action?

     If user_action = 12 (Needs cleaning):
       Allowed types: 2 (wake), 3 (generic), 32 (start_clean)
       Blocked types: 6 (update_recipe) → returns error

  3. CHANGE_TEMPERATURE is a special case – it maps to command_type 6
     (update_recipe) and carries a serving_temperature param.

  4. END_SESSION maps to None → delegated to SessionService.delete_session()
     which calls DELETE /v1/sessions/{id}.

Command type reference:
  2 = wake_device       – power on / prepare machine
  3 = generic_command  – NEXT_STEP, BYPASS_USER_ACTION, GO_TO_MASH,
                         GO_TO_BOIL, FINISH_BREW_SUCCESS, FINISH_BREW_FAILURE,
                         CLEAN_AFTER_BREW, BYPASS_CLEAN
  6 = update_recipe    – CHANGE_TEMPERATURE (sends serving_temperature)

The user_action → allowed command types map is defined in state_engine.py
(ALLOWED_COMMANDS_BY_USER_ACTION) and imported here.
"""

from typing import Any

from minibrew_client import MiniBrewClient
from session_service import SessionService
from keg_service import KegService
from state_engine import get_allowed_commands


class CommandService:
    """
    Validates and dispatches all commands (session and keg) to the
    MiniBrew API via SessionService / KegService.

    Two-stage design:
      1. validate against user_action (guard)
      2. dispatch via the appropriate service

    This separation means the guard logic is unit-testable independently
    of the API layer.
    """

    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client
        self._session_svc: SessionService | None = None
        self._keg_svc: KegService | None = None

    def set_session_service(self, svc: SessionService) -> None:
        self._session_svc = svc

    def set_keg_service(self, svc: KegService) -> None:
        self._keg_svc = svc

    # ── Session commands ────────────────────────────────────────────────

    async def execute_session_command(
        self,
        session_id: str,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Validate and dispatch a named session command.

        Args:
            session_id:  UUID of the target session.
            command:     Named command string
                         (END_SESSION, NEXT_STEP, CHANGE_TEMPERATURE, etc.).
            params:      Optional dict (e.g. {serving_temperature: 4.0}).

        Returns:
            {"error": "..."} if validation fails.
            API response dict on success.
        """
        if not self._session_svc:
            return {"error": "SessionService not configured"}

        # Try local cache first; fall back to API fetch.
        session = self._session_svc.get_session_cached(session_id)
        if not session:
            session = await self._session_svc.get_session(session_id)

        # Determine what the device will allow at its current user_action.
        user_action = session.get("user_action", 0) if session else 0
        allowed = get_allowed_commands(int(user_action))

        # Map named command → numeric command_type.
        type_map: dict[str, int | None] = {
            "END_SESSION":          None,   # Special: calls delete_session()
            "NEXT_STEP":            3,
            "BYPASS_USER_ACTION":   3,
            "CHANGE_TEMPERATURE":   6,     # → update_recipe(serving_temperature)
            "GO_TO_MASH":           3,
            "GO_TO_BOIL":           3,
            "FINISH_BREW_SUCCESS":   3,
            "FINISH_BREW_FAILURE":    3,
            "CLEAN_AFTER_BREW":      3,
            "BYPASS_CLEAN":         3,
        }
        cmd_type = type_map.get(command)

        # Guard: if the command requires a specific type, verify it's allowed.
        if cmd_type is not None and cmd_type not in allowed:
            return {
                "error": (
                    f"Command type {cmd_type} ({command}) is not allowed "
                    f"when user_action={user_action}. "
                    f"Allowed: {allowed}"
                ),
                "allowed": allowed,
            }

        # Dispatch.
        if command == "CHANGE_TEMPERATURE":
            return await self._session_svc.update_recipe(
                session_id,
                serving_temperature=params.get("serving_temperature") if params else None,
                recipe=params.get("beer_recipe") if params else None,
            )

        if cmd_type is None:
            # END_SESSION → DELETE /v1/sessions/{id}
            return await self._session_svc.delete_session(session_id)

        # All other commands → generic_command / wake_device / update_recipe
        return await self._session_svc.send_command(session_id, cmd_type, params)

    # ── Keg commands ────────────────────────────────────────────────────

    async def execute_keg_command(
        self,
        keg_uuid: str,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Dispatch a named keg command via KegService.

        Supported:
          PUT_INTO_SERVING_MODE  – start serving
          SET_KEG_TEMPERATURE   – set target temperature (params.temperature)
          RESET_KEG             – reset keg state
        """
        if not self._keg_svc:
            return {"error": "KegService not configured"}

        if command == "PUT_INTO_SERVING_MODE":
            return await self._keg_svc.put_into_serving_mode(keg_uuid)

        if command == "SET_KEG_TEMPERATURE":
            return await self._keg_svc.set_keg_temperature(
                keg_uuid,
                float(params.get("temperature", 0) if params else 0),
            )

        if command == "RESET_KEG":
            return await self._keg_svc.reset_keg(keg_uuid)

        return {"error": f"Unknown keg command: {command}"}
