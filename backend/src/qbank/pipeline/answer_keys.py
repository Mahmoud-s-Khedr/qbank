"""Match extracted answer keys to questions from the same source."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.models import Question, Source, SourcePage
from qbank.pipeline.schema import PageExtraction
from qbank.text.normalize import normalize_ar


def answer_keys_source(db: Session, source: Source) -> None:
    pages = db.scalars(
        select(SourcePage).where(SourcePage.source_id == source.id).order_by(SourcePage.page_number)
    )
    entries = []
    for page in pages:
        if page.extraction:
            extraction = PageExtraction.model_validate(page.extraction)
            if extraction.page_kind == "answer_key":
                entries.extend(extraction.answer_key_entries)
    questions = list(db.scalars(select(Question).where(Question.source_id == source.id)))
    matched = 0
    for entry in entries:
        candidates = [
            q for q in questions if normalize_ar(q.number_label) == normalize_ar(entry.number_label)
        ]
        if entry.section:
            section = [
                q
                for q in candidates
                if normalize_ar(str((q.metadata_json or {}).get("exam_title", "")))
                == normalize_ar(entry.section)
                or normalize_ar(str((q.metadata_json or {}).get("section", "")))
                == normalize_ar(entry.section)
            ]
            if section:
                candidates = section
        if len(candidates) != 1:
            continue
        q = candidates[0]
        matched += 1
        if q.answer_source == "human":
            continue
        if q.type in ("mcq_single", "mcq_multi"):
            labels = {normalize_ar(label) for label in entry.labels}
            q.choices = [
                {**choice, "is_correct": normalize_ar(str(choice.get("label", ""))) in labels}
                for choice in q.choices
            ]
        else:
            q.answer = entry.text or (", ".join(entry.labels) if entry.labels else None)
        q.answer_source = "key"
    source.metadata_json = {
        **(source.metadata_json or {}),
        "answer_key": {
            "entries": len(entries),
            "matched": matched,
            "unmatched": len(entries) - matched,
        },
    }
    source.pipeline_config = {**(source.pipeline_config or {}), "answer_key_matched": matched > 0}
