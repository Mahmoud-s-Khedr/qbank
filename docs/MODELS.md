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

## Results — run 2026-10-31 (14 golden pages, prompt `extract-v1`, thinking off/minimal)

| Model | Composite | Page kind | Q count | Stem CER (norm) | Choice CER | Type acc | Figure recall | Q box IoU | Valid | Mean latency | $/page |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`google/gemini-3.8-flash`** | **0.944** | 100% | 100% | 0.080 | 0.059 | 92.7% | 100% | **0.887** | 100% | 16.5 s | $0.0071 |
| `qwen/qwen3.8-flash` | 0.909 | 92.9% | 100% | 0.089 | 0.014 | 83.3% | 100% | 0.630 | 100%* | 31.3 s | $0.0016 |
| `openai/gpt-6-luna` | 0.856 | 85.7% | 92.9% | **0.064** | 0.034 | 85.4% | 83.3% | 0.327 | 100% | 12.7 s | **$0.0008** |
| `anthropic/claude-haiku-5.5` | 0.731 | 92.9% | 100% | 0.080 | 0.278 | 85.4% | 16.7% | 0.018 | 100% | 11.6 s | $0.0013 |
| `nvidia/nemotron-3.5-super-vl:free` | 0.436 | 92.9% | 92.9% | 0.432 | 0.693 | 0% | 0% | 0.053 | 100% | 8.2 s | $0 |

\* qwen needed the fallback on 21% of pages and is frequently rate-limited upstream (429s for hours on 2026-10-31).
Luna and Haiku were first run with a schema bug (tuple `prefixItems` rejected by OpenAI/Anthropic, now fixed) and re-run.
Total benchmark cost: ≈ $0.15.

### Decision

| Stage | Default | Why |
|---|---|---|
| `extract` | `google/gemini-3.8-flash` | Best overall and by far the best boxes (figure crops and the review overlay depend on them). ≈ $0.71 per 100 pages. |
| `extract_strong` | `google/gemini-3.8-flash`, reasoning `low` | Same model with more thinking. No premium model. |
| `verify` | `openai/gpt-6-luna` | A different family, the **best text accuracy**, and ~$0.0008/page. Verifying text is exactly its strength. |
| `structure` / `classify` / `compose` | `anthropic/claude-haiku-5.5` | Text-only stages, so box accuracy doesn't matter. Cheap. (Re-check once those stages exist.) |

A cheaper option for text-heavy subjects with few figures (e.g. Arabic literature) is `gpt-6-luna` for extraction (~9× cheaper).
It can be set per source via `pipeline_config`. Worth re-evaluating once the golden set grows.
