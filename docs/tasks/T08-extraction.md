# T08 — Page extraction: schema, prompt v1, extract stage, stitching, figure crops, questions

**Owner:** Codex (medium) · **Branch:** `task/T08` · **Refs:** SPEC F1.5–F1.6, F2 · ARCHITECTURE §3, §4, §5, §6 · AGENTS.md

## Goal
After pages are rendered, every page is read by the vision model. The results are stitched across pages, figures
are cropped, and questions and stimuli are stored as `draft`. This is the core of the product.

## Scope
`backend/**` only. Build on: `pipeline/orchestrator.py` (append stages; see `Stage.pending_status`), `worker.py` (actor patterns,
batching, `on_retry_exhausted`), `pipeline/pdf_cache.py`, `storage/`, `llm/` (`get_llm_client`, `image_part`, the stage configs and errors),
`models/`, `services/`, `api/routers/sources.py`. **Never make live LLM calls**: tests use `FakeLLMClient`.

## Requirements

### 1. LLM I/O schema: `pipeline/schema.py`
`PageExtraction` (Pydantic, strict-JSON-schema compatible: every field required, nullable instead of optional) mirrors the golden format
(`fixtures/golden/schema.json` on main), so that T10 can compare them directly:
- `page_kind`: `cover|blank|toc|section_divider|questions|answer_key|answer_sheet|other`
- `headings[]`: `{level: book|unit|chapter|lesson|exam|section, text, box_2d}`
- `stimuli[]`: `{ref, kind: passage|poem|figure|table|case, intro: str|null, content, box_2d, continues_from_previous, continues_on_next}`
- `questions[]`: `{number_label, type, stem, choices: [{label, content}], answer: {labels: [str], text: str|null} | null, stimulus_ref: str|null,
  figures: [{box_2d, kind: diagram|chart|table|photo}], box_2d, continues_from_previous, continues_on_next, confidence: float 0–1}`
- `answer_key_entries[]`: `{section: str|null, number_label, labels: [str], text: str|null}` (for answer-key pages; matched in T09)
- `page_confidence: float`, `notes: str`
- **Boxes from the model** use `box_2d = [ymin, xmin, ymax, xmax]` as integers 0–1000 (the convention Gemini models are trained on).
  `to_region_box()` converts to the stored `[x0, y0, x1, y1]` floats 0–1 (ARCHITECTURE §3), clamping and fixing swapped coordinates. This conversion lives **only** here.

### 2. Prompt v1: `pipeline/prompts/extract_v1.md` + `PROMPT_VERSION = "extract-v1"`
- Rendered with Jinja2 (add the `jinja2` dependency; export needs it later anyway). Variables: subject name, language, grade.
- The content follows the **transcription rules in `docs/tasks/T07-golden-set.md` §3** (they define the ground truth we are scored against):
  exact text with tashkeel, remove tatweel, the ignore-list for headers/footers/watermarks, poem formatting ` ... `, `____` blanks,
  table-row choices format, figures as boxes and not descriptions, stimulus rules, LaTeX for math (`$…$`, `\ce{}`), Western digits in `number_label`.
  Add: page-kind definitions, the box convention, "never invent text that is not printed", and an instruction to set `confidence`.
- Keep it concise. Every token costs money on every page. Target < 1,200 tokens.

### 3. Extract stage
- Register a stage `extract` after `render` (status `extracting`, `pending_status = PageStatus.rendered`).
- Actor `extract_pages(source_id, numbers)` in batches (reuse the batch-size setting). Per page:
  hires PNG from storage → `image_part(max_side=settings.extract_image_max_side, default 1600)` → `complete_json(stage="extract", schema=PageExtraction)`.
  Save the validated result to `source_pages.extraction` (JSONB), along with `page_kind`, `prompt_version`, `model` and `cost_usd` (sum per page). Status → `extracted`.
