import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.exams.sampler import Candidate, Row, RowResult, sample
from qbank.exams.versions import (
    ChoiceSpec,
    ItemSpec,
    KeyQuestion,
    answer_key_entry,
    build_layout,
    version_label,
)
from qbank.models import Exam, ExamItem, ExamVersion, Question, User
from qbank.schemas.exams import (
    AnswerKey,
    AnswerKeyEntry,
    Blueprint,
    BlueprintResult,
    BlueprintRowResult,
    ExamDetail,
    ExamSettings,
    VersionOut,
    VersionsIn,
)
from qbank.services import exams as exams_service
from qbank.services.errors import Invalid, NotFound
from qbank.services.unit_of_work import save

MAX_SEED = 2**31 - 1000


def _result(rows: list[RowResult], seed: int) -> BlueprintResult:
    return BlueprintResult(
        rows=[
            BlueprintRowResult(
                requested=r.requested,
                selected=r.selected,
                shortfall=r.shortfall,
                available=r.available,
            )
            for r in rows
        ],
        seed=seed,
    )


def _run(db: Session, user: User, exam: Exam, data: Blueprint) -> tuple[list[RowResult], int]:
    for blueprint_row in data.rows:
        if blueprint_row.section_id is not None:
            exams_service.section_for(db, exam.id, blueprint_row.section_id)
    seed = data.seed if data.seed is not None else secrets.randbelow(MAX_SEED)
    pool = [
        Candidate(
            id=q.id,
            chapter_id=q.chapter_id,
            lesson_id=q.lesson_id,
            type=q.type,
            difficulty=q.difficulty,
            tags=q.tags,
            stimulus_id=q.stimulus_id,
            stimulus_position=q.stimulus_position,
            duplicate_of_id=q.duplicate_of_id,
        )
        for q in db.scalars(
            select(Question).where(
                Question.org_id == user.org_id,
                Question.subject_id == exam.subject_id,
                Question.status == "approved",
            )
        )
    ]
    excluded = set(data.exclude_question_ids)
    if data.exclude_used_in_my_exams:
        excluded |= set(
            db.scalars(
                select(ExamItem.question_id)
                .join(Exam, ExamItem.exam_id == Exam.id)
                .where(Exam.owner_id == user.id, Exam.id != exam.id, Exam.status != "archived")
            )
        )
    fixed = {
        item.question_id
        for item, _ in exams_service.rows_of(db, exam.id)
        if item.origin != "blueprint"
    }
    rows = [
        Row(
            count=r.count,
            chapter_ids=r.chapter_ids,
            lesson_ids=r.lesson_ids,
            types=r.types,
            difficulty_min=r.difficulty_min,
            difficulty_max=r.difficulty_max,
            tags_any=r.tags_any,
        )
        for r in data.rows
    ]
    return sample(pool, rows, seed=seed, excluded=excluded, fixed=fixed), seed


def blueprint_preview(db: Session, user: User, exam_id: UUID, data: Blueprint) -> BlueprintResult:
    exam = exams_service.exam_for(db, user, exam_id)
    results, seed = _run(db, user, exam, data)
    return _result(results, seed)


def blueprint_apply(db: Session, user: User, exam_id: UUID, data: Blueprint) -> ExamDetail:
    exam = exams_service.exam_for(db, user, exam_id)
    results, seed = _run(db, user, exam, data)
    for item, _ in exams_service.rows_of(db, exam.id):
        if item.origin == "blueprint":
            db.delete(item)
    db.flush()
    default_section = exams_service.sections_of(db, exam.id)[0].id
    for row, result in zip(data.rows, results, strict=True):
        section_id = row.section_id or default_section
        position = len(exams_service.rows_of(db, exam.id, section_id))
        for question_id in result.selected:
            db.add(
                ExamItem(
                    exam_id=exam.id,
                    section_id=section_id,
                    question_id=question_id,
                    position=position,
                    points=row.points,
                    origin="blueprint",
                )
            )
            position += 1
        db.flush()
    exam.blueprint = data.model_copy(update={"seed": seed}).model_dump(mode="json")
    exams_service.touch(exam)
    save(db)
    return exams_service.detail(db, exam)


def _language(exam: Exam) -> str:
    return ExamSettings.model_validate(exam.settings).language


def generate_versions(db: Session, user: User, exam_id: UUID, data: VersionsIn) -> list[VersionOut]:
    exam = exams_service.exam_for(db, user, exam_id)
    rows = exams_service.rows_of(db, exam.id)
    if not rows:
        raise Invalid("exam_empty")
    language = _language(exam)
    sections = [
        (
            section.id,
            [
                ItemSpec(
                    item_id=item.id,
                    question_id=question.id,
                    type=question.type,
                    points=item.points,
                    stimulus_id=question.stimulus_id,
                    choices=[ChoiceSpec(pinned=bool(c.get("pinned"))) for c in question.choices],
                )
                for item, question in rows
                if item.section_id == section.id
            ],
        )
        for section in exams_service.sections_of(db, exam.id)
    ]
    base = data.seed if data.seed is not None else secrets.randbelow(MAX_SEED)
    for old in db.scalars(select(ExamVersion).where(ExamVersion.exam_id == exam.id)):
        db.delete(old)
    db.flush()
    created: list[ExamVersion] = []
    for index in range(data.count):
        original = data.keep_first_as_original and index == 0
        version = ExamVersion(
            exam_id=exam.id,
            label=version_label(language, index),
            seed=base + index,
            exam_revision=exam.revision,
            layout=build_layout(
                sections,
                seed=base + index,
                shuffle_questions=data.shuffle_questions and not original,
                shuffle_choices=data.shuffle_choices and not original,
            ),
        )
        db.add(version)
        created.append(version)
    save(db)
    return [
        VersionOut(
            id=v.id,
            label=v.label,
            seed=v.seed,
            exam_revision=v.exam_revision,
            stale=v.exam_revision < exam.revision,
            created_at=v.created_at,
        )
        for v in created
    ]


def answer_key(db: Session, user: User, exam_id: UUID, label: str) -> AnswerKey:
    exam = exams_service.exam_for(db, user, exam_id)
    version = db.scalar(
        select(ExamVersion).where(ExamVersion.exam_id == exam.id, ExamVersion.label == label)
    )
    if version is None:
        raise NotFound()
    language = _language(exam)
    layout_items: list[dict[str, object]] = [
        item
        for section in version.layout["sections"]  # type: ignore[attr-defined]  # JSONB is untyped
        for item in section["items"]
    ]
    questions = {
        q.id: q
        for q in db.scalars(
            select(Question).where(
                Question.id.in_([UUID(str(i["question_id"])) for i in layout_items])
            )
        )
    }
    entries: list[AnswerKeyEntry] = []
    warnings: list[str] = []
    for layout_item in sorted(layout_items, key=lambda i: int(str(i["number"]))):
        question = questions.get(UUID(str(layout_item["question_id"])))
        if question is None:
            continue
        entry, warning = answer_key_entry(
            layout_item,
            KeyQuestion(
                type=question.type,
                correct_flags=[c.get("is_correct") for c in question.choices],  # type: ignore[misc]
                answer_text=question.answer,
            ),
            language,
        )
        entries.append(AnswerKeyEntry.model_validate(entry))
        if warning:
            warnings.append(warning)
    return AnswerKey(label=version.label, items=entries, warnings=warnings)
