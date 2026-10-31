# T05 — Object storage, upload, worker, page rendering, sources/pages/jobs APIs

**Owner:** Codex · **Branch:** `task/T05` · **Refs:** SPEC F1 · ARCHITECTURE §2, §3, §5 (orchestrator, render) · AGENTS.md

## Goal
A user uploads a PDF. It is stored, and a background worker renders every page (tolerating broken pages).
Progress is observable via the API and SSE. This task also lays down the **pipeline orchestrator** that later stages plug into.

## Scope
`backend/**`, plus `docker-compose.yml` (add the app services) and `Makefile` (add dev targets). Another agent is editing CI files
in parallel (`.github/`, `.pre-commit-config.yaml`, and the `[tool.*]` sections of `pyproject.toml`), so don't touch those. You own the dependency lists.

## Existing code (read first)
`backend/src/qbank/`: `config.py`, `db/__init__.py` (Base, mixins), `models/__init__.py`, `services/` (`scoping.py`, `errors.py`,
`unit_of_work.py`, `taxonomy.py` as the style reference), `api/routers/taxonomy.py` (router style reference), `api/deps.py`,
`api/pagination.py`, `schemas/common.py` (`Page[T]`), `worker.py` (placeholder). Tests: `tests/conftest.py`, `tests/integration/test_core.py`.
Follow the established pattern: thin routers → services raising domain errors → schemas in `schemas/`.

## Requirements

### Dependencies
`boto3` (+ `boto3-stubs[s3]` in dev), `dramatiq[redis]`, `pymupdf`, `pillow`, `python-multipart`. Justify any others.

### Storage (`qbank/storage/`)
- `ObjectStore` Protocol: `put(key, fileobj, content_type)`, `put_bytes(...)`, `get_bytes(key)`, `open(key) -> BinaryIO` (streaming), `exists(key)`, `delete(key)`, `delete_prefix(prefix)`.
- `S3Store` (boto3, endpoint/bucket/keys from Settings, `ensure_bucket()` called lazily once) and `LocalStore` (root dir, path-traversal safe).
- Settings `storage_backend: Literal["s3", "local"] = "s3"`, `storage_local_root`. A `get_store()` factory (cached). Tests use `LocalStore` on `tmp_path`, plus one integration test of `S3Store` against the compose MinIO, skipped if it is unreachable.
- Key layout (put it in one module, `storage/keys.py`): `orgs/{org}/sources/{source}/original.pdf`, `…/pages/{n:04d}.webp` (display), `…/pages/{n:04d}.hires.png` (crop source).

### Models + migration
- `Source`, `SourcePage` and `Job` per ARCHITECTURE §3. `SourcePage.page_kind` is a nullable enum (values in ARCHITECTURE §5). The source also gets `stage` (str: current pipeline stage) and `error`.
- `Source.status`: `uploaded`/`rendering`/`extracting`/`validating`/`ready`/`failed`/`paused`. Later tasks add statuses, so use a Postgres enum and keep the values in one Python Enum.
- `ensure_deletable_subject` must now also fail if the subject has sources.

### Pipeline orchestrator (`qbank/pipeline/orchestrator.py`)
- An ordered stage registry: `STAGES: list[Stage]`, where each Stage has a `name`, a `start(source_id)` that enqueues the work, and the source status shown while it runs. T05 registers only `render`. T08+ append stages.
- `advance(source_id, finished_stage)`: an **atomic compare-and-set** (`UPDATE sources SET stage=:next … WHERE id=:id AND stage=:finished RETURNING id`). Only the caller that wins starts the next stage. With no next stage, the status becomes `ready`. This is what makes the per-page fan-out barrier safe when the last pages finish concurrently. Test it with two threads.
- `page_done(source_id, stage)`: called after each page task. If no pages of the source remain non-terminal for this stage, it calls `advance`.

