"""Near-duplicate question detection via pg_trgm and character similarity."""

from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.orm import Session

from qbank.models import Question, Stimulus, ValidationIssue
from qbank.text.normalize import content_hash, question_normalized_text

TRGM_THRESHOLD = 0.6
CONFIRM_RATIO_THRESHOLD = 0.9


def char_similarity(a: str, b: str) -> float:
    """Compute character-level similarity ratio in [0.0, 1.0] using SequenceMatcher."""
    if a == b:
        return 1.0 if a else 0.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def ensure_normalized(question: Question, stimulus_intro: str | None = None) -> str:
    """Populate normalized_text and content_hash on a Question instance."""
    norm = question_normalized_text(question.stem, question.choices, stimulus_intro)
    question.normalized_text = norm
    question.content_hash = content_hash(norm)
    return norm


def _sync_duplicate_issue(db: Session, question: Question, ratio: float) -> None:
    """Ensure the duplicate_of ValidationIssue row matches question.duplicate_of_id."""
    existing = list(
        db.scalars(
            select(ValidationIssue).where(
                ValidationIssue.question_id == question.id,
                ValidationIssue.code == "duplicate_of",
            )
        )
    )
    if question.duplicate_of_id is None:
        for issue in existing:
            db.delete(issue)
        return
    details: dict[str, object] = {
        "duplicate_of_id": str(question.duplicate_of_id),
        "similarity": round(ratio, 4),
    }
    message = f"Question is a near-duplicate of {question.duplicate_of_id}"
    if existing:
        existing[0].severity = "warning"
        existing[0].message = message
        existing[0].details = details
        for extra in existing[1:]:
            db.delete(extra)
    else:
        db.add(
            ValidationIssue(
                question_id=question.id,
                code="duplicate_of",
                severity="warning",
                message=message,
                details=details,
            )
        )


def _is_older_clause(question: Question) -> ColumnElement[bool]:
    same_source_older = and_(
        Question.source_id == question.source_id,
        or_(
            Question.position < question.position,
            and_(Question.position == question.position, Question.id < question.id),
        ),
    )
    if question.created_at is not None:
        other_source_older = and_(
            Question.source_id != question.source_id,
            or_(
                Question.created_at < question.created_at,
                and_(Question.created_at == question.created_at, Question.id < question.id),
            ),
        )
    else:
        other_source_older = and_(
            Question.source_id != question.source_id,
            Question.id < question.id,
        )
    return or_(same_source_older, other_source_older)


def _record_duplicate_match(
    db: Session,
    question: Question,
    match_id: UUID,
    ratio: float,
    *,
    sync_issue: bool,
) -> tuple[UUID, float]:
    question.duplicate_of_id = match_id
    question.metadata_json = {
        **(question.metadata_json or {}),
        "duplicate_similarity": round(ratio, 4),
    }
    if sync_issue:
        _sync_duplicate_issue(db, question, ratio)
    return match_id, ratio


def dedup_question(
    db: Session,
    question: Question,
    *,
    stimulus_intro: str | None = None,
    sync_issue: bool = True,
) -> tuple[UUID | None, float]:
    """Find the oldest duplicate in the same org and set duplicate_of_id."""
    if not question.normalized_text or not question.content_hash:
        ensure_normalized(question, stimulus_intro)
    db.flush()

    if not question.normalized_text:
        question.duplicate_of_id = None
        if sync_issue:
            _sync_duplicate_issue(db, question, 0.0)
        return None, 0.0

    is_older = _is_older_clause(question)

    if question.content_hash:
        exact_match = db.scalar(
            select(Question.id)
            .where(
                Question.org_id == question.org_id,
                Question.id != question.id,
                Question.content_hash == question.content_hash,
                is_older,
            )
            .order_by(Question.created_at.asc(), Question.position.asc(), Question.id.asc())
            .limit(1)
        )
        if exact_match is not None:
            return _record_duplicate_match(db, question, exact_match, 1.0, sync_issue=sync_issue)

    candidates = list(
        db.scalars(
            select(Question)
            .where(
                Question.org_id == question.org_id,
                Question.id != question.id,
                is_older,
                func.similarity(Question.normalized_text, question.normalized_text)
                > TRGM_THRESHOLD,
            )
            .order_by(Question.created_at.asc(), Question.position.asc(), Question.id.asc())
        )
    )
    for candidate in candidates:
        ratio = char_similarity(question.normalized_text, candidate.normalized_text)
        if ratio >= CONFIRM_RATIO_THRESHOLD:
            return _record_duplicate_match(db, question, candidate.id, ratio, sync_issue=sync_issue)

    question.duplicate_of_id = None
    if question.metadata_json and "duplicate_similarity" in question.metadata_json:
        meta = dict(question.metadata_json)
        meta.pop("duplicate_similarity", None)
        question.metadata_json = meta
    if sync_issue:
        db.execute(
            delete(ValidationIssue).where(
                ValidationIssue.question_id == question.id,
                ValidationIssue.code == "duplicate_of",
                ValidationIssue.resolved_at.is_(None),
            )
        )
    return None, 0.0


def _stimulus_intro(stim: Stimulus | None) -> str | None:
    if stim and stim.metadata_json and stim.metadata_json.get("intro") is not None:
        return str(stim.metadata_json["intro"])
    return None


def dedup_source(
    db: Session,
    source_id: UUID,
    *,
    questions: list[Question] | None = None,
    stimuli_by_id: dict[UUID, Stimulus] | None = None,
    sync_issue: bool = True,
) -> None:
    """Run deduplication across all unreviewed questions in a source."""
    if questions is None:
        questions = list(
            db.scalars(
                select(Question)
                .where(Question.source_id == source_id)
                .order_by(Question.position.asc(), Question.id.asc())
            )
        )
    if stimuli_by_id is None:
        stimuli = list(db.scalars(select(Stimulus).where(Stimulus.source_id == source_id)))
        stimuli_by_id = {s.id: s for s in stimuli}

    for q in questions:
        stim = stimuli_by_id.get(q.stimulus_id) if q.stimulus_id else None
        ensure_normalized(q, _stimulus_intro(stim))
    db.flush()

    for q in questions:
        if q.status in ("approved", "rejected"):
            continue
        stim = stimuli_by_id.get(q.stimulus_id) if q.stimulus_id else None
        dedup_question(db, q, stimulus_intro=_stimulus_intro(stim), sync_issue=sync_issue)
