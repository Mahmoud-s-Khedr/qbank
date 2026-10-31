# Task board

Owner key: **cx** = Codex (`codex-personal`, gpt-6.1-terra) · **ag** = agy (Gemini 4 Argon / 3.8 Flash) · **cc** = Claude Code (orchestrator).
Each task runs in its own git worktree on branch `task/Txx`. Claude Code reviews it, runs `make check`, and merges into `main`.
Detailed task files (`docs/tasks/Txx-*.md`) are written just before dispatch, so they reflect the merged state of `main`.

| ID | Phase | Task | Owner | Model / effort | Depends | Status |
|---|---|---|---|---|---|---|
| T00 | 0 | Repo, specs, AGENTS.md, fixtures, dispatch tooling | cc | — | — | done |
| T01 | 0 | Backend scaffold: uv, FastAPI app factory, config, health, SQLAlchemy+Alembic, ruff/mypy/pytest, Dockerfile, docker-compose (pg/redis/minio), Makefile | cx | terra / medium | T00 | todo |
| T02 | 0 | Frontend scaffold: Vite+React+TS strict, Tailwind v4, shadcn, ESLint/Prettier/Vitest, i18n ar/en + RTL, app shell, API client generation wiring | ag | argon-high | T00 | todo |
| T03 | 0 | CI: GitHub Actions (all jobs in ARCH §8), pre-commit, dependabot, gitleaks, `make check` | cx | terra / medium | T01,T02 | todo |
| T04 | 0 | Core data model + migrations, auth (argon2, JWT cookie, CSRF, roles), org scoping, users + taxonomy CRUD APIs | cx | terra / high | T01 | todo |
| T05 | 1 | Object storage (S3/local), upload API, Dramatiq worker, render stage, sources/pages APIs, jobs + SSE progress | cx | terra / medium | T04 | todo |
| T06 | 1 | LLM layer: OpenRouter client, model registry, retries, cost tracking, spend cap, fake + recorded clients | cx | terra / medium | T04 | todo |
| T07 | 1 | Golden set: hand-verified ground-truth JSON for ~15 fixture pages (all types, a stimulus, figures, a continuation) | ag + cc review | argon-high | T00 | todo |
| T08 | 1 | Extraction: PageExtraction schema, prompt v1, extract actor, fallback, stitching, figure cropping | cx | terra / high | T05,T06 | todo |
| T09 | 1 | Structure detection (chapter/lesson tree) + answer-key matching | cx | terra / high | T08 | todo |
| T10 | 1 | `qbank-eval` CLI + run on candidate models → MODELS.md results, choose defaults | cx + cc | terra / medium | T07,T08 | todo |
| T11 | 2 | Validation rules, confidence, verifier pass, Arabic normalization, dedup, classification | cx | terra / high | T08 | todo |
| T12 | 3 | Review APIs: question/stimulus CRUD, audit log, split/merge, re-crop, re-extract with diff, bulk approve | cx | terra / medium | T11 | todo |
| T13 | 3 | Shared UI: QmdRenderer, QmdEditor, PageCanvas (zoom/pan/boxes/draw) | ag | argon-high | T02 | todo |
| T14 | 3 | Sources UI: upload, list, detail w/ live progress, page grid, costs | ag | argon-high | T05,T13 | todo |
| T15 | 3 | Review workspace UI (split view, issues, editor, shortcuts, split/merge, re-crop, re-extract diff) | ag | argon-high | T12,T13 | todo |
| T16 | 4 | Bank search API (FTS + trigram + facets), bulk metadata edit, manual question create | cx | terra / medium | T11 | todo |
| T17 | 4 | Bank UI + taxonomy manager UI | ag | argon-high | T16,T13 | todo |
| T18 | 5 | Exams: model/API, sections, blueprint sampler, stimulus grouping, versions/shuffling (hypothesis tests) | cx | terra / high | T16 | todo |
| T19 | 5 | AI-assisted composition (compose stage) | cx | terra / medium | T18,T06 | todo |
| T20 | 5 | Exam builder UI (blueprint, manual cart, AI assistant, sections, versions) | ag | argon-high | T18,T19 | todo |
| T21 | 6 | PDF export: HTML templates, fonts, KaTeX, layout options, answer key, bubble sheet | cx | terra / high | T18 | todo |
| T22 | 6 | DOCX export via Pandoc + reference.docx (RTL, OMML) | cx | terra / high | T21 | todo |
| T23 | 6 | Export/preview UI, exam templates, admin settings (users, models, spend cap), cost dashboard | ag | argon-high | T21,T22 | todo |
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
