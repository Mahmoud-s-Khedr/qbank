# T22 — DOCX export via Pandoc (editable Word, native equations, RTL)

**Owner:** Claude Code sub-agent (Sonnet 5.5) · **Branch:** `task/T22` · **Refs:** SPEC F7.2, F7.3, F7.5 · ARCHITECTURE §4 · AGENTS.md

## Goal
The same exam, answer key and layout as the PDF (T21), but as a `.docx` a teacher can edit in Word. Equations must be **native Word equations (OMML)**, not images.
Arabic paragraphs are right-to-left, and figures are embedded images.

## Scope
`backend/**`, plus `.github/workflows/ci.yml` and `backend/Dockerfile` only if needed. Build on T21: `export/view.py` (`ExamView`, the per-version numbering, lettering,
points and digits helpers), `export/builder.py` (`render_export`), `schemas/exports.py` (`ExportKind`), `services/exports.py`, and the `render_exports` actor. Reuse the view model.
**Don't duplicate the layout logic.** If you need a small refactor of `view.py` to share it, keep the PDF output byte-for-byte the same (the existing PDF tests must still pass).
**Migrations:** only if needed. Use `down_revision` = the current head, and a file name prefix of `t22_`.

## Requirements
### Conversion
- **Pandoc via `pypandoc-binary`** (the bundled pandoc binary, so there's no system install locally, in CI or in Docker). Build a **Pandoc document** for the exam
  (generate Pandoc Markdown, or Pandoc JSON AST via `panflute`, whichever is more robust; justify it) and convert with `--reference-doc=<our reference.docx>`.
- **QMD → Pandoc:** `$…$` and `$$…$$` pass through as TeX math, so Pandoc emits OMML. `\ce{…}` (mhchem) isn't supported by Pandoc, so convert the common patterns to plain TeX
  (`\ce{H2O}` → `\mathrm{H_2O}`, `\ce{2H2 + O2 -> 2H2O}` → `\mathrm{2H_2 + O_2 \rightarrow 2H_2O}`, `^{2-}` charges, `(g)` and `(aq)` states, `<=>`) in a small, unit-tested converter.
  Unknown constructs fall back to the raw text in `\mathrm{}`.
- `![cap](asset:id)` → write the asset to a temp dir and reference it (Pandoc embeds it), with a width cap of about 60% of the text width. `____` → a visible blank (underlined spaces, or a fixed-width underline run).
- **RTL:** Pandoc `dir: rtl` metadata plus a reference doc whose styles are RTL (`w:bidi`, right alignment, an Arabic font such as **Noto Naskh Arabic**, with Arial as the fallback through `w:rFonts w:cs`).
  An English exam uses LTR. Mixed paragraphs must keep math LTR (OMML handles this).
- **Structure:** a header table (school, title, subject, grade, date, duration, total marks, version), student fields, instructions, sections with headings,
  continuously numbered questions (in the version's order and digits), each stimulus once with its group, MCQ choices in a **table** with 1/2/4 columns using the same auto rule as the PDF
  (re-lettered per version), points per question, and answer lines for essay/short_answer.
- **`reference.docx`:** generate it **reproducibly from code** (a script `export/make_reference_docx.py` using `python-docx` that patches Pandoc's default reference doc: fonts, sizes, RTL, margins A4 2 cm, and the table style).
  Commit the generated file, and add a test that regenerating it gives the same styles.
- Answer key DOCX: a table of number / answer / points per version.

### Exports
- Add `docx` and `answer_key_docx` to `ExportKind` and to `render_export`. The download content type is `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, and the filename uses the `.docx` extension (RFC 5987).
- Same API and actor as T21: `kinds` now accepts the new values.

### Tests
- Unit: the mhchem converter cases; QMD → Pandoc for math, assets, blanks and no raw HTML; the choice-table column rule matching the PDF's.
- Integration (Pandoc really runs): generate a DOCX for a 6-question Arabic exam with math, a chemistry formula and a figure, then unzip it and assert:
  `word/document.xml` contains `m:oMath` (native equations) and **no** equation images; `w:bidi` on the Arabic paragraphs; an embedded image under `word/media/`;
  the version's re-lettered choices in order; the header values. Also the answer key DOCX, and the API flow for `kinds: ["docx"]`.
- Keep all the existing PDF tests green.

## Acceptance
`make check` passes. Run `make api-gen` if the API schema changed. Save a sample to `.data/sample-exam.docx` (gitignored) for the orchestrator to inspect.
Commit on `task/T22` (message `T22: …`) and print the final report in the AGENTS.md format.
