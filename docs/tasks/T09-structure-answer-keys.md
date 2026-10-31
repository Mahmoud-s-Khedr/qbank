# T09 — Structure detection (chapter/lesson tree) and answer-key matching

**Owner:** Codex (medium) · **Branch:** `task/T09` · **Refs:** SPEC F2.5, F2.7 · ARCHITECTURE §5 (structure) · AGENTS.md

## Goal
Questions get placed in the subject's chapter → lesson taxonomy, and answers printed in answer-key sections get applied to their questions.

## Scope
`backend/**`. Build on: `pipeline/orchestrator.py` (stages after `materialize`, before T11's `validate`), `pipeline/schema.py`
(`headings`, `answer_key_entries`), `models/` (`Subject`, `Chapter`, `Lesson`, `Question`), `services/taxonomy.py`, `llm/` (stage `structure`), `text/normalize.py` (T11).
**No live LLM calls in tests.**
**Migrations:** use `down_revision` = the current head (`uv run --directory backend alembic heads`) and name the file `t09_structure.py`. Other tasks are adding migrations in parallel, and the orchestrator re-parents at merge. Note that T11 already added the `validate`, `verify` and `classify` stages after `materialize`. Insert `structure` and `answer_keys` between `materialize` and `validate`.

## Requirements
### 1. Structure stage (`pipeline/structure.py`, stage `structure`, text-only, cheap)
- Input: the ordered list of `(page_number, level, text)` headings from all extracted pages (deduplicate consecutive repeats such as running chapter tabs), plus the subject's existing tree (titles and ids).
- One LLM call (`complete_json`, schema `StructurePlan`) → `[{kind: chapter|lesson, title, start_page, existing_id: uuid|null}]` (lessons nested under chapters, in reading order).
  The prompt tells the model to map onto existing nodes when titles match in meaning, and never to invent nodes without a heading.
- **Without any LLM**, a deterministic fallback when there are ≤ 3 headings or the call fails: fuzzy-match heading text to existing nodes (normalized ratio ≥ 0.85), otherwise create nodes from chapter- and lesson-level headings.
- New nodes are created with `metadata.proposed = true` (add a JSONB `metadata` column to chapters/lessons) so the UI can show them as suggestions. Existing nodes are never renamed.
- Assign each question the lesson (and chapter) whose page range contains the question's first page. A mid-page lesson heading (e.g. "الهيكل الطرفي" on `test-2027` p. 2)
  uses the heading's `box` y-position: questions whose box starts below the heading belong to the new lesson.
- Exam-level headings (`exam`, e.g. "الاختبار السابع") are not taxonomy. Store them as `questions.metadata.exam_title` (useful for filtering later).
- Never overwrite a chapter/lesson set by a human (track `taxonomy_source: ai|human` on questions, the same pattern as difficulty).

### 2. Answer keys (`pipeline/answer_keys.py`, deterministic, no LLM)
- Collect the `answer_key_entries` from `answer_key` pages. Match each to a question of the same source by `(section or exam_title, number_label)`, falling back to `number_label` when unambiguous.
- Apply: set `choices[].is_correct` for the MCQ labels, or `answer` text for others. Never override an answer a human edited (track `answer_source: extracted|key|human`).
- Record `source.metadata.answer_key = {entries, matched, unmatched}` and set the context flag T11's `missing_answer` rule reads ("key matched for source"), so a question left without an answer becomes an error.

### 3. Stages
`materialize → structure → answer_keys → validate → …` (insert before T11's stages). Both are idempotent, and budget errors in `structure` fall back to the deterministic path instead of pausing.

### Tests
Heading dedup. The LLM plan mapped to existing nodes (fake client). The fallback path (no LLM). Mid-page lesson assignment by box y. Exam headings stored as metadata.
Human taxonomy preserved. Answer-key matching (by section, ambiguous number, unmatched). Human answers preserved. The `missing_answer` flag switching to error.

## Acceptance
`make check` passes. Run `make api-gen` if the API changed.
