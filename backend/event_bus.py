"""
Internal publish/subscribe event bus.

Services use the EventBus to communicate without hard dependencies:
the PollingWorker publishes "device_update" events and the
WebSocketManager subscribes to them – neither imports the other directly.

Topics (strings) map to a list of async handler callables.
Handlers are invoked sequentially; exceptions are swallowed so one
bad handler can't break the rest.
"""

import asyncio
from collections import defaultdict
from typing import Callable, Awaitable, Any


class EventBus:
    """
    Singleton async event bus.  Handlers are coroutines (not blocking
    functions) so publish() can await them all without blocking the caller.

    Thread-safety: uses an asyncio.Lock for subscribe/unsubscribe operations.
    """

    _instance: "EventBus | None" = None
    _initialized: bool = False

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        # event_name → [handler1, handler2, ...]
        self._subscribers: dict[str, list[Callable[[Any], Awaitable[None]]]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._initialized = True

    async def subscribe(
        self,
        event: str,
        handler: Callable[[Any], Awaitable[None]],
    ) -> None:
        """
        Register a handler to be called whenever the named event is published.

        Args:
            event:    Topic name (e.g. "device_update").
            handler:  Async callable that accepts the event payload (Any).
        """
        async with self._lock:
            self._subscribers[event].append(handler)

    async def publish(self, event: str, data: Any) -> None:
        """
        Invoke all handlers registered for this event with the given data.

        Handlers are called sequentially (not concurrently) and in the order
        they were subscribed.  Exceptions are caught and ignored so a
        misbehaving handler can't break the bus or the caller.
        """
        async with self._lock:
            handlers = list(self._subscribers.get(event, []))
        for handler in handlers:
            try:
                await handler(data)
            except Exception:
                pass

    async def publish_batch(self, events: list[tuple[str, Any]]) -> None:
        """
        Publish multiple events sequentially.
        Convenience method; individual publishes would work equally well.
        """
        for event, data in events:
            await self.publish(event, data)


def get_event_bus() -> EventBus:
    """Return the singleton EventBus instance."""
    return EventBus()
