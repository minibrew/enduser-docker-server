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

**Current active token:** `64747b138db8434284af1f85432b7d38`

---

## Known Bugs & Quirks

### 1. FERMENTATION_FAILED is not in the IntEnum
`state_engine.py` line 200 references `ProcessState.FERMENTATION_FAILED` which doesn't exist in the `ProcessState` enum (only `FERMENTING = 80` is there). This causes a startup crash when a WebSocket connects and `build_state_intelligence()` is called.

**Fix applied:** use raw integer `84` instead:
```python
# state_engine.py line 200 — was:
ProcessState.FERMENTATION_FAILED,
# now:
84,   # FERMENTATION_FAILED (not in the IntEnum)
```

### 2. Sessions List Can Show Dangling/Completed Sessions
The polling worker fetches **all** sessions from `GET /v1/sessions/` — this includes sessions that are finished (status 4 = done), failed (status 6), or pending cleaning. There is no active-session filter.

The dashboard shows every session as a card. If you have dozens of old sessions they all appear.

**Status values observed:**
| Status | Meaning |
|--------|---------|
| 2 | Active / in-progress |
| 4 | Completed / done |
| 6 | Failed / cancelled |

### 3. Delete Session Requires Wake First
Some sessions (device in "Needs cleaning" state, user_action=12) reject a DELETE immediately — the device must be woken first. The **Delete Session** button does this automatically: wake (type 2) → 1 second wait → DELETE.

### 4. `process_type` Map
```
0 = Brewing
1 = Fermentation
2 = Cleaning
```
Note: some sessions in the API show `process_type: 5` which is not mapped — these are climate/keg-type devices.

---

## Key Files & What They Do

```
backend/
├── main.py               # FastAPI app, all routes, lifespan startup/shutdown
├── minibrew_client.py    # httpx wrapper — ALL calls to api.minibrew.io go here
├── session_service.py    # Brew/clean/acid-create, send_command, delete_session
├── command_service.py    # Command routing + user_action guard validation
├── device_service.py    # breweryoverview fetch + enrichment
├── keg_service.py       # Keg commands + display name updates
├── state_engine.py      # ProcessState IntEnum, labels, phase mapping, ALLOWED_COMMANDS
├── state_store.py       # In-memory singleton (sessions/kegs/device)
├── websocket_manager.py # WebSocket connections registry + broadcast
├── event_bus.py          # Async pub/sub for internal events
├── polling_worker.py    # Background 2s poll loop → event bus
└── settings_store.py    # Fernet-encrypted token storage

frontend/
├── index.html           # Dashboard HTML + token gate overlay
├── app.js               # WebSocket client, render functions, all UI logic
├── style.css            # Dark theme styles
└── nginx.conf           # Proxies /ws, /sessions, /keg, /settings, /verify, /device
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
