# T12 — Review APIs: edit, audit log, split/merge, re-crop, re-extract with diff, bulk approve

**Owner:** Codex (medium) · **Branch:** `task/T12` · **Refs:** SPEC F4, F5.3, F5.4 · ARCHITECTURE §2 (API conventions), §3 · AGENTS.md

## Goal
Everything the review screen (T15) needs on the server: reviewers fix extraction mistakes, then approve or reject. Every change is audited.

## Scope
`backend/**`. Build on: `models/` (`Question`, `Stimulus`, `Asset`, `ValidationIssue`, `QuestionEvent` from T11), `pipeline/validate.py`
(re-validate after edits), `pipeline/materialize.py` (`crop`, `normalize_blanks`, `pinned`), `pipeline/extract.py` (`extract_page`),
`services/sources.py`, `api/routers/sources.py` (style). **No live LLM calls in tests.**

## Requirements (editor/admin for writes; teachers have read access only to `approved` questions)
### Questions
- `PATCH /api/v1/questions/{id}`: stem, choices, answer, explanation, type, chapter_id, lesson_id, difficulty (sets `difficulty_source = "human"`), tags, stimulus_id, stimulus_position.
  **Optimistic concurrency:** the request carries `version`, and a mismatch → 409 `code: version_conflict` with the current row. Validate QMD (reuse the rules from T11) and re-run validation for the question. Update `normalized_text` and `content_hash`.
- `POST /api/v1/questions` (F5.4, manual question; `source_id` null).
- `POST /api/v1/questions/{id}/approve`, `/reject` (with an optional `reason`), `/reopen` (→ needs_review).
  Approve is refused with 422 `code: unresolved_errors` while unresolved **error**-severity issues remain, unless `force: true` (admin only, recorded in the audit).
- `POST /api/v1/questions/bulk`: `{ids, action: approve|reject|set_metadata, metadata?: {chapter_id, lesson_id, difficulty, tags_add, tags_remove}}` → a per-id result list (partial success allowed).
- `POST /api/v1/issues/{id}/resolve` and `/unresolve`.
- `POST /api/v1/questions/{id}/split`: `{at: {field: "stem", offset} | {choice_index}}` → two questions (the second one gets `number_label + "b"` unless given), with the regions copied to both.
- `POST /api/v1/questions/merge`: `{ids: [a, b]}` (same source, ordered) → one question (stems joined, choices concatenated, regions unioned). The others are deleted, and the audit history is kept on the survivor.
- `DELETE /api/v1/questions/{id}` (only `draft`/`needs_review`/`rejected`).

### Figures and regions
- `POST /api/v1/questions/{id}/figures`: `{page_id, box}` → crop a new asset from the hires page, append `![](asset:id)` to the stem, and return the asset.
- `PUT /api/v1/assets/{id}/region`: `{box}` → re-crop **in place** (same asset id, new image, cache-busting ETag), so the existing QMD references stay valid.
- `DELETE /api/v1/questions/{id}/figures/{asset_id}`: removes the ref from the QMD and deletes the asset if nothing else references it.
- `PATCH /api/v1/questions/{id}` also accepts `regions` (the question's own boxes).

### Stimuli
`PATCH /api/v1/stimuli/{id}` (content, kind, intro), `POST /api/v1/stimuli` (manual, from a region), `DELETE` (only if no questions reference it), plus approve/reject like questions.

### Re-extract with diff (F4.6)
- `POST /api/v1/sources/{id}/pages/{n}/reextract`: `{model?}`, where the model must be allowed by the T06 guards → a job. The result is stored as a **proposal** (`page_proposals` table: page_id, extraction JSONB, model, cost, created_by, status `pending|accepted|discarded`) and **does not** touch live rows.
- `GET /api/v1/page-proposals/{id}` → `{proposal, diff}`. The diff is computed server-side against the page's current questions: per question, matched by number_label, the field-level changes; plus added and removed items.
- `POST /api/v1/page-proposals/{id}/accept`: `{number_labels?: [...]}` (all, if omitted) → apply to non-approved questions only (approved ones are listed as skipped), then re-validate. `/discard` discards it.
- `POST /api/v1/sources/{id}/pages/{n}/extract-region`: `{box}` → a synchronous single-region extraction (crop + LLM, stage `extract`) returning a draft `ExtractedQuestion` for the UI to confirm via `POST /questions`. Same guards; budget errors → 402 `code: budget_exceeded`.

### Audit (`question_events`)
Every mutation writes `{action, user_id, diff}`, where `diff` is a JSON field-level before/after of the changed fields only. `GET /api/v1/questions/{id}/history`.

### Review queue
`GET /api/v1/sources/{id}/review-queue?status=&severity=&page=&sort=page|severity|confidence` → a lightweight list (id, number_label, page, status, confidence, issue counts by severity),
plus totals. It is also the backing list for the keyboard next/prev navigation (stable ordering).

## Tests
Every endpoint: the happy path plus permission (teacher 403 on writes, cross-org 404), the version conflict, approve blocked by errors and forced by an admin,
the split/merge results and their audit, re-crop keeping the asset id with a changed ETag, the re-extract proposal → diff → partial accept (approved ones skipped),
extract-region with the fake client, bulk partial success, and review-queue ordering.

## Acceptance
`make check` passes. Run `make api-gen` and commit the generated files.
