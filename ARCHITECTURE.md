# MiniBrew Session Orchestrator — Architecture & Network

## Overview

```
                                     ┌─────────────────────────────────────────┐
                                     │           Docker Compose                 │
                                     │                                         │
 Browser (http://localhost:8080)     │  ┌──────────────┐    ┌────────────────┐ │
     │                                │  │   frontend   │    │    backend    │ │
     │  HTTP/WebSocket                │  │  (nginx:80)  │    │ (uvicorn:8000)│ │
     └───────────────────────────────► │  └──────┬───────┘    └───────┬────────┘ │
                                      │         │                    │          │
                                      │         │  proxy            │ API      │
                                      │         ▼                    ▼          │
                                      │  ┌──────────────┐    ┌────────────────┐ │
                                      │  │  localhost   │    │ api.minibrew.io│ │
                                      │  │  :8000        │    │ (HTTPS:443)    │ │
                                      │  └──────────────┘    └────────────────┘ │
                                      └─────────────────────────────────────────┘
```

## Component Map

| Component | Host | Port | Docker Service | Purpose |
|-----------|------|------|----------------|---------|
| Browser UI | localhost | 8080 | frontend | Single-page dashboard (HTML/JS/CSS) |
| Nginx | internal | 80 | frontend | Serves static files, proxies to backend |
| FastAPI Backend | internal | 8000 | backend | REST API + WebSocket orchestrator |
| MiniBrew API | api.minibrew.io | 443 | — | External AWS-hosted brewery API |
| WebSocket | localhost | 8000/ws | backend | Real-time push to browser |

## Communication Flow

```
Browser                    Nginx                     FastAPI                   MiniBrew API
   │                         │                          │                            │
   │──── HTTP GET / --------►│                          │                            │
   │                         │──── proxy /sessions/* ──►│                            │
   │                         │                          │──── HTTP GET /v1/breweryoverview/ ──►│
   │                         │                          │◄─── 200 OK + JSON ──────────────────│
   │                         │◄─── proxied response ────│                            │
   │◄─── HTTP response ─────│                          │                            │
   │                         │                          │                            │
   │──── WS /ws ────────────►│                          │                            │
   │                         │──── WS upgrade ─────────►│                            │
   │                         │                          │──── polling ───────────────►│
   │                         │                          │◄─── session data ────────────│
   │◄─── WS initial_state ───│                          │                            │
   │◄─── WS device_update ───│◄─── broadcast ────────────│                            │
```

## Ports & Endpoints

### Frontend (nginx) — `http://localhost:8080`
No direct API calls from browser — all requests proxied to backend.

| Route | Proxies To | Purpose |
|-------|-----------|---------|
| `/*` | `frontend:/usr/share/nginx/html` | Serves index.html, app.js, style.css, MB_logo.png |
| `/sessions/*` | `http://backend:8000/sessions/*` | Session CRUD proxy |
| `/session/*` | `http://backend:8000/session/*` | Session command proxy |
| `/recipes/*` | `http://backend:8000/recipes/*` | Recipe list/detail proxy |
| `/beers` | `http://backend:8000/beers` | Beer list proxy |
| `/beer-styles` | `http://backend:8000/beer-styles` | Beer styles proxy |
| `/keg/*` | `http://backend:8000/keg/*` | Keg command proxy |
| `/kegs` | `http://backend:8000/kegs` | Keg list proxy |
| `/verify` | `http://backend:8000/verify` | Brewery overview proxy |
| `/devices` | `http://backend:8000/devices` | Device list proxy |
| `/device` | `http://backend:8000/device` | Device state proxy |
| `/device/select` | `http://backend:8000/device/select` | Bucket/device selection |
| `/devices/all` | `http://backend:8000/devices/all` | All devices from all buckets |
| `/settings/*` | `http://backend:8000/settings/*` | Token settings proxy |
| `/auth/*` | `http://backend:8000/auth/*` | Auth proxy |
| `/health` | `http://backend:8000/health` | Health check proxy |
| `/audit/*` | `http://backend:8000/audit/*` | Audit log proxy |
| `/ws` | `ws://backend:8000/ws` | WebSocket upgrade |

