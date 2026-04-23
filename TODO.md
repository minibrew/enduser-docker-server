# TODO — MiniBrew Session Orchestrator

Features, improvements, and known gaps. Items marked **[done]** have been implemented.

---

## Authentication & Access Control

- [ ] **[JWT Authentication]** — Replace the bearer token gate with proper JWT-based user auth for the dashboard itself (separate from MiniBrew API token)
  - User logs in with username/password → server issues JWT
  - JWT middleware on all API routes (except `/health` and `/ws` initial handshake)
  - JWT refresh token flow with expiry
  - Login/logout UI in the header
  - Multi-user support: different users have their own stored MiniBrew tokens

- [ ] **OAuth2 / SSO** — Support Google or GitHub OAuth for dashboard login (Federated identity)

- [ ] **Role-Based Access Control (RBAC)** — Viewer vs Operator vs Admin roles
  - Viewers: read-only dashboard access
  - Operators: can send commands, create sessions
  - Admins: can manage settings, tokens, all operator actions

- [ ] **API Key Authentication** — For programmatic/machine access (REST API consumers)
  - Per-user API keys stored hashed in the database
  - `X-API-Key` header authentication
  - Key management UI (create, revoke, rotate)

- [ ] **Audit Log** — Log all commands sent, who sent them, when
  - Store in SQLite or PostgreSQL
  - Include: timestamp, user, session_id, command, device_uuid, result

---

## Active Command Buttons (Base Station Controls)

Currently these buttons exist but many are disabled based on `user_action` guards. The following commands are wired but inactive until the right session state:

| Button | Command | Gate Condition |
|--------|---------|---------------|
| End Session | `END_SESSION` | Always available when session selected |
| Next Step | `NEXT_STEP` | Available at specific user_action states |
| Bypass User Action | `BYPASS_USER_ACTION` | Available at specific user_action states |
| Change Temperature | `CHANGE_TEMPERATURE` | Available at fermentation/serving user_actions |
| Go To Mash | `GO_TO_MASH` | Available during brewing user_action |
| Go To Boil | `GO_TO_BOIL` | Available during brewing user_action |
| Finish Brew Success | `FINISH_BREW_SUCCESS` | Available at brewing complete user_action |
| Finish Brew Failure | `FINISH_BREW_FAILURE` | Available at brewing complete user_action |
| Clean After Brew | `CLEAN_AFTER_BREW` | Available at brewing done user_action |
| Bypass Clean | `BYPASS_CLEAN` | Available at cleaning user_action states |

To activate these, create a session first using the **+ Brew**, **+ Clean**, or **+ Acid Clean** buttons, then select the session card.

---

## Backend & Infrastructure

- [ ] **Redis / Valkey State Store** — Replace the in-memory `StateStore` singleton with a Redis-backed store
  - Enables horizontal scaling (multiple backend replicas)
  - Pub/sub via Redis for WebSocket broadcasts across replicas
  - Session state persistence across backend restarts

- [ ] **PostgreSQL Database** — Store persistent data:
  - User accounts + JWT hashes
  - Session history (for replay / analytics)
  - Audit log entries
  - Encrypted MiniBrew token vault (per user)
  - Keg display-name overrides

- [ ] **MQTT Listener** — Direct ingestion from MiniBrew device MQTT stream
  - Lower latency than 2s polling
  - Requires broker URL + credentials from MiniBrew
  - `MqttWorker` alongside `PollingWorker`

- [ ] **Health Checks** — Improve Docker health checks
  - Backend: test MiniBrew API reachability, not just `localhost:8000`
  - Frontend: test nginx + backend connectivity

- [ ] **Graceful Degradation** — Handle MiniBrew API downtime
  - Show stale-data indicator in UI when API unreachable
  - Queue commands and replay when API recovers
  - Exponential backoff on polling failures

