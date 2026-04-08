"""
FastAPI application entry point.

Wires together all services (MiniBrewClient, SessionService, CommandService,
KegService, DeviceService, PollingWorker) on startup and exposes the REST
API + WebSocket endpoint.  All routes are proxied through nginx at
http://localhost:8080 so the browser never calls the backend directly.

The lifespan context manager handles startup (service init, token loading,
first API sync) and shutdown (stop the polling worker cleanly).
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from minibrew_client import MiniBrewClient
from session_service import SessionService
from device_service import DeviceService
from command_service import CommandService
from keg_service import KegService
from polling_worker import PollingWorker
from websocket_manager import get_websocket_manager
from event_bus import get_event_bus
from state_store import get_state_store
from settings_store import (
    get_token as get_stored_token,
    save_token,
    delete_token,
    is_token_set,
)


# ---------------------------------------------------------------------------
# Application lifespan – runs once at startup and once at shutdown.
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:
      1. Load environment (docker-compose env_file sets MINIBREW_API_KEY etc.)
      2. Instantiate MiniBrewClient and all services.
      3. Load any stored token from encrypted disk storage; apply it if present.
      4. Perform a synchronous first sync (breweryoverview) so the device state
         is available immediately on the first WebSocket connection.
      5. Start PollingWorker (background 2-second poll loop).
      6. Subscribe the WebSocket broadcaster to the event bus.

    Shutdown:
      - Cancel the polling task gracefully.
    """
    load_dotenv()

    base_url = os.getenv("MINIBREW_API_BASE", "http://localhost:8080/api")
    api_key = os.getenv("MINIBREW_API_KEY") or None
    poll_interval = int(os.getenv("POLL_INTERVAL_MS", "2000"))

    # Core HTTP client – shared by all services.
    client = MiniBrewClient(base_url, api_key)

    # Service layer – each wraps MiniBrewClient for a specific domain.
    session_svc = SessionService(client)
    keg_svc = KegService(client)
    command_svc = CommandService(client)
    command_svc.set_session_service(session_svc)
    command_svc.set_keg_service(keg_svc)

    # Check if the user has a stored (encrypted) token from the Settings panel.
    # If so, hot-reload it so it overrides the .env token for this session.
    stored = get_stored_token()
    if stored:
        client._runtime_token = stored
        client._rebuild_headers()

    # Attach services to FastAPI app state so route handlers can access them.
    app.state.minibrew_client = client
    app.state.session_service = session_svc
    app.state.device_service = DeviceService(client)
    app.state.command_service = command_svc
    app.state.keg_service = keg_svc

    # First sync – fetch breweryoverview so the WebSocket initial_state
    # is populated when the first browser connects.
    try:
        overview = await client.verify()
        for key in ("brew_clean_idle", "fermenting", "serving", "brew_acid_clean_idle"):
            devices = overview.get(key, [])
            if devices:
                store = get_state_store()
                store.set_device_state(
                    "default",
                    {
                        "_raw": overview,
                        "uuid": devices[0].get("uuid") or devices[0].get("serial_number"),
                    },
                )
                break
    except Exception:
        pass  # PollingWorker will retry on next cycle.

    # Background polling – every poll_interval_ms the worker calls
    # breweryoverview, v1/sessions, and v1/kegs, then publishes a
    # device_update event to the EventBus.
    worker = PollingWorker(client, poll_interval)
    await worker.start()
    app.state.polling_worker = worker

    # Event bus – relays device_update events to the WebSocket manager.
    bus = get_event_bus()
    ws_mgr = get_websocket_manager()

    async def broadcast_device_events(data):
        await ws_mgr.broadcast({"type": "device_update", "payload": data})

    await bus.subscribe("device_update", broadcast_device_events)

    yield  # ── application runs here ──

    # Shutdown: stop the polling loop so uvicorn can exit cleanly.
    await worker.stop()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MiniBrew Session Orchestrator",
    lifespan=lifespan,
)