### Backend (FastAPI) — `http://localhost:8000`

#### Public Endpoints (no auth)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check |
| GET | `/settings/token` | Token status: `{token_set, source}` |
| POST | `/settings/token` | Save encrypted token (auth-bypassed in single-user mode) |
| DELETE | `/settings/token` | Reset to .env token |
| WS | `/ws` | WebSocket real-time push |
| POST | `/auth/register` | Register dashboard user |
| POST | `/auth/login` | Login → JWT access + refresh tokens |
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| GET | `/auth/me` | Current user info |

#### Protected Endpoints (JWT auth, currently bypassed → always returns admin)

| Method | Path | Calls MiniBrew API | Purpose |
|--------|------|-------------------|---------|
| GET | `/verify` | `GET /breweryoverview/` | Primary device status (4 buckets) |
| GET | `/devices` | `GET /v1/devices/` | Secondary device detail |
| GET | `/devices/all` | `GET /breweryoverview/` | All devices from all buckets |
| POST | `/device/select` | — | Switch active bucket |
| GET | `/sessions` | (from StateStore) | List all sessions from local cache |
| GET | `/sessions/{id}` | `GET /v1/sessions/{id}/` | Get session detail |
| GET | `/sessions/{id}/user-action/{action_id}` | `GET /v1/sessions/{id}/user_actions/{action_id}/` | Operator guidance |
| GET | `/sessions/{id}/cleaning-logs` | `GET /v1/sessions/{id}/logs/cleaning/` | Cleaning logs |
| POST | `/sessions` | `POST /v1/sessions/` | Create brew/clean/acid session |
| POST | `/sessions/{id}/wake-then-delete` | `PUT /v1/sessions/{id}/` then `DELETE` | Wake then delete |
| DELETE | `/sessions/{id}` | `DELETE /v1/sessions/{id}/` | Terminate session |
| POST | `/session/{id}/command` | `PUT /v1/sessions/{id}/` | Send command (type 2/3/6) |
| GET | `/recipes` | `GET /v1/recipes/` | List all recipes |
| GET | `/recipes/{id}` | `GET /v1/recipes/{id}/` | Get recipe detail + steps |
| GET | `/recipes/{id}/steps` | `GET /v1/recipes/{id}/steps/` | Get recipe steps |
| GET | `/beers` | `GET /v1/beers/` | List all beers |
| GET | `/beer-styles` | `GET /v1/beerstyles/` | List all beer styles |
| GET | `/kegs` | (from StateStore) | List all kegs from local cache |
| GET | `/kegs/{uuid}` | `GET /v1/kegs/{uuid}/` | Get keg detail |
| POST | `/keg/{uuid}/command` | `POST /v1/kegs/{uuid}/` | Send keg command |
| POST | `/keg/{uuid}/display-name` | `PATCH /v1/kegs/{uuid}/` | Update keg display name |
| GET | `/device` | — | Get cached device state for selected bucket |
| GET | `/audit/log` | — | Read audit log with filters |

