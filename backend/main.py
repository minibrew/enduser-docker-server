"""
FastAPI application entry point.

Wires together all services (MiniBrewClient, SessionService, CommandService,
KegService, DeviceService, RecipeService, PollingWorker) on startup and
exposes the REST API + WebSocket endpoint.

The lifespan context manager handles startup (service init, token loading,
first API sync) and shutdown (stop the polling worker cleanly).
"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from minibrew_client import MiniBrewClient
from session_service import SessionService
from device_service import DeviceService
from command_service import CommandService
from keg_service import KegService
from recipe_service import RecipeService
from polling_worker import PollingWorker
from websocket_manager import get_websocket_manager
from event_bus import get_event_bus
from state_store import get_state_store, BREWERY_BUCKETS
from settings_store import (
    get_token as get_stored_token,
    save_token,
    delete_token,
    is_token_set,
)
from auth_service import (
    ensure_started as ensure_auth_started,
    authenticate_user,
    create_user,
    verify_token,
    make_tokens_for_user,
    get_user_by_id,
)
from audit_service import (
    ensure_started as ensure_audit_started,
    log_action,
    get_logs,
    get_log_count,
)


# ---------------------------------------------------------------------------
# JWT auth
# ---------------------------------------------------------------------------

security = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    user_id: int
    username: str


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> AuthUser | None:
    """
    Validate the JWT in the Authorization header.
    Returns an AuthUser if valid, None if no token provided.
    Raises HTTPException 401 if the token is invalid/expired.
    """
    if not creds:
        return None
    payload = verify_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    try:
        return AuthUser(user_id=int(payload["sub"]), username=payload["username"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")


async def require_current_user(
    user: AuthUser | None = Depends(get_current_user),
) -> AuthUser:
    """Require a valid JWT — 401 if missing or invalid."""
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AuditQueryParams:
    def __init__(
        self,
        limit: int = 100,
        offset: int = 0,
        user_id: int | None = None,
        action_type: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ):
        self.limit = min(limit, 500)
        self.offset = offset
        self.user_id = user_id
        self.action_type = action_type
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.result = result
        self.start_time = start_time
        self.end_time = end_time


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()

    await ensure_auth_started()
    await ensure_audit_started()

    base_url = os.getenv("MINIBREW_API_BASE", "http://localhost:8080/api")
    api_key = os.getenv("MINIBREW_API_KEY") or None
    poll_interval = int(os.getenv("POLL_INTERVAL_MS", "2000"))

    client = MiniBrewClient(base_url, api_key)

    session_svc = SessionService(client)
    keg_svc = KegService(client)
    recipe_svc = RecipeService(client)
    dev_svc = DeviceService(client)
    command_svc = CommandService(client)
    command_svc.set_session_service(session_svc)
    command_svc.set_keg_service(keg_svc)

    stored = get_stored_token()
    if stored:
        client._runtime_token = stored
        client._rebuild_headers()

    app.state.minibrew_client = client
    app.state.session_service = session_svc
    app.state.device_service = dev_svc
    app.state.command_service = command_svc
    app.state.keg_service = keg_svc
    app.state.recipe_service = recipe_svc

    try:
        overview = await client.verify()
        store = get_state_store()
        store.set_brewery_overview(overview)
        for key in BREWERY_BUCKETS:
            if overview.get(key):
                store.select_bucket(key)
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


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MiniBrew Session Orchestrator",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Public endpoints (no auth required)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Auth ────────────────────────────────────────────────────────────────────

@app.post("/auth/register")
async def register(body: RegisterRequest):
    """Register a new dashboard user."""
    try:
        user = await create_user(body.username, body.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    await log_action(
        action_type="auth_register",
        resource_type="auth",
        resource_id=str(user["id"]),
        result="success",
        user_id=user["id"],
        username=user["username"],
    )
    tokens = make_tokens_for_user(user)
    return {"user": {"id": user["id"], "username": user["username"]}, **tokens}


@app.post("/auth/login")
async def login(body: LoginRequest):
    """Authenticate and receive JWT access + refresh tokens."""
    user = await authenticate_user(body.username, body.password)
    if not user:
        await log_action(
            action_type="auth_login",
            resource_type="auth",
            result="error",
            details={"username": body.username, "reason": "invalid credentials"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    tokens = make_tokens_for_user(user)
    await log_action(
        action_type="auth_login",
        resource_type="auth",
        resource_id=str(user["id"]),
        result="success",
        user_id=user["id"],
        username=user["username"],
    )
    return {"user": {"id": user["id"], "username": user["username"]}, **tokens}


@app.post("/auth/refresh")
async def refresh(body: RefreshRequest):
    """Exchange a valid refresh token for a new access token."""
    payload = verify_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    try:
        user = await get_user_by_id(int(payload["sub"]))
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    tokens = make_tokens_for_user(user)
    await log_action(
        action_type="token_refresh",
        resource_type="auth",
        resource_id=str(user["id"]),
        result="success",
        user_id=user["id"],
        username=user["username"],
    )
    return {"user": {"id": user["id"], "username": user["username"]}, **tokens}


@app.get("/auth/me")
async def me(user: AuthUser = Depends(require_current_user)):
    """Return the currently authenticated user's info."""
    return {"id": user.user_id, "username": user.username}


