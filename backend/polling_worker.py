import asyncio
from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store
from event_bus import get_event_bus


class PollingWorker:
    def __init__(self, client: MiniBrewClient, interval_ms: int = 2000) -> None:
        self._client = client
        self._interval = interval_ms / 1000.0
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._poll()
            except Exception:
                pass
            await asyncio.sleep(self._interval)

    async def _poll(self) -> None:
        store = get_state_store()
        bus = get_event_bus()

        try:
            overview = await self._client.verify()
            for key in ("brew_clean_idle", "fermenting", "serving", "brew_acid_clean_idle"):
                devices = overview.get(key, [])
                if devices:
                    store.set_device_state("default", {"_raw": overview, "devices": devices})
                    break
        except Exception:
            pass

        try:
            sessions_resp = await self._client.get_sessions()
            raw_sessions = sessions_resp.get("sessions", []) if isinstance(sessions_resp, dict) else sessions_resp
            for session_data in raw_sessions:
                session_id = session_data.get("id") or session_data.get("session_id")
                if session_id:
                    store.set_session(str(session_id), session_data)
        except Exception:
            pass

        try:
            kegs_resp = await self._client.get_kegs()
            raw_kegs = kegs_resp.get("kegs", []) if isinstance(kegs_resp, dict) else kegs_resp
            for keg_data in raw_kegs:
                keg_uuid = keg_data.get("uuid") or keg_data.get("id")
                if keg_uuid:
                    store.set_keg(str(keg_uuid), keg_data)
        except Exception:
            pass

        await bus.publish("device_update", {"sessions": store.list_sessions(), "kegs": store.list_kegs()})