# Task board

Owner key: **cc-sonnet** = Claude Code sub-agent on Sonnet 5.5 · **cx** = Codex (`codex-personal`, gpt-6.1-terra) · **ag** = agy (Gemini 4 Argon / 3.8 Flash) · **cc** = Claude Code (orchestrator).
Cost policy: Codex runs at medium effort by default. agy uses Gemini 3.8 Flash unless the UI work is complex. OpenRouter calls use only the cheap models in MODELS.md.
Each task runs in its own git worktree on branch `task/Txx`. Claude Code reviews it, runs `make check`, and merges into `main`.
Detailed task files (`docs/tasks/Txx-*.md`) are written just before dispatch, so they reflect the merged state of `main`.

| ID | Phase | Task | Owner | Model / effort | Depends | Status |
|---|---|---|---|---|---|---|
| T00 | 0 | Repo, specs, AGENTS.md, fixtures, dispatch tooling | cc | — | — | done |
| T01 | 0 | Backend scaffold: uv, FastAPI app factory, config, health, SQLAlchemy+Alembic, ruff/mypy/pytest, Dockerfile, docker-compose (pg/redis/minio), Makefile | cx | terra / medium | T00 | done |
| T02 | 0 | Frontend scaffold: Vite+React+TS strict, Tailwind v4, shadcn, ESLint/Prettier/Vitest, i18n ar/en + RTL, app shell, API client generation wiring | ag | flash or argon (complex UI only) | T00 | done |
| T03 | 0 | CI: GitHub Actions (all jobs in ARCH §8), pre-commit, dependabot, gitleaks, `make check` | cx | terra / medium | T01,T02 | done |
| T04 | 0 | Core data model + migrations, auth (argon2, JWT cookie, CSRF, roles), org scoping, users + taxonomy CRUD APIs | cx | terra / medium | T01 | done |
| T05 | 1 | Object storage (S3/local), upload API, Dramatiq worker, render stage, sources/pages APIs, jobs + SSE progress | cx | terra / medium | T04 | done |
| T06 | 1 | LLM layer: OpenRouter client, model registry, retries, cost tracking, spend cap, fake + recorded clients | cx | terra / medium | T04 | done |
| T07 | 1 | Golden set: hand-verified ground-truth JSON for ~15 fixture pages (all types, a stimulus, figures, a continuation) | ag + cc review | argon-high | T00 | done |
| T08 | 1 | Extraction: PageExtraction schema, prompt v1, extract actor, fallback, stitching, figure cropping | cx | terra / medium | T05,T06 | done |
| T09 | 1 | Structure detection (chapter/lesson tree) + answer-key matching | cx | terra / medium | T08 | done |
| T10 | 1 | `qbank-eval` CLI + run on candidate models → MODELS.md results, choose defaults | ag + cc | terra / medium | T07,T08 | done |
| T11 | 2 | Validation rules, confidence, verifier pass, Arabic normalization, dedup, classification | ag | argon-high | T08 | done |
| T12 | 3 | Review APIs: question/stimulus CRUD, audit log, split/merge, re-crop, re-extract with diff, bulk approve | cc-sonnet | sonnet 5.5 | T11 | done |
| T13 | 3 | Shared UI: QmdRenderer, QmdEditor, PageCanvas (zoom/pan/boxes/draw) | ag | flash or argon (complex UI only) | T02 | done |
| T14 | 3 | Sources UI: upload, list, detail w/ live progress, page grid, costs | ag | flash or argon (complex UI only) | T05,T13 | done |
| T15 | 3 | Review workspace UI (split view, issues, editor, shortcuts, split/merge, re-crop, re-extract diff) | cc-sonnet | sonnet 5.5 | T12,T13 | done |
| T16 | 4 | Bank search API (FTS + trigram + facets), bulk metadata edit, manual question create | ag | argon-high | T11 | done |
| T17 | 4 | Bank UI + taxonomy manager UI | ag | flash or argon (complex UI only) | T16,T13 | in progress |
| T18 | 5 | Exams: model/API, sections, blueprint sampler, stimulus grouping, versions/shuffling (hypothesis tests) | cc-sonnet | sonnet 5.5 | T16 | done |
| T19 | 5 | AI-assisted composition (compose stage) | cx | terra / medium | T18,T06 | done |
| T20 | 5 | Exam builder UI (blueprint, manual cart, AI assistant, sections, versions) | cc-sonnet | sonnet 5.5 | T18,T19 | in progress |
| T21 | 6 | PDF export: HTML templates, fonts, KaTeX, layout options, answer key, bubble sheet | cc-sonnet | sonnet 5.5 | T18 | done |
| T22 | 6 | DOCX export via Pandoc + reference.docx (RTL, OMML) | cc-sonnet | sonnet 5.5 | T21 | done |
| T23 | 6 | Export/preview UI, exam templates, admin settings (users, models, spend cap), cost dashboard | cx | terra / medium | T21,T22 | done |
| T24 | 7 | E2E: Playwright full flow on fixtures in CI with recorded LLM | cx | terra / medium | T15,T20,T23 | todo |
| T25 | 7 | Hardening: security review, rate limits, logging, prod compose + Caddy, README/deploy docs | cx + cc | terra / medium | T24 | todo |

## Parallel lanes

```
cx: T01 → T04 → T05 → T06 → T08 → T09/T11 → T12 → T16 → T18 → T19 → T21 → T22 → T24 → T25
ag: T02 → T07 → T13 → T14 → T15 → T17 → T20 → T23
cc: T00, T03 review, every merge, T10 decision, integration fixes, final acceptance (SPEC §4)
```

## Usage log

| Date | Task | Agent | Quota before → after |
|---|---|---|---|
| 2026-10-31 | T01 | codex medium | 5h 0→5%, weekly 41→41% |
| 2026-10-31 | T02 | agy argon-high | Argon weekly 100% (not yet re-read) |
| 2026-10-31 | T04 (+1 review round) | codex high/medium | 5h 5→~12%, weekly 41→42% |
| 2026-10-31 | T03 + T05 (+1 review round) | codex medium/high | 5h 12→58%, weekly 42→50% |
| 2026-10-31 | T07 | agy argon-high | finished files, then hit an auth 401; committed by cc |
| 2026-10-31 | T06 (+1 review round) | codex medium | 5h 58→68%, weekly 50→51% |
| 2026-10-31 | T08 (+1 continue round) | codex medium | 5h 68→91%, weekly 51→55%; live run test-2027 $0.0208 |
| 2026-10-31 | T18 | cc-sonnet 5.5 sub-agent | ~120k subagent tokens, 12 min |
| 2026-10-31 | T21 | cc-sonnet 5.5 sub-agent | ~195k subagent tokens, 20 min |
| 2026-10-31 | T11 | agy argon-high | — |
| 2026-10-31 | T22 | cc-sonnet 5.5 sub-agent | ~156k subagent tokens, 19 min |
| 2026-10-31 | T12 | cc-sonnet 5.5 sub-agent | ~205k subagent tokens (paused once at the Claude 5h limit) |
| 2026-10-31 | T19 | codex medium | 5h →8%, weekly 55→56% |
| 2026-10-31 | T09 | codex medium | — |
| 2026-10-31 | T15 | cc-sonnet 5.5 sub-agent | ~255k subagent tokens; cc added 3 backend endpoints it needed |
| 2026-10-31 | T23 (+1 continue round) | codex medium | weekly 56→~60% |