# ── Token settings (still public — drives the token gate) ─────────────────

@app.get("/settings/token")
async def get_token_status():
    token_set, source = is_token_set()
    return {"token_set": token_set, "source": source}


@app.post("/settings/token")
async def set_token(body: dict, user: AuthUser = Depends(require_current_user)):
    token = body.get("token", "").strip()
    if not token:
        return {"status": "error", "error": "Token cannot be empty"}
    save_token(token)
    await log_action(
        action_type="minibrew_token_update",
        resource_type="auth",
        result="success",
        user_id=user.user_id,
        username=user.username,
        details={"source": "settings_panel"},
    )
    return {"status": "ok", "message": "Token saved and applied"}


@app.delete("/settings/token")
async def reset_token(user: AuthUser = Depends(require_current_user)):
    delete_token()
    await log_action(
        action_type="minibrew_token_reset",
        resource_type="auth",
        result="success",
        user_id=user.user_id,
        username=user.username,
    )
    return {"status": "ok", "message": "Token reset to .env default"}


# ---------------------------------------------------------------------------
# Protected endpoints (auth required)
# ---------------------------------------------------------------------------

# ── Device & overview ──────────────────────────────────────────────────────

@app.get("/verify")
async def verify_connection(user: AuthUser = Depends(require_current_user)):
    client: MiniBrewClient = app.state.minibrew_client
    try:
        result = await client.verify()
        return {"status": "connected", "data": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/devices")
async def list_devices(user: AuthUser = Depends(require_current_user)):
    client: MiniBrewClient = app.state.minibrew_client
    try:
        devices = await client.get_devices()
        return {"devices": devices}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/device")
async def get_device(bucket: str = "", user: AuthUser = Depends(require_current_user)):
    dev_svc: DeviceService = app.state.device_service
    if bucket and bucket in BREWERY_BUCKETS:
        return dev_svc.get_device(bucket)
    return dev_svc.get_device(get_state_store().get_selected_bucket())


@app.get("/devices/all")
async def get_all_devices(user: AuthUser = Depends(require_current_user)):
    dev_svc: DeviceService = app.state.device_service
    overview = dev_svc.get_brewery_overview()
    selected = get_state_store().get_selected_bucket()
    devices = []
    for key in BREWERY_BUCKETS:
        for dev in overview.get(key, []):
            d = dict(dev)
            d["_bucket"] = key
            devices.append(d)
    return {"devices": devices, "selected": selected}


@app.post("/device/select")
async def select_device_bucket(body: dict, user: AuthUser = Depends(require_current_user)):
    bucket = body.get("bucket", "")
    if bucket not in BREWERY_BUCKETS:
        return {"status": "error", "error": f"Invalid bucket. Use one of: {list(BREWERY_BUCKETS)}"}
    store = get_state_store()
    store.select_bucket(bucket)
    dev_svc: DeviceService = app.state.device_service
    await log_action(
        action_type="device_select",
        resource_type="device",
        resource_id=bucket,
        result="success",
        user_id=user.user_id,
        username=user.username,
        details={"bucket": bucket},
    )
    return {"status": "ok", "bucket": bucket, "device": dev_svc.get_device(bucket)}


# ── Sessions ───────────────────────────────────────────────────────────────

@app.post("/sessions")
async def create_session(body: dict, user: AuthUser = Depends(require_current_user)):
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

    sid = result.get("id") or result.get("session_id")
    await log_action(
        action_type="session_create",
        resource_type="session",
        resource_id=str(sid) if sid else None,
        result="success" if sid else "error",
        user_id=user.user_id,
        username=user.username,
        device_uuid=minibrew_uuid,
        details={"session_type": session_type, "beer_recipe": beer_recipe},
    )
    return result


@app.get("/sessions")
async def list_sessions(user: AuthUser = Depends(require_current_user)):
    session_svc: SessionService = app.state.session_service
    return {"sessions": session_svc.list_sessions()}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str, user: AuthUser = Depends(require_current_user)):
    session_svc: SessionService = app.state.session_service
    session = session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: AuthUser = Depends(require_current_user)):
    session_svc: SessionService = app.state.session_service
    result = await session_svc.delete_session(session_id)
    await log_action(
        action_type="session_delete",
        resource_type="session",
        resource_id=session_id,
        result="success",
        user_id=user.user_id,
        username=user.username,
    )
    return result


