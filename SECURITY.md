# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please do **not** open a public issue. Instead:

1. **Email** the maintainer directly at the address in the repository's `CODEOWNERS` file
2. Or use **GitHub Security Advisories**: Go to the repo → Security → Report a vulnerability

Please include as much detail as possible:
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested remediation (if any)

We aim to respond within **48 hours** and will work with you on a disclosure timeline.

## Security Considerations

### Bearer Token Storage

The MiniBrew API bearer token is stored encrypted at rest using Fernet (AES-128-CBC with PBKDF2 key derivation) in `/app/data/settings.json` inside the Docker container.

- The master key is derived once at first boot and stored in `/app/data/.master.key`
- Tokens are encrypted before writing to disk
- **Warning**: The master key file persists across container restarts. If you need to purge all credentials, delete both files:

```bash
docker exec minibrew-backend rm -f /app/data/settings.json /app/data/.master.key
docker-compose restart backend
```

### Production Deployments

For production environments:

1. **Use Docker secrets** or Kubernetes secrets for `MINIBREW_API_KEY` instead of `.env` files
2. **Enable TLS** — this application does not handle TLS; terminate SSL at your reverse proxy (Caddy, Traefik, Nginx) or use a tunnel (Cloudflare Tunnel, ngrok)
3. **Restrict network access** — the backend should not be directly exposed to the internet; place it behind a properly configured reverse proxy with SSL
4. **Rotate tokens regularly** — rotate your MiniBrew API token via the Settings panel and update your secret manager
5. **No built-in rate limiting** — deploy behind a rate-limiting proxy (e.g. Nginx `limit_req`) to prevent abuse
6. **JWT (when implemented)** — store signing keys securely; use short-lived access tokens (15 min) + refresh tokens; never log tokens

## Known Security Limitations

- **No built-in authentication** (see [TODO.md](./TODO.md)) — the dashboard is currently open; use network-level access controls until JWT auth is implemented
- **No audit log** (see [TODO.md](./TODO.md)) — all commands are logged only to stdout; implement audit log before production use with sensitive equipment
- **In-memory state** — state is not persisted across backend restarts; do not rely on it for critical session tracking
