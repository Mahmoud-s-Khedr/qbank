# OpenRouter models

Prices are USD per 1M tokens (input / output), from the OpenRouter `/models` API on 2026-10-31.
`:batch` variants cost half and suit bulk re-ingestion where latency doesn't matter.
**These are candidates. The defaults get decided by `qbank-eval` on `fixtures/golden/` (task T10).**

## Per-stage candidates

| Stage | Role | Candidates (try in this order) | Price in/out |
|---|---|---|---|
| `extract` | Page image → structured JSON with bounding boxes. Needs strong Arabic OCR, diacritics, layout and box accuracy | `google/gemini-3.8-flash` (expected default) | 0.83 / 4.12 |
| | | `qwen/qwen3.8-flash` (budget option, strong at locating regions) | 0.15 / 0.47 |
| | | `openai/gpt-6.1-terra` | 1.00 / 5.00 |
| `extract_strong` | Fallback for low-confidence or failed pages, and user-triggered re-extraction | `google/gemini-4-argon` | 2.00 / 10.00 |
| | | `anthropic/claude-sonnet-5.5` | 2.00 / 10.00 |
| `verify` | Re-reads the page against the extracted JSON. **Must be a different model family from `extract`** | `anthropic/claude-sonnet-5.5` or `openai/gpt-6.1-terra` | |
| `structure` | Text-only: headings → chapter/lesson tree | `anthropic/claude-haiku-5.5` | 0.10 / 0.50 |
| `classify` | Text-only, batched: difficulty, tags, lesson | `anthropic/claude-haiku-5.5`, `openai/gpt-6-luna` | 0.10 / 0.50 |
| `compose` | AI exam assistant: reasoning over the candidate list | `anthropic/claude-sonnet-5.5`, `openai/gpt-6.1-terra` | |

## Rough cost (to be replaced by measured numbers)

One page is about 2–4k input tokens (image + prompt) and 1.5–3k output tokens.
With `gemini-3.8-flash` that is ≈ $0.01–0.015 per page, so ≈ $1 for the 72-page `test-exams.pdf`.
Verifier, structure and classify passes add about 20–40%.

## Eval protocol (T10)

For each candidate × golden page, record: question count exact match, stem and choice character error
rate (after normalization), correct type, stimulus linkage, figure IoU, answer correctness when the key
is on the page, valid-JSON rate, latency, and cost. Run each 2× to check consistency. The results table
goes below.

## Results

_Not run yet._
