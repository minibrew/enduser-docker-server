# MiniBrew Session Orchestrator — API Reference

**Base URL (proxied through nginx):** `http://localhost:8080`
**Backend (direct):** `http://localhost:8000`
**WebSocket:** `ws://localhost:8080/ws`
**MiniBrew API:** `https://api.minibrew.io/v1/`

---

## Authentication

Every MiniBrew API request requires:
```
Authorization: Bearer <token>
client: Breweryportal
```

Tokens are managed via the Settings panel or `.env` (`MINIBREW_API_KEY`). The backend stores encrypted tokens at `/app/data/settings.json` and propagates them to all active client instances without restart.

---

## Backend REST API

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe. Returns `{"status": "ok"}` |

---

### Token Management

| Method | Path | Description |
|--------|------|-------------|
| GET | `/settings/token` | Returns token status: `{token_set: bool, source: "env"\|"stored"\|null}` |
| POST | `/settings/token` | Body: `{token: string}` — encrypts and saves token, hot-reloads it |
| DELETE | `/settings/token` | Deletes stored token, reverts to `.env` token |

---

### Device

| Method | Path | Description |
|--------|------|-------------|
| GET | `/verify` | Proxies `GET /breweryoverview/` — groups devices by operational bucket |
| GET | `/devices` | Proxies `GET /v1/devices/` — per-device detail list |
| GET | `/device` | Returns enriched device state (phase, labels, failure flags) for `device_id=default` |

**`/verify` response:**
```json
{
  "status": "connected",
  "data": {
    "brew_clean_idle": [{ "uuid": "...", "process_state": 0, "user_action": 12, ... }],
    "fermenting": [],
    "serving": [],
    "brew_acid_clean_idle": []
  }
}
```

---

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sessions` | Returns all sessions from local state store |
| POST | `/sessions` | Create a new session |
| GET | `/sessions/{session_id}` | Fetch single session from API, cache it |
| DELETE | `/sessions/{session_id}` | Delete (END_SESSION) a session |
| POST | `/sessions/{session_id}/wake-then-delete` | Send wake (type 2), wait 1s, then delete |
| POST | `/session/{session_id}/command` | Send a named command to a session |

**Create session — `POST /sessions`**
```json
{ "session_type": 0, "minibrew_uuid": "2403B0994-SHNCANKM", "beer_recipe": {...} }
```
- `session_type: 0` = brew, `"clean_minibrew"` = clean, `"acid_clean_minibrew"` = acid clean

**Session command — `POST /session/{session_id}/command`**
```json
{ "command": "NEXT_STEP", "params": {} }
```
Allowed commands: `END_SESSION`, `NEXT_STEP`, `BYPASS_USER_ACTION`, `CHANGE_TEMPERATURE`, `GO_TO_MASH`, `GO_TO_BOIL`, `FINISH_BREW_SUCCESS`, `FINISH_BREW_FAILURE`, `CLEAN_AFTER_BREW`, `BYPASS_CLEAN`

**`CHANGE_TEMPERATURE` requires `params.serving_temperature`**

---

### Kegs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/kegs` | Returns all kegs from local state store |
| POST | `/keg/{keg_uuid}/command` | Send a named command to a keg |
| POST | `/keg/{keg_uuid}/display-name` | Update keg display name |

**Keg command — `POST /keg/{keg_uuid}/command`**
```json
{ "command": "PUT_INTO_SERVING_MODE", "params": {} }
```
```json
{ "command": "SET_KEG_TEMPERATURE", "params": { "temperature": 4.0 } }
```
```json
{ "command": "RESET_KEG", "params": {} }
```

**Update display name — `POST /keg/{keg_uuid}/display-name`**
```json
{ "display_name": "IPA Batch 42" }
```

---

## WebSocket (`/ws`)

Browser connects here for real-time state pushes.

**On connect:** server sends `initial_state` with `sessions`, `kegs`, and `device`.

**On each poll cycle:** server broadcasts `device_update` with current `sessions` and `kegs`.

**Client → server:** send `{type: "ping"}`, server replies `{type: "pong"}`.

```
ws://localhost:8080/ws
```

### Message Types (server → browser)

| `type` | Payload |
|--------|---------|
| `initial_state` | `{sessions: [...], kegs: [...], device: {...}}` |
| `device_update` | `{sessions: [...], kegs: [...], (partial — only changed fields)}` |
| `session_update` | A single session object |
| `system_event` | `{type, payload}` for notable internal events |

---

## MiniBrew API (upstream)

All upstream endpoints are called by the backend via `MiniBrewClient`. Token: `MINIBREW_API_KEY` from `.env`.

**Base:** `https://api.minibrew.io/v1/`
**Required header:** `client: Breweryportal`

### Devices

| Method | Path | Description |
|--------|------|-------------|
| GET | `/breweryoverview/` | Device overview grouped by bucket |
| GET | `/devices/` | Full device list with status details |

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/sessions/` | List all sessions (returns bare array) |
| GET | `/v1/sessions/{id}/` | Single session detail |
| POST | `/v1/sessions/` | Create new session |
| PUT | `/v1/sessions/{id}/` | Send command (`{command_type: 2\|3\|6, ...}`) |
| DELETE | `/v1/sessions/{id}/` | Delete/terminate session |
| GET | `/v1/sessions/{id}/user_actions/{action_id}/` | Operator guidance |

### Kegs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/kegs/` | List all kegs |
| GET | `/v1/kegs/{uuid}/` | Single keg detail |
| POST | `/v1/kegs/{uuid}/` | Send keg command |
| PATCH | `/v1/kegs/{uuid}/` | Update keg (e.g. display name) |

