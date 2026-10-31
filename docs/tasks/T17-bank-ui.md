# T17 — Question bank UI and taxonomy manager

**Owner:** agy (Gemini 3.8 Flash) · **Branch:** `task/T17` · **Refs:** SPEC F5 · ARCHITECTURE §7 · AGENTS.md

## Goal
Teachers and editors find, inspect and organize questions. Editors also manage the subject → chapter → lesson tree, including the AI-proposed nodes.

## Scope
`frontend/**` only. Read first: `src/api/client.ts`, `src/api/schema.d.ts` (generated: `/api/v1/bank/questions`, `/bank/tags`, `/bank/stats`, `/questions/move`, `/questions/bulk`,
`/questions/{id}`, `/questions/{id}/history`, the taxonomy endpoints `/subjects…`, `/chapters…`, `/lessons…` including `…/merge` and `…/reorder`), `src/api/hooks/*` (patterns),
`src/components/qmd/QmdRenderer.tsx`, `src/features/sources/sources-page.tsx` (table and filter patterns), `src/features/review/*` (status chips, bulk selection), `src/app/router.tsx`, `src/i18n/*.json`, and `src/test/*` (mocks).
Never hand-write API types. Don't touch `backend/`.

## Requirements
### `/bank`: search
- A subject selector (it remembers the last choice in localStorage) and a search box (debounced at 250 ms, search-as-you-type). The query goes into the URL, so searches can be shared.
- A filters sidebar (a Sheet on mobile) with **facet counts** from the response: chapter → lesson (nested), type, difficulty 1–5, status (editors only), source, tags (top 30 + autocomplete via `/bank/tags`), has figure, has answer, and exam title.
  Active filters show as removable chips. "Clear all".
- Sort: relevance (only when there's a query), newest, difficulty, source order. Show the "fuzzy match" notice when `match_mode = "fuzzy"`.
- Results are cards with a `QmdRenderer` preview of the stem (inline, clamped to 3 lines), type, difficulty dots, tags, status chip, chapter/lesson, source + page, a figure icon and an issues badge. "Load more" uses the cursor.
- The stats header (from `/bank/stats`) shows counts by status and type.
- **Detail drawer** (click a card): the full question rendered (the stimulus with its intro, the stem with figures, choices with the correct one marked, answer/explanation), the metadata, the history (editors), and "Open in review" (editors, when it has a source).
- **Bulk** (editors): multi-select (checkbox, shift-range, select all on the page) → approve/reject (`/questions/bulk`), set difficulty/tags (`set_metadata`), and move to a lesson (`/questions/move`, with a tree picker). Show per-id failures from the partial-success result.
- **"Add to exam"** (everyone): for selected questions, a dropdown of the user's draft exams (`GET /exams?status=draft`) → `POST /exams/{id}/items`. Show the response warnings (e.g. a stimulus group pulled in).

### `/bank/taxonomy`: taxonomy manager (editors; teachers see it read-only)
- Subjects list (create/rename/delete; delete shows the `not_empty` error nicely).
- The tree for the selected subject: chapters → lessons, each with an approved question count (from `/bank/stats`). Add, rename inline, reorder with up/down buttons (keyboard accessible) → the `…/reorder` endpoints.
  Move a lesson to another chapter, **merge** a lesson/chapter into another (a confirm dialog showing the number of questions that will move), and delete (empty only).
- **AI-proposed nodes** (`metadata.proposed = true`, from T09) get a "suggested" badge, with "Accept" (PATCH to clear the flag; if the API doesn't support that, list it in Follow-ups and just show the badge) and "Merge into…".

### Quality
i18n ar/en, the RTL guard, accessibility (the results list is a list with headings; the drawer gets focus trap and return; the tree uses `role="tree"` with aria-level, or nested lists with buttons). Teachers never see editor-only controls.
Tests (Vitest + Testing Library, mocked fetch): the debounced search calls the API with the right params and updates the URL; facet click → filter chip → query param; the fuzzy notice; load more;
the detail drawer rendering; bulk approve with partial failure shown; move to lesson; add to exam; tree reorder calls; merge confirm; delete `not_empty` error; teacher view hides the editor controls.

## Acceptance
From `frontend/`: `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` all pass, and the root `make check` passes.
**Commit your work on `task/T17` before printing the final report.**
