# T16 — Question bank search API (Arabic-aware FTS + trigram, facets) and taxonomy merge

**Owner:** agy (Gemini 4 Argon) · **Branch:** `task/T16` · **Refs:** SPEC F5.1, F5.2, §3 (performance) · ARCHITECTURE §3 (search) · AGENTS.md

## Goal
Teachers and editors find questions fast: Arabic-aware, diacritics-insensitive full-text search with typo tolerance, rich filters and facet counts.
Editors can also reorganize the taxonomy.

## Scope
`backend/**` only. Build on: `text/normalize.py` (`normalize_ar`, `question_normalized_text`), `models/` (`Question.normalized_text`, which has a pg_trgm GIN index from T11, plus `tags`, `difficulty`, `metadata_json`, `chapter_id`/`lesson_id`),
`services/scoping.py`, `api/pagination.py`, `services/taxonomy.py` (`ensure_deletable_*`), and the router style in `api/routers/`. No LLM calls.
**Migrations:** use `down_revision` = the current head (`uv run --directory backend alembic heads`) and name the file `t16_search.py`. Another task is adding a migration in parallel, and the orchestrator re-parents at merge.

## Requirements
### Search index
- `questions.search_vector`: a **generated stored** column, `to_tsvector('simple', coalesce(normalized_text, ''))`, with a GIN index. (`simple`, because the text is already normalized by `normalize_ar`. Mixed Arabic and English text works.)

### `GET /api/v1/bank/questions`
- Params: `q`, `subject_id`, `chapter_ids[]`, `lesson_ids[]`, `types[]`, `difficulty_min`, `difficulty_max`, `statuses[]`, `source_ids[]`, `tags[]` (match any), `has_figure` (the stem contains `asset:`),
  `has_answer`, `exam_title` (from `metadata_json`), `exclude_duplicates` (default true: hide questions whose `duplicate_of_id` is set), `sort` = `relevance|newest|difficulty|source_order`, `cursor`, and `limit` (≤ 100).
- **Teachers only ever see `approved` questions**, and the `statuses` param is ignored for them. Org scoping as everywhere else.
- `q`: normalize it with `normalize_ar`, then `websearch_to_tsquery('simple', …)`, adding prefix matching on the last token (`:*`) for search-as-you-type. Relevance is `ts_rank_cd`.
  **Typo fallback:** if FTS returns nothing, use pg_trgm `similarity(normalized_text, :q) > 0.3`, ordered by similarity. The response says `match_mode: "fts" | "fuzzy"`.
- Items: id, number_label, type, a stem preview (first 200 chars of the *original* stem, so diacritics are kept), choices count, difficulty, tags, status, chapter/lesson ids and titles, source title + page,
  stimulus id, has_figure, and `issues_count` by severity.
- **Facets** (in the same response, when `facets=true`): counts by chapter, lesson, type, difficulty, status, source and the top 30 tags. Each facet is computed with all the *other* filters applied (standard faceted search), and `total` with all of them.
- Pagination: keyset for `newest` and `difficulty`; an opaque offset cursor is fine for `relevance` and `source_order`.

### Other endpoints
- `GET /api/v1/bank/tags?subject_id=&q=` → tags with counts (autocomplete).
- `GET /api/v1/bank/stats?subject_id=` → counts by status/type/difficulty, plus approved per chapter/lesson (for the dashboard and the exam builder's inventory).
- **Taxonomy merge** (F5.2, editor+): `POST /api/v1/lessons/{id}/merge` `{into_lesson_id}` and `POST /api/v1/chapters/{id}/merge` `{into_chapter_id}`, same subject only. They move the questions (and lessons) and delete the source node.
  `POST /api/v1/questions/move` `{ids, lesson_id}` sets the lesson and chapter, with `taxonomy_source = "human"` if that column exists (otherwise skip it and note it).
  `ensure_deletable_subject/chapter/lesson` must now also return false when questions reference the node.

### Performance
- Add `scripts/bench_search.py` (not run in CI): it seeds N synthetic Arabic questions (default 100k) into a throwaway DB, runs 50 representative queries (text + filters + facets), and prints p50/p95.
  The target is **p95 < 300 ms at 100k**. Run it yourself with N = 100000 and put the numbers in your report. If needed, add indexes such as `(org_id, subject_id, status)` or partial indexes, and use `EXPLAIN ANALYZE` to justify them.

### Tests
Search with and without tashkeel matching the same question, alef variants, Arabic-Indic digits in the query, an English query, the prefix match, the fuzzy fallback with a typo,
each filter, teachers forced to approved, cross-org isolation, the facet counts excluding their own dimension, pagination stability for each sort, tags autocomplete, stats,
merge lesson/chapter (questions moved, node deleted, cross-subject rejected), and the delete checks now counting questions.

## Acceptance
`make check` passes. Run `make api-gen` and commit the generated files. Include the bench numbers in the report. **Commit your work on `task/T16` before printing the final report.**
