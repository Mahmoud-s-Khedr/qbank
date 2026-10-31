from collections import defaultdict
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qbank.api.pagination import paginate
from qbank.models import (
    Exam,
    ExamItem,
    ExamSection,
    ExamVersion,
    Question,
    Role,
    Stimulus,
    Subject,
    User,
)
from qbank.schemas.exams import (
    ExamDetail,
    ExamIn,
    ExamSettings,
    ExamSummary,
    ExamUpdate,
    ItemOut,
    ItemsIn,
    ItemUpdate,
    QuestionContent,
    ReorderItems,
    ReorderSections,
    SectionIn,
    SectionOut,
    SectionUpdate,
    StimulusContent,
    VersionOut,
)
from qbank.services.errors import Conflict, Invalid, NotFound
from qbank.services.exam_templates import check_exam_template
from qbank.services.scoping import get
from qbank.services.unit_of_work import found, save, update

Row = tuple[ExamItem, Question]


def exam_for(db: Session, user: User, exam_id: UUID) -> Exam:
    """The exam if it is in the caller's org and visible to them (admins see all, others own)."""
    stmt = select(Exam).where(Exam.id == exam_id, Exam.org_id == user.org_id)
    if user.role != Role.admin:
        stmt = stmt.where(Exam.owner_id == user.id)
    return found(db.scalar(stmt))


def sections_of(db: Session, exam_id: UUID) -> list[ExamSection]:
    return list(
        db.scalars(
            select(ExamSection)
            .where(ExamSection.exam_id == exam_id)
            .order_by(ExamSection.position, ExamSection.id)
        )
    )


def rows_of(db: Session, exam_id: UUID, section_id: UUID | None = None) -> list[Row]:
    stmt = (
        select(ExamItem, Question)
        .join(Question, ExamItem.question_id == Question.id)
        .where(ExamItem.exam_id == exam_id)
    )
    if section_id is not None:
        stmt = stmt.where(ExamItem.section_id == section_id)
    return [(i, q) for i, q in db.execute(stmt.order_by(ExamItem.position, ExamItem.id))]


def section_for(db: Session, exam_id: UUID, section_id: UUID) -> ExamSection:
    return found(
        db.scalar(
            select(ExamSection).where(ExamSection.id == section_id, ExamSection.exam_id == exam_id)
        )
    )


def groups_intact(rows: Sequence[Row]) -> bool:
    """Every stimulus group is one contiguous run, in stimulus_position order."""
    closed: set[UUID] = set()
    current: UUID | None = None
    last_position = -1
    for _, question in rows:
        sid = question.stimulus_id
        if sid != current:
            if current is not None:
                closed.add(current)
            if sid is not None and sid in closed:
                return False
            current, last_position = sid, -1
        if sid is not None:
            position = question.stimulus_position or 0
            if position < last_position:
                return False
            last_position = position
    return True


def place(rows: Sequence[Row], section_id: UUID) -> None:
    for index, (item, _) in enumerate(rows):
        item.section_id = section_id
        item.position = index


def touch(exam: Exam) -> None:
    exam.revision += 1


def totals(db: Session, exam_ids: Sequence[UUID]) -> dict[UUID, tuple[int, float]]:
    found_rows = db.execute(
        select(ExamItem.exam_id, func.count(), func.coalesce(func.sum(ExamItem.points), 0))
        .where(ExamItem.exam_id.in_(exam_ids))
        .group_by(ExamItem.exam_id)
    )
    return {exam_id: (int(count), float(points)) for exam_id, count, points in found_rows}


def summary(exam: Exam, totals_: dict[UUID, tuple[int, float]]) -> ExamSummary:
    count, points = totals_.get(exam.id, (0, 0.0))
    return ExamSummary(
        id=exam.id,
        created_at=exam.created_at,
        updated_at=exam.updated_at,
        title=exam.title,
        subject_id=exam.subject_id,
        owner_id=exam.owner_id,
        status=exam.status,
        revision=exam.revision,
        question_count=count,
        total_points=points,
    )


