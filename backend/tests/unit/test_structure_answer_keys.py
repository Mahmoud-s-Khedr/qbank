"""Deterministic structure and answer-key behavior."""

from unittest.mock import MagicMock
from uuid import uuid4

from qbank.llm import BudgetExceeded
from qbank.models import Chapter, Lesson, Question, Source, SourcePage
from qbank.pipeline.answer_keys import answer_keys_source
from qbank.pipeline.structure import PlanItem, StructurePlan, headings, match, structure_source
from qbank.pipeline.validate import ValidationContext, missing_answer


def extraction(
    kind: str, headings_data: list[dict[str, object]], entries: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "page_kind": kind,
        "headings": headings_data,
        "stimuli": [],
        "questions": [],
        "answer_key_entries": entries,
        "page_confidence": 1,
        "notes": "",
    }


def heading(level: str, text: str, y: int) -> dict[str, object]:
    return {"level": level, "text": text, "box_2d": [y, 0, y + 10, 100]}


def test_heading_dedup_and_fuzzy_match() -> None:
    pages = [
        SourcePage(
            page_number=1,
            extraction=extraction("questions", [heading("chapter", "الأحياء", 0)], []),
        ),
        SourcePage(
            page_number=2,
            extraction=extraction(
                "questions", [heading("chapter", "الأحياء", 0), heading("lesson", "درس", 500)], []
            ),
        ),
    ]
    assert [item[1] for item in headings(pages)] == ["chapter", "lesson"]
    node = Chapter(title="الاحياء")
    assert match("الأحياء", [node]) is node


def test_structure_midpage_and_human() -> None:
    page_id, chapter_id = uuid4(), uuid4()
    page = SourcePage(
        id=page_id,
        page_number=1,
        extraction=extraction(
            "questions",
            [
                heading("chapter", "Chapter", 0),
                heading("lesson", "Lesson", 500),
                heading("exam", "Exam", 100),
            ],
            [],
        ),
    )
    chapter = Chapter(id=chapter_id, title="Chapter", position=1)
    old = Question(
        regions=[{"page": str(page_id), "box": [0, 0.2, 1, 0.3]}],
        metadata_json={},
        taxonomy_source="human",
        chapter_id=chapter_id,
    )
    new = Question(regions=[{"page": str(page_id), "box": [0, 0.8, 1, 0.9]}], metadata_json={})
    db = MagicMock()
    db.scalars.side_effect = [[page], [chapter], [], [old, new]]
    # Give newly created lessons an ID just as a real session flush does.
    db.add.side_effect = lambda item: setattr(item, "id", uuid4())
    source = Source(id=uuid4(), org_id=uuid4(), subject_id=uuid4())
    structure_source(db, source)
    assert old.taxonomy_source == "human"
    assert old.lesson_id is None
    assert new.chapter_id == chapter_id
    assert new.lesson_id is not None
    assert new.metadata_json["exam_title"] == "Exam"


def test_answer_key_matching_and_validation() -> None:
    entries: list[dict[str, object]] = [
        {"section": "Exam A", "number_label": "1", "labels": ["b"], "text": None},
        {"section": None, "number_label": "2", "labels": ["a"], "text": None},
        {"section": None, "number_label": "9", "labels": ["a"], "text": None},
    ]
    page = SourcePage(page_number=1, extraction=extraction("answer_key", [], entries))
    choices = [{"label": "a", "is_correct": False}, {"label": "b", "is_correct": False}]
    q = Question(
        number_label="1", type="mcq_single", choices=choices, metadata_json={"exam_title": "Exam A"}
    )
    other = Question(
        number_label="1", type="mcq_single", choices=choices, metadata_json={"exam_title": "Exam B"}
    )
    human = Question(
        number_label="2",
        type="mcq_single",
        choices=choices,
        metadata_json={},
        answer_source="human",
    )
    db = MagicMock()
    db.scalars.side_effect = [[page], [q, other, human]]
    source = Source(id=uuid4(), metadata_json={}, pipeline_config={})
    answer_keys_source(db, source)
    assert q.choices[1]["is_correct"] is True
    assert human.choices == choices
    assert source.metadata_json["answer_key"] == {"entries": 3, "matched": 2, "unmatched": 1}
    assert missing_answer(other, ValidationContext(answer_key_matched=True))[0].severity == "error"


def test_llm_plan_maps_existing_nodes() -> None:
    page_id, chapter_id, lesson_id = uuid4(), uuid4(), uuid4()
    page = SourcePage(
        id=page_id,
        page_number=1,
        extraction=extraction(
            "questions",
            [
                heading("chapter", "Chapter", 0),
                heading("lesson", "Lesson", 100),
                heading("exam", "Exam", 200),
                heading("section", "Section", 300),
            ],
            [],
        ),
    )
    chapter = Chapter(id=chapter_id, title="Different chapter title", position=1)
    lesson = Lesson(id=lesson_id, chapter_id=chapter_id, title="Different lesson title", position=1)
    question = Question(regions=[{"page": str(page_id), "box": [0, 0.8, 1, 0.9]}], metadata_json={})
    client = MagicMock()
    client.complete_json.return_value.parsed = StructurePlan(
        items=[
            PlanItem(kind="chapter", title="Chapter", start_page=1, existing_id=chapter_id),
            PlanItem(kind="lesson", title="Lesson", start_page=1, existing_id=lesson_id),
        ]
    )
    db = MagicMock()
    db.scalars.side_effect = [[page], [chapter], [lesson], [question]]
    structure_source(db, Source(id=uuid4(), org_id=uuid4(), subject_id=uuid4()), client)
    assert question.chapter_id == chapter_id
    assert question.lesson_id == lesson_id
    db.add.assert_not_called()
    client.complete_json.assert_called_once()


def test_ambiguous_number_stays_unmatched() -> None:
    entry: dict[str, object] = {"section": None, "number_label": "1", "labels": ["a"], "text": None}
    page = SourcePage(page_number=1, extraction=extraction("answer_key", [], [entry]))
    first = Question(number_label="1", choices=[], metadata_json={})
    second = Question(number_label="1", choices=[], metadata_json={})
    db = MagicMock()
    db.scalars.side_effect = [[page], [first, second]]
    source = Source(id=uuid4(), metadata_json={}, pipeline_config={})
    answer_keys_source(db, source)
    assert source.metadata_json["answer_key"] == {"entries": 1, "matched": 0, "unmatched": 1}
    assert first.answer_source is None
    assert second.answer_source is None


def test_budget_error_uses_fallback() -> None:
    page_id, chapter_id = uuid4(), uuid4()
    page = SourcePage(
        id=page_id,
        page_number=1,
        extraction=extraction(
            "questions",
            [
                heading("chapter", "Chapter", 0),
                heading("exam", "Exam", 100),
                heading("section", "Section", 200),
                heading("book", "Book", 300),
            ],
            [],
        ),
    )
    chapter = Chapter(id=chapter_id, title="Chapter", position=1)
    question = Question(regions=[{"page": str(page_id), "box": [0, 0.8, 1, 0.9]}], metadata_json={})
    db = MagicMock()
    db.scalars.side_effect = [[page], [chapter], [], [question]]
    client = MagicMock()
    client.complete_json.side_effect = BudgetExceeded()
    structure_source(db, Source(id=uuid4(), org_id=uuid4(), subject_id=uuid4()), client)
    assert question.chapter_id == chapter_id
    assert question.taxonomy_source == "ai"
