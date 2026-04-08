import asyncio
import json
from typing import Any


class WebSocketManager:
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
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: Any) -> None:
        async with self._lock:
            self._connections.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        dead = []
        async with self._lock:
            for conn in self._connections:
                try:
                    await conn.send_text(payload)
                except Exception:
                    dead.append(conn)
            for conn in dead:
                self._connections.remove(conn)

    async def send_personal(self, ws: Any, message: dict[str, Any]) -> None:
        await ws.send_text(json.dumps(message))

    def connection_count(self) -> int:
        return len(self._connections)


def get_websocket_manager() -> WebSocketManager:
    return WebSocketManager()