def detail(db: Session, exam: Exam) -> ExamDetail:
    rows = rows_of(db, exam.id)
    stimuli = {
        s.id: s
        for s in db.scalars(
            select(Stimulus).where(
                Stimulus.id.in_({q.stimulus_id for _, q in rows if q.stimulus_id is not None})
            )
        )
    }
    by_section: dict[UUID, list[ItemOut]] = defaultdict(list)
    shown: set[UUID] = set()
    for item, question in rows:
        stimulus = None
        sid = question.stimulus_id
        if sid is not None and sid not in shown and sid in stimuli:
            shown.add(sid)
            stimulus = StimulusContent(id=sid, kind=stimuli[sid].kind, content=stimuli[sid].content)
        by_section[item.section_id].append(
            ItemOut(
                id=item.id,
                section_id=item.section_id,
                question_id=item.question_id,
                position=item.position,
                points=item.points,
                origin=item.origin,
                question=QuestionContent.model_validate(question, from_attributes=True),
                stimulus=stimulus,
            )
        )
    versions = db.scalars(
        select(ExamVersion).where(ExamVersion.exam_id == exam.id).order_by(ExamVersion.label)
    )
    base = summary(exam, {exam.id: (len(rows), sum(i.points for i, _ in rows))})
    return ExamDetail(
        **base.model_dump(),
        settings=ExamSettings.model_validate(exam.settings),
        blueprint=exam.blueprint,
        sections=[
            SectionOut(
                id=s.id,
                title=s.title,
                position=s.position,
                instructions=s.instructions,
                items=by_section[s.id],
            )
            for s in sections_of(db, exam.id)
        ],
        versions=[
            VersionOut(
                id=v.id,
                label=v.label,
                seed=v.seed,
                exam_revision=v.exam_revision,
                stale=v.exam_revision < exam.revision,
                created_at=v.created_at,
            )
            for v in sorted(versions, key=lambda v: v.created_at)
        ],
    )


def create(db: Session, user: User, data: ExamIn) -> ExamDetail:
    subject = found(get(db, Subject, user.org_id, data.subject_id))
    settings = data.settings or ExamSettings(language=subject.language.value)
    check_exam_template(db, user.org_id, settings.template_id)
    exam = Exam(
        org_id=user.org_id,
        owner_id=user.id,
        subject_id=subject.id,
        title=data.title,
        settings=settings.model_dump(mode="json"),
        status="draft",
        revision=1,
    )
    db.add(exam)
    db.flush()
    db.add(
        ExamSection(
            exam_id=exam.id,
            title="القسم الأول" if settings.language == "ar" else "Section 1",
            position=0,
        )
    )
    save(db)
    return detail(db, exam)


def listing(
    db: Session, user: User, status: str | None, cursor: str | None, limit: int
) -> dict[str, Any]:
    stmt = select(Exam).where(Exam.org_id == user.org_id)
    if user.role != Role.admin:
        stmt = stmt.where(Exam.owner_id == user.id)
    if status is not None:
        stmt = stmt.where(Exam.status == status)
    try:
        exams, next_cursor = paginate(db, stmt, Exam, cursor, limit)
    except ValueError:
        raise Invalid("invalid_cursor") from None
    counts = totals(db, [e.id for e in exams])
    return {"items": [summary(e, counts) for e in exams], "next_cursor": next_cursor}


def edit(db: Session, user: User, exam_id: UUID, data: ExamUpdate) -> ExamDetail:
    exam = exam_for(db, user, exam_id)
    if data.settings is not None:
        check_exam_template(db, user.org_id, data.settings.template_id)
    if data.title is not None or data.settings is not None:
        touch(exam)
    if data.title is not None:
        exam.title = data.title
    if data.settings is not None:
        exam.settings = data.settings.model_dump(mode="json")
    if data.status is not None:
        exam.status = data.status
    save(db)
    return detail(db, exam)


def delete(db: Session, user: User, exam_id: UUID) -> None:
    db.delete(exam_for(db, user, exam_id))
    save(db)


