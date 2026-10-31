# T06 — LLM layer: OpenRouter client, cost guardrails, call log, fake + recorded clients

**Owner:** Codex (medium) · **Branch:** `task/T06` · **Refs:** ARCHITECTURE §6 · `docs/MODELS.md` (cost policy and guardrails) · AGENTS.md

## Goal
One module, `qbank.llm`, through which **every** model call goes. Spend must be **impossible to lose control of**:
cheap-model allowlist, price ceilings, budgets checked before each call, every call metered. Tests never touch the network.

## Scope
`backend/**` only. Existing patterns to follow: `qbank/config.py`, `qbank/models/`, `qbank/services/`, `tests/conftest.py`.

## Requirements

### Settings (`qbank/config.py`, and add all of them to `.env.example`)
- `llm_mode: Literal["live", "fake", "recorded"] = "live"`. Tests force `fake`/`recorded`. `live` without a key raises `LLMNotConfigured` at call time, not at startup.
- `openrouter_base_url = "https://openrouter.ai/api/v1"`, `llm_timeout_s = 120`, `llm_max_retries = 3`.
- Per-stage defaults (`extract`, `extract_strong`, `verify`, `structure`, `classify`, `compose`) as a dict setting `llm_stage_models`, with values from `docs/MODELS.md`:
  extract → `google/gemini-3.8-flash`, extract_strong → the same model with `reasoning: low`, verify → `openai/gpt-6-luna`, structure/classify/compose → `anthropic/claude-haiku-5.5`.
  Each stage config: `{model, max_tokens, reasoning: "off" | "low" | "medium", temperature}`. The default reasoning is `"off"`.
- `llm_allowed_models: list[str]`: exactly the candidate list in MODELS.md. Any other model is refused with `ModelNotAllowed`.
- `llm_max_price_in_per_m = 1.0`, `llm_max_price_out_per_m = 5.0`: refuse a model whose known price exceeds these (`ModelTooExpensive`).
- `llm_budget_usd = 0.50`: the global cap on the **sum of `llm_calls.cost_usd`** across all orgs. Checked before every call (`BudgetExceeded`).

### Prices (`qbank/llm/pricing.py`)
- A static price table for the allowed models (from MODELS.md) is the offline source of truth for the guard.
- `refresh_prices()` (manual / CLI only, never in tests) fetches `GET /models` and updates a JSON cache file under `.data/`. The guard uses the higher of the static and cached values.
- `estimate_cost(model, input_tokens, output_tokens) -> Decimal`.

### Client (`qbank/llm/client.py`)
- `LLMClient` Protocol: `complete_json(*, stage, messages, schema: type[BaseModel], org_id, source_id=None, model_override=None) -> LLMResult[T]`. `LLMResult` carries `parsed`, `raw_text`, `model`, `input_tokens`, `output_tokens`, `reasoning_tokens`, `cost_usd`, `latency_ms`, `request_hash`.
  Also `complete_text(...)` with the same guards (used by later tasks).
- `OpenRouterClient`: the `openai` SDK with `base_url`, the headers `HTTP-Referer` and `X-Title: Qbank`, a timeout, and the SDK's `max_retries`.
  - `response_format={"type": "json_schema", "json_schema": {"name": schema.__name__, "strict": true, "schema": <pydantic JSON schema, made strict-compatible>}}`.
  - Through `extra_body`: `usage: {include: true}` (to get `cost`) and `reasoning` mapped from the stage config (`off` → `{"enabled": false}`, otherwise `{"effort": ...}`).
  - Parse and validate with Pydantic. If validation fails: **one** repair retry that sends the validation error back. If that fails too: `LLMOutputInvalid` (the call is still logged).
- **Guards, in order, before any network I/O:** allowlist → price ceiling → global budget → org monthly cap (`organizations.settings.llm_monthly_cap_usd`, optional) → spend so far this month. Each failure raises a distinct exception, with no call made.
- `image_part(data: bytes, *, max_side=1600, fmt="JPEG", quality=85)`: downscales and base64-encodes into an `image_url` content part. Use Pillow, which is already a dependency.
- `get_llm_client()`: a factory by `llm_mode`.

### Call log (model + migration)
- `llm_calls` table per ARCHITECTURE §3, plus `reasoning_tokens`, `error_code` and `org_id` (nullable for system calls). Written for **every** attempt, success or failure, in its own short transaction (so a failed pipeline transaction doesn't lose the record).
- `services/llm_costs.py`: `total_spend()`, `org_month_spend(org_id)`, `spend_by(stage | model | source)`.

### Test clients
- `FakeLLMClient`: queue scripted results or exceptions per stage. Records calls for assertions. It still runs the allowlist and price guards, so guard behaviour is tested even with the fake.
- `RecordedLLMClient`: replays `tests/fixtures/llm/<stage>/<request_hash>.json`. `request_hash` = sha256 of (model, stage, the messages with images replaced by their sha256, schema name). When `QBANK_LLM_RECORD=1` and mode is `live`, `OpenRouterClient` writes fixtures in that format (used manually later, never in CI).

### CLI (extend `python -m qbank.cli`)
- `llm-spend`: prints total, this month, and by stage and model.
- `llm-ping --model M [--image PATH]`: one tiny live call through the full guard chain. Prints tokens, cost and latency. Refuses if the budget is exceeded. (Never run in tests.)
- `llm-prices --refresh`.

### Tests (no network: use `httpx.MockTransport` passed to the openai client via `http_client=`; no new deps for mocking)
- Request shape: response_format json_schema, the reasoning mapping per stage, usage include, headers.
- Usage/cost parsing (including the reasoning tokens field) → `llm_calls` row.
- Repair retry: first invalid then valid → success with 2 rows logged. Twice invalid → `LLMOutputInvalid`.
- Every guard refuses **before** a request is made (assert the MockTransport saw 0 requests): a disallowed model, too expensive, global budget reached (seed `llm_calls`), org monthly cap reached.
- 429 then 200 → success (SDK retry). Timeout → a logged failure.
- Fake and Recorded clients: replay by hash, and a clear error when a fixture is missing.
- `image_part` downscales and returns a data URL.

## Acceptance
`make check` passes. `uv run --directory backend python -m qbank.cli llm-spend` works. The orchestrator will run one
`llm-ping` against the real API after merging. Do **not** run any live call yourself.
