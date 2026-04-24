# Future Features — MiniBrew Session Orchestrator

Additional planned features beyond the items in `TODO.md`, organized by category.

---

## 1. PostgreSQL-Backed Features

### 1.1 Session History with Full State Replay
Store every session in PostgreSQL with periodic state snapshots. Allow users to click a past session and scrub through its state timeline (process_state, temperature, gravity over time).

### 1.2 Per-User MiniBrew Token Vault
Allow multiple dashboard users, each with their own stored MiniBrew API token. The token is encrypted at rest per user and loaded into `MiniBrewClient` on their session. Switching users hot-reloads their token into the API client.

### 1.3 Recipe Library (Local)
Store imported and custom-crafted recipes locally in PostgreSQL with versioning. Users can save personal recipe variations with notes, water adjustments, and ingredient tweaks — distinct from the shared MiniBrew public recipe library.

### 1.4 Keg History
Track pour events, temperature setpoints, and display-name changes per keg over time. Enables "keg aging" tracking — how long a specific keg has been active, total pours, etc.

---

## 2. Real-Time & MQTT

### 2.1 Push Notifications (Browser)
Browser push notifications for:
- User action required (Needs cleaning, Add ingredients, etc.)
- Session complete / failure
- Keg temperature out of range

Using the Web Push API (`Notification.requestPermission()`) with a service worker to deliver notifications even when the browser tab is not active.

### 2.2 MQTT Device → Backend Events
Per `MQTT Message Specifications.md`, subscribe to device event topics and update Redis state directly from the MQTT stream — eliminating the 2-second polling loop for device state changes. Latency drops from 2s to near-real-time.

### 2.3 Command Delivery via MQTT
Commands that need fast delivery (e.g., emergency stop) should be sent via `backend/commands/{serial}` MQTT topic. WebSocket command path remains for debugging and fallback.

### 2.4 Device Online/Offline Status
Use the retained `devices/status/{serial}` message (online/offline) to show a live "device connectivity" indicator in the navbar. Currently, online status is only updated during the 2s poll cycle.

### 2.5 Batch Log Streaming
Subscribe to `devices/batchlogs/{serial}` for real-time fermentation data (gravity, temperature logged during fermentation), enabling live charting without polling.

---

## 3. Frontend Improvements

### 3.1 Temperature & Gravity Charts
Plot `current_temp`, `target_temp`, and `gravity` from breweryoverview as a live line chart on the device panel. Requires storing historical data points (Redis time-series or PostgreSQL snapshots).

Chart library candidates: Chart.js, uPlot, or Plotly.

### 3.2 Dark/Light Mode Toggle
Add a theme switcher in the settings modal. Persist the preference in `localStorage` and apply via a CSS class on `<body>`.

### 3.3 Responsive Mobile Layout
The dashboard works on tablet but mobile is rough. Progressive enhancement approach: collapse the navbar tabs into a hamburger menu, stack the controls grid vertically, simplify the session detail panel.

### 3.4 Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `N` | New session (open form) |
| `R` | Refresh device |
| `↑/↓` | Navigate session list |
| `Enter` | Send selected command |
| `Esc` | Close modal / cancel form |
| `W` | Toggle WebSocket console |

### 3.5 Toast Notifications
Replace console-only feedback with a toast notification system (bottom-right corner) for command success/failure, session lifecycle events, and connection status changes.

### 3.6 Keg Detail Modal
Click on a keg card to open a full detail modal showing:
- Current temperature, target temperature
- Current mode (serving/cleaning/idle)
- Total pour count
- Active session linked to this keg
- Historical temperature chart

### 3.7 Multi-Session View
A grid view showing all active sessions simultaneously with their current process_state, temperature, and user action — so operators can monitor a entire brewery floor from one screen.

### 3.8 Recipe Comparison
Select two recipes and display them side-by-side: mash schedule, boil steps, hopping, fermentation profile, expected OG/IBU/ABV. Useful for clone recipes and recipe planning.

---

## 4. Automation & Integration

### 4.1 n8n Workflow Automation
Webhook endpoints for brew lifecycle events that trigger n8n workflows:
- `POST /hooks/brew_complete` — triggers notification when a brew session transitions to BREWING_DONE_STATE
- `POST /hooks/cleaning_needed` — fires when user_action becomes 12 (Needs cleaning)
- `POST /hooks/temperature_alert` — fires when `current_temp` exceeds `target_temp` by a threshold
- `POST /hooks/keg_temperature_out_of_range`

n8n can then forward these to Slack, email, Telegram, or other systems.

### 4.2 Home Assistant Integration
MQTT discovery for MiniBrew devices as Home Assistant entities:
- Device sensor: current temp, target temp, gravity, process_state
- Switch entity: start/stop session
- Climate entity: temperature control
- Sensor: fermentation stage (from breweryoverview bucket)

### 4.3 OpenClaw AI Agent Control
Natural language control of brewing sessions via OpenClaw gateway. Example voice/text commands:
- "Start a mash step on device 2403B0994"
- "What's the current temperature?"
- "Tell me when the mash is done"

Requires the AI agent to read device state from the orchestrator API and decide which commands to send.

