# T14 — Login, auth guard, and the Sources screens (upload, list, detail with live progress)

**Owner:** agy (Gemini 4 Argon) · **Branch:** `task/T14` · **Refs:** SPEC F1.1–F1.4, §3 (i18n, a11y) · ARCHITECTURE §7 · AGENTS.md

## Goal
A user can sign in, upload a workbook PDF, and watch it being processed page by page.

## Scope
`frontend/**` only. Read first: `src/api/client.ts`, `src/api/schema.d.ts` (generated; the auth, taxonomy and sources endpoints are already in it),
`src/api/hooks/health.ts` (hook style), `src/app/*` (router, shell), `src/components/page-canvas/PageCanvas.tsx`, `src/i18n/*`.
**Never hand-write API types.** Use `paths`/`components` from `schema.d.ts`. If an endpoint you need is missing, list it in Follow-ups. Don't touch `backend/`.

## Requirements

### Auth
- `/login` page: email and password (react-hook-form + zod), errors from the API's problem+json `code` (`invalid_credentials` → a translated message), a loading state, and an Arabic default.
- `useMe()` (GET `/api/v1/auth/me`), `useLogin()`, `useLogout()`. Login sets the cookies server-side. The CSRF middleware in `client.ts` already handles headers.
- A route guard: unauthenticated users go to `/login?next=…`, and after login they return to `next` (same-origin paths only). A 401 from any query → invalidate `me` → redirect.
- Top bar: user menu (name, role, logout). The nav hides items the role can't use (`teacher` doesn't see Sources/Review).

### Sources list `/sources`
- A table: title, subject, status badge (colour plus text, never colour alone), pages (rendered/failed/total), cost (`$0.0000`), and created (relative time, localized).
  Filters: subject, status. Cursor pagination ("Load more"). Empty state with a CTA.
- An "Upload workbook" button (editor/admin only) opens an upload dialog.

### Upload dialog
- Subject select (from `/api/v1/subjects`), title (default: the file name without extension), grade (optional), and a file drop zone plus picker.
- Client-side validation: PDF only (`application/pdf` or a `.pdf` extension) and ≤ 300 MB, with clear messages.
- Upload with real progress (use `XMLHttpRequest` for `upload.onprogress`, sending credentials and the CSRF header. Document why it bypasses openapi-fetch). On 202, navigate to the source detail page.
  Server errors `invalid_pdf` and `file_too_large` map to translated messages.

### Source detail `/sources/:id`
- Header: title, subject, status, stage, cost, and a delete button (a confirm **dialog component**, never `window.confirm`).
- **Live progress**: `EventSource('/api/v1/sources/:id/events', { withCredentials: true })` updates the TanStack Query cache for the source.
  A progress bar per stage shows the counts. Reconnect with backoff on error. Close the stream on unmount and on a terminal status.
  If the source is `paused`, show the reason and a "Resume" button if `POST /sources/{id}/resume` exists in the schema (otherwise list it in Follow-ups).
- **Page grid**: thumbnails from `/api/v1/sources/:id/pages/:n/image?variant=display` (lazy-loaded, fixed aspect ratio, skeleton while loading),
  each with the page number, a status badge, a `page_kind` chip when known, and failed pages showing the error in a tooltip. It's virtualized or paginated past 200 pages
  (simple windowing is fine, but no new heavy dependencies).
- Clicking a page opens a page viewer (Sheet or route `/sources/:id/pages/:n`) using `PageCanvas` in `view` mode, with prev/next keyboard navigation (←/→ follow the reading direction:
  in RTL, ← goes to the **next** page).

### Quality
- All strings in `ar.json`/`en.json`. Logical CSS only (the RTL guard must pass). Accessible: labelled form fields, focus management in dialogs, `aria-live` for progress.
- Tests (Vitest + Testing Library with mocked fetch/EventSource/XHR): the login flow and redirect to `next`; the guard redirecting when 401; list rendering and filters;
  upload validation (wrong type, too large) and the success navigation; SSE events updating the progress UI; the RTL arrow-key mapping in the page viewer; role-based nav hiding.

## Acceptance
From `frontend/`: `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` all pass.
**Commit your work on `task/T14` before printing the final report.**
