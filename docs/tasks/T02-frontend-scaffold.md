# T02 — Frontend scaffold, i18n/RTL, app shell

**Owner:** agy (Gemini 4 Argon) · **Branch:** `task/T02` · **Refs:** ARCHITECTURE §7, SPEC §3 (i18n, a11y) · AGENTS.md

## Goal
A production-grade React app skeleton: strict tooling, Arabic-first RTL/LTR switching, the app shell with
navigation, and a typed API client wired to the backend's generated OpenAPI schema.

## Scope: files you own
`frontend/**` only. Do **not** touch `backend/`, `Makefile`, `.github/` or any root files.
The backend is being built in parallel by another agent. Its root `Makefile` calls your pnpm scripts by these exact names:
`lint`, `typecheck`, `test`, `build`, `api:gen`.

## Requirements

### Tooling
- Vite + React 19 + TypeScript. `tsconfig` strict with `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` and `noImplicitOverride`. Path alias `@/` → `src/`.
- pnpm, with `packageManager` pinned in package.json and the lockfile committed. Node ≥ 22.
- ESLint flat config: `typescript-eslint` `strictTypeChecked` + `stylisticTypeChecked`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `eslint-plugin-jsx-a11y` (recommended). Zero warnings allowed (`--max-warnings 0`).
- Prettier + `prettier-plugin-tailwindcss`.
- **RTL guard**: a script `scripts/check-logical-classes.mjs`, run as part of `pnpm lint`. It fails if any `.tsx`/`.ts` file under `src/` uses physical-direction Tailwind classes (`ml-`, `mr-`, `pl-`, `pr-`, `left-`, `right-`, `text-left`, `text-right`, `rounded-l-`, `rounded-r-`, `border-l-`, `border-r-`, including variants like `md:ml-2`). The logical equivalents (`ms-`, `me-`, `ps-`, `pe-`, `start-`, `end-`, `text-start`…) are required. Generated `components/ui/` files are included, so fix them if shadcn generates physical classes.
- Vitest + jsdom + @testing-library/react + @testing-library/user-event. Coverage via v8.
- package.json scripts: `dev`, `build` (tsc -b && vite build), `preview`, `lint` (eslint + RTL guard), `format`, `format:check`, `typecheck` (tsc --noEmit -p .), `test` (vitest run), `test:coverage`, and `api:gen` (`openapi-typescript ../backend/openapi.json -o src/api/schema.d.ts && prettier --write src/api/schema.d.ts`).

### Styling and UI
- Tailwind CSS v4 via `@tailwindcss/vite`. shadcn/ui initialized (`components.json`), with the components button, input, label, card, dropdown-menu, sheet, tooltip, separator, skeleton and sonner. Light and dark themes via CSS variables, with a theme toggle persisted to localStorage.
- Fonts via @fontsource: "IBM Plex Sans Arabic" (UI, 400/500/600/700) and "Noto Naskh Arabic" (content, exposed as the `font-content` utility).

### i18n
- i18next + react-i18next. `src/i18n/ar.json` and `en.json` with namespaced keys. Default language `ar`, persisted to localStorage.
- On language change, set `<html lang>` and `<html dir>` (`rtl` for ar, `ltr` for en). Radix/shadcn components must follow the direction (use Radix `DirectionProvider`).
- No hard-coded user-facing strings in components.

### API client
- `src/api/client.ts`: `openapi-fetch` client typed with `paths` from `src/api/schema.d.ts`. baseUrl is `/`, with `credentials: "include"`.
  Add a middleware that reads the `qbank_csrf` cookie and sends it as the `X-CSRF-Token` header on POST/PUT/PATCH/DELETE.
- `backend/openapi.json` may not exist yet. Commit an initial `src/api/schema.d.ts` generated from a minimal
  OpenAPI 3.1 document that you write to `frontend/src/api/bootstrap-openapi.json` and that contains **exactly** this one endpoint:
  `GET /api/v1/health` → 200 with schema `HealthOut {status: string, version: string, db: "ok" | "down"}` (all required).
  The orchestrator regenerates it from the real backend after merging.
- TanStack Query provider. A `useHealth()` hook in `src/api/hooks/health.ts`.
- Vite dev server proxies `/api` → `http://localhost:8000`.

### App shell and routing
- React Router 7 (data router). Layout: a collapsible sidebar (it becomes a Sheet on mobile) plus a top bar.
- Nav items (icons from lucide-react): Sources, Review, Question bank, Exams, Settings. Each route is a placeholder page with a translated title and an empty-state component. Add a 404 page.
- Top bar: app name "Qbank / بنك الأسئلة", a language switch (العربية / English), a theme toggle, and a backend status dot from `useHealth()` (green ok, amber db down, red unreachable) with a tooltip.
- Folder structure exactly as ARCHITECTURE §7 (`api/ app/ features/ components/ i18n/ lib/`).
- Accessible: landmarks, skip link, focus-visible styles, and keyboard-navigable nav.

### Tests (at least)
- Switching language flips `document.documentElement.dir` and `lang`, and re-renders the translated nav.
- The shell renders all nav items, and navigation shows the right placeholder page.
- The health dot shows each of its three states (mock fetch).
- The RTL guard script fails on a sample with `ml-2` and passes on `ms-2` (unit test the matcher function).

### Docker
- `frontend/Dockerfile`: multi-stage (node build → `caddy:2-alpine` serving `dist/`), with a `frontend/Caddyfile` doing SPA fallback and reverse proxy of `/api/*` to `api:8000`.

## Acceptance
From `frontend/`: `pnpm install --frozen-lockfile && pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` all pass.
`pnpm dev` shows the shell in Arabic RTL by default. Switching to English flips to LTR with no layout breakage.
