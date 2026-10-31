"""Question review: edit, status transitions, split/merge, bulk actions, issues, queue."""

import copy
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from qbank.models import (
    Asset,
    Chapter,
    Lesson,
    Question,
    QuestionEvent,
    Role,
    Source,
    SourcePage,
    Stimulus,
    Subject,
    User,
    ValidationIssue,
)
from qbank.pipeline.materialize import normalize_blanks, pinned
from qbank.pipeline.validate import get_model_confidence
from qbank.schemas.review import (
    ApproveIn,
    BulkIn,
    BulkOut,
    BulkResult,
    ChoiceIn,
    ChoiceSplit,
    QuestionCreate,
    QuestionPatch,
    QueueItem,
    QueueTotals,
    ReviewQueue,
    SplitIn,
    StemSplit,
)
from qbank.services.audit import (
    check_version,
    field_diff,
    load_question,
    record,
    require_unapproved,
    revalidate,
    snapshot,
)
from qbank.services.errors import Conflict, DomainError, Forbidden, Invalid, NotFound
from qbank.services.scoping import get
from qbank.services.unit_of_work import found, save

ASSET_REF = re.compile(r"asset:([0-9a-fA-F-]{36})")
DELETABLE = ("draft", "needs_review", "rejected")
SEVERITIES = ("error", "warning")


class UnresolvedErrors(Invalid):
    code = "unresolved_errors"


def _choices(items: Sequence[ChoiceIn]) -> list[dict[str, object]]:
    return [
        {
            "label": item.label,
            "content": normalize_blanks(item.content),
            "is_correct": item.is_correct,
            "pinned": pinned(item.content) if item.pinned is None else item.pinned,
        }
        for item in items
    ]


def _tags(tags: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))


def _texts(question: Question) -> str:
    return " ".join(
        [
            question.stem,
            question.explanation or "",
            *(str(choice.get("content", "")) for choice in question.choices),
        ]
    )


def _check_assets_impl(db: Session, question: Question, before_text: str) -> None:
    new_refs = set(ASSET_REF.findall(_texts(question))) - set(ASSET_REF.findall(before_text))
    for ref in new_refs:
        try:
            asset_id = UUID(ref)
        except ValueError:
            raise Invalid("unknown_asset") from None
        owned = db.scalar(
            select(Asset.id).where(Asset.id == asset_id, Asset.org_id == question.org_id)
        )
        if owned is None:
            raise Invalid("unknown_asset")


def _check_regions(regions: list[dict[str, object]]) -> None:
    for region in regions:
        box = region.get("box")
        if (
            not isinstance(region.get("page"), str)
            or not isinstance(box, list)
            or len(box) != len((0, 0, 0, 0))
            or not all(isinstance(v, int | float) for v in box)
        ):
            raise Invalid("invalid_regions")


def _check_taxonomy_impl(db: Session, question: Question, *, chapter_given: bool) -> None:
    chapter = lesson = None
    if question.lesson_id is not None:
        lesson = found_or_invalid(get(db, Lesson, question.org_id, question.lesson_id))
        if question.chapter_id is None or not chapter_given:
            question.chapter_id = lesson.chapter_id
        elif lesson.chapter_id != question.chapter_id:
            raise Invalid("lesson_chapter_mismatch")
    if question.chapter_id is not None:
        chapter = found_or_invalid(get(db, Chapter, question.org_id, question.chapter_id))
        if chapter.subject_id != question.subject_id:
            raise Invalid("chapter_subject_mismatch")


def found_or_invalid[T](value: T | None) -> T:
    if value is None:
        raise Invalid("unknown_reference")
    return value


def _check_stimulus_impl(db: Session, question: Question) -> None:
    if question.stimulus_id is None:
        return
    stimulus = db.scalar(
        select(Stimulus).where(
            Stimulus.id == question.stimulus_id, Stimulus.org_id == question.org_id
        )
    )
    if stimulus is None or stimulus.source_id != question.source_id:
        raise Invalid("invalid_stimulus")


