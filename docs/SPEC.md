# Qbank — Product Specification

AI-powered question bank and exam generator. Teachers, schools and education centers
upload scanned workbooks (PDF). The system extracts every question into a structured,
searchable bank. Users review the results against the original pages, then build
customized, print-ready exams.

Primary market: Egyptian / Arab secondary education. Content is mostly **Arabic (RTL)**,
with English, math notation, chemistry formulas, diagrams and tables mixed in.
Subjects: Mathematics, Physics, Chemistry, Biology, Arabic, English (the list is extensible).

---

## 1. Users and roles

| Role | Can do |
|---|---|
| `admin` | Everything in the org, plus manage users, model settings and exam templates |
| `editor` | Upload sources, review and edit questions, manage the taxonomy |
| `teacher` | Search the bank (approved questions only), build and export exams |

Multi-tenant: every record belongs to an `organization`. Users only see their org's data.

## 2. Functional requirements

### F1 — Upload and ingestion
- F1.1 Upload a PDF (up to 300 MB / 1000 pages) and pick a subject, grade and title.
- F1.2 The system renders every page to an image and runs the extraction pipeline in the background.
- F1.3 Live progress per source: pages rendered, extracted and validated, failures, and LLM cost so far.
- F1.4 Damaged PDFs are tolerated: pages that fail to render are marked `failed` and the rest continue. `fixtures/pdfs/test-exams.pdf` has a broken page tree from page 61, and `test-2027.pdf` has a syntax error.
- F1.5 Re-run extraction for one page or a whole source, optionally with a different model.
- F1.6 Idempotent: re-processing a page replaces that page's unreviewed questions. It never touches reviewed ones.

### F2 — Extraction
For each page, extract:
- F2.1 **Questions**: number as printed, type, stem, choices (with their printed labels: أ ب ج د / a b c d / 1 2 3 4), and the correct answer when it is on the page. Each question carries a bounding box per page it spans.
- F2.2 **Stimuli**: a shared passage, poem, case, table or figure that several questions depend on. Example: in `test1.pdf` a poem feeds questions 1–5. Questions link to their stimulus.
- F2.3 **Figures and tables**: bounding boxes that are cropped into image assets and referenced from the question, choice or stimulus content. Simple tables are also transcribed as Markdown tables.
- F2.4 **Math and science notation**: transcribed as LaTeX (`$...$` inline, `$$...$$` display). Chemistry uses `\ce{}` (mhchem).
- F2.5 **Structure**: chapter, lesson, unit and exam headings, assigned to questions. Running headers, footers, page numbers and watermarks are ignored.
- F2.6 **Cross-page continuation**: a question or stimulus that starts on page N and continues on N+1 is stitched into one item.
- F2.7 **Answer keys**: answer-key sections (often at the end of a book) are matched to questions by section and number.
- F2.8 Question types: `mcq_single`, `mcq_multi`, `true_false`, `fill_blank`, `short_answer`, `essay`, `matching`, `ordering`.
- F2.9 Metadata per question: subject, chapter, lesson, type, difficulty (1–5, AI-estimated with a stated reason, human-overridable), language, source and page(s), number in the source, tags.
- F2.10 Diacritics (tashkeel) are preserved exactly when they appear in the source, because they carry meaning in Arabic-language questions.

### F3 — Validation
Every extracted question gets a list of issues (`error` | `warning`) and a confidence score (0–1).
Rules include at least:
- MCQ with fewer than 2 choices, duplicate choice labels, or a non-contiguous label sequence.
- Missing correct answer (warning if the source has no key; error if a key was matched but failed to apply).
- The stem references a figure ("الشكل المقابل", "the figure", "الصورة") but no figure is attached.
- Empty or truncated stem, or a stem ending mid-sentence on the last page region (possible continuation).
- LaTeX that fails to parse.
- Question numbers on a page that are not sequential (a gap means a question may have been missed).
- A near-duplicate of an existing question (trigram similarity ≥ 0.9). The duplicate is linked, not deleted.
- Low model self-reported confidence.
- An optional **LLM verifier pass**: a second model from a different family re-reads the page image against the extracted JSON and reports discrepancies. It runs on pages below the confidence threshold, or on all pages if the source is configured that way.

Status flow: `draft` → (`needs_review` if any error or confidence < threshold) → `approved` | `rejected`.
Only `approved` questions are visible to teachers and usable in exams.

### F4 — Review interface
- F4.1 Review queue per source, sortable by status, issue severity and page.
- F4.2 Split view: the page image on one side, with bounding boxes of all extracted items overlaid (colour by status). The editable question is on the other side. Clicking a box selects its question, and the reverse.
- F4.3 The editor has Markdown + LaTeX with live rendered preview (RTL-aware), choices, correct answer, type, metadata, difficulty and tags.
- F4.4 Fix figures: redraw or adjust a bounding box on the page image, and the figure is re-cropped.
- F4.5 Split one question into two, merge two into one, attach or detach a stimulus, and create a missed question by drawing a box (optionally with an "extract this region" LLM call).
- F4.6 Re-extract the page with a stronger model and see a diff before accepting.
- F4.7 Approve or reject, singly or in bulk. Keyboard shortcuts for the review loop (next, prev, approve, reject).
- F4.8 Full audit history per question: who changed what, and when.