def archive(db: Session, user: User, exam_id: UUID) -> ExamDetail:
    exam = exam_for(db, user, exam_id)
    exam.status = "archived"
    save(db)
    return detail(db, exam)


def duplicate(db: Session, user: User, exam_id: UUID) -> ExamDetail:
    source = exam_for(db, user, exam_id)
    copy = Exam(
        org_id=source.org_id,
        owner_id=user.id,
        subject_id=source.subject_id,
        title=f"{source.title} (copy)",
        settings=source.settings,
        blueprint=source.blueprint,
        status="draft",
        revision=1,
    )
    db.add(copy)
    db.flush()
    mapping: dict[UUID, UUID] = {}
    for section in sections_of(db, source.id):
        clone = ExamSection(
            exam_id=copy.id,
            title=section.title,
            position=section.position,
            instructions=section.instructions,
        )
        db.add(clone)
        db.flush()
        mapping[section.id] = clone.id
    for item, _ in rows_of(db, source.id):
        db.add(
            ExamItem(
                exam_id=copy.id,
                section_id=mapping[item.section_id],
                question_id=item.question_id,
                position=item.position,
                points=item.points,
                origin=item.origin,
            )
        )
    save(db)
    return detail(db, copy)


def get_detail(db: Session, user: User, exam_id: UUID) -> ExamDetail:
    return detail(db, exam_for(db, user, exam_id))


# --- sections ---------------------------------------------------------------------------------


def add_section(db: Session, user: User, exam_id: UUID, data: SectionIn) -> ExamDetail:
    exam = exam_for(db, user, exam_id)
    position = len(sections_of(db, exam.id))
    db.add(
        ExamSection(
            exam_id=exam.id, title=data.title, instructions=data.instructions, position=position
        )
    )
    touch(exam)
    save(db)
    return detail(db, exam)


def _section_exam(db: Session, user: User, section_id: UUID) -> tuple[Exam, ExamSection]:
    section = found(db.get(ExamSection, section_id))
    return exam_for(db, user, section.exam_id), section


def edit_section(db: Session, user: User, section_id: UUID, data: SectionUpdate) -> ExamDetail:
    exam, section = _section_exam(db, user, section_id)
    update(section, data)
    touch(exam)
    save(db)
    return detail(db, exam)


def delete_section(db: Session, user: User, section_id: UUID) -> ExamDetail:
    exam, section = _section_exam(db, user, section_id)
    siblings = [s for s in sections_of(db, exam.id) if s.id != section.id]
    if not siblings:
        raise Conflict("last_section")
    if rows_of(db, exam.id, section.id):
        raise Conflict("not_empty")
    db.delete(section)
    for index, sibling in enumerate(siblings):
        sibling.position = index
    touch(exam)
    save(db)
    return detail(db, exam)


def reorder_sections(db: Session, user: User, exam_id: UUID, data: ReorderSections) -> ExamDetail:
    exam = exam_for(db, user, exam_id)
    sections = {s.id: s for s in sections_of(db, exam.id)}
    if sorted(data.ids) != sorted(sections):
        raise Invalid("ids_mismatch")
    for index, section_id in enumerate(data.ids):
        sections[section_id].position = index
    touch(exam)
    save(db)
    return detail(db, exam)


# --- items ------------------------------------------------------------------------------------


