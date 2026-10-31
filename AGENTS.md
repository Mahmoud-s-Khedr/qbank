# AGENTS.md — rules for every coding agent working in this repo

You are implementing one task from `docs/tasks/`. Read, in this order:
1. This file.
2. Your task file (`docs/tasks/Txx-*.md`), which sets your scope.
3. Only the sections of `docs/SPEC.md` / `docs/ARCHITECTURE.md` your task references.

Do not read the whole repo "to get context". Your task file lists the files that matter.

## Project

Qbank turns scanned (mostly Arabic, RTL) workbook PDFs into a reviewed question bank
and generates print-ready exams (PDF + editable DOCX). Every page is read by a
multimodal LLM via OpenRouter: the PDFs' embedded text layers are garbled and
must never be trusted.

## Layout

```
backend/    Python 3.12, uv, FastAPI, SQLAlchemy 2, Alembic, Dramatiq   (package: qbank)
frontend/   React 19, Vite, TypeScript strict, Tailwind v4, TanStack Query, pnpm
fixtures/   test PDFs (fixtures/pdfs) and golden annotations (fixtures/golden)
docs/       SPEC.md, ARCHITECTURE.md, MODELS.md, TASKS.md, tasks/Txx-*.md
scripts/    repo tooling (agent dispatch, etc.)
```

## Commands (run from the repo root)

| What | Command |
|---|---|
| Start infra (postgres, redis, minio) | `make infra-up` |
| Backend: install / lint / types / tests | `make be-install` / `make be-lint` / `make be-types` / `make be-test` |
| Frontend: install / lint / types / tests / build | `make fe-install` / `make fe-lint` / `make fe-types` / `make fe-test` / `make fe-build` |
| Regenerate the OpenAPI schema and TS client | `make api-gen` |
| Everything CI runs | `make check` |

If a target you need does not exist yet, and your task is the one creating the tooling, add it.

## Definition of done (all must hold before you finish)

1. `make check` passes locally: lint, format check, type check and tests for every stack you touched.
2. New behaviour has tests. Backend coverage must not drop below the threshold in `pyproject.toml`.
3. If you changed the API: `make api-gen` was run and `backend/openapi.json` plus `frontend/src/api/schema.d.ts` are committed.
4. If you changed models: there is an Alembic migration, and `alembic check` reports no drift.
5. No secrets in code. Config comes from env vars via `qbank.config.Settings`. Add any new var to `.env.example`.
6. You committed your work on your task branch with a clear message (`Txx: <summary>`).

## Hard rules

- Stay inside your task's scope. If you find a needed change outside it, write it under "Follow-ups" in your report. Do not make the change.
- Never call a real LLM in tests. All LLM traffic goes through `qbank.llm`. Tests use recorded fixtures (`backend/tests/fixtures/llm/`) or the fake client.
- Never weaken lint or type config, or add blanket `# type: ignore` / `eslint-disable`, to make checks pass. Narrow, commented suppressions only.
- Never edit `docs/SPEC.md`, `docs/ARCHITECTURE.md` or `AGENTS.md`. Propose changes in your report.
- The frontend talks to the backend only through the generated client in `frontend/src/api/`. Never hand-write request or response types.
- All user-facing strings go through i18n (`ar` and `en`). Every layout must work in RTL and LTR.
- Keep dependencies minimal. Justify each new one in your report.

## Final report (print this as your last message)

```
## Txx report
Status: done | partial | blocked
Summary: <2-4 lines>
Files changed: <list>
Checks: <commands run and their result>
Decisions: <non-obvious choices made>
Follow-ups: <anything out of scope, or spec problems found>
```