def _check_assets(db: Session, question: Question, before_text: str) -> None:
    with db.no_autoflush:  # unvalidated ids must not reach the database
        _check_assets_impl(db, question, before_text)


def _check_taxonomy(db: Session, question: Question, *, chapter_given: bool) -> None:
    with db.no_autoflush:
        _check_taxonomy_impl(db, question, chapter_given=chapter_given)


def _check_stimulus(db: Session, question: Question) -> None:
    with db.no_autoflush:
        _check_stimulus_impl(db, question)


def get_visible(db: Session, user: User, question_id: UUID) -> Question:
    """Teachers only see approved questions; everyone is limited to their organization."""
    question = load_question(db, user.org_id, question_id)
    if user.role == Role.teacher and question.status != "approved":
        raise NotFound()
    return question


def create(db: Session, user: User, data: QuestionCreate) -> Question:
    subject = found(get(db, Subject, user.org_id, data.subject_id))
    question = Question(
        org_id=user.org_id,
        subject_id=subject.id,
        source_id=None,
        chapter_id=data.chapter_id,
        lesson_id=data.lesson_id,
        position=0,
        number_label=data.number_label,
        type=data.type,
        stem=normalize_blanks(data.stem),
        choices=_choices(data.choices),
        answer=data.answer,
        explanation=data.explanation,
        difficulty=data.difficulty,
        difficulty_source="human" if data.difficulty is not None else None,
        language=subject.language,
        tags=_tags(data.tags),
        regions=[],
        status="draft",
        confidence=1.0,
        version=1,
        metadata_json={"model_confidence": 1.0, "manual": True},
    )
    _check_taxonomy(db, question, chapter_given=data.chapter_id is not None)
    db.add(question)
    db.flush()
    _check_assets(db, question, "")
    revalidate(db, question)
    after = snapshot(question)
    record(db, question, user, "create", field_diff({}, after))
    save(db)
    return question


def patch(db: Session, user: User, question_id: UUID, data: QuestionPatch) -> Question:
    question = load_question(db, user.org_id, question_id, lock=True)
    check_version(question, data.version)
    before, before_text = snapshot(question), _texts(question)
    fields = data.model_fields_set - {"version"}
    if "stem" in fields and data.stem is not None:
        question.stem = normalize_blanks(data.stem)
    if "choices" in fields and data.choices is not None:
        question.choices = _choices(data.choices)
    if "regions" in fields and data.regions is not None:
        _check_regions(data.regions)
        question.regions = data.regions
    if "tags" in fields and data.tags is not None:
        question.tags = _tags(data.tags)
    if "difficulty" in fields:
        question.difficulty = data.difficulty
        question.difficulty_source = "human" if data.difficulty is not None else None
    for name in (
        "answer",
        "explanation",
        "type",
        "number_label",
        "chapter_id",
        "lesson_id",
        "stimulus_id",
        "stimulus_position",
    ):
        if name in fields:
            setattr(question, name, getattr(data, name))
    if fields & {"chapter_id", "lesson_id"}:
        _check_taxonomy(db, question, chapter_given="chapter_id" in fields)
    if "stimulus_id" in fields:
        _check_stimulus(db, question)
    _check_assets(db, question, before_text)
    question.version += 1
    revalidate(db, question)
    diff = field_diff(before, snapshot(question))
    record(db, question, user, "update", diff)
    save(db)
    return question


def _transition(  # noqa: PLR0913, PLR0917 -- one audited status change with its context
    db: Session,
    user: User,
    question: Question,
    status: str,
    action: str,
    extra: dict[str, object] | None = None,
) -> None:
    before = snapshot(question)
    question.status = status
    question.version += 1
    diff = field_diff(before, snapshot(question))
    diff.update({name: {"before": None, "after": value} for name, value in (extra or {}).items()})
    record(db, user=user, question=question, action=action, diff=diff)


