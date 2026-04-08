# Contributing to MiniBrew Session Orchestrator

Thank you for contributing! Please read this guide before submitting PRs or issues.

## Development Setup

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- A MiniBrew account with API access

### Local Development (without Docker)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
MINIBREW_API_BASE=https://api.minibrew.io/v1/ \
MINIBREW_API_KEY=your_key \
python -m uvicorn main:app --port 8000 --reload

# Frontend (separate terminal)
cd frontend
python -m http.server 8080
```

Open http://localhost:8080

### Running Tests

```bash
# Backend tests
cd backend
pytest

# Lint
ruff check .

# Type check
mypy .
```

### Docker-Based Development

All stack operations use the `minibrew.sh` wrapper:

```bash
# Edit .env with your MINIBREW_API_KEY
cp .env.example .env

# Build and start
./minibrew.sh build

# Tail backend logs
./minibrew.sh logs

# Restart only backend (fast rebuild)
./minibrew.sh backend

# Check status
./minibrew.sh status
```

## Project Structure

```
minibrew-session-orchestrator/
├── backend/
│   ├── main.py              # FastAPI app + all routes
│   ├── minibrew_client.py  # MiniBrew API httpx wrapper
│   ├── session_service.py   # Session CRUD
│   ├── command_service.py   # Command routing + guards
│   ├── device_service.py    # Device state sync
│   ├── keg_service.py       # Keg management
│   ├── state_engine.py      # ProcessState/UserAction maps
│   ├── polling_worker.py    # Background poll loop
│   ├── websocket_manager.py # WS connection registry
│   ├── event_bus.py         # Internal pub/sub
│   ├── diff_engine.py        # Smart diffing
│   ├── state_store.py       # In-memory singleton
│   └── settings_store.py    # Encrypted token storage
├── frontend/
│   ├── index.html           # Dashboard HTML
│   ├── app.js               # WebSocket client + render logic
│   ├── style.css            # Dark theme CSS
│   └── nginx.conf           # Nginx proxy config
└── docker-compose.yml
```

## Code Conventions

### Python

- **Type annotations required** on all function signatures
- **No `print()`** — use `logging.getLogger(__name__).info(...)` instead
- **Async all the way** — use `async/await` for all I/O (httpx, file I/O)
- **No global mutable state** except for singleton services (StateStore, EventBus, etc.)
- **Pydantic models** for all request/response shapes
- **Exception handling** — never let unhandled exceptions propagate to FastAPI's default 500 response; catch and log with structured error context

### JavaScript

- **No framework** — vanilla JS only
- **ES modules** pattern — one global function per section, no `var`
- **No inline event handlers** — use `addEventListener` in `app.js`
- **No `any` type** — prefer explicit types or JSDoc annotations

### CSS

- **CSS custom properties** (variables) for colors, spacing
- **BEM naming** for component classes: `block__element--modifier`
- **No Tailwind** — plain CSS only, matching existing project style

## Submitting Changes

### Bug Fixes

1. Open an issue first (or comment on existing one)
2. Create a branch: `git checkout -b fix/short-description`
3. Write the fix + tests
4. PR description must include: what was broken, what was fixed, how to test

### New Features

1. Check the [TODO.md](./TODO.md) — comment on the item to say you're working on it
2. Create a branch: `git checkout -b feature/feature-name`
3. Implement with tests
4. Update `TODO.md` if applicable
5. PR must include: motivation, changes, screenshot (if UI), test steps

### PR Requirements

- [ ] All tests pass
- [ ] `ruff check .` passes with no warnings
- [ ] `mypy --strict backend/` passes
- [ ] No new `console.log` or `print` statements
- [ ] New environment variables documented in README and `.env.example`
- [ ] New API endpoints documented

## Commit Messages

Format: `type: short description`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `security`

Examples:
```
feat: add JWT authentication
fix: token gate not dismissing after save
docs: add troubleshooting section to README
refactor: extract command routing into CommandService
chore: pin pytest version to 8.x
```

## Reporting Security Issues

Please do **not** file a public GitHub issue for security vulnerabilities. Instead:

1. Email the maintainer directly (see `CODEOWNERS`)
2. Or use GitHub's **Security Advisories** feature ( Advisors → Report vulnerability)

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
