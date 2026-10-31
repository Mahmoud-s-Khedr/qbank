# T21 — PDF export: HTML templates, fonts, KaTeX, layout options, answer keys, bubble sheet

**Owner:** Claude Code sub-agent (Sonnet 5.5) · **Branch:** `task/T21` · **Refs:** SPEC F7.1, F7.3–F7.6 · ARCHITECTURE §3 (exports, exam_templates), §4 (QMD), §9 · AGENTS.md

## Goal
Print-ready A4 PDFs for every exam version, Arabic-first and right-to-left, with correct math, figures, an answer key and an optional bubble sheet.
Exports are generated in the background, stored, and downloadable again later.

## Scope
`backend/**`, `.github/workflows/ci.yml` (only to install Chromium for the backend job), and `backend/Dockerfile`.
Build on: `exams/versions.py` + `services/exams.py` + `services/exam_generation.py` (layout, display numbering and lettering, answer key),
`models/` (`Exam`, `ExamVersion`, `Asset`, `Question`, `Stimulus`), `storage/`, `worker.py` (actor patterns), `api/routers/exams.py`.
**Migrations:** take the current Alembic head from `uv run --directory backend alembic heads` as `down_revision`, and name the file `t21_exports.py`
(other tasks add migrations in parallel; the orchestrator re-parents at merge).

## Requirements
### 1. QMD → HTML (server side): `qbank/export/qmd.py`
`markdown-it-py` + `mdit-py-plugins` (dollarmath, tables), with **no raw HTML** (`html=False`). `$…$`/`$$…$$` become `<span class="math inline">…</span>` / `<div class="math display">…</div>`,
rendered by KaTeX in the browser at print time. `![cap](asset:<id>)` → `<img src="data:…">` (inline the asset bytes from storage, so the page has no network dependency).
`____` → `<span class="blank"></span>`. `dir="auto"` on block elements. The behaviour must match the frontend `QmdRenderer` (read `frontend/src/components/qmd/QmdRenderer.tsx`).

### 2. Templates: `qbank/export/templates/*.html.j2` (Jinja2, autoescape on)
- `exam.html.j2`: header block (org/school name, logo, exam title, subject, grade, date, duration, total marks, and student name/number/class fields),
  instructions, sections with titles and instructions, questions with continuous display numbers, stimulus printed **once** before its group (with "اقرأ … ثم أجب" intro if present),
  MCQ choices re-lettered per version with an **auto layout** (4 per row if every choice is ≤ 18 chars, 2 per row if ≤ 40, otherwise 1; overridable via `layout.choices_per_row`),
  figures (max width 60% of the column, never split across pages: `break-inside: avoid`), and answer lines after essay/short_answer questions (`layout.answer_space_lines`).
  The points per question are shown in the margin. `layout.columns` is 1 or 2 (CSS columns). `font_size_pt` is applied.
- `answer_key.html.j2`: version label, a table of number → correct label(s)/answer text → points, and the total.
- `bubble_sheet.html.j2`: only for exams where every item is MCQ. A student info block, then rows of circles labelled with the version's lettering, 2–3 columns of numbers.
- **Digits:** `layout.digits = "arabic"` converts all digits that the template prints (numbers, points, dates; not math, not question content) to Arabic-Indic ٠١٢٣٤٥٦٧٨٩.
- **RTL:** `<html dir="rtl" lang="ar">` for Arabic exams, `ltr` for English. Use logical CSS properties throughout.
- **Fonts and KaTeX are vendored**, with no CDN at runtime: put Noto Naskh Arabic (OFL, from `frontend/node_modules/@fontsource/noto-naskh-arabic` woff2 files)
  and KaTeX (`frontend/node_modules/katex/dist`: `katex.min.js`, `katex.min.css`, `contrib/auto-render.min.js`, `contrib/mhchem.min.js`, fonts) in `qbank/export/vendor/`,
  with their LICENSE files. The CSS is inlined and the fonts are referenced via `file://` paths (Chromium loads them from disk).

### 3. HTML → PDF: `qbank/export/pdf.py`
- The Playwright Python sync API with Chromium (`playwright` dependency). Executable: `settings.export_chromium_path` if set, else Playwright's bundled Chromium.
- Load the HTML, wait for fonts (`document.fonts.ready`) and KaTeX auto-render to finish (set a `window.__qbankReady = true` flag), then `page.pdf(format="A4", print_background=True, margin=…, display_header_footer=True, footer_template=…)`.
  The footer shows "صفحة X من Y" / "Page X of Y" with the exam title and version label. (Chromium's footer uses Western digits for page numbers. Document this as a known limitation.)
- One browser per worker process, reused (lazy singleton), with a new context per export. A 60 s timeout per export.

### 4. Exports: model + API + actor
- `exports` table (ARCHITECTURE §3): exam_version_id, kind (`pdf` | `answer_key_pdf` | `bubble_sheet_pdf`; T22 adds `docx`/`answer_key_docx`), status (`pending|ready|failed`), file_key, error, exam_revision, size_bytes.
  **Stale** is computed (`exam_revision < exam.revision`), not stored.
- `exam_templates` table (org_id, name, header JSONB, logo_asset_id) + `GET/POST/PATCH/DELETE /api/v1/exam-templates` (admin writes). `exams.settings.template_id` (optional) supplies header defaults, with the exam's own values winning.
- `POST /api/v1/exams/{id}/exports` `{versions: ["A","B"] | "all", kinds: [...]}` → 202 + job. Actor `render_exports(export_ids)`.
- `GET /api/v1/exams/{id}/exports` (with `stale`), `GET /api/v1/exports/{id}/download` (streamed; the filename `<exam-title>-<version>-<kind>.pdf`, RFC 5987-encoded for Arabic), `DELETE /api/v1/exports/{id}`.
- Permissions follow exam visibility (T18 rules).

### 5. CI, Docker, Makefile
- `ci.yml` backend job: add `uv run --directory backend playwright install --with-deps chromium` before the tests (cache `~/.cache/ms-playwright`).
- `backend/Dockerfile`: install Chromium's runtime deps and the browser via Playwright in the image (keep it non-root, and keep image size reasonable). Leave Pandoc to T22.
- Locally, `google-chrome` is installed at `/usr/bin/google-chrome`. Tests may use it via `QBANK_EXPORT_CHROMIUM_PATH` when Playwright's browser isn't installed.

### Tests
- Unit (no browser): QMD→HTML (math, assets inlined, no raw HTML, blanks), template rendering (RTL/LTR, the stimulus printed once, re-lettered choices in version order, the auto choice layout thresholds,
  Arabic-Indic digit conversion, bubble sheet only for all-MCQ exams, answer key matching the T18 answer-key endpoint).
- Integration (marked `pdf`, which **must run in CI**): generate a real PDF for a 6-question Arabic exam with math and one figure. Open it with PyMuPDF and assert ≥ 1 page, A4 size, and an embedded Noto Naskh font,
  plus the answer key PDF and the bubble sheet. Plus the export API flow: 202 → actor → `ready` → download (content-type, filename) → edit the exam → `stale: true`.

## Acceptance
`make check` passes (backend). Run `make api-gen` and commit the generated files. Commit on `task/T21` (message `T21: …`) and print the final report in the AGENTS.md format.
