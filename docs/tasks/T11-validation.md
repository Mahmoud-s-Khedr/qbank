# T11 — Validation, confidence, verifier pass, Arabic normalization, dedup, classification

**Owner:** agy (Gemini 4 Argon) · **Branch:** `task/T11` · **Refs:** SPEC F2.9, F3 · ARCHITECTURE §3 (search normalization), §5, §6 · `docs/MODELS.md` · AGENTS.md

## Goal
Every extracted question is checked automatically and gets issues, a confidence score and a status. Near-duplicates are linked.
Difficulty and tags are estimated cheaply. Only trustworthy questions skip the review queue.

## Scope
`backend/**`. Build on the T08 code: `pipeline/orchestrator.py` (stages), `pipeline/materialize*.py`, `models/` (`Question`, `Stimulus`, `Asset`),
`llm/` (stages `verify` and `classify`, guards). **No live LLM calls.** Tests use `FakeLLMClient`.

## Requirements

### 1. Arabic normalization: `qbank/text/normalize.py`
`normalize_ar(text) -> str`: strip tashkeel (U+064B–U+0652, U+0670) and tatweel; unify أ إ آ ٱ → ا, ى → ي, ة → ه, ؤ → و, ئ → ي; map Arabic-Indic and Persian digits to ASCII;
lowercase Latin; drop QMD syntax (`$…$` kept as its TeX content, `![…](asset:…)` removed, Markdown punctuation stripped); collapse whitespace.
Property tests with hypothesis (idempotent; never longer than the input in letters).

### 2. Data
- `validation_issues` and `question_events` tables (ARCHITECTURE §3).
- `questions.normalized_text` (stem + choices + stimulus intro, normalized) with a **pg_trgm GIN index**, and `content_hash` (sha256 of the normalized text).
  (`search_vector` and FTS are T16's. Don't add them.)

### 3. Rules engine: `pipeline/validate.py`
A registry of rule functions `(question, context) -> list[Issue]` with stable `code`s, each with a unit test:
`mcq_too_few_choices` (error), `mcq_duplicate_labels` (error), `mcq_label_sequence` (warning: labels not contiguous in their alphabet, e.g. أ ب د),
`missing_answer` (warning; error if an answer key was matched for the source but this question got none: T09 will set that context flag, so default it off),
`figure_referenced_not_attached` (error: the stem mentions الشكل/الصورة/الرسم/المقابل/figure/diagram/graph/chart/table without an asset ref, either in the question or its stimulus),
`empty_stem` (error), `truncated_stem` (warning: ends mid-word, or with `،`/`و`, or the stem is < 8 normalized chars for a non-fill_blank type),
`latex_invalid` (error: unbalanced `$`, or unbalanced braces in math; `pylatexenc` is acceptable if justified, otherwise a small balanced-delimiter checker),
`numbering_gap` (warning: on a page, the question numbers skip, e.g. 3 → 5), `low_confidence` (warning: question confidence < 0.6),
`duplicate_of` (warning: see §5), and `stimulus_orphan` (warning: a stimulus with no questions).

### 4. Confidence and status
`confidence = model_confidence × Π(penalty per issue)` (error 0.5, warning 0.85, capped to [0, 1]). Document it in the code.
Status: any error, or confidence < `settings.review_threshold` (0.75) → `needs_review`. Otherwise it stays `draft`, meaning "auto-OK, still unapproved". Only humans approve, in T12.
Issues are replaced on every validate run. Resolved issues (`resolved_at` set) are kept if the same code still applies.

### 5. Dedup: `pipeline/dedup.py`
For each new question: candidates via `similarity(normalized_text, :t) > 0.6` (pg_trgm, same org), then confirm with a char-level ratio (`rapidfuzz` is acceptable;
justify it, or use difflib). Set `duplicate_of_id` to the oldest match if the ratio is ≥ 0.9, and add the `duplicate_of` issue. Exact `content_hash` matches are instant.
Never delete. The SPEC §4.4 scenario must work: the same page uploaded twice → all of its questions are flagged against the first upload.

### 6. Verifier pass: `pipeline/verify.py` (stage `verify`, a different model family; default `openai/gpt-6-luna`)
- Policy from `source.pipeline_config.verify`: `"off" | "low_confidence" | "all"`, default `"low_confidence"` (pages with any question below the review threshold).
- One call per page: the page image (same preprocessing as extract) + the page's extracted questions as compact JSON → a `Verification` schema of discrepancies
  `[{number_label, field: stem|choices|answer|type|figure|missing_question, problem, suggested_fix: str|null, severity}]`.
- Discrepancies become `verifier_*` issues (they never auto-edit content). Budget errors pause the source, same as extract.

### 7. Classification: `pipeline/classify.py` (stage `classify`, text-only, cheap)
Batches of 20 questions (text only, no images) → `[{id, difficulty 1–5, difficulty_reason (≤ 15 words, in the question's language), tags (≤ 3)}]`.
Only fills fields where `difficulty_source != "human"`. Budget errors pause the source.

### 8. Stages
After `materialize`: `validate` (validate + dedup), then `verify` (if the policy needs it, and then re-validate the affected questions), then `classify`, then `ready`. All are idempotent, and the
budget-pause/resume behaviour matches extract.

### 9. API
`GET /api/v1/questions/{id}` and the source questions list include `issues[]`, `confidence`, `status`, `duplicate_of_id`, `difficulty`, `difficulty_reason` and `tags`.
Add `GET /api/v1/sources/{id}/summary`: question counts by status, issues by code and severity, and spend by stage.

### Tests
One test per rule (positive and negative). Confidence and status mapping. Dedup (exact, near, below threshold, cross-org isolation).
The verifier policy routing and how issues get created. Classification batching and that human difficulty is preserved. The full stage chain on the synthetic PDF from T08's tests.
Budget pause in verify and classify. Normalization property tests.

## Acceptance
`make check` passes. Run `make api-gen` and commit the generated files.
