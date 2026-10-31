# T25 — Hardening: security, rate limits, observability, production deployment

**Owner:** Codex (medium) · **Branch:** `task/T25` · **Refs:** SPEC §3 (security, reliability) · ARCHITECTURE §8, §9 · AGENTS.md

## Goal
Make Qbank safe to run for a real school: abuse protection, secure defaults, useful logs and health checks, and a documented one-command production deployment.

## Scope
`backend/**`, `frontend/Caddyfile`, `frontend/Dockerfile` (only if needed), `docker-compose.prod.yml` (new), `.env.prod.example` (new), `Makefile`, `docs/DEPLOY.md` (new) and `docs/SECURITY.md` (new).
**Don't** touch `frontend/src/**` (other tasks are editing the UI in parallel), and don't edit README.md (the orchestrator updates it).
**Migrations:** only if needed. Use `down_revision` = the current head and the file name prefix `t25_`.

## Requirements
### 1. Security
- **Rate limits** (Redis-backed, fixed-window or token-bucket, in `qbank/security/ratelimit.py`): login 10 / 15 min per (IP, email) **and** 50 / 15 min per IP → 429 `code: rate_limited` with `Retry-After`;
  uploads 20 / hour per user; `/compose` and `/reextract` and `/extract-region` 30 / hour per user (all configurable). Behind a reverse proxy, trust `X-Forwarded-For` only from `settings.trusted_proxies`.
- **Security headers** middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `Permissions-Policy` (camera/mic/geo off), and HSTS when `cookie_secure`.
  Caddy (SPA) sends a strict **CSP**: `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
  Verify the built SPA works under it (KaTeX uses inline styles, hence `style-src 'unsafe-inline'`). Document why.
- **Passwords:** a minimum length of 10 on create/change, rejecting the 1,000 most common passwords (a small bundled list file). Add `POST /api/v1/auth/change-password` (current + new).
  **Session revocation:** add `users.token_version`, include it in the JWT, and check it in `current_user`. It's bumped on password change, deactivation and role change.
- Review and fix if needed: path traversal in `LocalStore` keys (already tested; re-check), upload content sniffing (the PDF magic bytes are already checked; also reject encrypted PDFs early with `code: encrypted_pdf`),
  SSRF (the server must never fetch user-supplied URLs; confirm the QMD export doesn't), SQL built from user input (grep for f-strings in `text()`; parametrize them), and error responses leaking internals.
- `docs/SECURITY.md`: the threat model (assets, actors, trust boundaries), the controls in place, known limitations, and how to report issues.

### 2. Observability
- structlog JSON logs with `request_id`, `user_id`, `org_id`, `path`, `status`, `duration_ms` (an access-log middleware). Never log secrets, cookies, passwords or LLM prompt contents. Make the log level configurable.
- The worker logs the actor name, source_id, duration and outcome per message.
- `GET /api/v1/ready` (readiness: DB, Redis and object storage reachable, with a 2 s timeout each) next to the existing `/health` (liveness).

### 3. Production deployment
- `docker-compose.prod.yml`: `caddy` (the frontend image: serves the SPA, reverse-proxies `/api/*` to `api:8000`, automatic HTTPS for `${QBANK_DOMAIN}`), `api` (uvicorn with `--workers ${API_WORKERS:-2}`, `--proxy-headers`),
  `worker` (dramatiq; `deploy.replicas` configurable), `migrate` (a one-shot `alembic upgrade head` that runs before the API and worker start), `postgres` (with a volume and healthcheck), `redis`, and `minio` (optional profile; an external S3 is supported via env).
  All services get restart policies, healthchecks, non-root users where possible, and no ports exposed except Caddy's 80/443.
- `.env.prod.example` with every variable documented (generate-a-secret hints, `QBANK_ENV=prod`, `QBANK_COOKIE_SECURE=true`, the OpenRouter key, budgets and caps).
- Makefile targets: `prod-build`, `prod-up`, `prod-down`, `prod-logs`, `prod-admin` (runs `python -m qbank.cli create-admin` inside the api container), and `prod-backup` (`pg_dump` to `./backups/<date>.sql.gz` plus a note about object storage).
- `docs/DEPLOY.md`: requirements (a VPS size estimate), DNS, the env setup, first boot, creating the admin, backups and restore, upgrades (pull, build, up, migrations run automatically), scaling workers, cost controls (the OpenRouter key limit + `QBANK_LLM_BUDGET_USD` + per-org caps), and troubleshooting.
- **Smoke test it locally:** `QBANK_DOMAIN=localhost make prod-up` (Caddy's internal CA for localhost). `curl -k https://localhost/` returns the SPA, and `https://localhost/api/v1/ready` is all OK. Then `make prod-down -v`. Put the commands and output in your report.

### Tests
Rate limits (the per-IP+email and per-IP limits, Retry-After, the trusted-proxy handling, and the reset after the window, using a time override). Security headers present. Password policy and change-password. Token revocation on password change, deactivation and role change.
The encrypted PDF rejected. The readiness endpoint with each dependency down (mocked). The access-log fields (and that no cookies or passwords appear in the log).

## Acceptance
`make check` passes. Run `make api-gen` and commit the generated files. The prod smoke test passes locally (with the evidence in your report).