def _unresolved_errors(db: Session, question_id: UUID) -> list[ValidationIssue]:
    return list(
        db.scalars(
            select(ValidationIssue).where(
                ValidationIssue.question_id == question_id,
                ValidationIssue.severity == "error",
                ValidationIssue.resolved_at.is_(None),
            )
        )
    )


def approve_one(db: Session, user: User, question: Question, data: ApproveIn) -> None:
    check_version(question, data.version)
    if data.force and user.role != Role.admin:
        raise Forbidden()
    if question.status not in ("draft", "needs_review"):
        raise Conflict("invalid_transition")
    errors = _unresolved_errors(db, question.id)
    extra: dict[str, object] = {}
    if errors:
        if not data.force:
            raise UnresolvedErrors(extra={"issues": [issue.code for issue in errors]})
        extra = {"forced": True, "overridden_issues": [issue.code for issue in errors]}
    _transition(db, user, question, "approved", "approve", extra)


def reject_one(
    db: Session, user: User, question: Question, reason: str | None, version: int | None
) -> None:
    check_version(question, version)
    if question.status not in ("draft", "needs_review", "approved"):
        raise Conflict("invalid_transition")
    _transition(db, user, question, "rejected", "reject", {"reason": reason} if reason else None)


def reopen_one(db: Session, user: User, question: Question, version: int | None) -> None:
    check_version(question, version)
    if question.status not in ("approved", "rejected"):
        raise Conflict("invalid_transition")
    _transition(db, user, question, "needs_review", "reopen")


def change_status(db: Session, user: User, question_id: UUID, action: str, data: Any) -> Question:
    question = load_question(db, user.org_id, question_id, lock=True)
    if action == "approve":
        approve_one(db, user, question, data)
    elif action == "reject":
        reject_one(db, user, question, data.reason, data.version)
    else:
        reopen_one(db, user, question, data.version)
    save(db)
    return question


def set_metadata_one(db: Session, user: User, question: Question, data: BulkIn) -> None:
    metadata = data.metadata
    if metadata is None:
        raise Invalid()
    before = snapshot(question)
    fields = metadata.model_fields_set
    if fields & {"chapter_id", "lesson_id"}:
        if "chapter_id" in fields:
            question.chapter_id = metadata.chapter_id
        if "lesson_id" in fields:
            question.lesson_id = metadata.lesson_id
        _check_taxonomy(db, question, chapter_given="chapter_id" in fields)
    if "difficulty" in fields:
        question.difficulty = metadata.difficulty
        question.difficulty_source = "human" if metadata.difficulty is not None else None
    if metadata.tags_add or metadata.tags_remove:
        removed = set(metadata.tags_remove)
        question.tags = [t for t in _tags([*question.tags, *metadata.tags_add]) if t not in removed]
    diff = field_diff(before, snapshot(question))
    if diff:
        question.version += 1
        record(db, question, user, "set_metadata", diff)


def bulk(db: Session, user: User, data: BulkIn) -> BulkOut:
    results: list[BulkResult] = []
    for question_id in dict.fromkeys(data.ids):
        try:
            with db.begin_nested():
                question = load_question(db, user.org_id, question_id, lock=True)
                if data.action == "approve":
                    approve_one(db, user, question, ApproveIn())
                elif data.action == "reject":
                    reject_one(db, user, question, data.reason, None)
                else:
                    set_metadata_one(db, user, question, data)
                db.flush()
        except DomainError as exc:
            results.append(BulkResult(id=question_id, ok=False, code=exc.code))
        else:
            results.append(
                BulkResult(
                    id=question_id, ok=True, status=question.status, version=question.version
                )
            )
    save(db)
    ok = sum(1 for result in results if result.ok)
    return BulkOut(results=results, succeeded=ok, failed=len(results) - ok)


def _issue(db: Session, user: User, issue_id: UUID) -> tuple[ValidationIssue, Question]:
    row = db.execute(
        select(ValidationIssue, Question)
        .join(Question, ValidationIssue.question_id == Question.id)
        .where(ValidationIssue.id == issue_id, Question.org_id == user.org_id)
    ).first()
    if row is None:
        raise NotFound()
    return row[0], row[1]


