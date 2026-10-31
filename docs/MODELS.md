# OpenRouter models

**Cost policy:** cheap models only. The OpenRouter key has a hard **$1 credit limit**.
Models priced above roughly $1/M input or $5/M output tokens are **not used** without explicit approval from the project owner.
Model thinking is **off or low** by default, because thinking tokens are billed as output.

Prices are USD per 1M tokens (input / output), from the OpenRouter `/models` API on 2026-10-31.
**These are candidates. Defaults get decided by `qbank-eval` on `fixtures/golden/` (task T10).**

## Per-stage candidates

| Stage | Role | Candidates | Price in/out |
|---|---|---|---|
| `extract` | Page image → structured JSON + boxes (Arabic OCR, diacritics, layout) | `google/gemini-3.8-flash` (expected default) | 0.83 / 4.12 |
| | | `qwen/qwen3.8-flash` | 0.15 / 0.47 |
| | | `openai/gpt-6-luna` | 0.10 / 0.50 |
| | | `anthropic/claude-haiku-5.5` | 0.10 / 0.50 |
| | | `nvidia/nemotron-3.5-super-vl:free` (free, rate-limited; worth a look) | 0 / 0 |
| `extract_strong` | Retry for low-confidence/failed pages | Same model as `extract` with thinking set to `low` (no premium model) | — |
| `verify` | Re-read the page against the extraction. Must be a different model family from `extract` | `openai/gpt-6-luna` or `anthropic/claude-haiku-5.5` | 0.10 / 0.50 |
| `structure` | Text-only: headings → chapter/lesson tree | `anthropic/claude-haiku-5.5` | 0.10 / 0.50 |
| `classify` | Text-only, batched: difficulty, tags | `anthropic/claude-haiku-5.5`, `openai/gpt-6-luna` | 0.10 / 0.50 |
| `compose` | AI exam assistant over a candidate list | `anthropic/claude-haiku-5.5`, `openai/gpt-6-luna` | 0.10 / 0.50 |

Not used (over budget): `google/gemini-4-argon`, `anthropic/claude-sonnet-5.5` / `opus` / `fable`, and `openai/gpt-6.1-terra` / `sol` / `astra`.

## Measured costs

| Date | Model | Test | Tokens in / out | Cost | Latency |
|---|---|---|---|---|---|
| 2026-10-31 | gemini-3.8-flash | 1 page, short JSON, default thinking (it used most of `max_tokens` on thinking) | 1,128 / 296 | $0.0020 | 5.0 s |

Estimated full extraction with thinking off (≈1.2k in / 2–3k out): **≈ $0.01 per page with gemini-3.8-flash, and ≈ $0.0015 with the $0.10/$0.50 models.**

## Guardrails (implemented in T06)

- A model allowlist in settings, and a refusal to call any model whose listed price exceeds `QBANK_LLM_MAX_PRICE_IN` / `QBANK_LLM_MAX_PRICE_OUT` (defaults $1 / $5 per 1M).
- A `max_tokens` limit and a thinking setting per stage (default: off).
- Every call is recorded in `llm_calls` with its cost (from OpenRouter `usage`). A global dev budget `QBANK_LLM_BUDGET_USD` (default 0.50) and the per-org monthly cap are checked **before** each call.
- `qbank-eval` prints a cost estimate and requires `--max-cost` before it runs.

## Eval plan (T10), sized for the $1 limit

14 golden pages, 3 of which are non-question pages.
- Run 1: all 5 extract candidates × 14 pages, thinking off. Estimated **≈ $0.25**.
- Run 2: a repeat with the top 2 (consistency check). Estimated **≈ $0.15**.
- Total ≈ $0.40, which leaves headroom for development.

## Results

_Not run yet._
