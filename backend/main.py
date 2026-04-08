import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
import httpx
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
from diff_engine import should_broadcast, compute_diff
from settings_store import get_token as get_stored_token, save_token, delete_token, is_token_set


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()

    base_url = os.getenv("MINIBREW_API_BASE", "http://localhost:8080/api")
    api_key = os.getenv("MINIBREW_API_KEY") or None
    poll_interval = int(os.getenv("POLL_INTERVAL_MS", "2000"))

    client = MiniBrewClient(base_url, api_key)
    session_svc = SessionService(client)
    keg_svc = KegService(client)
    command_svc = CommandService(client)
    command_svc.set_session_service(session_svc)
    command_svc.set_keg_service(keg_svc)

    stored = get_stored_token()
    if stored:
        client._runtime_token = stored
        client._rebuild_headers()

    app.state.minibrew_client = client
    app.state.session_service = session_svc
    app.state.device_service = DeviceService(client)
    app.state.command_service = command_svc
    app.state.keg_service = keg_svc

    try:
        overview = await client.verify()
        for key in ("brew_clean_idle", "fermenting", "serving", "brew_acid_clean_idle"):
            devices = overview.get(key, [])
            if devices:
                store.set_device_state("default", {"_raw": overview, "uuid": devices[0].get("uuid") or devices[0].get("serial_number")})
                break
    except Exception:
        pass

    worker = PollingWorker(client, poll_interval)
    await worker.start()
    app.state.polling_worker = worker

    bus = get_event_bus()
    ws_mgr = get_websocket_manager()

    async def broadcast_device_events(data):
        await ws_mgr.broadcast({"type": "device_update", "payload": data})

    await bus.subscribe("device_update", broadcast_device_events)

    yield

    await worker.stop()


app = FastAPI(title="MiniBrew Session Orchestrator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/verify")
async def verify_connection():
    client: MiniBrewClient = app.state.minibrew_client
    try:
        result = await client.verify()
        return {"status": "connected", "data": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/devices")
async def list_devices():
    client: MiniBrewClient = app.state.minibrew_client
    try:
        devices = await client.get_devices()
        return {"devices": devices}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/session/{session_id}/command")
async def session_command(session_id: str, body: dict):
    cmd_svc: CommandService = app.state.command_service
    command = body.get("command")
    params = body.get("params")
    result = await cmd_svc.execute_session_command(session_id, command, params)
    return result


@app.post("/keg/{keg_uuid}/command")
async def keg_command(keg_uuid: str, body: dict):
    cmd_svc: CommandService = app.state.command_service
    command = body.get("command")
    params = body.get("params")
    result = await cmd_svc.execute_keg_command(keg_uuid, command, params)
    return result


@app.post("/keg/{keg_uuid}/display-name")
async def keg_display_name(keg_uuid: str, body: dict):
    keg_svc: KegService = app.state.keg_service
    display_name = body.get("display_name")
    result = await keg_svc.update_display_name(keg_uuid, display_name)
    return result


@app.post("/sessions")
async def create_session(body: dict):
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
        result = await session_svc.create_brew_session(minibrew_uuid, beer_recipe)
    return result


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    session_svc: SessionService = app.state.session_service
    return await session_svc.delete_session(session_id)


@app.get("/sessions")
async def list_sessions():
    session_svc: SessionService = app.state.session_service
    return {"sessions": session_svc.list_sessions()}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session_svc: SessionService = app.state.session_service
    session = session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/kegs")
async def list_kegs():
    keg_svc: KegService = app.state.keg_service
    return {"kegs": keg_svc.list_kegs()}


@app.get("/device")
async def get_device(device_id: str = "default"):
    dev_svc: DeviceService = app.state.device_service
    return await dev_svc.sync_device(device_id)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_mgr = get_websocket_manager()
    await ws_mgr.connect(ws)

    store = get_state_store()
    dev_svc: DeviceService = app.state.device_service

    sessions = store.list_sessions()
    kegs = store.list_kegs()
    device = await dev_svc.sync_device()

    await ws.send_json({
        "type": "initial_state",
        "payload": {
            "sessions": sessions,
            "kegs": kegs,
            "device": device,
        }
    })

    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await ws_mgr.disconnect(ws)


@app.get("/settings/token")
async def get_token_status():
    token_set, source = is_token_set()
    return {"token_set": token_set, "source": source}


@app.post("/settings/token")
async def set_token(body: dict):
    token = body.get("token", "").strip()
    if not token:
        return {"status": "error", "error": "Token cannot be empty"}
    save_token(token)
    return {"status": "ok", "message": "Token saved and applied"}


@app.delete("/settings/token")
async def reset_token():
    delete_token()
    return {"status": "ok", "message": "Token reset to .env default"}