def set_issue_resolved(
    db: Session, user: User, issue_id: UUID, *, resolved: bool
) -> ValidationIssue:
    issue, question = _issue(db, user, issue_id)
    if (issue.resolved_at is not None) == resolved:
        return issue
    issue.resolved_at = datetime.now(UTC) if resolved else None
    issue.resolved_by = user.id if resolved else None
    record(
        db,
        question,
        user,
        "issue_resolve" if resolved else "issue_unresolve",
        {f"issue:{issue.code}": {"before": not resolved, "after": resolved}},
    )
    save(db)
    return issue


def delete_question(db: Session, user: User, question_id: UUID) -> None:
    question = load_question(db, user.org_id, question_id, lock=True)
    if question.status not in DELETABLE:
        raise Conflict("question_not_deletable")
    _unlink_duplicates(db, [question.id])
    db.delete(question)
    save(db)


def _unlink_duplicates(db: Session, ids: list[UUID]) -> None:
    db.execute(
        update(Question).where(Question.duplicate_of_id.in_(ids)).values(duplicate_of_id=None)
    )


def _shift_positions(db: Session, source_id: UUID | None, after: int) -> None:
    if source_id is not None:
        db.execute(
            update(Question)
            .where(Question.source_id == source_id, Question.position > after)
            .values(position=Question.position + 1)
        )


def split(db: Session, user: User, question_id: UUID, data: SplitIn) -> tuple[Question, Question]:
    question = load_question(db, user.org_id, question_id, lock=True)
    require_unapproved(question)
    before = snapshot(question)
    choices = copy.deepcopy(question.choices)
    stem = question.stem
    first: tuple[str, list[dict[str, object]], str | None]
    second: tuple[str, list[dict[str, object]], str | None]
    if isinstance(data.at, StemSplit):
        if not 0 < data.at.offset < len(stem):
            raise Invalid("invalid_split_point")
        first = (stem[: data.at.offset].rstrip(), [], None)
        second = (stem[data.at.offset :].lstrip(), choices, question.answer)
    elif isinstance(data.at, ChoiceSplit):
        if not 0 < data.at.choice_index < len(choices):
            raise Invalid("invalid_split_point")
        first = (stem, choices[: data.at.choice_index], question.answer)
        second = ("", choices[data.at.choice_index :], None)
    else:  # pragma: no cover -- the union is exhausted above
        raise Invalid()
    sibling = Question(
        org_id=question.org_id,
        subject_id=question.subject_id,
        source_id=question.source_id,
        chapter_id=question.chapter_id,
        lesson_id=question.lesson_id,
        stimulus_id=question.stimulus_id,
        stimulus_position=question.stimulus_position,
        position=question.position + 1,
        number_label=data.number_label or question.number_label + "b",
        type=question.type,
        stem=second[0],
        choices=second[1],
        answer=second[2],
        difficulty=question.difficulty,
        difficulty_source=question.difficulty_source,
        language=question.language,
        tags=list(question.tags),
        regions=copy.deepcopy(question.regions),
        status="needs_review",
        confidence=get_model_confidence(question),
        version=1,
        metadata_json={
            "model_confidence": get_model_confidence(question),
            "split_from": str(question.id),
        },
    )
    _shift_positions(db, question.source_id, question.position)
    db.add(sibling)
    question.stem, question.choices, question.answer = first
    question.version += 1
    db.flush()
    revalidate(db, question)
    revalidate(db, sibling)
    record(
        db,
        question,
        user,
        "split",
        {
            **field_diff(before, snapshot(question)),
            "split_into": {"before": None, "after": str(sibling.id)},
        },
    )
    record(
        db,
        sibling,
        user,
        "split_create",
        {
            **field_diff({}, snapshot(sibling)),
            "split_from": {"before": None, "after": str(question.id)},
        },
    )
    save(db)
    return question, sibling


