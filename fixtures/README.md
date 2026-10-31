# Fixtures

| Path | Tracked in git | Contents |
|---|---|---|
| `pdfs/` | **No** | Sample scanned workbooks used for pipeline and robustness tests |
| `golden/pages/` | **No** | 200 DPI renders of the golden pages |
| `golden/<page>.json` | **No** | Hand-verified ground truth (verbatim text + normalized boxes) used by `qbank-eval` |
| `golden/schema.json` | Yes | JSON Schema of the golden format |

The sample workbooks are commercial, copyrighted material, so they — and the golden transcriptions of
their pages — are **kept out of the public repository**. Tests that need them are skipped automatically when the files are absent.

To run the full suite locally, place these files in `fixtures/pdfs/`:

| File | Pages | Why it matters |
|---|---|---|
| `test-exams.pdf` | 72 (page tree broken from p. 61) | Full workbook: passages, poems, essays, blank OMR sheets, damaged pages |
| `test-2027.pdf` | 2 (has a syntax error) | Biology: labelled figures, table-row choices, a bar chart |
| `test1.pdf` | 1 | Identical to `test-exams.pdf` p. 28, a duplicate-detection case |
| `test2.pdf` | 1 | Identical to `test-2027.pdf` p. 1, a duplicate-detection case |

Any Arabic exam workbook with similar features works for development. Golden-set evaluation
needs the exact files.

Note: `test-exams.pdf` has a damaged page tree, and different renderers disagree on its page order
(`pdftoppm` vs PyMuPDF). Qbank and the golden renders both use PyMuPDF's order.

Validate and visualize golden files with `scripts/golden_validate.py` and `scripts/golden_overlay.py`
(`uv run --with pillow --with jsonschema python scripts/...`).
