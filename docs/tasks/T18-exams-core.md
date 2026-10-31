# T18 — Exams: model and API, sections, blueprint sampler, stimulus grouping, versions and answer keys

**Owner:** Claude Code sub-agent (Sonnet 5.5) · **Branch:** `task/T18` · **Refs:** SPEC F6.1, F6.2, F6.4–F6.8 · ARCHITECTURE §3 (exams tables) · AGENTS.md

## Goal
The exam engine (excluding the AI assistant, T19, and export, T21): teachers assemble exams from approved questions by blueprint or by hand,
and generate deterministic shuffled versions with correct answer keys.

## Scope
`backend/**` only. Build on: `models/__init__.py` (`Question` already has difficulty, tags, stimulus_id/position, duplicate_of_id, status, chapter/lesson),
`services/` + `api/routers/` style (thin routers, domain errors in `services/errors.py`, org scoping via `services/scoping.py`), `api/pagination.py`,
`schemas/common.py`, and `tests/conftest.py` (`database`, `client`), with `tests/integration/test_core.py` as the auth-helper reference.
**Migrations:** the current Alembic head is `220eaa6800df`. Name your migration file `t18_exams.py` with `down_revision = "220eaa6800df"`.
(Another task is adding a migration in parallel. The orchestrator re-parents at merge.)

## Requirements
### Models + migration
`exams`, `exam_sections`, `exam_items` and `exam_versions` per ARCHITECTURE §3, plus `exams.revision int` (incremented on every content change) and
`exam_versions.exam_revision` (the revision it was generated from; a version is **stale** when `exam_revision < exam.revision`).
`exams.settings` JSONB, validated by Pydantic: `header {school_name, exam_title, subject_label, grade, date, duration_minutes, instructions}`,
`layout {columns: 1|2, font_size_pt: 10–16, digits: "arabic"|"western", answer_space_lines: 0–20, choices_per_row: "auto"|1|2|4}`, `language: ar|en`.

### API (every role can build exams; a teacher sees and edits only their own exams; an admin sees all in the org; questions must be `approved`, same org)
- `POST/GET /api/v1/exams` (list: own exams, filter `status`, cursor pagination), `GET/PATCH/DELETE /api/v1/exams/{id}`, `POST /exams/{id}/duplicate`, `POST /exams/{id}/archive`.
- Sections: `POST /exams/{id}/sections`, `PATCH/DELETE /exam-sections/{id}`, `POST /exams/{id}/sections/reorder`. A new exam starts with one default section.
- Items: `POST /exams/{id}/items` `{question_ids, section_id?, points?}` (adding a question that belongs to a stimulus adds the **whole stimulus group**, in order, if it isn't already present),
  `PATCH /exam-items/{id}` (points, section_id, position), `DELETE /exam-items/{id}` (removing one item of a stimulus group asks to remove the group: a 409 `code: stimulus_group` unless `?group=true`),
  `POST /exams/{id}/items/reorder` `{section_id, ids}` (stimulus groups must stay contiguous and in order, otherwise 422).
- `GET /exams/{id}` returns the full exam: settings, sections → items (with question content: stem, choices, stimulus content once per group), `total_points` (computed), `question_count`, `revision`, and versions with their `stale` flag.

### Blueprint sampler (`qbank/exams/sampler.py`, pure and deterministic)
`POST /exams/{id}/blueprint/preview` and `/apply`, `{rows: [{chapter_ids?, lesson_ids?, types?, difficulty_min?, difficulty_max?, tags_any?, count, points, section_id?}], seed?, exclude_question_ids?, exclude_used_in_my_exams?: bool}`
→ `{rows: [{requested, selected: [question_id], shortfall, available}], seed}`. Apply writes the items (replacing the items previously created by the blueprint, tracked via `exam_items.origin = "blueprint" | "manual"`).
- Only `approved` questions of the exam's subject. Rows are filled in order, and a question is used at most once across rows.
- **Duplicates:** questions in the same duplicate cluster (`duplicate_of_id` chains, both directions) are treated as one. At most one per exam.
- **Stimulus groups** count as `len(group)` questions toward a row and are taken whole or not at all. Pick singles and groups so that the row's count is met exactly when possible
  (a small knapsack: it's fine to prefer singles, then fill with groups that fit). Never exceed `count`.
- Seeded `random.Random(seed)`. The same inputs + seed → the same output.
- `exclude_used_in_my_exams`: skip questions in the caller's other non-archived exams.
- **Property tests (hypothesis):** never exceeds count; every selected question matches its row's filters; no duplicate clusters; stimulus groups intact; deterministic; shortfall = requested − selected.

### Versions (`qbank/exams/versions.py`, pure and deterministic)
- `POST /exams/{id}/versions` `{count: 1–10, seed?, shuffle_questions: true, shuffle_choices: true, keep_first_as_original: false}` → it replaces existing versions, labelled A, B, C… (Arabic exams: أ, ب, ج…).
- Per version, `layout`: for each section, the item order (shuffled, where **stimulus groups move as a unit** and keep their internal order) and, per MCQ item, a choice permutation.
  **Pinned choices keep their original positions**, and only the non-pinned ones are permuted among the remaining slots.
- Display numbering is continuous across sections (1…N). Choice display labels are re-lettered by position using the exam language's alphabet (أ ب ج د هـ… / A B C D E…). They are **never** copied from the source labels.
- `GET /exams/{id}/versions/{label}/answer-key` → `[{number, question_id, type, correct: [display labels in this version] | null, answer_text | null, points}]`. MCQs without a known correct answer → `correct: null` plus a warning list in the response.
- **Tests:** permutations are valid; pinned positions are fixed; groups stay contiguous; the answer key is consistent (map each version's correct display label back through the permutation → the original correct choice); deterministic by seed; staleness after an edit.

## Acceptance
`make check` passes (backend). Run `make api-gen` and commit the generated `backend/openapi.json` and `frontend/src/api/schema.d.ts`.
Commit on `task/T18` with message `T18: …`, and print the final report in the AGENTS.md format.
