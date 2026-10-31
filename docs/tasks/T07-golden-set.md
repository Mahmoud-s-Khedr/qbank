# T07 — Golden set: hand-verified ground truth for extraction

**Owner:** agy (Gemini 4 Argon) · **Branch:** `task/T07` · **Refs:** SPEC F2, ARCHITECTURE §3 (regions), §4 (QMD) · AGENTS.md

## Goal
Exact, carefully transcribed ground truth for 14 page images. `qbank-eval` (T10) scores every candidate
OpenRouter model against it, so **accuracy matters more than speed**. Model choice for the whole product
depends on this data. Transcribe what is printed, not what you think it should say.

## Scope
`fixtures/golden/**` and `scripts/golden_*.py` only.

## Inputs
The page images (200 DPI) are already in `fixtures/golden/pages/`:

| File | What it is |
|---|---|
| `test-exams__p001.png` | Book cover (no questions) |
| `test-exams__p003.png` | Blank page |
| `test-exams__p006.png` | Exam 4 header + long reading passage + MCQs that depend on it |
| `test-exams__p007.png` | Continuation of exam 4 (questions continue from p006) |
| `test-exams__p016.png` | Essay section ("ثانيًا: الأسئلة المقالية") |
| `test-exams__p017.png` | Exam 5 header + poem + MCQs |
| `test-exams__p022.png` | End of an exam: essay + closing |
| `test-exams__p028.png` | Exam 7: poem stimulus shared by questions 1–5 |
| `test-exams__p030.png` | Dense MCQs, 2- and 4-column choice layouts, several small stimuli |
| `test-exams__p033.png` | Exam 8 header + passage |
| `test-exams__p044.png` | Section divider "أوراق إجابة الاختبارات (بابل شيت)" |
| `test-exams__p045.png` | Blank OMR bubble answer sheet (no questions) |
| `test-2027__p001.png` | Biology: MCQs 61–67 with anatomical figures labelled X/Y/Z/W |
| `test-2027__p002.png` | Biology: Q68 figure, Q72 table-row choices, Q74 bar chart, lesson heading "الهيكل الطرفي" mid-page, chapter tab "الفصل 1" |

You must actually look at each image (open it at full resolution, and zoom into regions when text is small).

## Output

### 1. `fixtures/golden/schema.json`
A JSON Schema (draft 2020-12) for the format below. Every golden file must validate against it.

### 2. One file per page: `fixtures/golden/<image-stem>.json`
```jsonc
{
  "image": "pages/test-exams__p028.png",
  "source_pdf": "test-exams.pdf",
  "page_number": 28,
  "page_kind": "questions",   // cover | blank | toc | section_divider | questions | answer_key | answer_sheet | other
  "headings": [               // in reading order; ignore running headers/footers
    {"level": "exam", "text": "الاختبار السابع", "box": [x0, y0, x1, y1]}
    // level: book | unit | chapter | lesson | exam | section
  ],
  "stimuli": [
    {
      "ref": "s1",
      "kind": "poem",          // passage | poem | figure | table | case
      "intro": "اقرأ الأبيات التالية ثم أجب: قال الشاعر فاروق جويدة:",
      "content": "<QMD>",
      "box": [x0, y0, x1, y1],
      "continues_from_previous": false,
      "continues_on_next": false
    }
  ],
  "questions": [
    {
      "number_label": "1",     // as printed, converted to Western digits ("١" → "1")
      "type": "mcq_single",    // mcq_single | mcq_multi | true_false | fill_blank | short_answer | essay | matching | ordering
      "stem": "<QMD>",
      "choices": [{"label": "أ", "content": "<QMD>"}],   // [] for non-MCQ
      "answer": null,          // or {"labels": ["ب"]} or {"text": "<QMD>"}, ONLY if printed on this page
      "stimulus_ref": "s1",    // or null
      "figures": [{"box": [x0, y0, x1, y1], "kind": "diagram"}],  // diagram | chart | table | photo
      "box": [x0, y0, x1, y1], // whole question incl. choices and figures; on THIS page only
      "continues_from_previous": false,
      "continues_on_next": false
    }
  ],
  "notes": "anything ambiguous, and how you resolved it"
}
```

### 3. Transcription rules (follow exactly)
- **Boxes**: `[x0, y0, x1, y1]`, normalized 0–1 relative to the image width/height, origin top-left, 3 decimal places.
  Boxes must be tight but fully contain their content. Measure them in pixels on the image, then divide. Do not estimate.
- **Text**: transcribe exactly. Keep tashkeel (diacritics) exactly as printed. Remove tatweel/kashida (ـ) that is only used for
  visual stretching. Normalize whitespace to single spaces. Keep punctuation as printed (، ؛ ؟ : .).
- **Labels**: the printed choice labels (أ ب ج د or 1 2 3 4 or a b c d), without circles or parentheses.
- **Ignore**: running headers and footers ("موسوعة بيان في التقويم والتدريب…", "اللغة العربية للثانوية العامة"), page numbers, the watermark logo, and side tabs. The exception is the chapter tab "الفصل 1": record it as a heading with level `chapter`.
- **Poems**: one verse per line (lines separated by `\n`). The two hemistichs are separated by ` ... `. Keep the verse numbers if printed.
- **Fill-in dots** (".........."): replace them with `____` in the stem.
- **Table-row choices** (e.g. Q72): `content` = `"<col1 header>: <cell1> | <col2 header>: <cell2>"`.
- **Figures**: do not describe the figure in the stem. Just add a `figures[]` entry with its box. Labels inside the figure (X, Y, A, B) belong to the figure box.
- **Shared stimulus**: if a poem/passage/figure is shared by several questions, it is a stimulus and each question references it via `stimulus_ref`. A sentence printed immediately above a question that only that question uses (e.g. "قال الزهاوي: …" above Q10) is a stimulus too (`kind: "case"` for prose, `"poem"` for verse).
- Math/chemistry (if any): LaTeX per ARCHITECTURE §4.
- Non-question pages: `page_kind` is set, and `questions`/`stimuli` are `[]`.

### 4. Tooling (Python, stdlib + Pillow + jsonschema, run with `uv run --with pillow --with jsonschema python scripts/...`)
- `scripts/golden_validate.py`: validates every golden JSON against the schema and also checks that all boxes are within 0–1 with x0<x1 and y0<y1, that the `stimulus_ref`s resolve, that question numbers on a page are unique, and that MCQs have ≥ 2 choices. Exits non-zero on any problem.
- `scripts/golden_overlay.py`: draws every box on its page (questions red, stimuli blue, figures green, headings orange, with the number_label/ref written next to each box) and saves the results to `.data/golden-overlays/<stem>.png`. **Use these overlays to check and fix your own boxes before finishing.** Iterate until every box is visually tight and correct.

## Acceptance
- 14 golden JSON files plus the schema and the two scripts. `golden_validate.py` passes.
- You opened each overlay and corrected any box that was off (say so in your report, with the number of corrections made).
- Report any page where you are unsure of a transcription in `notes` and in your final report.
