# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
