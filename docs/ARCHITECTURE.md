# Qbank — Architecture

## 1. System overview

```
             ┌────────────┐   REST (OpenAPI)   ┌──────────────┐
  browser ──▶│  frontend  │ ─────────────────▶ │   api        │──┐
             │ React/Vite │ ◀── generated TS ─ │  FastAPI     │  │
             └────────────┘      client        └──────┬───────┘  │
                                                      │ enqueue  │ SQL
                                             ┌────────▼───────┐  │
                                             │ Redis (broker) │  │
                                             └────────┬───────┘  │
                                             ┌────────▼───────┐  ▼
                     OpenRouter ◀── LLM ──── │ worker         │──▶ PostgreSQL 18
                                             │ Dramatiq       │     (pg_trgm, FTS)
                                             └────────┬───────┘
                                                      ▼
                                             Object storage (S3 API: MinIO in dev)
                                             PDFs, page renders, figure crops, exports
```

One Python package, `qbank`, with two entrypoints: `qbank.api.main:app` (uvicorn) and
`qbank.worker` (dramatiq). Both share the domain layer.

## 2. Backend

**Stack:** Python 3.12, uv, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.0 (sync, psycopg 3), Alembic,
Dramatiq + Redis, PyMuPDF (render), Pillow + OpenCV-headless (crop/refine), `openai` SDK pointed at
OpenRouter, Jinja2 + Playwright/Chromium (PDF), Pandoc (DOCX), argon2-cffi, PyJWT, structlog.
**Quality:** ruff (lint + format), mypy (strict on `qbank/`), pytest, pytest-cov, hypothesis (shuffling/sampler).

### Package layout

```
backend/
  pyproject.toml  uv.lock  alembic.ini  Dockerfile  openapi.json
  src/qbank/
    config.py            Settings (env-driven)
    db/                  engine, session, base, migrations/ (alembic)
    models/              SQLAlchemy models (one module per aggregate)
    schemas/             Pydantic API schemas
    api/
      main.py            app factory, routers, middleware, exception handlers
      deps.py            auth, current user/org, db session
      routers/           auth, users, taxonomy, sources, pages, questions, stimuli, review, bank, exams, exports, settings, costs
    services/            business logic, called by routers and actors (no FastAPI imports here)
    storage/             ObjectStore protocol + S3 and local-FS backends
    llm/                 OpenRouter client, model registry, cost tracking, fake + recorded clients
    pipeline/
      render.py          PDF → page images
      extract.py         page image → PageExtraction (LLM)
      schema.py          Pydantic models for LLM I/O (source of truth for the JSON schemas)
      prompts/           versioned prompt templates (*.md, Jinja2)
      stitch.py          cross-page merging
      figures.py         bbox → crop (+ OpenCV tighten)
      structure.py       chapter/lesson tree
      answer_keys.py     answer-key matching
      validate.py        rules engine + confidence
      verify.py          LLM verifier pass
      classify.py        difficulty / tags / lesson assignment
      dedup.py
      orchestrator.py    per-source state machine
    exams/
      sampler.py         blueprint → selection
      versions.py        seeded shuffling
      compose_ai.py      AI-assisted composition
    export/
      html.py  pdf.py  docx.py  templates/  fonts/  reference.docx
    worker.py            dramatiq broker + actors
    eval/                qbank-eval CLI (golden-set benchmark)
  tests/
    unit/  integration/  fixtures/llm/  conftest.py
```

Rule: **routers are thin, services hold the logic, and models hold no logic.** Org scoping is applied in
services through a `scoped(query, org_id)` helper. Every service function takes `org_id` explicitly.

