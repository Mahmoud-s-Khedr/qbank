# T01 — Backend scaffold, infra, Makefile

**Owner:** Codex · **Branch:** `task/T01` · **Refs:** ARCHITECTURE §2, §8, §9 · AGENTS.md

## Goal
A runnable, fully linted and type-checked FastAPI skeleton with database plumbing, local
infrastructure, and the root Makefile that every later task uses. No business features yet.

## Scope: files you own
`backend/**`, `docker-compose.yml`, `Makefile`, `.env.example`. Do **not** create anything under `frontend/` or `.github/`.

## Requirements

### Project (`backend/`)
- uv project, `requires-python = ">=3.12,<3.13"`, src layout, package `qbank`, `uv.lock` committed.
- Runtime deps: fastapi, uvicorn[standard], pydantic, pydantic-settings, sqlalchemy>=2, psycopg[binary]>=3, alembic, structlog, uuid-utils (for uuid7).
- Dev deps (uv dependency group `dev`): ruff, mypy, pytest, pytest-cov, httpx.
- `ruff`: line-length 100, target py312. `select = ["E","W","F","I","B","UP","SIM","RUF","S","N","PT","C4","DTZ","T20","ASYNC","PL","PERF"]` with only well-justified ignores (e.g. `S101` in tests via per-file-ignores, `PLR0913` if needed). Configure ruff format.
- `mypy`: `strict = true`, the pydantic plugin, and `files = ["src", "tests"]`.
- `pytest`: `testpaths = ["tests"]`, markers `integration` (needs postgres), coverage on `qbank` with `fail_under = 80`.

### Code
- `qbank/config.py`: `Settings(BaseSettings)` with `env_prefix="QBANK_"`, reading `.env`. Fields: `env` (`dev`/`test`/`prod`), `database_url`, `redis_url`, `s3_endpoint_url`, `s3_bucket`, `s3_access_key`, `s3_secret_key` (SecretStr), `openrouter_api_key` (SecretStr | None), `jwt_secret` (SecretStr), `cors_origins` (list). Provide `get_settings()` with an lru_cache.
- `qbank/db/`: an engine/session factory (sync SQLAlchemy 2, psycopg 3), the `get_db` dependency, and a declarative `Base` with a naming convention for constraints. Mixins: `UUIDPk` (uuid7 default), `Timestamps` (`created_at`/`updated_at`, timezone-aware, server defaults).
- Alembic in `backend/src/qbank/db/migrations/`, configured from `Settings.database_url`, with `target_metadata = Base.metadata` and `compare_type=True`. Add one initial migration that enables the extensions `pg_trgm` and `unaccent`.
- `qbank/api/main.py`: `create_app()` factory with CORS, request-id middleware, structlog JSON logging, and RFC 7807 problem+json exception handlers (`HTTPException`, `RequestValidationError`, unhandled → 500 without leaking internals). Export `app = create_app()`.
- **Health contract (the frontend task T02 depends on this exact shape):**
  `GET /api/v1/health` → `200 {"status": "ok", "version": "<pkg version>", "db": "ok" | "down"}`. The `db` field comes from a `SELECT 1` with a short timeout. If the DB is down, still return 200 with `"db": "down"`.
- `qbank/api/openapi_dump.py`: `python -m qbank.api.openapi_dump` writes `backend/openapi.json` (sorted keys, indent 2, trailing newline). Commit the generated file.
- `qbank/worker.py`: a minimal placeholder module (only a docstring and a TODO for T05). Do not add Dramatiq yet.

### Tests
- `tests/conftest.py`: an app fixture and a TestClient fixture. An `integration` DB fixture creates a throwaway database `qbank_test_<random>` on the server from `QBANK_DATABASE_URL`, runs `alembic upgrade head`, and drops it afterwards.
- Tests: health endpoint with DB up (integration) and with DB down (unit, by overriding the dependency); problem+json for 404 and 422; settings load from env; `alembic upgrade head` then `alembic check` shows no drift (integration).

### Infra
- `docker-compose.yml` (root) with services `postgres` (postgres:18), `redis` (redis:8-alpine) and `minio` (+ a one-shot `minio-init` that creates the bucket). Use healthchecks and named volumes. **Use non-default host ports** so nothing clashes with services on the dev machine: postgres `55432`, redis `56379`, minio `59000` (console `59001`).
- `backend/Dockerfile`: multi-stage, uv-based, non-root user, runs `uvicorn qbank.api.main:app`. (T21 will add Pandoc and Chromium later. Leave a comment.)
- `.env.example` with every `QBANK_*` var, pointing at the compose ports.

### Makefile (root). Create all of these targets; frontend ones delegate to pnpm scripts that T02 provides:
```
infra-up infra-down
be-install be-lint be-fmt be-types be-test be-test-unit be-migrate be-openapi
fe-install fe-lint fe-types fe-test fe-build      # = pnpm -C frontend install|lint|typecheck|test|build
api-gen      # be-openapi, then (if frontend/ exists) pnpm -C frontend api:gen
check        # be-lint be-types be-test; plus fe-lint fe-types fe-test fe-build if frontend/package.json exists
```
`be-lint` = `ruff check` + `ruff format --check`. `be-test` runs everything, including integration tests (it needs infra-up). `be-test-unit` runs `-m "not integration"`.
All backend commands run with `uv run --directory backend`.

## Acceptance
- `make infra-up && make be-install && make check` passes from a clean clone (the frontend part is skipped if `frontend/` is absent).
- `uv run --directory backend uvicorn qbank.api.main:app` serves `/api/v1/health` and `/docs`.
- `backend/openapi.json` is committed and matches `make be-openapi` output.
