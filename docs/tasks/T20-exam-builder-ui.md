# T20 — Exam builder UI (manual, blueprint and AI assistant; settings; versions and exports)

**Owner:** Claude Code sub-agent (Sonnet 5.5) · **Branch:** `task/T20` · **Refs:** SPEC F6, F7.4–F7.6 · ARCHITECTURE §7 · AGENTS.md

## Goal
A teacher builds an exam in minutes in any of three ways (hand-picking from the bank, a blueprint, or describing it to the AI assistant), tweaks the layout,
generates versions and exports PDF/DOCX/answer keys.

## Scope
`frontend/**` only. Read first: `src/api/client.ts`, `src/api/schema.d.ts` (generated): `/exams`, `/exams/{id}`, sections/items/reorder, `/exams/{id}/blueprint/preview|apply`,
`/exams/{id}/compose` + `/exam-proposals/{id}/apply|discard` + `/exams/{id}/proposals`, `/exams/{id}/versions`, `/exams/{id}/versions/{label}/answer-key`, `/exam-templates`,
`/exams/{id}/exports` + `/exports/{id}/download`, `/bank/questions` (search + facets), `/bank/stats`, and `/subjects/{id}/tree`.
Patterns: `src/api/hooks/*`, `src/components/qmd/*`, `src/features/review/*` (multi-pane layout, keyboard and bulk patterns), `src/features/sources/*`, `src/app/router.tsx`, `src/i18n/*.json`, `src/test/*`.
**Exports panel:** another task (T23) is building `src/features/exports/exam-exports-panel.tsx` (`<ExamExportsPanel examId />`) in parallel. If that file exists on your branch, embed it.
If not, build the "Versions" part yourself (generate versions + list them + per-version answer key view) and leave a clearly marked `{/* T23: ExamExportsPanel */}` slot. The orchestrator wires it at merge.
Never hand-write API types. Don't touch `backend/`.

## Requirements
### `/exams`: list
My exams (the admin toggle "all in org"), filtered by status (draft/final/archived), with title, subject, question count, total points, updated time and versions (with a stale badge).
Create (subject + title, optionally a template) → navigate to the builder. Duplicate and archive.

### `/exams/:id`: builder (two panes plus a sticky summary bar)
- **Summary bar:** title (editable inline), question count, total points, sections count, a revision indicator, and a "versions are stale" warning when the exam changed after the versions were generated.
- **Left pane: the exam:** sections (add/rename/delete/reorder; section instructions), and items within each section showing a QMD preview, type, difficulty, points (editable), and remove.
  **Stimulus groups** render as one grouped block (the stimulus once, then its questions) and move and remove together (handle the 409 `stimulus_group` by offering "remove the whole group").
  Reorder items with up/down buttons (keyboard accessible); drag-and-drop is optional (no heavy dependency). Moving between sections is supported. Show the 422 errors from reorder clearly.
- **Right pane tabs:**
  1. **Add from bank**: an embedded compact search (`/bank/questions`: query, chapter/lesson/type/difficulty filters, approved only) with an "Add" button per result (items already in the exam are marked) and add to the selected section.
  2. **Blueprint**: a rows editor (chapter/lesson multi-select from the subject tree, types, difficulty min–max, count, points, target section), with the available counts shown per row from `/bank/stats` when possible.
     "Preview" → per row selected/requested/shortfall/available, showing the selected questions. "Apply" → replaces the blueprint items. Seed control ("reshuffle").
  3. **AI assistant**: a prompt textarea with example prompts in Arabic and English → `POST /compose` (a loading state that explains it takes a few seconds; show the cost). Show the proposal: the plan (sections and rows), the selected questions grouped by row (with a QMD preview),
     the rationale and warnings. The teacher can remove questions or swap one for another candidate (if the API exposes candidates; otherwise remove only) → "Apply" or "Discard". The proposal history list comes from `/exams/{id}/proposals`.
     A 402 `budget_exceeded` shows a friendly message, and a 502 `compose_failed` offers a retry.
  4. **Settings**: header (school name, exam title, subject label, grade, date, duration, instructions) with a template picker (`/exam-templates`) that pre-fills it, and layout (columns 1/2, font size, Arabic-Indic vs Western digits, answer lines, choices per row auto/1/2/4, language). Save via PATCH, debounced.
  5. **Versions & export**: the `ExamExportsPanel` (see Scope), plus an answer-key preview per version (from the answer-key endpoint, as a table).
- **Preview**: a "Preview" toggle renders the exam read-only in print order (version A order if versions exist) using `QmdRenderer`. It approximates the printed layout and respects the RTL and digits settings for the numbering.

### Quality
i18n ar/en, the RTL guard, accessibility (tabs with roving focus, live regions for async results, dialogs managing focus), and optimistic updates with rollback for points and reorder.
Tests (mocked fetch): create exam → builder; add from bank; a stimulus group added and removed as a unit (409 handling); reorder calls and 422 display; blueprint preview → apply;
the AI assistant proposal → remove one → apply, plus the 402 and 502 messages; settings PATCH (debounced) with a template prefill; versions generation and stale warning; the preview rendering in RTL with Arabic-Indic numbering.

## Acceptance
From `frontend/`: `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` all pass, and the root `make check` passes.
Commit on `task/T20` (message `T20: …`) and print the final report in the AGENTS.md format.
