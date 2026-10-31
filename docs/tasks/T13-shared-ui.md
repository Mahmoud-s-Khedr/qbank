# T13 — Shared UI: QmdRenderer, QmdEditor, PageCanvas

**Owner:** agy (Gemini 4 Argon) · **Branch:** `task/T13` · **Refs:** ARCHITECTURE §4 (QMD), §7 · SPEC F4.2–F4.4 · AGENTS.md

## Goal
The three components every later screen is built on: rendering question content, editing it, and showing a scanned
page with interactive bounding boxes. They must be correct in Arabic RTL, and accessible.

## Scope
`frontend/**` only. Read first: `frontend/src/app/*`, `frontend/src/components/ui/*`, `frontend/src/i18n/*`,
`frontend/eslint.config.js`, and `frontend/scripts/check-logical-classes.mjs`. Don't touch the API client or `backend/`.

## Components (`frontend/src/components/`)

### `qmd/QmdRenderer.tsx`
`<QmdRenderer source: string, resolveAsset: (id) => string | undefined, lang?: "ar" | "en", inline?: boolean />`
- react-markdown + remark-gfm + remark-math + rehype-katex, plus KaTeX mhchem (`katex/contrib/mhchem`) for `\ce{}`.
- **No raw HTML** (no rehype-raw). Links get `rel="noopener noreferrer"` and only allow http(s).
- `![caption](asset:<uuid>)` → `<img src={resolveAsset(uuid)} alt={caption} loading="lazy">`. An unknown asset renders a visible placeholder ("الصورة غير متاحة").
- Blanks: 4+ underscores → a styled inline blank (`<span class="qmd-blank" aria-label="فراغ">`).
- Direction: `dir="auto"` on each block, so mixed Arabic/English paragraphs work. Math is always LTR inside RTL text.
- `inline` mode renders without block wrappers (for choices).
- Content font `font-content` (Noto Naskh Arabic). Tables get borders and RTL alignment.
- Memoized. A KaTeX parse error renders the raw TeX in a red-bordered span (`throwOnError: false`, `errorColor`).

### `qmd/QmdEditor.tsx`
`<QmdEditor value onChange lang resolveAsset label error? />`, a controlled component.
- A textarea with `dir="auto"` (no heavy editor dependency) and a live `QmdRenderer` preview beside it (stacked on narrow screens).
- Toolbar (with i18n labels and tooltips): inline math `$…$`, display math, fraction `\frac{}{}`, √, superscript/subscript, `\ce{}`, blank `____`, and a table template. Each inserts at the cursor and preserves the undo stack (`document.execCommand('insertText')` with a fallback).
- Keyboard: Ctrl/Cmd+M inline math, Ctrl/Cmd+Shift+M display math.
- Works with react-hook-form via `forwardRef`.

### `page-canvas/PageCanvas.tsx`
```ts
type Box = [number, number, number, number];            // normalized 0–1, x0,y0,x1,y1, origin top-left
type Region = { id: string; box: Box; kind: "question" | "stimulus" | "figure" | "heading";
                status?: "ok" | "warning" | "error" | "approved"; label?: string };
<PageCanvas src width height regions selectedId? onSelect?(id) mode?: "view" | "edit" | "draw"
            onChange?(id, box) onCreate?(box) />
```
- Shows the page image and an absolutely-positioned SVG overlay sized to the image. Boxes are converted from normalized to pixel coordinates.
- Zoom: buttons (+, −, fit width, fit page), Ctrl+wheel, pinch-safe. Pan: drag on empty space, or hold space and drag. The zoom level shows as a %.
- Colours by `kind`, and border style by `status` (dashed for warning, red for error, green for approved). The selected box is thicker and has resize handles.
- `edit` mode: drag the selected box to move it, and drag its 8 handles to resize. Arrow keys nudge (Shift = 10×). Esc deselects. Results are clamped to 0–1, and `onChange` is called on pointer-up with the normalized box (3 decimals).
- `draw` mode: drag to create a box → `onCreate(box)`. Boxes under 1% of the page size are ignored.
- **Coordinates are physical image coordinates. They never mirror in RTL.** Only the toolbar follows the direction.
- Accessibility: each region is a focusable `<g role="button" tabindex=0 aria-label="<kind> <label>">`, Enter/Space selects, and there's a visible focus ring.
- Pointer events only (mouse + touch + pen).

### Dev playground
Route `/dev/components` (registered **only** when `import.meta.env.DEV`). Its samples: an Arabic MCQ with tashkeel and math, a chemistry
equation, a GFM table, a blank, a broken LaTeX string, and a missing asset. Plus a PageCanvas with a sample image (put a small
placeholder PNG in `src/dev/`. Do **not** use the copyrighted fixture pages) and editable boxes.

## Tests (Vitest + Testing Library)
- Renderer: math renders KaTeX markup. `\ce{H2O}` works. Raw `<script>` is not rendered. `asset:` resolves (and the missing placeholder shows). The blank renders. `dir="auto"` is set. A bad TeX string doesn't throw.
- Editor: each toolbar button inserts the right snippet at the cursor. onChange fires. The keyboard shortcuts work.
- PageCanvas: normalized → pixel placement at 2 zoom levels. Clicking a region calls onSelect. Moving with arrow keys calls onChange with the clamped normalized box. Drawing creates a box. Tiny draws are ignored. The RTL document direction does not mirror the box coordinates.
- Keep the existing tests green, and keep lint at zero warnings (including the RTL guard).

## Dependencies
react-markdown, remark-gfm, remark-math, rehype-katex, katex. Nothing else without a justification in your report.

## Acceptance
From `frontend/`: `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` all pass.
**Commit your work on `task/T13` before printing the report.**
