# T03 — CI, pre-commit, dependency automation, quality gates

**Owner:** Codex · **Branch:** `task/T03` · **Refs:** ARCHITECTURE §8 · AGENTS.md

## Goal
Every quality gate runs automatically on every PR and push to `main`, and the same checks can be run locally.
The user explicitly asked that CI and linting be configured correctly. Treat this as a first-class deliverable.

## Scope
`.github/**`, `.pre-commit-config.yaml`, `.editorconfig`, `.python-version`, `.node-version`, `Makefile`,
`backend/pyproject.toml` **only** the `[tool.*]` sections (no dependency changes), `backend/src/qbank/config.py` (dev secret only),
and test files if needed to clear warnings.
**Do not change dependencies** (`[project]`/`[dependency-groups]`, `uv.lock`, `package.json` deps, `pnpm-lock.yaml`):
another agent is changing backend dependencies in parallel. Run tools that aren't project deps with `uvx`, `pnpm dlx` or Docker.

## Current state
Backend: ruff, mypy strict, pytest with coverage ≥ 80% (integration tests need postgres). Frontend: eslint (strict-type-checked, 0 warnings),
the RTL guard, prettier, `tsc --noEmit`, vitest and vite build. API contract: `make api-gen` regenerates `backend/openapi.json` and
`frontend/src/api/schema.d.ts`. Read `Makefile`, `backend/pyproject.toml`, `frontend/package.json` and `docker-compose.yml` first.

## Requirements

### 1. `.github/workflows/ci.yml`
Triggers: `pull_request`, `push` to `main`, `workflow_dispatch`. `permissions: contents: read`. A `concurrency` group per ref
with cancel-in-progress for PRs. Every job has a `timeout-minutes`. Use current major versions of official actions
(`actions/checkout`, `actions/setup-node`, `astral-sh/setup-uv` with cache, `pnpm/action-setup`, `docker/setup-buildx-action`, `docker/build-push-action`).

Jobs:
1. **backend**: services `postgres:18` and `redis:8-alpine` with health options. Env `QBANK_DATABASE_URL` and `QBANK_REDIS_URL` point at the service containers.
   Steps: `make be-install` → `make be-lint` → `make be-types` → `make be-test` (uploads `coverage.xml` as an artifact) → `alembic upgrade head` + `alembic check`.
2. **frontend**: Node from `.node-version` and pnpm from `packageManager`, with the pnpm store cached.
   Steps: `make fe-install` (frozen) → `make fe-lint` → `pnpm -C frontend format:check` → `make fe-types` → `pnpm -C frontend test:coverage` → `make fe-build`.
3. **contract**: sets up both stacks and runs `make contract-check` (see Makefile), which fails if `make api-gen` changes any tracked file.
4. **docker**: builds `backend/Dockerfile` and `frontend/Dockerfile` with buildx and the GHA cache (no push).
5. **security**: gitleaks over the full history (`fetch-depth: 0`), run via the official Docker image (`zricethezav/gitleaks`), **not** the licensed gitleaks-action.
   `pip-audit` on the exported locked requirements (`uv export --frozen --no-dev --no-hashes | uvx pip-audit -r /dev/stdin --strict` or equivalent).
   `pnpm -C frontend audit --prod --audit-level high`.
6. An **all-green** gate job (`needs: [backend, frontend, contract, docker, security]`) that branch protection can require as a single check.

Do not add the e2e job (T24) or eval.yml (T10). Leave a comment noting where they go.

### 2. Warnings are errors
- Backend pytest: `filterwarnings = ["error"]`, plus narrowly-scoped ignores only for third-party deprecations you cannot fix (comment each one).
  The current run shows 21 warnings. Fix them:
  - `InsecureKeyLengthWarning`: make the dev default `jwt_secret` ≥ 32 chars (and `.env.example` too), and use a ≥ 32-char secret in tests.
  - The Starlette `httpx` TestClient deprecation: add a narrowly-scoped ignore with a comment. Do not change dependencies.
- Frontend: vitest must fail on unhandled errors/rejections (the default), and there should be no React `act()` warnings. Fix any you find.

### 3. Makefile additions
- `contract-check`: `make api-gen` then `git diff --exit-code -- backend/openapi.json frontend/src/api/schema.d.ts`.
- `lint-actions`: actionlint via Docker (`rhysd/actionlint`).
- `pre-commit-install`.
- `check` additionally runs `contract-check` and `lint-actions`.

### 4. `.pre-commit-config.yaml`
`pre-commit-hooks` (trailing-whitespace, end-of-file-fixer, check-yaml, check-json, check-toml, check-merge-conflict,
check-added-large-files `--maxkb=1024` excluding `^fixtures/`, mixed-line-ending), `ruff-pre-commit` (ruff check --fix, ruff format),
gitleaks, plus local hooks for prettier (changed frontend files) and eslint (changed frontend files) via `pnpm -C frontend exec`,
and mypy as a local `uv run` hook on push only (`stages: [pre-push]`). Exclude generated files (`schema.d.ts`, `openapi.json`, `uv.lock`, `pnpm-lock.yaml`)
from formatters where needed. `pre-commit run --all-files` must pass on the current tree. Fix trivial whitespace/EOF issues it finds.

### 5. Dependabot (`.github/dependabot.yml`)
Ecosystems `uv` (`/backend`), `npm` (`/frontend`), `github-actions` (`/`), and `docker` (`/backend`, `/frontend`). Weekly, with grouped minor+patch updates,
an open-PR limit of 5 per ecosystem, and conventional commit prefixes.

### 6. Repo hygiene
- `.editorconfig` (utf-8, lf, final newline, 2-space indent, 4 for Python, keep trailing whitespace in Markdown).
- `.python-version` (`3.12`) and `.node-version` (`22`).
- `.github/pull_request_template.md` with a checklist mirroring the AGENTS.md Definition of Done.

## Verification you must do locally (put the results in your report)
- `make lint-actions`: 0 findings.
- `pre-commit run --all-files`: passes.
- `make check`: passes, with **0 warnings** in the backend pytest output.
- Build both Docker images locally (`docker build backend` and `docker build frontend`).
- Run each security command locally and report its result. If an audit finds a real vulnerability in a pinned dep, report it as a follow-up. Do not upgrade it.
- The repo has no GitHub remote yet, so you cannot run the workflow on GitHub. Make sure every `run:` step is a command you executed locally.

## Acceptance
All of the above pass locally, and the workflow is actionlint-clean.
