# Maintainers

## Primary Maintainer

**Your Name Here**
- GitHub: [@yourgithub](https://github.com/YOUR_GITHUB)
- Email: your@email.com

## Project Mission

The MiniBrew Session Orchestrator aims to be the most capable open-source control plane for MiniBrew brewing devices. It prioritizes:

1. **Reliability** — deterministic command validation; no phantom commands sent to the device
2. **Real-time fidelity** — all state changes pushed to all connected clients immediately
3. **Observability** — every numerical code mapped to a human-readable label; failure states cannot be missed
4. **Security** — credentials encrypted at rest; no plaintext token storage
5. **Self-hostability** — runs entirely in Docker on your own hardware

## Release Process

1. Changes merged to `main` trigger CI pipeline (lint → test → build → scan)
2. On a git tag `vX.Y.Z`, Docker images are built and pushed to Docker Hub
3. A GitHub Release is created with the changelog for that version
4. `CHANGELOG.md` is updated as part of the PR merge

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Stable, shippable code |
| `feature/*` | Work in progress features |
| `fix/*` | Bug fixes in progress |

PRs from `feature/*` or `fix/*` → `main` require at least one review approval.

## Communication

- **Issues** — preferred for bugs and feature requests
- **Discussions** — use for questions, setup help, general conversation
- **Security issues** — see [SECURITY.md](./SECURITY.md); do not open public issues
