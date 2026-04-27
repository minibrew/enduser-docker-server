"""
Background polling loop that keeps the local StateStore in sync with the
MiniBrew API.

PollingWorker runs as an asyncio.Task started during app startup.
Every `poll_interval_ms` milliseconds it calls:
  1. breweryoverview  → updates device state
  2. v1/sessions     → updates session list
  3. v1/kegs          → updates keg list

Each successful poll publishes a "device_update" event to the EventBus,
which in turn triggers WebSocket broadcasts to all connected browsers.
"""

import asyncio

from minibrew_client import MiniBrewClient
from state_store import get_state_store, BREWERY_BUCKETS
from event_bus import get_event_bus
from state_engine import build_state_intelligence


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

        # ── 1. Device overview (all 4 buckets) ─────────────────────────
        try:
            overview = await self._client.verify()
            store.set_brewery_overview(overview)
            # Only select a device if none is currently selected
            if not store.get_selected_device_uuid():
                for key in BREWERY_BUCKETS:
                    devs = overview.get(key, [])
                    if devs:
                        uuid = devs[0].get("uuid") or devs[0].get("serial_number")
                        if uuid:
                            store.select_device(uuid)
                            break

            for key in BREWERY_BUCKETS:
                devices = overview.get(key, [])
                for d in devices:
                    uuid = d.get("uuid") or d.get("serial_number")
                    if not uuid:
                        continue

                    intelligence = build_state_intelligence(
                        state=d.get("process_state", 0),
                        user_action=d.get("user_action", 0),
                        current_state=d.get("current_state", 0),
                    )
                    device_state = {
                        **intelligence,
                        "uuid": uuid,
                        "custom_name": d.get("title"),
                        "stage": d.get("stage"),
                        "software_version": d.get("software_version"),
                        "online": d.get("online", False),
                        "updating": d.get("updating", False),
                        "beer_name": d.get("beer_name"),
                        "beer_style": d.get("beer_style"),
                        "current_temp": d.get("current_temp"),
                        "target_temp": d.get("target_temp"),
                        "gravity": d.get("gravity"),
                        "session_id": d.get("session_id"),
                        "active_session": d.get("session_id"),
                        "_raw": d,
                        "_bucket": key,
                    }
                    store.set_device_state(uuid, device_state)
        except Exception:
            pass

        # ── 2. Sessions ────────────────────────────────────────────────
        try:
            sessions_resp = await self._client.get_sessions()
            raw = sessions_resp.get("sessions", []) if isinstance(sessions_resp, dict) else sessions_resp
            for sd in raw:
                sid = sd.get("id") or sd.get("session_id")
                if sid:
                    store.set_session(str(sid), sd)
        except Exception:
            pass

        # ── 3. Kegs ───────────────────────────────────────────────────
        try:
            kegs_resp = await self._client.get_kegs()
            raw = kegs_resp.get("kegs", []) if isinstance(kegs_resp, dict) else kegs_resp
            for kd in raw:
                kid = kd.get("uuid") or kd.get("id")
                if kid:
                    store.set_keg(str(kid), kd)
        except Exception:
            pass

        # Broadcast updated state to all WebSocket clients.
        await bus.publish(
            "device_update",
            {
                "sessions": store.list_sessions(),
                "kegs": store.list_kegs(),
                "overview": store.get_brewery_overview(),
                "selected_bucket": store.get_selected_bucket(),
                "selected_uuid": store.get_selected_device_uuid(),
                "devices": store.get_all_devices(),
            },
        )
