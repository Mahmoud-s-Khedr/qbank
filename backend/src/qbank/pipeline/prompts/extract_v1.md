Transcribe this {{ language }} workbook page for {{ subject }} (grade {{ grade }}). Never invent text that is not printed. Return the requested JSON, with all fields present and null where unknown.

Classify page_kind: cover (book cover), blank (empty), toc (contents), section_divider (section title), questions (exercises), answer_key (answers), answer_sheet (blank response grid), or other. On non-question pages return empty questions and stimuli. Record answer-key entries separately.

Transcribe exactly, preserving printed tashkeel and punctuation; remove decorative tatweel and normalize whitespace. Ignore running headers and footers, page numbers, watermark logos, and side tabs, except record a chapter tab like الفصل 1 as a chapter heading. Use Western digits for number_label. Choice labels exclude circles and parentheses.

Use one poem verse per line, separating its hemistichs with ` ... `; retain printed verse numbers. Replace fill-in dots with `____`. For table-row choices use `header: cell | header: cell`. Transcribe simple tables as Markdown. Use LaTeX $...$ or $$...$$ for mathematics and \ce{} for chemistry.

Do not describe figures in text: include their boxes, including labels, in figures. A passage, poem or figure shared by questions is a stimulus; a sentence immediately above one question used only by it is also a stimulus (case for prose, poem for verse). Link questions using stimulus_ref. Mark continuation flags when an item crosses a page boundary.

All box_2d values are [ymin, xmin, ymax, xmax] integers on a 0–1000 scale relative to the image, origin top left. Boxes should tightly contain the complete item. Set each question's confidence and page_confidence from 0 to 1 to reflect transcription certainty.
