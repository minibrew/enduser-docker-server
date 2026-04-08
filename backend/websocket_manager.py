"""
Manages all active WebSocket connections to browsers.

WebSocketManager is a singleton that keeps a thread-safe list of connected
client WebSocket objects.  It is called by:
  - main.py (websocket_endpoint) on connect/disconnect
  - PollingWorker via EventBus → broadcast_device_events on device updates

Key design decisions:
  - Uses an asyncio.Lock so concurrent connect/disconnect/broadcast calls
    don't corrupt the connection list.
  - Dead connections (browser closed tab, network drop) are detected and
    removed lazily during broadcast – we don't need a separate heartbeat.
  - Every connected browser receives every device_update – the frontend
    is lightweight enough that full-state diffing isn't needed at the
    WebSocket layer (DiffEngine handles browser-side decisions).
"""

import asyncio
import json
from typing import Any


class WebSocketManager:
    """
    Singleton registry of active WebSocket connections.

    Using a singleton here means the main.py websocket endpoint, the
    PollingWorker, and any future component can all share the same
    connection registry without explicit wiring.
    """

    _instance: "WebSocketManager | None" = None

    def __new__(cls) -> "WebSocketManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._connections: list[Any] = []
        self._lock = asyncio.Lock()
        self._initialized = True

    async def connect(self, ws: Any) -> None:
        """
        Register a new browser WebSocket connection.

        Called from main.py websocket_endpoint when the browser upgrades.
        """
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: Any) -> None:
        """
        Remove a connection when the browser disconnects or the socket errors.
        Uses remove() which is O(n); acceptable given disconnect frequency.
        """
        async with self._lock:
            self._connections.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Send a JSON message to every connected browser.

        Dead connections are pruned after the send attempt – if a browser
        closed the tab the send will raise, and we remove it from the list.

        Args:
            message:  A JSON-serialisable dict (e.g. {type, payload}).
        """
        payload = json.dumps(message)
        dead: list[Any] = []

        async with self._lock:
            conns = list(self._connections)

        for conn in conns:
            try:
                await conn.send_text(payload)
            except Exception:
                dead.append(conn)

        # Remove browsers that went away during the broadcast.
        if dead:
            async with self._lock:
                for conn in dead:
                    self._connections.remove(conn)

    async def send_personal(self, ws: Any, message: dict[str, Any]) -> None:
        """
        Send a message to a single specific connection.
        Used for personal responses (e.g. command acknowledgement).
        """
        await ws.send_text(json.dumps(message))

    def connection_count(self) -> int:
        """Return the number of currently connected browser tabs."""
        return len(self._connections)


def get_websocket_manager() -> WebSocketManager:
    """Return the singleton WebSocketManager instance."""
    return WebSocketManager()
