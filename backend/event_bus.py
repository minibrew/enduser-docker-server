import asyncio
from collections import defaultdict
from typing import Callable, Awaitable, Any


class EventBus:
    _instance: "EventBus | None" = None

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._subscribers: dict[str, list[Callable[[Any], Awaitable[None]]]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._initialized = True

    async def subscribe(self, event: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        async with self._lock:
            self._subscribers[event].append(handler)

    async def publish(self, event: str, data: Any) -> None:
        async with self._lock:
            handlers = list(self._subscribers.get(event, []))
        for handler in handlers:
            try:
                await handler(data)
            except Exception:
                pass

    async def publish_batch(self, events: list[tuple[str, Any]]) -> None:
        for event, data in events:
            await self.publish(event, data)


def get_event_bus() -> EventBus:
    return EventBus()