### API conventions
- Prefix `/api/v1`. JSON. Errors use RFC 7807 problem+json `{type, title, status, detail, code}`.
- Cursor pagination: `?cursor=&limit=` returns `{items, next_cursor}`.
- Auth: `POST /api/v1/auth/login` sets an httpOnly `qbank_session` JWT cookie. A double-submit CSRF token header `X-CSRF-Token` is required on unsafe methods.
- Long operations return `202` + `{job_id}`. `GET /api/v1/jobs/{id}` reports progress, and `GET /api/v1/sources/{id}/events` streams it over SSE.
- `backend/openapi.json` is generated (`make api-gen`) and committed. CI fails on drift.

## 3. Data model (PostgreSQL)

All tables have `id UUID PK (uuid7)`, `created_at` and `updated_at`. Tenant tables have `org_id FK`.

| Table | Key columns |
|---|---|
| `organizations` | name, settings JSONB (model config, spend cap, digits style) |
| `users` | org_id, email (unique), name, password_hash, role (`admin`/`editor`/`teacher`), is_active |
| `subjects` | org_id, name, language (`ar`/`en`), grade |
| `chapters` | subject_id, title, position |
| `lessons` | chapter_id, title, position |
| `sources` | org_id, subject_id, title, grade, file_key, page_count, status (`uploaded`/`rendering`/`extracting`/`validating`/`ready`/`failed`/`paused`), pipeline_config JSONB, cost_usd |
| `source_pages` | source_id, page_number, page_kind, image_key, width_px, height_px, dpi, status (`pending`/`rendered`/`extracted`/`validated`/`failed`), error, extraction JSONB (raw validated LLM output), prompt_version, model, cost_usd |
| `stimuli` | org_id, source_id, kind (`passage`/`poem`/`figure`/`table`/`case`), content (QMD), regions JSONB |
| `questions` | org_id, subject_id, chapter_id?, lesson_id?, source_id?, stimulus_id?, stimulus_position, number_label, type, stem (QMD), choices JSONB `[{label, content, is_correct, pinned}]`, answer (QMD), explanation (QMD), difficulty smallint, difficulty_reason, difficulty_source (`ai`/`human`), language, tags text[], regions JSONB, status, confidence real, content_hash, duplicate_of_id?, search_vector tsvector (generated), version int |
| `assets` | org_id, source_page_id?, kind (`figure`/`table`/`logo`), image_key, region JSONB, width, height |
| `validation_issues` | question_id, code, severity, message, details JSONB, resolved_at, resolved_by |
| `question_events` | question_id, user_id?, action, diff JSONB (the audit log) |
| `llm_calls` | org_id, source_id?, stage, model, prompt_version, input_tokens, output_tokens, cost_usd, latency_ms, status, request_hash |
| `jobs` | org_id, kind, status, progress JSONB, error, ref_id |
| `exams` | org_id, owner_id, title, subject_id, settings JSONB (header, duration, instructions, layout, digits), blueprint JSONB, status (`draft`/`final`/`archived`) |
| `exam_sections` | exam_id, title, position, instructions |
| `exam_items` | exam_id, section_id, question_id, position, points |
| `exam_versions` | exam_id, label, seed, layout JSONB (question order + choice permutation per item) |
| `exports` | exam_version_id, kind (`pdf`/`docx`/`answer_key_pdf`/`answer_key_docx`/`bubble_sheet`), file_key, exam_revision, stale bool |
| `exam_templates` | org_id, name, header JSONB, logo_asset_id |

