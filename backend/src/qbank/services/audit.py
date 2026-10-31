"""Question audit trail, optimistic concurrency and re-validation shared by the review services."""

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.config import get_settings
from qbank.models import Question, QuestionEvent, Source, Stimulus, User
from qbank.pipeline.dedup import dedup_question, ensure_normalized
from qbank.pipeline.validate import ValidationContext, validate_question
from qbank.schemas.bank import QuestionOut
from qbank.services.errors import Conflict, NotFound, VersionConflict

TRACKED = (
    "number_label",
    "type",
    "stem",
    "choices",
    "answer",
    "explanation",
    "chapter_id",
    "lesson_id",
    "difficulty",
    "difficulty_source",
    "tags",
    "stimulus_id",
    "stimulus_position",
    "regions",
    "status",
    "position",
)


def jsonable(value: object) -> Any:
    """A JSON-safe deep copy (UUIDs and other scalars become strings)."""
    return json.loads(json.dumps(value, default=str))


def snapshot(question: Question) -> dict[str, Any]:
    return {name: jsonable(getattr(question, name)) for name in TRACKED}


def field_diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, object]:
    """Field-level before/after of the fields that changed only."""
    return {
        name: {"before": before.get(name), "after": after.get(name)}
        for name in after
        if before.get(name) != after.get(name)
    }


def record(
    db: Session,
    question: Question,
    user: User | None,
    action: str,
    diff: dict[str, object],
) -> QuestionEvent:
    event = QuestionEvent(
        question_id=question.id, user_id=user.id if user else None, action=action, diff=diff
    )
    db.add(event)
    return event


def load_question(db: Session, org_id: UUID, question_id: UUID, *, lock: bool = False) -> Question:
    stmt = select(Question).where(Question.id == question_id, Question.org_id == org_id)
    if lock:
        stmt = stmt.with_for_update()
    question = db.scalar(stmt)
    if question is None:
        raise NotFound()
    return question


def check_version(question: Question, version: int | None) -> None:
    if version is not None and version != question.version:
        raise VersionConflict(
            extra={"current": QuestionOut.model_validate(question).model_dump(mode="json")}
        )


def require_unapproved(question: Question) -> None:
    if question.status == "approved":
        raise Conflict("question_approved")


def stimulus_intro(stimulus: Stimulus | None) -> str | None:
    if stimulus is not None and stimulus.metadata_json.get("intro") is not None:
        return str(stimulus.metadata_json["intro"])
    return None


def revalidate(db: Session, question: Question) -> None:
    """Refresh normalized text/hash, duplicate link and validation issues of one question."""
    db.flush()
    source = db.get(Source, question.source_id) if question.source_id else None
    questions: list[Question] = [question]
    stimuli: list[Stimulus] = []
    if source is not None:
        questions = list(
            db.scalars(
                select(Question)
                .where(Question.source_id == source.id)
                .order_by(Question.position, Question.id)
            )
        )
        stimuli = list(db.scalars(select(Stimulus).where(Stimulus.source_id == source.id)))
    context = ValidationContext(
        answer_key_matched=bool(source and source.pipeline_config.get("answer_key_matched")),
        questions=questions,
        stimuli=stimuli,
        stimuli_by_id={s.id: s for s in stimuli},
    )
    intro = stimulus_intro(context.stimuli_by_id.get(question.stimulus_id or UUID(int=0)))
    ensure_normalized(question, intro)
    if question.status not in ("approved", "rejected"):
        dedup_question(db, question, stimulus_intro=intro, sync_issue=False)
    validate_question(db, question, context, review_threshold=get_settings().review_threshold)
