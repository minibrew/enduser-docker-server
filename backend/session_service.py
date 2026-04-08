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
from state_store import get_state_store


# Duplicate of USER_ACTION_LABELS in state_engine.py – kept here for
# convenience in command-result formatting.  In a future refactor
# this module should import from state_engine directly.
USER_ACTION_LABELS: dict[int, str] = {
    0:  "None",
    2:  "Prepare cleaning",
    3:  "Add cleaning agent",
    4:  "Fill water",
    5:  "Ready to clean",
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

    # ── Read operations ────────────────────────────────────────────────

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """
        Fetch a single session from the API and cache it locally.
        Returns the raw API response.
        """
        result = await self._client.get_session(session_id)
        get_state_store().set_session(str(session_id), result)
        return result

    async def get_user_action_details(
        self,
        session_id: str,
        action_id: int,
    ) -> dict[str, Any]:
        """
        Fetch operator guidance for a specific user_action ID.
        Returns step-by-step instructions the UI can display to the operator.
        """
        return await self._client.get_user_action(session_id, action_id)

    # ── State store access ──────────────────────────────────────────────

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        Return all sessions from the local cache.
        Populated by PollingWorker on every poll cycle.
        """
        return get_state_store().list_sessions()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """
        Return a cached session by ID without hitting the API.
        Returns None if the session has not been seen yet.
        """
        return get_state_store().get_session(session_id)


def user_action_label(action_id: int) -> str:
    """Map a user_action integer to its operator-facing label."""
    return USER_ACTION_LABELS.get(action_id, f"Action {action_id}")
