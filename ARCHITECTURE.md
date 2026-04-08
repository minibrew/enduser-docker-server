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
   │                         │──── proxy /session/* ───►│                            │
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
   │                         │                          │                            │
   │◄─── WS device_update ───│◄─── broadcast ────────────│                            │
```

## Ports & Endpoints

### Frontend (nginx) — `http://localhost:8080`
No direct API calls from browser — all requests proxied to backend.

| Route | Proxies To | Purpose |
|-------|-----------|---------|
| `/*` | `frontend:/usr/share/nginx/html` | Serves index.html, app.js, style.css, MB_logo.png |
| `/session/*` | `http://backend:8000/session/*` | Session command proxy |
| `/sessions/*` | `http://backend:8000/sessions/*` | Session CRUD proxy |
| `/keg/*` | `http://backend:8000/keg/*` | Keg command proxy |
| `/kegs` | `http://backend:8000/kegs` | Keg list proxy |
| `/verify` | `http://backend:8000/verify` | Brewery overview proxy |
| `/devices` | `http://backend:8000/devices` | Device list proxy |
| `/device` | `http://backend:8000/device` | Device state proxy |
| `/health` | `http://backend:8000/health` | Health check proxy |
| `/ws` | `ws://backend:8000/ws` | WebSocket upgrade |

### Backend (FastAPI) — `http://localhost:8000`

| Method | Path | Calls MiniBrew API | Purpose |
|--------|------|-------------------|---------|
| GET | `/health` | — | Liveness check |
| GET | `/verify` | `GET /v1/breweryoverview/` | Primary device status |
| GET | `/devices` | `GET /v1/devices/` | Secondary device detail |
| GET | `/sessions` | `GET /v1/sessions/` | List all sessions |
| GET | `/sessions/{id}` | `GET /v1/sessions/{id}/` | Get session detail |
| POST | `/sessions` | `POST /v1/sessions/` | Create brew/clean/acid session |
| DELETE | `/sessions/{id}` | `DELETE /v1/sessions/{id}/` | Terminate session |
| POST | `/session/{id}/command` | `PUT /v1/sessions/{id}/` | Send command (type 2/3/6) |
| GET | `/kegs` | `GET /v1/kegs/` | List all kegs |
| GET | `/kegs/{uuid}` | `GET /v1/kegs/{uuid}/` | Get keg detail |
| POST | `/keg/{uuid}/command` | `POST /v1/kegs/{uuid}/` | Send keg command |
| POST | `/keg/{uuid}/display-name` | `PATCH /v1/kegs/{uuid}/` | Update keg display name |
| GET | `/device` | — | Get cached device state |
| WS | `/ws` | — | Real-time WebSocket |

### MiniBrew API (AWS) — `https://api.minibrew.io`

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/v1/breweryoverview/` | Bearer + `client: Breweryportal` | Device groups: brew_clean_idle, fermenting, serving, brew_acid_clean_idle |
| GET | `/v1/devices/` | Bearer + `client: Breweryportal` | Raw device list with current_state, process_state, user_action |
| GET | `/v1/sessions/` | Bearer + `client: Breweryportal` | List sessions |
| GET | `/v1/sessions/{id}/` | Bearer + `client: Breweryportal` | Session detail |
| POST | `/v1/sessions/` | Bearer + `client: Breweryportal` | Create session (type 0=brew, clean_minibrew, acid_clean_minibrew) |
| PUT | `/v1/sessions/{id}/` | Bearer + `client: Breweryportal` | Send session command (type 2=wake, 3=generic, 6=update_recipe) |
| DELETE | `/v1/sessions/{id}/` | Bearer + `client: Breweryportal` | Terminate session |
| GET | `/v1/sessions/{id}/user_actions/{actionId}/` | Bearer + `client: Breweryportal` | Operator step-by-step instructions |
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
       ├──► StateStore (in-memory) ──► WebSocketManager
       │                                      │
       ├──► EventBus.publish("device_update") │
       │                                      │
       └───────────────────────────────────► broadcast({ device_update })
                                              │
                                              ▼
                                     All Connected Browsers
                                     (initial_state / device_update)
```

## Session Command Routing

```
POST /session/{id}/command
         │
         ▼
CommandService.execute_session_command()
         │
         ├── user_action from session ──► get_allowed_commands()
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
6. **In-memory store** — ready to swap for Redis/Valkey when horizontal scaling is needed

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MINIBREW_API_BASE` | `http://localhost:8080/api` | Base URL for MiniBrew API |
| `MINIBREW_API_KEY` | — | Bearer token for API auth |
| `POLL_INTERVAL_MS` | `2000` | Polling interval in milliseconds |
| `LOG_LEVEL` | `INFO` | Logging verbosity |