---

## Command Types

| Value | Name | Description |
|-------|------|-------------|
| 2 | `wake_device` | Power on / wake the machine |
| 3 | `generic_command` | NEXT_STEP, BYPASS, GO_TO_MASH, etc. |
| 6 | `update_recipe` | CHANGE_TEMPERATURE (sends `serving_temperature`) |

---

## Process State Codes

| Code | Label | Phase |
|------|-------|-------|
| 0 | IDLE | — |
| 24 | MASH_IN | BREWING |
| 30 | MASH_HEATUP | BREWING |
| 31 | MASHING | BREWING |
| 40 | LAUTERING | BREWING |
| 50 | BOILING_HEATUP | BREWING |
| 51 | BOILING | BREWING |
| 60 | COOL_WORT | BREWING |
| 70 | BREW_DONE | BREWING |
| 71 | BREW_FAILED | BREWING |
| 74 | PITCH_COOLING | BREWING |
| 75 | PREPARE_FERMENTATION | FERMENTATION |
| 76 | PLACE_AIRLOCK | FERMENTATION |
| 77 | REMOVE_AIRLOCK | FERMENTATION |
| 78 | PLACE_TRUB_CONTAINER | FERMENTATION |
| 80 | FERMENTATION_TEMP_CONTROL | FERMENTATION |
| 81 | REMOVE_TRUB | FERMENTATION |
| 82 | FERMENTATION_ADD_INGREDIENT | FERMENTATION |
| 83 | FERMENTATION_REMOVE_INGREDIENT | FERMENTATION |
| 84 | FERMENTATION_FAILED | FERMENTATION |
| 88 | PREPARE_SERVING | SERVING |
| 90 | COOL_BEFORE_SERVING | SERVING |
| 91 | MOUNT_TAP | SERVING |
| 92 | SERVING_TEMP_CONTROL | SERVING |
| 93 | SERVING_FAILED | SERVING |
| 101 | PREPARE_CIP | CLEANING |
| 103 | BACKFLUSH | CLEANING |
| 108 | CIP_DONE | CLEANING |
| 109 | CIP_FAILED | CLEANING |
| 111 | CIRCULATE_BOILING_PATH | CLEANING |
| 112 | CIRCULATE_MASHING_PATH | CLEANING |
| 113 | RINSE_COUNTERFLOW_BOIL | CLEANING |
| 114 | RINSE_COUNTERFLOW_MASHTUN | CLEANING |

### High-Level Phases

| Phase | Process States |
|-------|--------------|
| BREWING | 24, 30, 31, 39, 40, 43, 50, 51, 52, 59, 60, 70, 71, 74 |
| FERMENTATION | 75, 76, 77, 78, 80, 81, 82, 83, 84 |
| SERVING | 88, 90, 91, 92, 93 |
| CLEANING | 101, 103, 108, 109, 111, 112, 113, 114 |

### Failure States (red FAIL prefix)

| Code | Label |
|------|-------|
| 71 | BREW_FAILED |
| 84 | FERMENTATION_FAILED |
| 93 | SERVING_FAILED |
| 109 | CIP_FAILED |

---

## User Action Codes

| Code | Label |
|------|-------|
| 0 | None |
| 2 | Prepare cleaning |
| 3 | Add cleaning agent |
| 4 | Fill water |
| 5 | Ready to clean |
| 12 | Needs cleaning |
| 13 | Needs acid cleaning |
| 21 | Start brewing |
| 22 | Add ingredients |
| 23 | Mash in |
| 24 | Heat to mash |
| 25 | Mash done |
| 26 | Prepare fermentation |
| 27 | Cool to fermentation |
| 28 | Add yeast |
| 30 | Fermentation complete |
| 31 | Transfer to serving |
| 32 | Start cleaning |
| 33 | Rinse |
| 34 | Acid clean |
| 35 | Sanitize |
| 36 | Finished cleaning |
| 37 | CIP Finished |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MINIBREW_API_BASE` | `https://api.minibrew.io/v1/` | MiniBrew API base URL |
| `MINIBREW_API_KEY` | *(required)* | Bearer token for MiniBrew API |
| `MINIBREW_CLIENT_HEADER` | `Breweryportal` | Required API header (constant) |
| `POLL_INTERVAL_MS` | `2000` | Polling interval in milliseconds |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING) |

---

## Architecture Overview

```
Browser
  └── nginx :8080
        ├── /ws           → backend :8000 (WebSocket)
        ├── /settings/*   → backend :8000
        ├── /health       → backend :8000
        ├── /verify       → backend :8000
        ├── /devices      → backend :8000
        ├── /device       → backend :8000
        ├── /session/*    → backend :8000
        ├── /sessions/*   → backend :8000
        ├── /keg/*        → backend :8000
        ├── /kegs         → backend :8000
        └── /*           → frontend :80 (static files)

backend :8000
  ├── PollingWorker (every 2s)
  │     ├── GET /breweryoverview/
  │     ├── GET /v1/sessions/
  │     └── GET /v1/kegs/
  ├── StateStore (in-memory)
  ├── EventBus (async pub/sub)
  └── WebSocketManager → broadcasts to all browser clients

MiniBrew API (upstream)
  └── api.minibrew.io/v1/
```