# Allow cross-origin requests from any host so the browser can call the
# backend regardless of which port nginx is serving from.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health & token settings
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Liveness probe – used by Docker HEALTHCHECK and the nginx proxy."""
    return {"status": "ok"}


@app.get("/settings/token")
async def get_token_status():
    """
    Returns whether a MiniBrew API token is currently active and where
    it is sourced from.

    Response:
      - token_set: bool   – whether any token is available
      - source:    str   – "env" (from .env), "stored" (from Settings panel),
                           or None (no token at all → UI shows token gate)
    """
    token_set, source = is_token_set()
    return {"token_set": token_set, "source": source}


@app.post("/settings/token")
async def set_token(body: dict):
    """
    Save a new MiniBrew API bearer token.

    The token is encrypted with Fernet (AES) and written to
    /app/data/settings.json.  It immediately replaces the active token
    in all MiniBrewClient instances via _set_runtime_token(), so
    subsequent API calls use the new credentials without a restart.
    """
    token = body.get("token", "").strip()
    if not token:
        return {"status": "error", "error": "Token cannot be empty"}
    save_token(token)
    return {"status": "ok", "message": "Token saved and applied"}


@app.delete("/settings/token")
async def reset_token():
    """
    Delete the stored token override and revert all MiniBrewClient
    instances to using the .env token.  Call this when you want to
    stop using a runtime token and go back to the default.
    """
    delete_token()
    return {"status": "ok", "message": "Token reset to .env default"}


# ---------------------------------------------------------------------------
# Device endpoints (proxies to MiniBrew API)
# ---------------------------------------------------------------------------

@app.get("/verify")
async def verify_connection():
    """
    Proxy for GET /breweryoverview/ – the primary device-status endpoint.
    Returns grouped device data keyed by operational bucket
    (brew_clean_idle, fermenting, serving, brew_acid_clean_idle).

    If the MiniBrew API returns an error (401, timeout, etc.) the
    exception is caught and returned as {status: "error", error: ...}.
    """
    client: MiniBrewClient = app.state.minibrew_client
    try:
        result = await client.verify()
        return {"status": "connected", "data": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/devices")
async def list_devices():
    """
    Proxy for GET /devices/ – the secondary device-detail endpoint.
    Returns per-device records with connection_status, current_state,
    process_state, last_time_online, etc.
    """
    client: MiniBrewClient = app.state.minibrew_client
    try:
        devices = await client.get_devices()
        return {"devices": devices}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/device")
async def get_device(device_id: str = "default"):
    """
    Return the enriched device state for the named device_id (default: "default").
    Enriches the raw breweryoverview data with process_state labels,
    phase names, user_action descriptions, and failure indicators from
    the state engine.
    """
    dev_svc: DeviceService = app.state.device_service
    return await dev_svc.sync_device(device_id)


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@app.post("/sessions")
async def create_session(body: dict):
    """
    Create a new MiniBrew session.

    Body fields:
      - session_type:   0=brew, "clean_minibrew", or "acid_clean_minibrew"
      - minibrew_uuid: UUID of the target device
      - beer_recipe:   Optional JSON recipe object (brew sessions only)
    """
    session_svc: SessionService = app.state.session_service
    session_type = body.get("session_type")
    minibrew_uuid = body.get("minibrew_uuid")
    beer_recipe = body.get("beer_recipe")

    if session_type == 0:
        result = await session_svc.create_brew_session(minibrew_uuid, beer_recipe)
    elif session_type == "clean_minibrew":
        result = await session_svc.create_clean_session(minibrew_uuid)
    elif session_type == "acid_clean_minibrew":
        result = await session_svc.create_acid_clean_session(minibrew_uuid)
    else:
        # Default to brew session.
        result = await session_svc.create_brew_session(minibrew_uuid, beer_recipe)
    return result


@app.get("/sessions")
async def list_sessions():
    """Return all sessions currently held in the in-memory state store."""
    session_svc: SessionService = app.state.session_service
    return {"sessions": session_svc.list_sessions()}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """
    Fetch a single session from MiniBrew API and update the store.
    Returns 404 if the session is not found.
    """
    session_svc: SessionService = app.state.session_service
    session = session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    DELETE /v1/sessions/{id} on the MiniBrew API – terminates the session.
    This is the END_SESSION operation.  Also removes the session from
    the local state store so it disappears from the dashboard immediately.
    """
    session_svc: SessionService = app.state.session_service
    return await session_svc.delete_session(session_id)


@app.post("/session/{session_id}/command")
async def session_command(session_id: str, body: dict):
    """
    Send a named command to a session.

    The CommandService validates the command against the session's
    current user_action to ensure the command is allowed in the
    present state (e.g. END_SESSION is always allowed; temperature
    changes are only allowed at fermentation/serving user_actions).

    Body: {command: str, params?: object}
    """
    cmd_svc: CommandService = app.state.command_service
    command = body.get("command")
    params = body.get("params")
    result = await cmd_svc.execute_session_command(session_id, command, params)
    return result


# ---------------------------------------------------------------------------
# Keg endpoints
# ---------------------------------------------------------------------------

@app.get("/kegs")
async def list_kegs():
    """Return all kegs currently in the state store."""
    keg_svc: KegService = app.state.keg_service
    return {"kegs": keg_svc.list_kegs()}


@app.post("/keg/{keg_uuid}/command")
async def keg_command(keg_uuid: str, body: dict):
    """
    Send a named command to a keg.

    Supported commands:
      - PUT_INTO_SERVING_MODE
      - SET_KEG_TEMPERATURE  (params.temperature: float)
      - RESET_KEG
    """
    cmd_svc: CommandService = app.state.command_service
    command = body.get("command")
    params = body.get("params")
    result = await cmd_svc.execute_keg_command(keg_uuid, command, params)
    return result


@app.post("/keg/{keg_uuid}/display-name")
async def keg_display_name(keg_uuid: str, body: dict):
    """
    Update the custom display name of a keg.
    Persisted on the MiniBrew API via PATCH /v1/kegs/{uuid}.
    """
    keg_svc: KegService = app.state.keg_service
    display_name = body.get("display_name")
    result = await keg_svc.update_display_name(keg_uuid, display_name)
    return result


# ---------------------------------------------------------------------------
# WebSocket – real-time push to the browser
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    Browser connects here for real-time state pushes.

    On connection:
      1. Accept the WebSocket upgrade.
      2. Register the connection in WebSocketManager.
      3. Send an 'initial_state' message with all current sessions, kegs,
         and enriched device state so the dashboard is immediately populated.
      4. Enter a receive loop – the only client→server message is 'ping',
         which is answered with 'pong'.  All other messages are ignored.
      5. On disconnect: remove the connection from WebSocketManager.

    After connection, the browser receives:
      - device_update  – broadcast by PollingWorker on every poll cycle
      - session_update – sent when a command changes session state
      - system_event   – sent for notable internal events (errors, resets)
    """
    await ws.accept()
    ws_mgr = get_websocket_manager()
    await ws_mgr.connect(ws)

    store = get_state_store()
    dev_svc: DeviceService = app.state.device_service

    # Build initial_state from whatever is currently in the state store.
    sessions = store.list_sessions()
    kegs = store.list_kegs()
    device = await dev_svc.sync_device()

    await ws.send_json({
        "type": "initial_state",
        "payload": {
            "sessions": sessions,
            "kegs": kegs,
            "device": device,
        },
    })

    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await ws_mgr.disconnect(ws)