@app.post("/sessions/{session_id}/wake-then-delete")
async def wake_then_delete_session(session_id: str, user: AuthUser = Depends(require_current_user)):
    session_svc: SessionService = app.state.session_service
    await session_svc.wake_device(session_id)
    import asyncio
    await asyncio.sleep(1)
    result = await session_svc.delete_session(session_id)
    await log_action(
        action_type="session_delete",
        resource_type="session",
        resource_id=session_id,
        result="success",
        user_id=user.user_id,
        username=user.username,
        details={"method": "wake_then_delete"},
    )
    return result


@app.post("/session/{session_id}/command")
async def session_command(
    session_id: str,
    body: dict,
    user: AuthUser = Depends(require_current_user),
):
    cmd_svc: CommandService = app.state.command_service
    command = body.get("command")
    params = body.get("params")
    result = await cmd_svc.execute_session_command(session_id, command, params)
    is_error = result.get("error") is not None
    await log_action(
        action_type="session_command",
        resource_type="session",
        resource_id=session_id,
        command=command,
        result="error" if is_error else "success",
        user_id=user.user_id,
        username=user.username,
        details={"params": params, "error": result.get("error")},
    )
    return result


@app.get("/sessions/{session_id}/user-action/{action_id}")
async def get_session_user_action(
    session_id: str,
    action_id: int,
    user: AuthUser = Depends(require_current_user),
):
    client: MiniBrewClient = app.state.minibrew_client
    try:
        result = await client.get_user_action_steps(str(session_id), action_id)
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/sessions/{session_id}/cleaning-logs")
async def get_session_cleaning_logs(session_id: str, user: AuthUser = Depends(require_current_user)):
    client: MiniBrewClient = app.state.minibrew_client
    try:
        result = await client.get_cleaning_logs(str(session_id))
        return result
    except Exception as e:
        return {"error": str(e)}


# ── Kegs ──────────────────────────────────────────────────────────────────

@app.get("/kegs")
async def list_kegs(user: AuthUser = Depends(require_current_user)):
    keg_svc: KegService = app.state.keg_service
    return {"kegs": keg_svc.list_kegs()}


@app.post("/keg/{keg_uuid}/command")
async def keg_command(
    keg_uuid: str,
    body: dict,
    user: AuthUser = Depends(require_current_user),
):
    cmd_svc: CommandService = app.state.command_service
    command = body.get("command")
    params = body.get("params")
    result = await cmd_svc.execute_keg_command(keg_uuid, command, params)
    is_error = result.get("error") is not None
    await log_action(
        action_type="keg_command",
        resource_type="keg",
        resource_id=keg_uuid,
        command=command,
        result="error" if is_error else "success",
        user_id=user.user_id,
        username=user.username,
        details={"params": params, "error": result.get("error")},
    )
    return result