### MiniBrew API (AWS) — `https://api.minibrew.io`

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/breweryoverview/` | Bearer + `client: Breweryportal` | Device groups: brew_clean_idle, fermenting, serving, brew_acid_clean_idle (no `/v1/` prefix) |
| GET | `/v1/devices/` | Bearer + `client: Breweryportal` | Raw device list with current_state, process_state, user_action |
| GET | `/v1/sessions/` | Bearer + `client: Breweryportal` | List sessions |
| GET | `/v1/sessions/{id}/` | Bearer + `client: Breweryportal` | Session detail |
| POST | `/v1/sessions/` | Bearer + `client: Breweryportal` | Create session (type 0=brew, clean_minibrew, acid_clean_minibrew) |
| PUT | `/v1/sessions/{id}/` | Bearer + `client: Breweryportal` | Send session command (type 2=wake, 3=generic, 6=update_recipe) |
| DELETE | `/v1/sessions/{id}/` | Bearer + `client: Breweryportal` | Terminate session |
| GET | `/v1/sessions/{id}/user_actions/{actionId}/` | Bearer + `client: Breweryportal` | Operator step-by-step instructions |
| GET | `/v1/sessions/{id}/logs/cleaning/` | Bearer + `client: Breweryportal` | Cleaning process logs |
| GET | `/v1/recipes/` | Bearer + `client: Breweryportal` | List all recipes (supports `?beer=` filter) |
| GET | `/v1/recipes/{id}/` | Bearer + `client: Breweryportal` | Recipe detail |
| GET | `/v1/recipes/{id}/steps/` | Bearer + `client: Breweryportal` | Recipe brew steps |
| GET | `/v1/beers/` | Bearer + `client: Breweryportal` | List all beers |
| GET | `/v1/beerstyles/` | Bearer + `client: Breweryportal` | List all beer styles |
| GET | `/v1/kegs/` | Bearer + `client: Breweryportal` | List kegs |
| GET | `/v1/kegs/{uuid}/` | Bearer + `client: Breweryportal` | Keg detail |
| POST | `/v1/kegs/{uuid}/` | Bearer + `client: Breweryportal` | Send keg command |
| PATCH | `/v1/kegs/{uuid}/` | Bearer + `client: Breweryportal` | Update keg (display_name) |

## Data Flow — Polling & Push

```
MiniBrew API (poll every 2s)
       │
       ▼
PollingWorker._poll()
       │
       ├──► breweryoverview ──► 4 buckets stored in StateStore
       │                              │
       ├──► all sessions ─────────────► StateStore
       │                              │
       ├──► all kegs ─────────────────► StateStore
       │                              │
       └──► EventBus.publish("device_update")
                    │
                    ▼
             WebSocketManager.broadcast()
                    │
                    ▼
           All Connected Browsers
```

## Data Flow — Command Dispatch

```
POST /session/{id}/command
         │
         ▼
CommandService.execute_session_command()
         │
         ├── user_action from session ──► ALLOWED_COMMANDS_BY_USER_ACTION guard
         │
         ├── command = "CHANGE_TEMPERATURE"  ──► type 6 ──► update_recipe(serving_temperature)
         ├── command = "END_SESSION"        ──► DELETE /v1/sessions/{id}/
         └── other command                 ──► type 3 ──► generic_command()
```

## Key Design Decisions

1. **No browser polling** — backend pushes via WebSocket; breweryoverview is polled every 2s
2. **client: Breweryportal** enforced centrally in `MiniBrewClient._headers`
3. **Session-first** — all control goes through `POST /v1/sessions/` then `PUT /v1/sessions/{id}/`
4. **Command guards** — command type validated against user_action before dispatch
5. **State engine** — maps user_action IDs to operator-friendly labels (12="Needs cleaning", 21="Start brewing", etc.)
6. **In-memory store** — `StateStore` singleton is ephemeral; disappears on restart (Redis swap planned)
7. **Multi-device via breweryoverview buckets** — `breweryoverview` returns 4 named buckets; the UI dropdown lets users switch between them; the selected bucket's first device is the active device
8. **`/v1/` prefix convention** — `breweryoverview` uses no `/v1/` prefix; all session and keg endpoints use `/v1/`
9. **Auth bypassed** — `get_current_user()` returns hardcoded admin; JWT auth is scaffolded but inactive in single-user mode
10. **Audit log** — all commands and auth events appended to `/app/data/audit.log` (JSONL)

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MINIBREW_API_BASE` | `https://api.minibrew.io/v1/` | Base URL for MiniBrew API |
| `MINIBREW_API_KEY` | — | Bearer token for API auth |
| `POLL_INTERVAL_MS` | `2000` | Polling interval in milliseconds |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `JWT_SECRET` | *(auto-generated)* | Secret for JWT signing (auto-generated if not set) |
