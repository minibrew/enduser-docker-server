# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-04-23

### Added
- **Multi-device support** — Header dropdown shows all devices across all brewery buckets (brew_clean_idle, fermenting, serving, brew_acid_clean_idle); selecting a device switches the dashboard context to that bucket's enriched device state
- **Session dropdown** — Sessions tab now shows a sorted dropdown (highest ID first, defaulting to the most recent session); each option displays `#ID [Status] BeerName ProcessState ★`; active session marked with ★
- **Recipe browser** — Recipes tab lists all recipes from `GET /v1/recipes/`; click any recipe to view brew steps; start a brew session directly from a recipe
- **Beer styles browser** — `GET /v1/beerstyles/` endpoint exposed via backend
- **User action operator guidance** — Step-by-step instructions fetched from `GET /v1/sessions/{id}/user_actions/{actionId}/` and displayed in the session detail panel when a user_action is active
- **Cleaning logs** — `GET /v1/sessions/{id}/logs/cleaning/` endpoint exposed for troubleshooting cleaning cycles

### Changed
- **Sessions tab UX** — Replaced session cards grid with a single sorted dropdown; highest session ID auto-selected on load
- **Multi-device WebSocket** — WebSocket now sends `overview`, `selected_bucket`, and `devices[]` (all devices with their bucket) on every `device_update`; `bucket_changed` message on bucket switch
- **`state_store.py` rewrite** — Per-bucket device state storage; `set_brewery_overview()` stores the full 4-bucket response; `select_bucket()` / `get_selected_bucket()` manage active bucket; `get_all_devices()` returns flattened device list

### Fixed
- **Double `/v1/v1/` paths** — `MiniBrewClient` base_url included `/v1/` and session/keg methods also prefixed paths with `/v1/` → 404 on all session and keg calls. Fixed by removing `/v1` from all session and keg method paths.
- **FERMENTATION_FAILED crash** — `ProcessState.FERMENTATION_FAILED` does not exist in the IntEnum (only `FERMENTING = 80`). Fixed by using raw integer `84`.
- **Session ID field** — API returns `session_id` not `id`; `sessionKey()` helper (`s.id ?? s.session_id`) used in all render functions
- **`USER_ACTION_LABELS` duplication** — Removed duplicate copy from `session_service.py`; now imports from `state_engine.py`

### Deprecated
- `breweryoverview` is the **primary** device data source; `v1/devices` is supplementary (not updated in real-time)
- `/debug/sessions-raw` endpoint removed

---

## [0.2.0] — 2026-04-08

### Added
- **Runtime token management** — Settings panel (⚙) allows updating the MiniBrew bearer token at runtime without restarting; stored encrypted in `/app/data/settings.json`
- **Token gate** — If no token is found (neither `.env` nor stored), the UI presents a blocking full-screen token entry screen before anything else loads
- **Token source tracking** — `/settings/token` endpoint returns `{token_set, source}` indicating whether the active token comes from `.env` or encrypted storage
- **Hot token reload** — Saved tokens are applied to all active `MiniBrewClient` instances immediately without dropping WebSocket connections
- **Delete stored token** — Reset button removes encrypted token override and reverts to `.env` default
- **`MB_logo.png` in Docker image** — Logo file now correctly copied into the frontend Docker image; previously missing from the build

### Changed
- **Frontend Dockerfile** — Now copies `MB_logo.png` and `network_diagram.svg` in addition to `index.html`, `app.js`, `style.css`
- **nginx.conf** — Added `/settings` proxy route so the frontend can reach the settings endpoints

### Fixed
- **Logo rendering** — `MB_logo.png` was not being served because the Dockerfile omitted it from the `COPY` command
- **Settings `DELETE` endpoint** — The `DELETE /settings/token` endpoint was not saved in the initial implementation; now functional

---

## [0.1.0] — 2026-04-08

### Added
- **FastAPI backend** with full session, keg, and device orchestration
- **WebSocket real-time push** — browser receives `initial_state`, `device_update`, `session_update`, `system_event` messages without polling
- **ProcessState / UserAction / Phase maps** — all numerical MiniBrew codes displayed as human-readable labels; unknown codes show as `X (NULL)` in red
- **Failure state detection** — BREWING_FAILED (71), FERMENTATION_FAILED (84), SERVING_FAILED (93), CIP_FAILED (109) shown with red FAIL prefix
- **Command validation guards** — `CommandService` validates commands against `user_action` before dispatching to MiniBrew API
- **Session management** — create brew (type=0), clean (`clean_minibrew`), and acid clean (`acid_clean_minibrew`) sessions
- **Keg management** — serving mode, temperature control, beer name, reset; `display_name` endpoint for custom keg naming
- **Auto-refresh dropdown** — 1/2/3/4/5/10 second intervals; remembers last active source (breweryoverview vs v1/devices)
- **Docker Compose setup** — `nginx:alpine` frontend + `uvicorn` backend; health checks, restart policies
- **Network architecture diagram** (`network_diagram.svg`) and `ARCHITECTURE.md`
- **Settings endpoint** (`/settings/token` GET) — returns token status

### Known Limitations
- No built-in authentication (see [TODO.md](./TODO.md) — JWT Auth)
- No persistent storage — state is in-memory only
- No unit or E2E tests
- No MQTT support — polling at 2s interval only