### Worker (`qbank/worker.py`)
- A Dramatiq Redis broker from Settings. Tests use `StubBroker` + `Worker` (or call the actors' `.fn` directly).
- Actors: `render_source(source_id)`, which opens the PDF via PyMuPDF and determines `page_count` (≤ `settings.max_pages`, default 1000; otherwise the source fails with `code: too_many_pages`), creates the `SourcePage` rows and enqueues `render_page` per page; and `render_page(source_id, page_number)`, which renders a display WebP at `settings.render_dpi_display` (150) and a hires PNG at `settings.render_dpi_hires` (300), stores both, and records `width_px`, `height_px` and `dpi`.
  **Any exception for one page marks that page `failed` with the error message, and processing continues.** Both actors are idempotent (re-running skips pages already rendered).
- Retries: Dramatiq retries for transient errors (storage), max 3. A broken PDF page is not transient, so don't retry it.
- `python -m qbank.worker` or `dramatiq qbank.worker` runs it.

### API
- `POST /api/v1/sources` (editor+): multipart `file`, `subject_id`, `title`, `grade?`. Validate the `%PDF-` magic bytes and `settings.max_upload_mb` (300). Stream to storage without reading the whole file into memory.
  Creates the Source + a Job (`kind: ingest`) and starts the pipeline. Returns **202** `{source: SourceOut, job_id}`. Bad file → 422 `code: invalid_pdf`. Too big → 413 `code: file_too_large`.
- `GET /api/v1/sources` (paginated; filters `subject_id`, `status`), `GET /api/v1/sources/{id}` (with `page_counts` by status, `cost_usd`), `DELETE /api/v1/sources/{id}` (editor+; deletes rows and the storage prefix).
- `GET /api/v1/sources/{id}/pages`: all pages (no pagination needed; ≤ 1000) with status, page_kind, error and dimensions.
- `GET /api/v1/sources/{id}/pages/{n}/image?variant=display|hires`: streams the image from storage with `Cache-Control: private, max-age=86400` and an `ETag`. Org-scoped.
- `GET /api/v1/jobs/{id}`: status and progress.
- `GET /api/v1/sources/{id}/events`: **SSE** (`text/event-stream`). Every second it emits a `progress` event (source status, stage, page_counts) only when something changed, plus a keep-alive comment every 15 s. It closes on a terminal status. Implement it by polling the DB in a threadpool (no extra infra). Make the interval a setting so tests run fast.

### Dev ergonomics
- `docker-compose.yml`: `api` and `worker` services under the profile `app` (built from `backend/Dockerfile`, depend on healthy infra, env from `.env`).
- Makefile: `be-dev` (uvicorn --reload) and `be-worker` (dramatiq with 4 processes and 4 threads by default, overridable).

### Tests
- Storage: LocalStore round-trip and traversal rejection. S3Store integration (skip if MinIO is down).
- Upload: happy path (202, rows, file stored), a non-PDF file, an oversize file (set the limit small in the test), a teacher gets 403, and cross-org 404.
- Render on `fixtures/pdfs/test-2027.pdf` (2 pages): both pages rendered, images exist, and the source becomes `ready`.
- **Robustness**: `fixtures/pdfs/test-exams.pdf`. Pages that fail to load (from 61 on) are `failed` with an error, pages 1–60 are rendered, and the source still reaches `ready`. Mark it `@pytest.mark.slow` (register the marker; it still runs in `make be-test`). Use a low DPI via settings in tests to keep it fast.
- Orchestrator CAS: two concurrent `advance` calls → exactly one wins.
- SSE: emits at least one progress event and closes on a terminal status.
- Image endpoint: content-type, ETag, 304 on `If-None-Match`.

## Acceptance
`make infra-up && make be-install && make check` passes (backend part; leave frontend files alone apart from `make api-gen` output).
Locally: `make be-dev` + `make be-worker`, upload `test-2027.pdf` with curl, and watch the events stream to `ready`.