### 4.4 IFTTT / Zapier Integration
Webhook-based integration for non-technical users to connect MiniBrew events to thousands of apps without writing code.

---

## 5. Observability & Operations

### 5.1 Prometheus Metrics Endpoint
Expose `GET /metrics` returning Prometheus-format metrics:
- `minibrew_polling_duration_seconds` (histogram)
- `minibrew_command_requests_total{command, result}` (counter)
- `minibrew_active_sessions_total` (gauge)
- `minibrew_websocket_connections_total` (gauge)
- `minibrew_api_latency_seconds{endpoint}` (histogram)

### 5.2 Structured JSON Logging
Replace all `print()` and basic `logging` with structured JSON logs:
```json
{"level": "INFO", "ts": "2026-04-23T10:12:00Z", "event": "command_sent", "session_id": "abc", "command": "NEXT_STEP", "duration_ms": 340}
```
Easily ingestable into Datadog, Loki, or CloudWatch.

### 5.3 Stale-Data Indicator
If `breweryoverview` fails to fetch for > 10 seconds, show a yellow warning badge on the device panel: "⚠ Device data may be stale". If it fails for > 60 seconds, escalate to red: "❌ Device unreachable".

### 5.4 Command Queue with Replay
When the MiniBrew API is down, queue commands in Redis and replay them on recovery with exponential backoff. Show users a "pending commands" badge so they know their command was captured.

### 5.5 Health Check Endpoint Overhaul
Improve Docker healthcheck to actually test MiniBrew API reachability (not just `localhost:8000`). Use `/verify` as the health check — if it returns 200, container is healthy; if it times out or returns 401 for > 30s, mark unhealthy.

### 5.6 Rate Limiting
Per-device and per-session command rate limiting:
- Max 1 command per device per 3 seconds
- Max 5 commands per session per minute
- Return `429 Too Many Requests` when exceeded, with a `Retry-After` header

---

## 6. Recipe & Brewing Intelligence

### 6.1 Mash Profile Designer
Visual editor to design custom mash schedules (step mash, decoction) with target temperatures and hold times. Exports a recipe JSON that can be imported into MiniBrew or used to start a session.

### 6.2 Water Chemistry Calculator
Integrated water chemistry tool that:
- Takes a base water profile (Ca, Mg, Na, Cl, SO4, HCO3)
- Takes a target style (from BeerXML or user selection)
- Calculates salt additions (CaCO3, CaSO4, MgSO4, NaCl, NaHCO3)
- Shows resulting ion profile and compares to target

Already partially done via the static water profiles tab — needs to be interactive.

### 6.3 Brew Calculator
Calculator for:
- OG/FG estimation from grain bill
- IBU calculation from hopping schedule
- ABV estimate
- Yeast pitch rate

### 6.4 Session Timer / Countdown
Show elapsed time and countdown for active brew steps. When a step has a target duration, display countdown. When a step is waiting on a user_action, show how long it has been waiting (possible stuck detection).

---

## 7. Multi-Tenant & Access Control

### 7.1 Role-Based Access Control (RBAC)
| Role | Permissions |
|------|------------|
| Viewer | Read-only dashboard access |
| Operator | Can send commands, create sessions |
| Admin | Full access + token management + user management |

### 7.2 API Key Authentication
Programmatic REST API access for home automation integrations. Per-user API keys stored hashed in PostgreSQL. Auth via `X-API-Key` header.

### 7.3 OAuth2 / SSO
Google or GitHub OAuth for dashboard login (Federated identity).

---

## 8. Testing & CI/CD

### 8.1 Playwright E2E Tests
Critical user flows to cover:
- Token gate → enter token → dashboard loads
- Create brew session → verify session card appears in dropdown
- Send command → verify WebSocket `device_update` received
- Settings → save token → verify `/settings/token` returns `stored`
- Import recipe JSON → verify it appears in recipe list
- Delete session → verify removed from dropdown

### 8.2 CI/CD Pipeline (GitHub Actions)
```
on: [push, pull_request]
jobs:
  lint:
    runs: ruff check . && mypy backend/
  test:
    runs: pytest tests/
  e2e:
    runs: playwright test
  build:
    runs: docker build . -t minibrew-orchestrator:$GITHUB_SHA
    only_on: [tag]
```

### 8.3 Dependency Pinning & Dependabot
Pin all `requirements.txt` entries to exact versions. Enable Dependabot for automated security updates.

---

## 9. Documentation

### 9.1 API Changelog
Document all breaking changes between API versions so integrators can track evolution.

### 9.2 MiniBrew API Schema Documentation
Reverse-engineer the full `breweryoverview` and `v1/devices` schema based on real API observations — field names, types, nullability, example values.

### 9.3 Video Tutorial
Getting started guide: Docker install, token extraction from browser, first brew session from the dashboard.

### 9.4 Architecture Decision Records (ADRs)
Document key decisions in `docs/adr/`:
- ADR-001: Why in-memory StateStore instead of Redis
- ADR-002: Why WebSocket instead of Server-Sent Events
- ADR-003: Why polling was chosen over MQTT (before MQTT was available)
- ADR-004: Token storage strategy (Fernet encryption)
