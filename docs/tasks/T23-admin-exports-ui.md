# T23 — Admin and settings UI, cost dashboard, exam templates, exports panel (+ the small backend endpoints they need)

**Owner:** Codex (medium) · **Branch:** `task/T23` · **Refs:** SPEC F7.4–F7.6, F8.1–F8.3 · ARCHITECTURE §6, §7 · `docs/MODELS.md` · AGENTS.md

## Goal
Admins can manage users, organization settings (including LLM spend caps), exam header templates, and see what the AI is costing.
Teachers get a reusable **exports panel** to generate and download PDF/DOCX/answer keys for an exam's versions (the exam builder, T20, embeds it).

## Scope
`backend/**` (only the endpoints listed below) and `frontend/**`.
Backend read-first: `services/llm_costs.py` (`total_spend`, `org_month_spend`, `spend_by`), `models/` (`Organization.settings`, `ExamTemplate`, `Export`, `LLMCall`), `api/routers/exports.py`, `api/routers/users.py`, `services/exam_templates.py`, `config.py`.
Frontend read-first: `src/api/client.ts`, `src/api/hooks/*` (patterns), `src/app/router.tsx`, `src/app/app-shell.tsx`, `src/features/settings/settings-page.tsx` (placeholder), `src/features/sources/*` (page and table patterns), `src/i18n/*.json`, `src/test/auth-sources.test.tsx` (mocks).
**Migrations:** only if needed. Use `down_revision` = the current head and the file name prefix `t23_`.

## Backend endpoints (admin only unless stated; tests required)
- `GET /api/v1/org/settings` / `PATCH /api/v1/org/settings`: `{name, llm_monthly_cap_usd: number|null, verify_policy: "off"|"low_confidence"|"all", default_digits: "arabic"|"western", default_template_id: uuid|null, extract_model: one of the allowed models}`,
  validated and stored in `organizations.settings`. The pipeline must read `verify_policy` and `extract_model` as org-level defaults when a source has no override (check `pipeline/verify.py` and the extract stage; wire them if they're missing).
- `GET /api/v1/costs/summary?months=6` → `{total_usd, this_month_usd, cap_usd, by_month: [...], by_stage: [...], by_model: [...], top_sources: [{source_id, title, cost_usd, pages, cost_per_page}]}`, scoped to the org.
- `POST /api/v1/exam-templates/{id}/logo` (multipart, PNG/JPEG/WebP ≤ 2 MB, re-encoded to PNG ≤ 600 px wide) → it stores an asset and sets `logo_asset_id`. `GET /api/v1/assets/{id}/image` already serves it.

## Frontend
### `/settings` (admin; tabs, with the selected tab in the URL)
1. **Organization**: name, digits default, default template, and the AI section: extract model (from `GET /llm/models`, showing the price per 1M tokens), verify policy, and a monthly cap with a hint ("≈ N pages at the current model's average cost").
2. **Users**: a table (name, email, role, active, last login), invite (create with a password, shown once with a copy button), change role, deactivate. You can't demote or deactivate yourself (the server enforces this too; show its error).
3. **Exam templates**: list/create/edit/delete, header fields (school name, default instructions, …), logo upload with a preview, and a live **header preview** that uses the same fields the PDF uses.
4. **Costs**: KPI tiles (this month vs. cap with a progress bar, total, average cost per page), cost by month (a simple accessible bar chart in **SVG, without a chart library**, with axis labels and a data table fallback), by stage, by model, and top sources. Format money to 4 decimals under $1, otherwise 2.

### `ExamExportsPanel` component (`src/features/exports/exam-exports-panel.tsx`): exported for T20 and **also mounted on a temporary route `/exams/:id/exports`** until T20 exists
- Props: `examId`. It shows the exam's versions (from `GET /exams/{id}`). If there are none, it offers "Generate versions" (`POST /exams/{id}/versions` with a count and a shuffle toggle).
- Kind checkboxes (exam PDF, answer key PDF, bubble sheet PDF when all items are MCQ, exam DOCX, answer key DOCX) × version selection → `POST /exams/{id}/exports`.
  Poll `GET /exams/{id}/exports` every 2 s while any export is pending.
- A list of exports with status, size, created time, a **stale** badge plus a "regenerate" action, download (an `<a href>` to `/exports/{id}/download`), and delete.
- Failed exports show their error.

### Quality
i18n ar/en, the RTL guard, accessibility (labelled controls, the chart's data table, focus management in dialogs), and role gating (non-admins never see the admin tabs; teachers can use the exports panel).
Tests: backend endpoint tests (permissions, validation, the org defaults used by the pipeline, the cost aggregation numbers, logo re-encoding). Frontend tests (mocked fetch) for each settings tab's main flow,
the self-demote error shown, the cost chart rendering with its table fallback, the exports panel generating and polling until ready, the stale badge, and the bubble-sheet option hidden for non-MCQ exams.

## Acceptance
`make check` passes. Run `make api-gen` and commit the generated files.
