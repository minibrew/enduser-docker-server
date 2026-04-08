"""
Background polling loop that keeps the local StateStore in sync with the
MiniBrew API.

PollingWorker runs as an asyncio.Task started during app startup.
Every `poll_interval_ms` milliseconds it calls:
  1. breweryoverview  → updates device state
  2. v1/sessions      → updates session list
  3. v1/kegs          → updates keg list

Each successful poll publishes a "device_update" event to the EventBus,
which in turn triggers WebSocket broadcasts to all connected browsers.

Why polling?
  - The MiniBrew device does not support WebSockets or server-sent events.
  - Polling at 2 s gives acceptable latency for a personal brewing dashboard.
  - Future: replace this with an MQTT listener for lower latency
    (see TODO.md).
"""

import asyncio
from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store
from event_bus import get_event_bus


class PollingWorker:
    """
    Runs a continuous poll loop against the MiniBrew API while the
    application is running.

    The loop runs every `_interval` seconds.  On each iteration it
    fetches breweryoverview, sessions, and kegs and updates the
    shared StateStore.  Then it publishes a "device_update" event
    so the WebSocketManager can push the new state to browsers.
    """

    def __init__(self, client: MiniBrewClient, interval_ms: int = 2000) -> None:
        """
        Args:
            client:      Shared MiniBrewClient instance (already configured
                         with the bearer token).
            interval_ms: How often to poll, in milliseconds.
                         Default 2000 ms (2 seconds).
        """
        self._client = client
        self._interval = interval_ms / 1000.0   # Convert to seconds for sleep().
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background poll loop.  Idempotent – safe to call twice."""
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """
        Stop the poll loop and cancel the background task.

        The try/except asyncio.CancelledError block is required – awaiting
        a cancelled task raises CancelledError, which we treat as normal.
        """
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        """
        Inner loop – runs until stop() sets _running to False.

        Each iteration:
          1. Calls _poll() (updates store + publishes event).
          2. Sleeps for _interval seconds.
        Exceptions in _poll() are swallowed so one bad poll doesn't
        terminate the loop.
        """
        while self._running:
            try:
                await self._poll()
            except Exception:
                # Network glitches, API downtime – just log and continue.
                # StateStore keeps the last known good data.
                pass
            await asyncio.sleep(self._interval)

    async def _poll(self) -> None:
        """
        Fetch latest data from the MiniBrew API and update the state store.

        Each section (overview, sessions, kegs) is independent – if one
        fails the others still update.  The breweryoverview keys
        (brew_clean_idle, fermenting, serving, brew_acid_clean_idle) are
        checked in priority order; the first non-empty bucket drives the
        device state shown in the UI.
        """
        store = get_state_store()
        bus = get_event_bus()

        # ── 1. Device overview ────────────────────────────────────────
        try:
            overview = await self._client.verify()
            for key in ("brew_clean_idle", "fermenting", "serving", "brew_acid_clean_idle"):
                devices: list[dict[str, Any]] = overview.get(key, [])
                if devices:
                    # Attach the raw overview so DeviceService can enrich it.
                    store.set_device_state(
                        "default",
                        {"_raw": overview, "devices": devices},
                    )
                    break
        except Exception:
            pass

        # ── 2. Sessions ────────────────────────────────────────────────
        try:
            sessions_resp = await self._client.get_sessions()
            # The MiniBrew API wraps the list in {"sessions": [...]} or
            # returns a bare list depending on the endpoint version.
            raw_sessions = (
                sessions_resp.get("sessions", [])
                if isinstance(sessions_resp, dict)
                else sessions_resp
            )
            for session_data in raw_sessions:
                session_id = session_data.get("id") or session_data.get("session_id")
                if session_id:
                    store.set_session(str(session_id), session_data)
        except Exception:
            pass

        # ── 3. Kegs ────────────────────────────────────────────────────
        try:
            kegs_resp = await self._client.get_kegs()
            raw_kegs = (
                kegs_resp.get("kegs", [])
                if isinstance(kegs_resp, dict)
                else kegs_resp
            )
            for keg_data in raw_kegs:
                keg_uuid = keg_data.get("uuid") or keg_data.get("id")
                if keg_uuid:
                    store.set_keg(str(keg_uuid), keg_data)
        except Exception:
            pass

        # Notify the EventBus so the WebSocket manager can push to browsers.
        await bus.publish(
            "device_update",
            {
                "sessions": store.list_sessions(),
                "kegs": store.list_kegs(),
            },
        )