- **Fallback** (ARCHITECTURE §6): on `LLMOutputInvalid`, or `page_confidence < settings.extract_fallback_threshold` (0.5), retry once with stage `extract_strong`. Keep the better result.
- **Budget errors** (`BudgetExceeded`, `OrgBudgetExceeded`): the source status becomes `paused` with the error code, and its remaining pages stay `rendered` so the stage can resume. Add `POST /api/v1/sources/{id}/resume` (editor+) to restart the current stage.
- Any other per-page error → the page is `failed` with the error. The rest continue.
- Pages are independent (no "previous page" context in the prompt), so they run in parallel. Continuation is resolved by stitching.

### 4. Materialize stage (one actor per source, after extract)
- Register stage `materialize` (status `extracting`). It runs once, when all pages are terminal for `extract`.
- **Idempotency** (SPEC F1.6): first delete this source's `draft`/`needs_review` questions, stimuli and assets that came from the pipeline. `approved`/`rejected` rows are never touched.
- **Stitch**: walk pages in order. A question/stimulus with `continues_on_next` on page N merges with the first item on page N+1 that has `continues_from_previous`
  (stem/content concatenated with a newline, choices appended, regions from both pages). If there's no match, keep the item and record `notes` in its metadata.
- **Figures**: crop each figure box from the hires PNG (pad 1%, then tighten with OpenCV: trim near-white borders but keep labels; add `opencv-python-headless`),
  store as WebP → an `assets` row → append `![](asset:<id>)` to the end of the owning question stem (or stimulus content).
- **Persist**: `stimuli` and `questions` per ARCHITECTURE §3 (create these tables plus `assets` now; `validation_issues`, `question_events` and `search_vector` come in later tasks).
  Questions get: subject from the source, `language` from the subject, `status = "draft"`, `confidence`, `number_label`, `regions` `[{page: <source_page_id>, box}]`,
  `stimulus_id` + `stimulus_position` (order within the stimulus), and `choices` `[{label, content, is_correct, pinned}]` (`is_correct` from the answer when present; `pinned` true if the content matches
  "all/none of the above" patterns in ar/en: جميع ما سبق, كل ما سبق, لا شيء مما سبق, all of the above, none of the above).
- Only `questions`/`answer_key` page kinds produce rows.

### 5. Read APIs (minimal; full editing is T12)
- `GET /api/v1/sources/{id}/questions` (all for the source, ordered by page then position, with regions/stimulus_id/status/confidence),
  `GET /api/v1/questions/{id}`, `GET /api/v1/sources/{id}/stimuli`, `GET /api/v1/assets/{id}/image` (streamed, ETag, org-scoped).
- `GET /api/v1/sources/{id}/pages/{n}` includes the raw `extraction` JSON (for the review UI's debugging panel).

### 6. Tests (all with `FakeLLMClient`; no copyrighted fixtures needed)
- Build a synthetic 3-page PDF in-test with PyMuPDF: Arabic-ish text lines plus a drawn rectangle as a "figure".
- Box conversion: Gemini order → normalized, clamping, swapped coords.
- Happy path: render → extract → materialize. Questions and stimuli exist, a figure asset exists and is referenced in the stem, and regions point at the right page ids.
- Stitching: a question continuing from page 1 to page 2 becomes one question with 2 regions.
- Fallback: invalid output → the strong stage is used. Low confidence → the strong stage is used, and the better result is kept.
- Budget exceeded mid-run → the source is `paused`, the remaining pages are `rendered`, and `/resume` continues and finishes.
- A failing page doesn't block the others. A non-question page produces no rows.
- Idempotency: re-running materialize keeps approved questions and replaces drafts.
- Pinned choice detection.

## Acceptance
`make check` passes. The orchestrator will then run one **live** extraction on `test-2027.pdf` (2 pages, ≈ $0.02) after merging, so make
`make be-worker` + upload work end-to-end with `QBANK_LLM_MODE=live`.