**Regions** (bounding boxes) are always stored as `[{"page": <source_page_id>, "box": [x0, y0, x1, y1]}]`.
Coordinates are normalized to 0–1 with the origin at the top-left. Any LLM-specific convention
(e.g. Gemini's `[ymin, xmin, ymax, xmax]` on 0–1000) is converted inside `qbank.llm`/`pipeline.extract` only.

**Search**: `questions.search_vector` is built from the normalized stem + choices + stimulus. Normalization
strips tashkeel and tatweel, unifies alef forms (أ إ آ → ا), maps ى→ي and ة→ه, and folds digits. A GIN index
on `search_vector` plus a pg_trgm GIN index on the normalized text (used for dedup and fuzzy search).

## 4. Content format — QMD

All rich text (stem, choices, answer, stimulus) is **QMD**: CommonMark + GFM tables + math.
- Inline math `$...$`, display `$$...$$`. LaTeX subset that KaTeX supports. Chemistry uses `\ce{...}` (mhchem).
- Figures: `![caption](asset:<asset_uuid>)`.
- Blanks for fill-in: `____` (4+ underscores).
- No raw HTML.
- Text direction is inferred per paragraph (first strong character). The `language` field sets the default.

Renderers: frontend `react-markdown` + `remark-gfm` + `remark-math` + `rehype-katex` (+ mhchem).
PDF export uses the same pipeline server-side (Jinja2 → HTML with KaTeX auto-render in Chromium).
DOCX export converts QMD → Pandoc Markdown (`asset:` refs resolved to files) → `pandoc --reference-doc`,
which produces native OMML equations.

## 5. Ingestion pipeline

```
upload ─▶ render (per page) ─▶ extract (per page, parallel) ─▶ stitch ─▶ crop figures
       ─▶ structure (chapters/lessons) ─▶ answer keys ─▶ validate ─▶ [verify] ─▶ classify ─▶ dedup ─▶ ready
```

- **Orchestrator** (`pipeline/orchestrator.py`): a per-source state machine. Each stage is a Dramatiq actor. Per-page stages fan out and a barrier (count of pages in the terminal state) triggers the next stage. All stages are idempotent and keyed by (source_id, page_number, stage, prompt_version). Workers can restart at any time.
- **Render**: PyMuPDF at 200 DPI (config) → WebP for display and PNG at 300 DPI kept for figure cropping. Each page is wrapped in try/except, so a broken page becomes `failed` with its error recorded.
- **Page kind**: every page is classified (`cover`/`blank`/`toc`/`section_divider`/`questions`/`answer_key`/`answer_sheet`/`other`) in the same extract call. Only `questions` and `answer_key` pages produce items. Workbooks contain many non-question pages, e.g. `test-exams.pdf` pp. 1–5 and 44–60 (blank OMR sheets).
- **Extract**: one LLM call per page, image + prompt + a JSON schema derived from `pipeline/schema.py::PageExtraction` via `response_format={"type":"json_schema"}`. The prompt carries the subject/language and the previous page's last item (for continuation). Output: `headings[]`, `stimuli[]`, `questions[]`, `answer_key_entries[]`, `continues_from_previous: bool`, `continues_on_next: bool`, `page_confidence`. Validated with Pydantic, with one repair retry on failure.
- **Stitch**: merges an item flagged `continues_on_next` with page N+1's first item flagged `continues_from_previous`.
- **Figures**: crop from the 300 DPI render, tightened with OpenCV (trim whitespace, keep labels), then stored as an asset and referenced in QMD.
- **Structure**: a text-only LLM call over the ordered headings of all pages builds the chapter/lesson tree and maps page ranges to lessons. It is matched against the existing subject taxonomy (fuzzy). New nodes are created as proposals.
- **Validate / verify / classify / dedup**: see SPEC F3. Classification (difficulty, tags) is batched with ~20 questions per text-only call.

**Prompts** live in `pipeline/prompts/*.md` with a `PROMPT_VERSION` constant. Changing a prompt means bumping the version.

## 6. LLM layer (`qbank.llm`)

- `LLMClient` protocol: `complete_json(stage, messages, schema, model=None) -> (parsed, CallMeta)`.
- `OpenRouterClient` uses the `openai` SDK with `base_url=https://openrouter.ai/api/v1`, the `HTTP-Referer`/`X-Title` headers and `usage: {include: true}` so cost comes back. Retries on 429/5xx with exponential backoff and jitter, plus a per-call timeout.
- **Model registry**: per-stage defaults from settings, overridable per org and per source. Stages: `extract`, `extract_strong` (re-extract/fallback), `verify`, `structure`, `classify`, `compose`. Defaults are in `docs/MODELS.md`.
- **Fallback**: if `extract` output fails validation twice, or `page_confidence` < 0.5, retry once with `extract_strong`.
- Every call writes an `llm_calls` row, and the org spend cap is checked before each call.
- **Testing**: `FakeLLMClient` (scripted responses) and `RecordedLLMClient` (replays JSON fixtures in `tests/fixtures/llm/<stage>/<request_hash>.json`). Recording mode `QBANK_LLM_RECORD=1` is only used manually, with a real key.

## 7. Frontend

**Stack:** React 19, Vite, TypeScript (strict, `noUncheckedIndexedAccess`), React Router 7, TanStack Query,
Tailwind CSS v4 with logical properties (`ms-`/`me-`/`ps-`/`pe-`, never `ml-`/`mr-`), shadcn/ui (Radix),
react-hook-form + zod, i18next (`ar` default, `en`), react-markdown + remark-math + rehype-katex,
openapi-typescript + openapi-fetch (generated client in `src/api/`), Vitest + Testing Library, Playwright (e2e),
ESLint flat config (typescript-eslint strict-type-checked, react-hooks, jsx-a11y), Prettier.
Arabic UI font: IBM Plex Sans Arabic. Content fonts: Noto Naskh Arabic + Amiri (also bundled for export).

```
frontend/src/
  api/          schema.d.ts (generated), client.ts, hooks per resource
  app/          router, providers, layout shell (sidebar, topbar, lang switch)
  features/     auth, sources, review, bank, taxonomy, exams, exports, settings, costs
  components/   ui/ (shadcn), QmdRenderer, QmdEditor, PageCanvas (image + boxes), …
  i18n/         ar.json, en.json
  lib/
```

Key components:
- `QmdRenderer`: the single renderer for all content (RTL-aware, KaTeX, asset images, tables).
- `PageCanvas`: the page image with zoom/pan and an SVG overlay of the normalized boxes. It supports select, draw and resize.
- `ReviewWorkspace`: PageCanvas | question list | QmdEditor + issues panel, with keyboard shortcuts.

## 8. Tooling, CI and quality gates

- **Makefile** at the root wraps everything (see AGENTS.md). `make check` equals CI.
- **pre-commit**: ruff, ruff-format, prettier, eslint (changed files), gitleaks, end-of-file/trailing-whitespace, check-added-large-files (except `fixtures/pdfs`).
- **GitHub Actions** `ci.yml` (on PR + push to main), with jobs:
  1. `backend`: uv sync --frozen → ruff check → ruff format --check → mypy → pytest (with postgres + redis service containers) with coverage ≥ 80% → `alembic upgrade head` + `alembic check` → OpenAPI drift check.
  2. `frontend`: pnpm install --frozen-lockfile → eslint → prettier --check → tsc --noEmit → vitest (coverage) → vite build → API-client drift check.
  3. `docker`: build the api/worker and frontend images (no push).
  4. `e2e` (after 1–3): docker compose up with `QBANK_LLM_MODE=recorded` → Playwright full flow on fixtures.
  5. `security`: gitleaks, `pip-audit`, `pnpm audit --prod` (high+ fails).
- `eval.yml`: `workflow_dispatch` only. Runs `qbank-eval` against real OpenRouter models using the `OPENROUTER_API_KEY` secret, and uploads the report artifact.
- Dependabot for pip (uv), npm and github-actions. Weekly, grouped.

## 9. Deployment

- `docker-compose.yml` for dev (postgres, redis, minio, plus optional api/worker/frontend profiles).
- `docker-compose.prod.yml`: api, worker (scalable), frontend served by Caddy (static + reverse proxy `/api`), postgres, redis and minio (or external S3).
- The backend image includes Pandoc, Playwright Chromium and the bundled fonts.