### F5 — Question bank
- F5.1 Browse and search: full-text search (Arabic-aware, diacritics-insensitive), with filters for subject, grade, chapter, lesson, type, difficulty, source, status and tags. Results show counts per facet.
- F5.2 Taxonomy management: subjects → chapters → lessons. Rename, reorder, merge, and move questions between them.
- F5.3 Bulk edit metadata on selected questions.
- F5.4 Manually add questions (not from a source).

### F6 — Exam builder
- F6.1 **Blueprint mode**: rows of (chapter/lesson scope, type, difficulty range, count, points per question). The system samples approved questions. It reports a shortfall when a row cannot be filled.
- F6.2 **Manual mode**: add specific questions from the bank to the exam, then reorder them and group them into sections.
- F6.3 **AI-assisted mode**: the teacher describes the exam in natural language ("45-minute biology test on chapter 2, mostly medium, 20 MCQ + 2 essay"). The AI proposes a blueprint and a concrete question selection from the bank, with a short rationale. The teacher edits it before accepting. The AI only picks existing approved questions; it never invents questions.
- F6.4 Questions that share a stimulus stay together, in order, with the stimulus printed once.
- F6.5 No duplicates or near-duplicates in one exam. Optionally exclude questions used in the teacher's previous exams.
- F6.6 Sections, points, duration and instructions. The total mark is computed.
- F6.7 **Versions**: N versions (A, B, C …) with a deterministic seed. Question order is shuffled within sections (stimulus groups move as a unit) and choice order is shuffled, except choices flagged as pinned (e.g. "all of the above", "جميع ما سبق").
- F6.8 Exams can be saved, duplicated, edited and archived.

### F7 — Export
- F7.1 **PDF** (print-ready, A4): exam header (org/school name, logo, subject, grade, date, duration, total marks, student name/number fields), instructions, questions with figures, and page numbers ("صفحة ١ من ٤"). RTL for Arabic exams. Arabic-Indic or Western digits, configurable.
- F7.2 **DOCX** (editable in Word): the same content, with native Word equations (OMML) rather than images, RTL paragraphs, and figures as images.
- F7.3 **Answer key** document per version. An optional OMR-style bubble answer sheet for MCQ-only exams.
- F7.4 Layout options: 1 or 2 columns, MCQ choices laid out automatically (1, 2 or 4 per row depending on length), font size, and an optional space for answers after essay questions.
- F7.5 Org-level exam header templates (logo, school name, default instructions).
- F7.6 Exports are stored and downloadable again. Changing the exam marks previous exports stale.

### F8 — Administration
- F8.1 User management (invite, role, deactivate).
- F8.2 Per-org model settings: which OpenRouter model to use for each pipeline stage, the verifier policy, and a monthly spend cap. Ingestion pauses when the cap is reached.
- F8.3 Cost dashboard: LLM spend per source, per stage and per month.

## 3. Non-functional requirements

- **i18n**: the UI is in Arabic and English, switchable, with full RTL/LTR mirroring. Default `ar`.
- **Performance**: extraction runs pages in parallel (default concurrency 8 per source). A 100-page workbook should finish in under 10 minutes, depending on the model. Bank search should take under 300 ms p95 for 100k questions.
- **Reliability**: every LLM call has retries with backoff, a timeout, and schema validation of the output (one repair retry on invalid JSON). Jobs are resumable after a worker restart.
- **Cost visibility**: every LLM call records model, tokens and cost (from OpenRouter's `usage` response).
- **Security**: password hashing (argon2), JWT in an httpOnly cookie, CSRF protection for cookie auth, per-org row scoping enforced in the data-access layer, upload type and size validation, and no secrets in the repo.
- **Accessibility**: WCAG 2.1 AA for the web UI.
- **Quality gates**: CI runs lint, format, type checks, unit and integration tests, migration-drift and OpenAPI-drift checks, the frontend build, Docker builds and e2e tests. See ARCHITECTURE §8.

## 4. Acceptance — "done" for the whole product

1. Upload `fixtures/pdfs/test-exams.pdf`. It processes completely, pages 61+ are reported as failed, and the rest are extracted.
2. On the golden pages (`fixtures/golden/`), the default model reaches at least 95% exact question count, at least 90% choice-text match (normalized), and figure bounding-box IoU of at least 0.7. Measured by `qbank-eval`.
3. The poem in `test1.pdf` is extracted as one stimulus linked to its questions.
4. `test1.pdf` uploaded after `test-exams.pdf` flags all its questions as duplicates.
5. A reviewer can fix a figure crop, approve questions and see them in the bank.
6. A teacher builds a 20-question exam by blueprint and by AI assistant, and exports 2 versions as PDF + DOCX + answer keys. The Arabic text renders correctly and the DOCX opens in Word with editable equations.
7. CI is green on `main`.
