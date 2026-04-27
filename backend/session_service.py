"""
Session CRUD and command dispatch.

SessionService handles the business logic for all session operations:
  - Creating brew, clean, and acid-clean sessions
  - Sending typed commands (wake, generic, update_recipe)
  - Fetching individual session details
  - Deleting sessions (END_SESSION)

All write operations immediately update the local StateStore so the
WebSocket push reflects the latest state without waiting for the next poll.

Session creation:
  - POST /v1/sessions/ with minibrew_uuid and session_type
  - Supported types: 0 (brew), "clean_minibrew", "acid_clean_minibrew"
  - Brew sessions accept an optional beer_recipe JSON blob

END_SESSION:
  - Calls DELETE /v1/sessions/{id} on the MiniBrew API
  - Removes the session from local StateStore so it disappears from UI
"""

from typing import Any

from minibrew_client import MiniBrewClient
from state_engine import USER_ACTION_LABELS
from state_store import get_state_store


class SessionService:
    """
    All session-oriented operations.  Thin wrapper around MiniBrewClient
    that also manages the local StateStore cache.
    """

    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client

    # ── Session lifecycle ────────────────────────────────────────────────

    async def create_brew_session(
        self,
        minibrew_uuid: str,
        beer_recipe: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Start a new brewing session.

        Args:
            minibrew_uuid: UUID of the target MiniBrew device.
            beer_recipe:   Optional JSON blob (name, style, hops, etc.).
        """
        data = {
            "minibrew_uuid": minibrew_uuid,
            "session_type": 0,
            "beer_recipe": beer_recipe or {},
        }
        result = await self._client.create_session(data)
        session_id = result.get("id") or result.get("session_id")
        if session_id:
            get_state_store().set_session(str(session_id), result)
        return result

    async def create_clean_session(self, minibrew_uuid: str) -> dict[str, Any]:
        """Start a clean-minibrew (alkaline CIP) session."""
        data = {
            "minibrew_uuid": minibrew_uuid,
            "session_type": "clean_minibrew",
        }
        result = await self._client.create_session(data)
        session_id = result.get("id") or result.get("session_id")
        if session_id:
            get_state_store().set_session(str(session_id), result)
        return result

    async def create_acid_clean_session(self, minibrew_uuid: str) -> dict[str, Any]:
        """Start an acid-clean session."""
        data = {
            "minibrew_uuid": minibrew_uuid,
            "session_type": "acid_clean_minibrew",
        }
        result = await self._client.create_session(data)
        session_id = result.get("id") or result.get("session_id")
        if session_id:
            get_state_store().set_session(str(session_id), result)
        return result

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """
        Terminate a session (END_SESSION).

        Calls DELETE /v1/sessions/{id} and removes the session from
        the local StateStore so it disappears from the UI immediately
        without waiting for the next poll.
        """
        result = await self._client.delete_session(session_id)
        get_state_store().remove_session(str(session_id))
        return result

    # ── Command dispatch ─────────────────────────────────────────────────

    async def send_command(
        self,
        session_id: str,
        command_type: int,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Low-level command sender.  Use this for generic_command (type 3)
        or wake_device (type 2).

        Args:
            session_id:    Target session UUID.
            command_type:  2 (wake) or 3 (generic).
            params:         Optional dict (e.g. {serving_temperature: 4.0}).
        """
        result = await self._client.send_session_command(session_id, command_type, params)
        get_state_store().set_session(str(session_id), result)
        return result

    async def wake_device(self, session_id: str) -> dict[str, Any]:
        """Send command_type=2 (wake_device) – power on / start the machine."""
        return await self.send_command(session_id, command_type=2)

    async def generic_command(
        self,
        session_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send command_type=3 (generic_command) – NEXT_STEP, GO_TO_MASH, etc."""
        return await self.send_command(session_id, command_type=3, params=params)

    async def update_recipe(
        self,
        session_id: str,
        serving_temperature: float | None = None,
        recipe: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send command_type=6 (update_recipe).

        The MiniBrew API uses this for CHANGE_TEMPERATURE – the
        serving_temperature param updates the target fermentation/serving temp.

        Args:
            session_id:            Target session UUID.
            serving_temperature:   New target temperature in °C.
            recipe:                Optional recipe override blob.
        """
        params: dict[str, Any] = {}
        if serving_temperature is not None:
            params["serving_temperature"] = serving_temperature
        if recipe:
            params["beer_recipe"] = recipe
        return await self.send_command(
            session_id,
            command_type=6,
            params=params if params else None,
        )

    async def associate_keg(self, session_id: str, keg_uuid: str) -> dict[str, Any]:
        """
        Associate a SmartKeg with an active session.
        Sends PUT /v1/sessions/{id}/ with {"keg_uuid": keg_uuid}.
        """
        data = {"keg_uuid": keg_uuid}
        result = await self._client.update_session(session_id, data)
        get_state_store().set_session(str(session_id), result)
        return result

    # ── Read operations ────────────────────────────────────────────────

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """
        Fetch a single session from the API and cache it locally.
        Returns the raw API response.
        """
        result = await self._client.get_session(session_id)
        get_state_store().set_session(str(session_id), result)
        return result

    def get_session_cached(self, session_id: str) -> dict[str, Any] | None:
        """Return a session from the local cache without hitting the API."""
        return get_state_store().get_session(str(session_id))

    async def get_user_action_steps(
        self,
        session_id: str,
        action_id: int,
    ) -> dict[str, Any]:
        """
        Fetch step-by-step operator guidance for a specific user_action ID.
        Returns title, description, and action_steps[] with images/videos.
        """
        return await self._client.get_user_action_steps(str(session_id), action_id)

    async def get_cleaning_logs(self, session_id: str) -> dict[str, Any]:
        """Fetch cleaning process logs for a session."""
        return await self._client.get_cleaning_logs(str(session_id))

    # ── State store access ──────────────────────────────────────────────

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        Return all sessions from the local cache.
        Populated by PollingWorker on every poll cycle.
        """
        return get_state_store().list_sessions()


def user_action_label(action_id: int) -> str:
    """Map a user_action integer to its operator-facing label."""
    return USER_ACTION_LABELS.get(action_id, f"Action {action_id}")