- [ ] **Metrics & Observability** — Add structured logging + metrics
  - [Langfuse](https://langfuse.com/) tracing for AI agent integration
  - Prometheus metrics endpoint (`/metrics`)
  - Request latency histograms
  - Error rate counters

- [ ] **Rate Limiting** — Protect MiniBrew API from burst requests
  - Per-session command rate limiting
  - Per-device command rate limiting
  - 429 Too Many Requests response when exceeded

---

## Automation & Integration

- [ ] **n8n Workflow Automation** — Webhook triggers for brew lifecycle events
  - Brew complete → notify via Slack/Email
  - Cleaning needed → trigger Telegram message
  - Keg temperature out of range → alert
  - Webhook endpoints at `/hooks/brew_complete`, `/hooks/cleaning_needed`, etc.

- [ ] **OpenClaw AI Agent** — Natural language control of brewing sessions
  - "Start a mash step" / "What's the current temperature?"
  - OpenClaw gateway integration with the orchestrator's command API
  - Multi-agent routing: AI agent reads device state, decides actions

- [ ] **Home Assistant Integration** — MQTT discovery + entity exposes
  - MiniBrew device as Home Assistant entity
  - Home Assistant automations triggered by brew state changes

---

## Frontend Improvements

- [ ] **Charts & Graphs** — Temperature, gravity, and fermentation curves over time
  - Use Chart.js or similar
  - Plot `current_temp`, `target_temp`, `gravity` from breweryoverview over session lifetime

- [ ] **Session History View** — Past sessions with full state replay
  - Session cards show duration, final gravity, outcome (success/fail)
  - Click to expand and see step-by-step state timeline

- [ ] **Push Notifications** — Browser notifications for:
  - User action required (Needs cleaning, Add ingredients, etc.)
  - Session complete
  - Failure states (BREWING_FAILED, etc.)

- [ ] **Dark/Light Mode Toggle** — Theme switcher in settings

- [ ] **Responsive Mobile Layout** — The dashboard currently works on tablet but mobile is rough

- [ ] **Keyboard Shortcuts** — Keyboard navigation for session selection and commands
  - `N` — new session
  - `R` — refresh
  - `↑/↓` — navigate session list
  - `Enter` — send selected command

- [ ] **Toast Notifications** — Non-blocking feedback for command success/failure instead of only console log

- [ ] **Keg Detail Modal** — Click on a keg card to see full details, history, pour counts

- [x] **Multi-Device Support** — Manage multiple MiniBrew devices from one dashboard *(done in v0.3.0)*
  - Device selector dropdown in header — lists all devices across all 4 brewery buckets
  - Aggregate view across all devices via `breweryoverview`; bucket selector switches active device
  - Active bucket tracked in `StateStore`; `bucket_changed` WebSocket message on switch

---

## Testing

- [ ] **Unit Tests** — `pytest` for:
  - `state_engine.py` — ProcessState, UserAction, Phase maps
  - `diff_engine.py` — should_broadcast / compute_diff logic
  - `command_service.py` — command routing and guard validation
  - `session_service.py` — session creation and lifecycle

- [ ] **Integration Tests** — httpx async test client against live endpoints
  - Test full command flow: create session → send command → verify state change

- [ ] **E2E Tests** — Playwright
  - Token gate → enter token → dashboard loads
  - Create brew session → verify session card appears
  - Send command → verify WebSocket update received
  - Settings panel → save token → verify `/settings/token` returns stored

- [ ] **CI/CD Pipeline** — GitHub Actions
  - Run tests on every PR
  - Lint: `ruff` / `flake8` + `mypy` type check
  - Build Docker images on tag push
  - Security scan: Trivy on Docker images

---

## Code Quality

- [ ] **Type Annotations** — All Python files fully typed (use `mypy --strict`)
- [ ] **Structured Logging** — Replace `print()` / basic `logging` with JSON structured logs
- [ ] **Dependency Pinning** — Pin all `requirements.txt` to exact versions
- [ ] **Dependabot / Renovate** — Automated dependency updates
- [ ] **API Documentation** — OpenAPI 3.1 spec auto-generated from FastAPI routes
  - Swagger UI at `/docs`
  - ReDoc at `/redoc`

---

## Documentation

- [ ] **API Changelog** — Document breaking changes between versions
- [ ] **MiniBrew API Reverse Engineering** — Document the full `breweryoverview` and `v1/devices` schema based on real API observations
- [ ] **Video Tutorial** — Getting started: install, token extraction, first brew session

---

## Priority Order

1. **[JWT Authentication]** — Security first; required for any multi-user or internet-exposed deployment
2. **[PostgreSQL Database]** — Foundation for users, audit log, session history
3. **[Redis State Store]** — Required before horizontal scaling or MQTT
4. **[E2E Tests + CI/CD]** — Catch regressions before they reach production
5. **[MQTT Listener]** — Latency improvement for real-time control
6. **[Audit Log]** — Compliance and debugging
7. **[Session History View]** — User experience
8. **[Charts & Graphs]** — User experience
9. [Everything else]