def add_items(db: Session, user: User, exam_id: UUID, data: ItemsIn) -> ExamDetail:
    exam = exam_for(db, user, exam_id)
    if data.section_id is not None:
        section = section_for(db, exam.id, data.section_id)
    else:
        section = sections_of(db, exam.id)[0]
    questions = {
        q.id: q
        for q in db.scalars(
            select(Question).where(
                Question.id.in_(data.question_ids), Question.org_id == user.org_id
            )
        )
    }
    if len(questions) != len(set(data.question_ids)):
        raise NotFound("question_not_found")
    if any(q.status != "approved" for q in questions.values()):
        raise Invalid("question_not_approved")
    present = rows_of(db, exam.id)
    have = {q.id for _, q in present}
    have_stimuli = {q.stimulus_id for _, q in present if q.stimulus_id is not None}
    additions: list[Question] = []
    for question_id in data.question_ids:
        question = questions[question_id]
        if question.id in have:
            continue
        sid = question.stimulus_id
        if sid is None:
            additions.append(question)
            have.add(question.id)
        elif sid not in have_stimuli:
            group = db.scalars(
                select(Question)
                .where(
                    Question.stimulus_id == sid,
                    Question.org_id == user.org_id,
                    Question.status == "approved",
                )
                .order_by(Question.stimulus_position, Question.position, Question.id)
            )
            for member in group:
                additions.append(member)
                have.add(member.id)
            have_stimuli.add(sid)
    position = len(rows_of(db, exam.id, section.id))
    for question in additions:
        db.add(
            ExamItem(
                exam_id=exam.id,
                section_id=section.id,
                question_id=question.id,
                position=position,
                points=data.points,
                origin="manual",
            )
        )
        position += 1
    if additions:
        touch(exam)
    save(db)
    return detail(db, exam)


def _item_exam(db: Session, user: User, item_id: UUID) -> tuple[Exam, ExamItem, Question]:
    item = found(db.get(ExamItem, item_id))
    return exam_for(db, user, item.exam_id), item, found(db.get(Question, item.question_id))


def _group_rows(db: Session, exam: Exam, question: Question) -> list[Row]:
    if question.stimulus_id is None:
        return []
    return [r for r in rows_of(db, exam.id) if r[1].stimulus_id == question.stimulus_id]


def edit_item(db: Session, user: User, item_id: UUID, data: ItemUpdate) -> ExamDetail:
    exam, item, question = _item_exam(db, user, item_id)
    if data.points is not None:
        item.points = data.points
    if data.section_id is not None or data.position is not None:
        if len(_group_rows(db, exam, question)) > 1:
            raise Invalid("stimulus_group")
        origin_section = item.section_id
        target = (
            section_for(db, exam.id, data.section_id).id
            if data.section_id is not None
            else origin_section
        )
        target_rows = [r for r in rows_of(db, exam.id, target) if r[0].id != item.id]
        index = len(target_rows) if data.position is None else min(data.position, len(target_rows))
        target_rows.insert(index, (item, question))
        if not groups_intact(target_rows):
            raise Invalid("stimulus_group")
        place(target_rows, target)
        if target != origin_section:
            place(
                [r for r in rows_of(db, exam.id, origin_section) if r[0].id != item.id],
                origin_section,
            )
    touch(exam)
    save(db)
    return detail(db, exam)


def delete_item(db: Session, user: User, item_id: UUID, group: bool) -> ExamDetail:
    exam, item, question = _item_exam(db, user, item_id)
    members = _group_rows(db, exam, question)
    if len(members) > 1 and not group:
        raise Conflict("stimulus_group")
    doomed = {i.id for i, _ in members} if group and members else {item.id}
    sections = {i.section_id for i, _ in rows_of(db, exam.id) if i.id in doomed}
    for row_item, _ in rows_of(db, exam.id):
        if row_item.id in doomed:
            db.delete(row_item)
    db.flush()
    for section_id in sections:
        place(rows_of(db, exam.id, section_id), section_id)
    touch(exam)
    save(db)
    return detail(db, exam)


def reorder_items(db: Session, user: User, exam_id: UUID, data: ReorderItems) -> ExamDetail:
    exam = exam_for(db, user, exam_id)
    section = section_for(db, exam.id, data.section_id)
    current = {i.id: (i, q) for i, q in rows_of(db, exam.id, section.id)}
    if sorted(data.ids) != sorted(current):
        raise Invalid("ids_mismatch")
    ordered = [current[i] for i in data.ids]
    if not groups_intact(ordered):
        raise Invalid("stimulus_group")
    place(ordered, section.id)
    touch(exam)
    save(db)
    return detail(db, exam)