@app.post("/keg/{keg_uuid}/display-name")
async def keg_display_name(keg_uuid: str, body: dict, user: AuthUser = Depends(require_current_user)):
    keg_svc: KegService = app.state.keg_service
    display_name = body.get("display_name")
    result = await keg_svc.update_display_name(keg_uuid, display_name)
    await log_action(
        action_type="keg_update",
        resource_type="keg",
        resource_id=keg_uuid,
        result="success",
        user_id=user.user_id,
        username=user.username,
        details={"display_name": display_name},
    )
    return result


# ── Beer & recipe ─────────────────────────────────────────────────────────

@app.get("/beers")
async def list_beers(user_id: int = 1, user: AuthUser = Depends(require_current_user)):
    client: MiniBrewClient = app.state.minibrew_client
    try:
        result = await client.get_beers(user_id)
        return {"beers": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/beer-styles")
async def list_beer_styles(user: AuthUser = Depends(require_current_user)):
    client: MiniBrewClient = app.state.minibrew_client
    try:
        result = await client.get_beer_styles()
        return {"beer_styles": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/recipes")
async def list_recipes(beer_id: int | None = None, user: AuthUser = Depends(require_current_user)):
    recipe_svc: RecipeService = app.state.recipe_service
    if beer_id:
        try:
            api_recipes = await recipe_svc.list_recipes()
            return {"recipes": api_recipes}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return {"recipes": recipe_svc.list_cached_recipes()}


@app.get("/recipes/{recipe_id}")
async def get_recipe(recipe_id: str, user: AuthUser = Depends(require_current_user)):
    recipe_svc: RecipeService = app.state.recipe_service
    try:
        detail = await recipe_svc.get_recipe(recipe_id)
        steps = await recipe_svc.get_recipe_steps(recipe_id)
        return {"recipe": detail, "steps": steps}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/recipes/{recipe_id}/steps")
async def get_recipe_steps(recipe_id: str, user: AuthUser = Depends(require_current_user)):
    recipe_svc: RecipeService = app.state.recipe_service
    try:
        steps = await recipe_svc.get_recipe_steps(recipe_id)
        return {"steps": steps}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Audit log ──────────────────────────────────────────────────────────────

@app.get("/audit/log")
async def audit_log(
    limit: int = 100,
    offset: int = 0,
    user_id: int | None = None,
    action_type: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    result: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    user: AuthUser = Depends(require_current_user),
):
    """
    Retrieve audit log entries with optional filters.

    Query params:
      limit, offset — pagination
      user_id, action_type, resource_type, resource_id, result — filters
      start_time, end_time — ISO 8601 UTC timestamp range
    """
    logs = await get_logs(
        limit=limit,
        offset=offset,
        user_id=user_id,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        start_time=start_time,
        end_time=end_time,
    )
    total = await get_log_count(
        user_id=user_id,
        action_type=action_type,
        resource_type=resource_type,
        start_time=start_time,
        end_time=end_time,
    )
    return {"logs": logs, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# WebSocket (no JWT — WS doesn't support Bearer auth; rely on token gate UI)
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_mgr = get_websocket_manager()
    await ws_mgr.connect(ws)

    store = get_state_store()
    dev_svc: DeviceService = app.state.device_service

    try:
        await dev_svc.sync_device()
        sessions = store.list_sessions()
        kegs = store.list_kegs()
    except Exception:
        sessions = store.list_sessions()
        kegs = store.list_kegs()

    overview = store.get_brewery_overview()
    selected = store.get_selected_bucket()
    all_devices = store.get_all_devices()
    selected_device = store.get_device_state(selected) if selected else {}

    await ws.send_json({
        "type": "initial_state",
        "payload": {
            "sessions": sessions,
            "kegs": kegs,
            "overview": overview,
            "selected_bucket": selected,
            "devices": all_devices,
            "device": selected_device,
        },
    })

    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif data.get("type") == "select_bucket":
                bucket = data.get("bucket", "")
                if bucket in BREWERY_BUCKETS:
                    store.select_bucket(bucket)
                    await ws.send_json({
                        "type": "bucket_changed",
                        "payload": {
                            "bucket": bucket,
                            "device": store.get_device_state(bucket),
                            "sessions": store.list_sessions(),
                        },
                    })
    except WebSocketDisconnect:
        await ws_mgr.disconnect(ws)
