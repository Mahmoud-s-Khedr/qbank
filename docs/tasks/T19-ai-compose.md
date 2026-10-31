# T19 — AI-assisted exam composition (stage `compose`)

**Owner:** Codex (medium) · **Branch:** `task/T19` · **Refs:** SPEC F6.3 · ARCHITECTURE §6 · `docs/MODELS.md` · AGENTS.md

## Goal
A teacher describes an exam in natural language. The AI proposes a blueprint **and** a concrete selection from approved questions,
with a short rationale. **The AI never writes questions. It only picks ids from a candidate list we give it.**

## Scope
`backend/**`. Build on: `exams/sampler.py` (`BlueprintRow`, filters, duplicate clusters, stimulus groups), `services/exams.py`, `services/exam_generation.py`,
`llm/` (`complete_json`, stage `compose` → `anthropic/claude-haiku-5.5`, guards, budget errors), `api/routers/exams.py`. **No live LLM calls in tests.**
**Migrations:** use `down_revision` = the current head (`uv run --directory backend alembic heads`) and name the file `t19_compose.py`. Other tasks are adding migrations in parallel, and the orchestrator re-parents at merge.

## Flow: `POST /api/v1/exams/{id}/compose` `{prompt, language?}` → 200 `{proposal_id, blueprint, selection, rationale, warnings, cost_usd}`
1. **Plan (LLM call 1):** the prompt + the subject's chapter/lesson tree (ids and titles) + inventory counts of approved questions per lesson × type × difficulty
   (a compact table, computed by SQL) → `ComposePlan {title?, duration_minutes?, sections: [{title, rows: [BlueprintRow-compatible]}], notes}`.
   Validate every id against the tree and clamp counts to the inventory.
2. **Candidates (deterministic):** run the T18 sampler for each row with `oversample = 3×` (a new sampler option returning up to 3× count candidates, keeping the group and duplicate rules).
3. **Select (LLM call 2):** a compact candidate list `[{ref: "c17", type, difficulty, lesson, tags, stem_preview (first 140 normalized chars), group_size}]` + the plan → `ComposeSelection {rows: [{refs: ["c17", …]}], rationale (≤ 80 words, in the request language)}`.
   **Refs map back to ids server-side.** Unknown refs are dropped (with a warning), and the counts are re-checked (fill any shortfall deterministically from the remaining candidates, with a warning).
   Stimulus groups and duplicate clusters are re-validated after the AI selection.
4. Store it as a **proposal** (`exam_proposals` table: exam_id, user_id, prompt, plan JSONB, selection JSONB, rationale, cost_usd, status `pending|applied|discarded`). Nothing touches the exam yet.
- `POST /api/v1/exam-proposals/{id}/apply` `{edits?: {remove_question_ids, add_question_ids}}` → creates the sections and items (origin `ai`), records it in the exam, and bumps the revision. `/discard` discards it.
- `GET /api/v1/exams/{id}/proposals`.
- Budget errors → 402 `code: budget_exceeded`. Invalid LLM output after the repair retry → 502 `code: compose_failed`. Neither leaves a partial state.
- Cost: both calls are text-only and compact. Keep the candidate list ≤ ~3k tokens (truncate previews, cap the candidates at 120), and log the token counts.

## Tests (FakeLLMClient)
The plan validation (unknown ids dropped, counts clamped). Refs mapped back, with an unknown ref → warning. Shortfall filled deterministically. Stimulus groups kept whole. Duplicates excluded.
Apply with edits. Discard. A budget error → 402 with no proposal saved. An invalid output → 502. Permissions follow T18 exam visibility. The candidate-list token cap.

## Acceptance
`make check` passes. Run `make api-gen` and commit the generated files.
