# T10 — `qbank-eval`: benchmark extraction models against the golden set

**Owner:** agy (Gemini 4 Argon) · **Branch:** `task/T10` · **Refs:** `docs/MODELS.md` (eval plan, cost policy) · SPEC §4.2 · AGENTS.md

## Goal
A CLI that runs the **real extraction code path** (same prompt, schema and image preprocessing as the pipeline) for candidate models
over the golden pages, scores each one, and writes a report. The orchestrator uses it to pick the default model. **It costs real money,
so cost control is part of the spec.**

## Scope
`backend/src/qbank/eval/**`, `backend/tests/unit/test_eval*.py`, plus the `[project.scripts]` entry and Makefile target.
Read first: `backend/src/qbank/pipeline/schema.py` (`PageExtraction`, `to_region_box`), `pipeline/extract*.py` (the per-page extraction function),
`llm/` (`get_llm_client`, `image_part`, the stage configs, the errors, `estimate_cost`), `fixtures/golden/schema.json`, and `scripts/golden_validate.py`.
The golden JSON and page images are **local-only** files (see `fixtures/README.md`). They exist on the orchestrator's machine but not in CI.
**Do not make any live LLM call yourself.** Tests use `FakeLLMClient`.

## CLI
`uv run --directory backend qbank-eval --models M1,M2 [--pages GLOB] [--repeat N] --max-cost USD [--out DIR] [--dry-run]`
- It runs the exact function the pipeline's extract stage uses for one page (refactor that function into a reusable pure-ish function
  in `pipeline/` if it isn't one yet, without changing behaviour), with `model_override`. Stage `extract`, so the guards and budget apply. Calls are logged in `llm_calls` with `stage="eval"` (add that stage value).
- **Before any call:** print a cost estimate per model (pages × repeat × estimated tokens × price; use ~1,300 input tokens per image plus the prompt, and the stage `max_tokens` as the output worst case and 2,500 as the expected case).
  If the worst-case total exceeds `--max-cost`, exit non-zero without calling. `--dry-run` prints the estimate only.
- **During the run:** track actual spend. Stop cleanly, with a partial report, if it would exceed `--max-cost`.
- Models run sequentially and pages with concurrency 4. Errors per page are recorded and the run continues.

## Metrics (per model, per page, and aggregate) in `eval/metrics.py`, pure functions with unit tests
- `page_kind` accuracy.
- Question count exact-match rate. Questions are matched by `number_label` (also report unmatched/extra).
- For matched questions: stem **CER** (character error rate) in two variants, *exact* (tashkeel kept) and *normalized* (strip tashkeel/tatweel, unify alef forms, ى→ي, ة→ه, collapse spaces).
  Choice CER (by label), choice count match, `type` accuracy, `stimulus_ref` linkage accuracy (mapped through matched stimuli).
- Stimuli: count match, content CER (normalized), kind accuracy.
- Boxes: question box IoU (mean), figure detection precision/recall at IoU ≥ 0.5, and the mean IoU of matched figures (greedy best-IoU matching).
- Answers: accuracy where the golden file has an answer.
- Ops: valid-output rate, fallback rate, mean/p95 latency, total and per-page cost.
- A single **composite score** (document the weights in the report): 0.35 × (1 − normalized stem CER) + 0.15 × (1 − choice CER) + 0.15 × question count match + 0.1 × type acc + 0.1 × figure recall + 0.1 × question box IoU + 0.05 × page_kind acc.

## Report
`eval-reports/<timestamp>/report.md` and `results.json` (the directory is gitignored). A Markdown table per model, a per-page breakdown, the 10 worst
question diffs per model (golden vs predicted, side by side), and the cost and latency summary. Print the summary table to stdout too.
`make eval MODELS=... MAX_COST=...` wraps it.

## Tests (no network)
- Metrics: CER (identical, empty, Arabic with and without tashkeel), IoU edge cases, greedy matching, number-label matching with missing/extra, the composite score.
- CLI with `FakeLLMClient` and a tiny synthetic golden set in `tmp_path` (generate 2 images with Pillow plus golden JSON): the estimate is printed; it refuses when the estimate is > max-cost; it stops mid-run when actual spend would exceed max-cost; the report files are written.

## Acceptance
`make check` passes (backend). `qbank-eval --dry-run --models google/gemini-3.8-flash --max-cost 0.1` prints an estimate on the orchestrator's machine.
**Commit your work on `task/T10` before printing the final report.**
