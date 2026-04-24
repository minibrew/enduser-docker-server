# Backend Recreation Plan — MiniBrew Session Orchestrator

## Context

This document outlines a plan to recreate the MiniBrew Session Orchestrator backend using a proper task queue architecture (Celery + PostgreSQL) instead of the current in-memory polling approach, and to integrate real-time device communication via MQTT as specified in `MQTT Message Specifications.md`.

---

## 1. Architecture Overview

### Target Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API Server | FastAPI + Uvicorn | REST endpoints + WebSocket |
| Task Queue | Celery + Redis | Async background jobs (polling, commands) |
| Message Broker | MQTT (broker from MiniBrew) | Real-time device events |
| Database | PostgreSQL | Persistent state, session history, audit log, users |
| Cache / Real-time | Redis + Celery Events | Celery result backend, pub/sub |
| State Store | Redis | Device/session state (replaces in-memory StateStore) |

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           Browser (Dashboard)                             │
│                     HTTP/WebSocket — localhost:8080                      │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Nginx (frontend container)                             │
│              Proxies /ws → backend, serves static files                   │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (:8000)                                 │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Auth API     │  │ Device API   │  │ Session API │  │ WebSocketMgr │ │
│  │ /auth/*     │  │ /devices/*  │  │ /sessions/* │  │ /ws          │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Service Layer                                   │   │
│  │  MiniBrewClient │ StateService │ CommandService │ AuditService   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐
│   Celery Worker   │  │  MQTT Client     │  │   PostgreSQL              │
│  (Celery beat     │  │  (aiomqtt /      │  │  (asyncpg / SQLAlchemy    │
│   scheduled)      │  │   asyncio-mqtt)  │  │   with Alembic migrations) │
│                  │  │                  │  │                           │
│  • poll_brewer   │  │ Subscribe:       │  │ Tables:                   │
│    yoverview     │  │  devices/events  │  │   • users                 │
│  • poll_sessions │  │  devices/status  │  │   • sessions              │
│  • poll_kegs     │  │  devices/batch   │  │   • kegs                  │
│  • sync_state    │  │    logs          │  │   • audit_log              │
│                  │  │                  │  │   • device_state           │
│                  │  │ Publish:        │  │   • miniBrew_tokens (vault)│
│                  │  │  backend/cmds   │  │                           │
└──────────────────┘  └──────────────────┘  └───────────────────────────────┘
          │                      │
          │                      ▼
          │            ┌──────────────────┐
          │            │  MQTT Broker      │
          │            │ (MiniBrew cloud) │
          │            │                  │
          │            │ Topics per       │
          │            │ MQTT Spec:       │
          │            │  BE→DE: commands │
          │            │  DE→BE: events   │
          │            │  DE→BE: batchlogs│
          │            │  DE→BE: status   │
          │            └──────────────────┘
          │
          ▼
┌──────────────────┐
│  Redis           │
│  (Celery result  │
│   backend +      │
│   pub/sub for    │
│   WS broadcast)  │
└──────────────────┘
```

---

## 2. MQTT Integration Plan

### Referencing: `MQTT Message Specifications.md`

The MQTT spec defines a structured topic hierarchy. Integrate as follows:

#### Topic Mapping

| Direction | Topic Pattern | Action | Payload |
|-----------|--------------|--------|---------|
| BE → DE | `backend/commands/{SerialNumber}` | Celery task publishes command | Protobuf `Command` message |
| DE → BE | `devices/events/{SerialNumber}` | MQTTWorker subscribes | Protobuf `Event` message |
| DE → BE | `devices/status/{SerialNumber}` | MQTTWorker subscribes (retained) | Protobuf `Info` message (online/offline) |
| DE → BE | `devices/batchlogs/{SerialNumber}` | MQTTWorker subscribes | Protobuf `BatchLog` message |
| BE → DE | `backend/events/{SerialNumber}` | Ack / control response | Protobuf `EventResponse` |

#### Serial Number Format
From spec: `15AB510E93FA46` (MAC address without `:` or `-`), or device serial number like `1903K0001-ABCD1234`. The MiniBrew device UUID (e.g. `2403B0994-SHNCANKM`) maps to this serial number.

#### Protobuf Schema
Reference: https://github.com/minibrew/minibrew-protobuf

```protobuf
// Estimated from spec — verify against minibrew-protobuf repo
message Command {
  string serial_number = 1;
  int32 command_type = 2;   // 2=wake, 3=generic, 6=update_recipe
  map<string, string> params = 3;
  int64 timestamp = 4;
}

message Event {
  string serial_number = 1;
  int32 event_type = 2;
  bytes payload = 3;
  int64 timestamp = 4;
}

message Info {
  string serial_number = 1;
  string software_version = 2;
  bool online = 3;
  int64 last_seen = 4;
}
```

#### MQTT Worker Design

```python
# Pseudocode — mqtt_worker.py (Celery task)
@celery_app.task
def mqtt_subscribe():
    """
    Long-running task (run with celery worker --pool=gevent
    or use a separate asyncio loop).

    Subscribes to device event topics per MQTT spec.
    On each message: parse protobuf → update Redis state →
    publish to Redis pub/sub → WebSocket broadcasts.
    """
    async def on_message(topic: str, payload: bytes):
        topic_parts = topic.split("/")  # e.g. ["devices", "events", "15AB510E93FA46"]
        serial = topic_parts[2]

        if topic_parts[1] == "events":
            event = Event_pb2.Event().ParseFromString(payload)
            await state_service.update_device_event(serial, event)
        elif topic_parts[1] == "status":
            info = Info_pb2.Info().ParseFromString(payload)
            await state_service.update_device_online(serial, info)

        # Broadcast via Redis pub/sub
        await redis_client.publish(f"ws:broadcast", serialize_state())

    async with aiomqtt.Client() as client:
        await client.subscribe("devices/events/#")
        await client.subscribe("devices/status/#")
        await client.message_loop(on_message)
```

#### Transition Strategy (Polling → MQTT)

1. **Phase 1**: Keep `PollingWorker` running alongside new `MqttWorker`; use MQTT data when available, fall back to polling
2. **Phase 2**: Make polling exponential-backoff on MQTT success; eventually disable polling
3. **Phase 3**: Polling disabled; pure MQTT-driven state updates

---

## 3. PostgreSQL Schema Plan

### Core Tables

```sql
-- Users for dashboard auth (distinct from MiniBrew API tokens)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Encrypted MiniBrew API token vault (per user)
CREATE TABLE minibrew_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    encrypted_token BYTEA NOT NULL,
    source VARCHAR(20) DEFAULT 'env',  -- 'env', 'stored'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Session history for replay/analytics
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    minibrew_uuid VARCHAR(255) NOT NULL,
    session_type SMALLINT NOT NULL,  -- 0=brew, 1=clean, 2=acid_clean
    beer_recipe JSONB,
    status SMALLINT DEFAULT 1,       -- 1=active, 2=in_progress, 4=completed, 6=failed
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Keg display-name overrides
CREATE TABLE kegs (
    uuid VARCHAR(255) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    display_name VARCHAR(255),
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

-- Device state snapshots (for history/replay)
CREATE TABLE device_state_history (
    id SERIAL PRIMARY KEY,
    serial_number VARCHAR(255) NOT NULL,
    process_state INTEGER,
    user_action INTEGER,
    phase VARCHAR(50),
    is_failure BOOLEAN,
    snapshot JSONB NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log (replace JSONL file with PostgreSQL)
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    username VARCHAR(255),
    action_type VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    command VARCHAR(100),
    result VARCHAR(20),
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_action_type ON audit_log(action_type);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_minibrew_uuid ON sessions(minibrew_uuid);
CREATE INDEX idx_device_state_history_serial ON device_state_history(serial_number);
```

### Alembic Migrations
Use Alembic for schema migrations — `alembic init` + `alembic revision --autogenerate`.

---

## 4. Celery Task Design

### Task Registry

```python
# backend/celery_app.py
from celery import Celery
celery_app = Celery("minibrew")
celery_app.conf.broker_url = "redis://redis:6379/0"
celery_app.conf.result_backend = "redis://redis:6379/0"
celery_app.conf.redis_celery_db = 1
celery_app.conf.include = ["backend.tasks.poll_tasks", "backend.tasks.command_tasks"]
celery_app.conf.beat_schedule = {
    "poll-brewery-overview": {
        "task": "poll_brewery_overview",
        "schedule": 2.0,
    },
    "poll-sessions": {
        "task": "poll_sessions",
        "schedule": 2.0,
    },
    "poll-kegs": {
        "task": "poll_kegs",
        "schedule": 2.0,
    },
}
```

### Key Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `poll_brewery_overview` | Every 2s | Fetch breweryoverview → update Redis state |
| `poll_sessions` | Every 2s | Fetch /v1/sessions → upsert into PostgreSQL |
| `poll_kegs` | Every 2s | Fetch /v1/kegs → upsert into PostgreSQL |
| `send_session_command` | On-demand | Celery task: validate user_action guard → PUT to MiniBrew API → log to audit |
| `send_mqtt_command` | On-demand | Publish command to MQTT broker `backend/commands/{serial}` |
| `mqtt_subscribe` | Long-running | Subscribes to MQTT topics; updates Redis on device events |
| `sync_device_state` | On-demand | Fetch + enrich device state; store in Redis |

### Command Flow (Celery Task)

```
POST /session/{id}/command
         │
         ▼
Celery task: send_session_command(session_id, command, params)
         │
         ├──► Validate user_action → ALLOWED_COMMANDS_BY_USER_ACTION
         │
         ├──► MiniBrewClient.send_session_command() via REST API
         │         (or publish to MQTT for devices that support it)
         │
         └──► AuditService.log_action() → PostgreSQL audit_log
```

---

## 5. Redis State Design

### Keys

| Key | Type | TTL | Description |
|-----|------|-----|-------------|
| `state:brewery_overview` | Hash | None | Full breweryoverview (4 buckets) |
| `state:device:{bucket}` | Hash | None | Enriched device state per bucket |
| `state:session:{id}` | Hash | None | Session data |
| `state:keg:{uuid}` | Hash | None | Keg data |
| `state:selected_bucket` | String | None | Currently selected bucket |
| `ws:broadcast` | Channel | — | Pub/sub for WebSocket broadcast trigger |
| `user:token:{user_id}` | String | Session | User's active MiniBrew token |

### Broadcasting via Redis Pub/Sub

```python
# When MQTT or polling task updates state:
await redis.publish("ws:broadcast", json.dumps(update_payload))

# FastAPI WebSocket endpoint subscribes:
async def websocket_endpoint(ws):
    await ws.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe("ws:broadcast")
    async for message in pubsub.listen():
        await ws.send_json(message["data"])
```

This replaces the in-memory `EventBus` with a Redis-backed pub/sub that works across multiple backend replicas.

---

## 6. API Changes

### New Endpoints (PostgreSQL-backed)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sessions/history` | Paginated session history from PostgreSQL |
| GET | `/audit/log` | Paginated audit log with filters |
| GET | `/metrics` | Prometheus metrics endpoint |
| POST | `/hooks/brew_complete` | n8n webhook: brew complete event |
| POST | `/hooks/cleaning_needed` | n8n webhook: cleaning needed event |

### Changed Behaviors

| Before | After |
|--------|-------|
| `/sessions` → from in-memory StateStore | `/sessions` → from PostgreSQL |
| `/kegs` → from in-memory StateStore | `/kegs` → from PostgreSQL |
| `EventBus` (in-memory pub/sub) | Redis pub/sub (multi-replica safe) |
| No auth on `POST /settings/token` | Proper JWT auth on all protected endpoints |
| Token gate UI only | Full JWT auth with login/logout UI |

---

## 7. Implementation Phases

### Phase 1: Foundation
- [ ] Set up PostgreSQL with Alembic migrations
- [ ] Set up Redis for Celery broker + result backend
- [ ] Move `StateStore` → Redis (`state:*` keys)
- [ ] Move `audit_service` JSONL → PostgreSQL `audit_log`
- [ ] Move user auth from bypass → real JWT with PostgreSQL users table
- [ ] Add `minibrew_tokens` vault table

### Phase 2: Celery Integration
- [ ] Create `celery_app.py` with Redis backend
- [ ] Convert `PollingWorker` → Celery beat scheduled tasks
- [ ] Convert command dispatch → Celery tasks with audit logging
- [ ] Wire WebSocket → Redis pub/sub subscription

### Phase 3: MQTT Integration
- [ ] Set up MQTT client (aiomqtt) as Celery task
- [ ] Define protobuf messages per minibrew-protobuf
- [ ] Implement topic subscription per MQTT spec
- [ ] Update Redis state from MQTT events
- [ ] Implement transition strategy (polling + MQTT, then polling off)

### Phase 4: Polish
- [ ] Add Prometheus metrics endpoint
- [ ] Add rate limiting (per-device, per-session)
- [ ] Add graceful degradation on MiniBrew API downtime
- [ ] Add session history replay view
- [ ] Add n8n webhook endpoints

---

## 8. Key Files to Create

```
backend/
├── celery_app.py              # Celery app + beat schedule
├── tasks/
│   ├── __init__.py
│   ├── poll_tasks.py         # poll_brewery_overview, poll_sessions, poll_kegs
│   ├── command_tasks.py      # send_session_command, send_mqtt_command
│   └── mqtt_tasks.py        # mqtt_subscribe (long-running)
├── db/
│   ├── __init__.py
│   ├── connection.py          # asyncpg connection pool
│   ├── models.py             # SQLAlchemy or raw asyncpg queries
│   └── migrations/           # Alembic migrations
├── redis_state.py            # Redis state store (replaces StateStore)
├── services/
│   ├── mqtt_client.py        # aiomqtt wrapper
│   └── proto/
│       ├── commands_pb2.py   # Generated from minibrew-protobuf
│       └── events_pb2.py
├── middleware/
│   └── jwt_auth.py           # FastAPI JWT dependency
└── api/
    └── deprecated.py          # Mark old endpoints if routing changes
```

---

## 9. Testing Plan

```bash
# Unit tests
pytest tests/unit/state_engine/     # ProcessState, UserAction, command guards
pytest tests/unit/command_service/ # routing and validation
pytest tests/unit/celery_tasks/   # task functions (mock MiniBrewClient)

# Integration tests
pytest tests/integration/api/      # httpx async client against live endpoints
pytest tests/integration/celery/  # Celery task execution with Redis

# E2E tests (Playwright)
pytest tests/e2e/
  ├── test_token_gate.py          # token gate → dashboard loads
  ├── test_session_lifecycle.py  # create brew → send command → delete
  └── test_websocket.py          # WebSocket receives device_update

# MQTT integration tests (mock broker)
pytest tests/integration/mqtt/
```

---

## 10. Migration from Current Code

### Mapping: Current Module → New Module

| Current | New | Notes |
|---------|-----|-------|
| `polling_worker.py` | `tasks/poll_tasks.py` | Celery beat scheduled tasks |
| `state_store.py` | `redis_state.py` | Redis hash storage |
| `event_bus.py` | `redis pub/sub` | `ws:broadcast` channel |
| `websocket_manager.py` | `redis pub/sub subscriber` | WebSocket subscribes to Redis |
| `command_service.py` | `tasks/command_tasks.py` | Celery task + guard validation |
| `minibrew_client.py` | `services/minibrew_client.py` | Same httpx wrapper |
| `session_service.py` | `services/session_service.py` + PostgreSQL | Persisted to DB |
| `settings_store.py` | PostgreSQL `minibrew_tokens` + Redis | Encrypted token vault |
| `auth_service.py` | `middleware/jwt_auth.py` | Real JWT, PostgreSQL users |
| `audit_service.py` | PostgreSQL `audit_log` | JSONL → relational |

### Backward Compatibility
- Keep REST API surface identical (same `/sessions`, `/device`, `/command` paths)
- WebSocket message types unchanged (`initial_state`, `device_update`, etc.)
- Frontend requires no changes

---

## 11. Environment Variables (New)

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@postgres:5432/minibrew` | PostgreSQL connection |
| `REDIS_URL` | `redis://redis:6379/0` | Redis for Celery + state |
| `MQTT_BROKER_URL` | *(required for MQTT)* | MQTT broker URL |
| `MQTT_USERNAME` | — | MQTT auth username |
| `MQTT_PASSWORD` | — | MQTT auth password |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery broker (same as REDIS_URL) |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | Celery result backend |
| `MINIBREW_API_BASE` | `https://api.minibrew.io/v1/` | MiniBrew API base |
| `MINIBREW_API_KEY` | — | MiniBrew bearer token |
| `JWT_SECRET` | *(auto-generated)* | JWT signing secret |
| `POLL_INTERVAL_MS` | `2000` | Fallback polling interval (used until MQTT fully online) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
