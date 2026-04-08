"""
MiniBrew REST API client.

All HTTP calls to api.minibrew.io go through this class. It enforces the
required `client: Breweryportal` header on every request and supports hot-
token-reload so the bearer token can be updated at runtime without
restarting the server.
"""

import httpx
from typing import Any


# Maps numeric command_type values to human-readable names.
# Sent to the MiniBrew API when issuing session commands.
SESSION_COMMAND_TYPES: dict[int, str] = {
    2: "wake_device",
    3: "generic_command",
    6: "update_recipe",
}


class MiniBrewClient:
    # Class-level registry of all active MiniBrewClient instances.
    # Updated by _set_runtime_token / _reset_to_env_token so that a
    # token change is propagated to every instance without a restart.
    _instances: list["MiniBrewClient"] = []

    # Runtime token overrides _api_key for the lifetime of the process.
    # Set when the user saves a new token via the Settings panel.
    _runtime_token: str | None = None

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        """
        Initialise the client with the API base URL and optional bearer token.

        Args:
            base_url:  Root of the MiniBrew API (e.g. https://api.minibrew.io/v1/).
            api_key:   Bearer token from .env — used as the default if no runtime
                       override has been saved via the Settings panel.
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._rebuild_headers()
        # Register this instance so it receives hot-token-reload updates.
        MiniBrewClient._instances.append(self)

    # ------------------------------------------------------------------
    # Internal helpers – build/rebuild the httpx headers dict.
    # Called on init and whenever the active token changes.
    # ------------------------------------------------------------------

    def _rebuild_headers(self) -> None:
        """
        Rebuild the `Authorization` header using whichever token is active:
        runtime override (from Settings panel) first, then the .env fallback.

        All requests carry `client: Breweryportal` as required by the API.
        """
        token = self._runtime_token or self._api_key
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "client": "Breweryportal",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------
    # Core HTTP verbs – each opens a fresh AsyncClient so connections
    # are not shared across concurrent requests.
    # ------------------------------------------------------------------

    async def _get(self, path: str) -> Any:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=15) as client:
            resp = await client.get(path)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=15) as client:
            resp = await client.post(path, json=json)
            resp.raise_for_status()
            return resp.json()

    async def _put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=15) as client:
            resp = await client.put(path, json=json)
            resp.raise_for_status()
            return resp.json()

    async def _delete(self, path: str) -> Any:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=15) as client:
            resp = await client.delete(path)
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Device / overview
    # ------------------------------------------------------------------

    async def verify(self) -> dict[str, Any]:
        """
        Fetch `breweryoverview` – the primary endpoint that groups devices
        by their current operational bucket (brew_clean_idle, fermenting,
        serving, brew_acid_clean_idle).

        Used by PollingWorker to detect state changes every poll cycle.
        """
        return await self._get("/breweryoverview/")

    async def get_devices(self) -> list[dict[str, Any]]:
        """
        Fetch the raw `/devices/` list. Each device carries detailed fields
        including connection_status, current_state, process_state,
        last_time_online, and last_process_state_change.
        """
        return await self._get("/devices/")

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    async def get_sessions(self) -> list[dict[str, Any]]:
        """List all active and recent sessions."""
        return await self._get("/v1/sessions/")

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Fetch a single session by its UUID string."""
        return await self._get(f"/v1/sessions/{session_id}/")

    async def create_session(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new session (brew, clean_minibrew, or acid_clean_minibrew).
        Body must include minibrew_uuid and session_type.
        """
        return await self._post("/v1/sessions/", json=data)

    async def update_session(self, session_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """PUT to an existing session – used for generic_command / update_recipe."""
        return await self._put(f"/v1/sessions/{session_id}/", json=data)

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """
        DELETE a session. This is the END_SESSION operation – terminates
        the session on the MiniBrew device.
        """
        return await self._delete(f"/v1/sessions/{session_id}/")

    async def send_session_command(
        self,
        session_id: str,
        command_type: int,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a typed command to a session.

        Args:
            session_id:   UUID of the target session.
            command_type: 2=wake_device, 3=generic_command, 6=update_recipe.
            params:       Optional payload (e.g. serving_temperature for type 6).

        The command_type is included in the PUT body alongside any params.
        """
        payload: dict[str, Any] = {"command_type": command_type}
        if params:
            payload.update(params)
        return await self._put(f"/v1/sessions/{session_id}/", json=payload)

    async def get_user_action(self, session_id: str, action_id: int) -> dict[str, Any]:
        """
        Fetch operator step-by-step instructions for a given user_action ID.
        Used to surface guidance text to the dashboard.
        """
        return await self._get(f"/v1/sessions/{session_id}/user_actions/{action_id}/")

    # ------------------------------------------------------------------
    # Kegs
    # ------------------------------------------------------------------

    async def get_kegs(self) -> list[dict[str, Any]]:
        """List all registered kegs."""
        return await self._get("/v1/kegs/")

    async def get_keg(self, keg_uuid: str) -> dict[str, Any]:
        """Fetch a single keg by its UUID."""
        return await self._get(f"/v1/kegs/{keg_uuid}/")

    async def send_keg_command(
        self,
        keg_uuid: str,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a command to a keg (e.g. PUT_INTO_SERVING_MODE, SET_KEG_TEMPERATURE).

        Args:
            keg_uuid:  UUID of the target keg.
            command:   Named command string.
            params:    Optional parameters (e.g. temperature value).
        """
        payload: dict[str, Any] = {"command": command}
        if params:
            payload.update(params)
        return await self._post(f"/v1/kegs/{keg_uuid}/", json=payload)

    async def update_keg(self, keg_uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """PATCH a keg record – used for updating the display_name."""
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=15) as client:
            resp = await client.patch(f"/v1/kegs/{keg_uuid}/", json=data)
            resp.raise_for_status()
            return resp.json()


# ---------------------------------------------------------------------------
# Hot-token-reload helpers.
# Called by settings_store.py when the user saves or resets a token via the
# Settings panel. Iterates every registered MiniBrewClient instance and
# rebuilds its headers so the new credentials are used on the next request.
# ---------------------------------------------------------------------------


def _set_runtime_token(token: str | None) -> None:
    """
    Install a runtime token override. This replaces the .env token for all
    subsequent API calls in every active MiniBrewClient instance.

    Args:
        token: The encrypted token from Settings panel, or None to clear.
    """
    MiniBrewClient._runtime_token = token
    for instance in MiniBrewClient._instances:
        instance._rebuild_headers()


def _reset_to_env_token() -> None:
    """
    Remove the runtime token override and revert all client instances to
    using the token from the .env file (read from the OS environment at
    startup or via docker-compose env_file).
    """
    MiniBrewClient._runtime_token = None
    for instance in MiniBrewClient._instances:
        instance._rebuild_headers()
