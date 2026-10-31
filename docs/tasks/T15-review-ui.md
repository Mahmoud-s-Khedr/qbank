# T15 — Review workspace UI

**Owner:** Claude Code sub-agent (Sonnet 5.5) · **Branch:** `task/T15` · **Refs:** SPEC F4 · ARCHITECTURE §7 · AGENTS.md

## Goal
The screen where an editor turns extracted drafts into trusted questions quickly. The scanned page sits on one side and the editable question on the other.
Boxes, issues, keyboard-driven approve/reject, figure re-crop, split/merge, and re-extract with a diff.

## Scope
`frontend/**` only. Read first:
- `src/api/client.ts`, `src/api/schema.d.ts` (generated: all the T12 review endpoints, the T11 issues fields and the T08 question/stimulus/page shapes are in it), `src/api/hooks/sources.ts` (hook style)
- `src/components/page-canvas/PageCanvas.tsx` (regions, select, edit and draw modes, `initialFit`), `src/components/qmd/QmdRenderer.tsx`, `src/components/qmd/QmdEditor.tsx`
- `src/features/sources/source-detail-page.tsx` (layout and patterns), `src/app/router.tsx`, `src/i18n/*.json`, and `src/test/auth-sources.test.tsx` (test helpers and mocks)

Relevant endpoints: `GET /sources/{id}/review-queue`, `GET /sources/{id}/questions`, `GET /sources/{id}/stimuli`, `GET /questions/{id}`, `PATCH /questions/{id}` (with `version`),
`POST /questions/{id}/approve|reject|reopen`, `POST /questions/bulk`, `POST /questions/{id}/split`, `POST /questions/merge`, `GET /questions/{id}/history`,
`POST /issues/{id}/resolve|unresolve`, `POST /questions/{id}/figures`, `PUT /assets/{id}/region`, `DELETE /questions/{id}/figures/{asset_id}`, `PATCH /stimuli/{id}`,
`POST /sources/{id}/pages/{n}/reextract` → job → `GET /page-proposals/{id}` (`{proposal, diff}`) → `/accept` / `/discard`, `POST /sources/{id}/pages/{n}/extract-region`, and `GET /sources/{id}/pages/{n}`.
Never hand-write API types. Use `paths`/`components`. If something you need is missing, add it to Follow-ups and degrade gracefully.

## Requirements
### Route and layout: `/sources/:id/review` (editor/admin), plus a "Review" button on the source detail page and the Review nav item (it lists the sources that have `needs_review` questions)
Three panes, collapsible on narrow screens (tabs on mobile):
1. **Queue** (narrow): from the review queue, with filters (status, severity) and sort (page, severity, confidence). Each row shows number_label, page, a status chip, and issue counts by severity (icon + number, never colour alone). Totals sit at the top.
2. **Page** (wide): `PageCanvas` showing the current question's page, with **all** regions on that page (questions, stimuli, figure assets, headings) coloured by kind and status. The current question is selected.
   Clicking a box selects that item. When a question spans 2 pages, a page switcher appears.
3. **Editor**: `QmdEditor` for the stem, a choices editor (add/remove/reorder, mark correct, "pinned" toggle), answer/explanation, type select, difficulty (1–5, showing the AI reason and source), tags (autocomplete if `/bank/tags` exists), and the stimulus (shown read-only with an "edit stimulus" link).
   The **issues panel** lists the issues with severity, message, and resolve/unresolve. The verifier's suggested fixes get an "apply" button that patches the field.
   A **history** tab shows the audit events.
- Save: explicit (Ctrl/Cmd+S) or autosave on blur. Send `version`. **On 409 `version_conflict`**, show a dialog with the server's current values vs. your edits, and options to reload or overwrite (re-send with the new version).

### Actions
- **Keyboard** (with a help overlay on `?`): J/K or ↓/↑ = next/prev in the queue; A = approve; R = reject (prompts for a reason); E = focus the editor; Ctrl/Cmd+S = save; F = enter figure-draw mode; Esc = cancel the mode.
  Approve while error-severity issues remain → show the 422 `unresolved_errors` message and list the issues (admins get a "force approve" option).
- **Bulk**: multi-select in the queue (checkboxes, plus Shift-click ranges) → approve/reject/set metadata.
- **Figures**: "Add figure" → draw mode on the canvas → `POST /questions/{id}/figures`. Selecting a figure asset's box → edit mode → drag/resize → `PUT /assets/{id}/region`.
  After a re-crop, **cache-bust** the image URL (append `?v=<updated_at or a counter>`) because the server sends `max-age=86400`. Removing a figure needs a confirm dialog.
- **Split/Merge**: split at the cursor position in the stem, or at a choice. Merge with the next question (a confirm dialog shows both).
- **Missed question**: draw a region → `extract-region` → prefill a new question form → save via `POST /questions` with `regions` set.
- **Re-extract page**: a model select (only allowed models; the default is the source's model) → job progress → a **diff view** (per question: field-level before/after, plus added and removed), checkboxes per question → accept selected / discard. Approved questions show as "skipped".

### Quality
- All strings are in `ar.json`/`en.json`. The RTL guard passes. Content renders via `QmdRenderer`. Box coordinates are never mirrored.
- Accessible: panes are landmarks with labels, the queue is a listbox with aria-selected, focus is managed after approve (move to next), and shortcuts are documented and disabled while typing in inputs.
- Performance: the queue can hold 1,000 items (window it if needed, without heavy deps). Prefetch the next question.
- Tests (Vitest + Testing Library, mocked fetch): queue rendering and filters; selecting an item loads the page and regions; J/K navigation; approve moving to the next item; approve blocked by errors showing the message;
  the version-conflict dialog; figure add (draw → POST) and re-crop (edit → PUT plus a cache-busted src); split/merge calls; the re-extract diff and accept-selected; bulk approve; keyboard shortcuts ignored inside inputs.

## Acceptance
From `frontend/`: `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` all pass, and the root `make check` passes.
Commit on `task/T15` (message `T15: …`) and print the final report in the AGENTS.md format.
