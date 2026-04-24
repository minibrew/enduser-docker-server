# Operator & Maintainer Guide

This file captures everything you need to know to operate, debug, and extend the MiniBrew Session Orchestrator that isn't obvious from the code alone.

---

## First Things First — Token is Everything

The single most common failure mode: **sessions showing empty, device info stale, or all commands failing with 401 errors** → the API token is expired or wrong.

```
Symptoms:
  - /sessions returns [] even though you know there are active sessions
  - /verify returns {status: "error", error: "Token is invalid or expired"}
  - Delete/wake commands fail silently or return 401

Fix:
  1. Update MINIBREW_API_KEY in .env, then:
       ./minibrew.ps1 rebuild
  2. Or enter a new token via the dashboard Settings panel (⚙) — this
     saves an encrypted copy that overrides .env without rebuilding
```

**Token tip:** Never log or commit API tokens. The server encrypts tokens saved via the Settings panel at rest using Fernet (AES-128-CBC).

---

## Known Bugs & Quirks

### 1. Sessions List Shows All Sessions
The polling worker fetches **all** sessions from `GET /v1/sessions/` — this includes sessions that are finished (status 4 = done), failed (status 6), or pending cleaning. The sessions dropdown shows all of them sorted by ID (highest first). There is currently no active-only filter.

**Status values observed:**
| Status | Meaning |
|--------|---------|
| 1 | Active |
| 2 | In-progress |
| 4 | Completed / done |
| 6 | Failed / cancelled |

### 2. Delete Session Requires Wake First
Some sessions (device in "Needs cleaning" state, user_action=12) reject a DELETE immediately — the device must be woken first. The **Delete Session** button does this automatically: wake (type 2) → 1 second wait → DELETE.

### 3. `process_type` Map
```
0 = Brewing
1 = Fermentation
2 = Cleaning
```
Note: some sessions in the API show `process_type: 5` which is not mapped — these are climate/keg-type devices.

### 4. `breweryoverview` — The Primary Device Source
The `breweryoverview` endpoint (no `/v1/` prefix) returns the **4-bucket view** and is the primary source for device state. `GET /v1/devices/` is supplementary — it may not reflect real-time state as it is only polled alongside sessions. Do not rely on `v1/devices` for live device state.

### 5. Active Session Detection
`active_session` on a device in `breweryoverview` is the device's **currently active session ID**. A session is considered "active on device" when `String(session.id) === String(device.active_session)`. The active session is marked with ★ in the sessions dropdown.

### 6. Auth is Bypassed
`get_current_user()` in `main.py` returns a hardcoded `AuthUser(user_id=1, username="admin")` — all auth endpoints work (register/login/refresh/me) but JWT validation is skipped. This is intentional for single-user mode. All protected endpoints accept any request without a real token check.

---

## Key Files & What They Do

```
backend/
├── main.py               # FastAPI app, all routes, lifespan startup/shutdown
├── minibrew_client.py    # httpx wrapper — ALL calls to api.minibrew.io go here
├── session_service.py    # Brew/clean/acid-create, send_command, delete_session
├── command_service.py    # Command routing + user_action guard validation
├── device_service.py     # breweryoverview fetch + enrichment; per-bucket storage
├── keg_service.py        # Keg commands + display name updates
├── recipe_service.py     # Recipe list/detail/steps, beer styles, beer list
├── state_engine.py        # ProcessState IntEnum, labels, phase mapping, ALLOWED_COMMANDS
├── state_store.py        # In-memory singleton; per-bucket device state; sessions/kegs cache
├── websocket_manager.py  # WebSocket connections registry + broadcast
├── event_bus.py          # Async pub/sub for internal events
├── polling_worker.py     # Background asyncio 2s poll loop
├── settings_store.py      # Fernet-encrypted token storage
├── auth_service.py       # JWT auth (bypassed — always returns admin user)
├── audit_service.py      # JSONL audit log at /app/data/audit.log
├── diff_engine.py        # Smart diffing for WebSocket broadcast decisions
└── keg_service.py        # Keg CRUD + display name

frontend/
├── index.html            # Dashboard HTML — navbar with 4 tabs, token gate overlay
├── app.js                # WebSocket client, render functions, tab nav, device/session dropdowns
├── style.css             # Dark theme styles — navbar, tabs, session dropdown, tables
└── nginx.conf            # Proxies /ws, /sessions, /recipes, /beers, /keg, /settings, /verify, /device
```

---

## Docker / Deployment

- **Backend port:** 8000 (internal), mapped to 8000 on host
- **Frontend port:** 8080 (nginx, serves dashboard + proxies to backend)
- **Health check:** `curl http://localhost:8000/health` — backend must respond
- **Restart script:** `./minibrew.ps1` (PowerShell) or `./minibrew.sh` (bash)
- **Token propagation:** `docker-compose env_file:` sets env vars in container — `.env` is read at container start, NOT mounted into the container filesystem

### Rebuild after .env change
```powershell
./minibrew.ps1 rebuild
```

### View logs
```powershell
./minibrew.ps1 logs backend
./minibrew.ps1 logs frontend
```

---

## Session Lifecycle

```
Needs cleaning (ua=12)
  └── "Delete Session" → wake (type 2) + 1s wait + DELETE
      └── Session gone

Needs cleaning (ua=12) + user clicks "+ Clean"
  └── create_session("clean_minibrew", uuid)
      └── Session starts
           └── user_action changes over time
                └── user clicks "End Session" or "Delete Session"
                     └── DONE
```

---

## Process States & Phase Detection

The backend maps `process_state` → `phase` (BREWING / FERMENTATION / SERVING / CLEANING). Unknown codes display as `X (NULL)` in red on the dashboard.

Key failure states (render red FAIL on header):
- 71 BREW_FAILED
- 84 FERMENTATION_FAILED
- 93 SERVING_FAILED
- 109 CIP_FAILED

---

## Adding a New Command

1. Add to `command_service.py type_map` — maps named command → numeric `command_type`
2. Add to `ALLOWED_COMMANDS_BY_USER_ACTION` in `state_engine.py` — gate by `user_action`
3. If it's a new `command_type` value, add it to `SESSION_COMMAND_TYPES` in `minibrew_client.py`
4. Add button in `index.html` with `data-command="YOUR_COMMAND"`
5. Handle in `app.js` click handler (or `updateCommandButtonsFromSession`)

---

## Token Encryption

Tokens saved via the Settings panel are encrypted with Fernet (AES) and written to `/app/data/settings.json`. The server must be running to save tokens this way — the encrypted file persists across restarts.

If you lose the token: reset via Settings panel or update `.env` and rebuild.

---

## Polling & Real-Time Updates

- **Poll interval:** 2 seconds (set by `POLL_INTERVAL_MS` in `.env`)
- **No WebSocket from MiniBrew device** — backend polls breweryoverview + sessions + kegs every cycle
- **WebSocket is push only** — browser never polls the backend, only receives broadcasts
- **If WS disconnects:** auto-reconnects after 3 seconds; suppress-ws-logs checkbox silences the noise in console

---

## Troubleshooting Checklist

```
[ ] Can you reach the dashboard?      → http://localhost:8080
[ ] Does /health return ok?          → http://localhost:8080/health
[ ] Does /verify return data?         → http://localhost:8080/verify
[ ] Does /sessions return sessions?  → http://localhost:8080/sessions
[ ] Check backend logs:              → ./minibrew.ps1 logs backend
[ ] Restart everything:              → ./minibrew.ps1 restart
[ ] Full rebuild:                    → ./minibrew.ps1 rebuild
```