def merge(db: Session, user: User, ids: list[UUID]) -> Question:
    if len(set(ids)) != len(ids):
        raise Invalid("duplicate_ids")
    first = load_question(db, user.org_id, ids[0], lock=True)
    second = load_question(db, user.org_id, ids[1], lock=True)
    if first.source_id is None or first.source_id != second.source_id:
        raise Invalid("different_sources")
    if (first.position, first.id) >= (second.position, second.id):
        raise Invalid("not_ordered")
    require_unapproved(first)
    require_unapproved(second)
    before = snapshot(first)
    removed = snapshot(second)
    first.stem = f"{first.stem}\n{second.stem}".strip()
    first.choices = [*first.choices, *copy.deepcopy(second.choices)]
    first.answer = first.answer or second.answer
    first.explanation = first.explanation or second.explanation
    first.stimulus_id = first.stimulus_id or second.stimulus_id
    first.regions = [*first.regions, *(r for r in second.regions if r not in first.regions)]
    first.tags = _tags([*first.tags, *second.tags])
    first.version += 1
    db.execute(
        update(QuestionEvent)
        .where(QuestionEvent.question_id == second.id)
        .values(question_id=first.id)
    )
    _unlink_duplicates(db, [second.id])
    db.delete(second)
    db.flush()
    revalidate(db, first)
    record(
        db,
        first,
        user,
        "merge",
        {**field_diff(before, snapshot(first)), "merged_from": {"before": None, "after": removed}},
    )
    save(db)
    return first


def history(db: Session, user: User, question_id: UUID) -> list[QuestionEvent]:
    question = get_visible(db, user, question_id)
    return list(
        db.scalars(
            select(QuestionEvent)
            .where(QuestionEvent.question_id == question.id)
            .order_by(QuestionEvent.created_at, QuestionEvent.id)
        )
    )


def review_queue(  # noqa: PLR0913, PLR0917 -- independent query filters
    db: Session,
    user: User,
    source_id: UUID,
    status: str | None,
    severity: str | None,
    page: int | None,
    sort: str,
) -> ReviewQueue:
    found(db.scalar(select(Source.id).where(Source.id == source_id, Source.org_id == user.org_id)))
    pages = {
        str(page_id): number
        for page_id, number in db.execute(
            select(SourcePage.id, SourcePage.page_number).where(SourcePage.source_id == source_id)
        )
    }
    stmt = select(Question).where(Question.source_id == source_id, Question.org_id == user.org_id)
    if user.role == Role.teacher:
        stmt = stmt.where(Question.status == "approved")
    if status:
        stmt = stmt.where(Question.status == status)
    items: list[QueueItem] = []
    for question in db.scalars(stmt):
        counts = dict.fromkeys(SEVERITIES, 0)
        for issue in question.issues:
            if issue.resolved_at is None and issue.severity in counts:
                counts[issue.severity] += 1
        first_page = str(question.regions[0].get("page")) if question.regions else None
        number = pages.get(first_page) if first_page else None
        if page is not None and number != page:
            continue
        if severity and not counts.get(severity):
            continue
        items.append(
            QueueItem(
                id=question.id,
                number_label=question.number_label,
                position=question.position,
                page=number,
                status=question.status,
                confidence=question.confidence,
                issues=counts,
            )
        )
    items.sort(key=lambda i: _sort_key(i, sort))
    by_status: dict[str, int] = {}
    by_severity = dict.fromkeys(SEVERITIES, 0)
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
        for name, count in item.issues.items():
            by_severity[name] += count
    return ReviewQueue(
        items=items,
        totals=QueueTotals(count=len(items), by_status=by_status, by_severity=by_severity),
    )


def _sort_key(item: QueueItem, sort: str) -> tuple[Any, ...]:
    page = item.page if item.page is not None else 10**9
    tail = (item.position, str(item.id))
    if sort == "severity":
        return (-item.issues["error"], -item.issues["warning"], page, *tail)
    if sort == "confidence":
        return (item.confidence, page, *tail)
    return (page, *tail)
