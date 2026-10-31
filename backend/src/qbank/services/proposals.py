"""Re-extraction proposals: queue a job, diff against live rows, accept or discard."""

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qbank import llm
from qbank.config import get_settings
from qbank.db import new_uuid
from qbank.llm import (
    BudgetExceeded,
    LLMClient,
    LLMError,
    LLMNotConfigured,
    LLMOutputInvalid,
    ModelNotAllowed,
    ModelTooExpensive,
    OrgBudgetExceeded,
)
from qbank.llm.client import guard_model
from qbank.models import Job, PageProposal, Question, Source, SourcePage, Subject, User
from qbank.pipeline.extract import PROMPT_VERSION, extract_page
from qbank.pipeline.materialize import crop, normalize_blanks, pinned, render_crop
from qbank.pipeline.schema import PageExtraction, to_region_box
from qbank.pipeline.schema import Question as ExtractedQuestion
from qbank.schemas.review import (
    AcceptIn,
    AcceptOut,
    AddedItem,
    ChangedItem,
    DraftQuestion,
    ExtractRegionIn,
    FieldChange,
    PageProposalOut,
    ProposalDetail,
    ProposalDiff,
    RemovedItem,
    SkippedItem,
)
from qbank.services import sources as sources_service
from qbank.services.audit import field_diff, record, revalidate, snapshot
from qbank.services.errors import (
    BadGateway,
    Conflict,
    DomainError,
    Invalid,
    NotFound,
    PaymentRequired,
)
from qbank.services.unit_of_work import found, save
from qbank.storage import get_store, keys

ASSET_REF = re.compile(r"\n?!\[[^\]]*\]\(asset:[^)]*\)")
FIELDS = ("type", "stem", "choices", "answer", "correct_labels")


class ServiceUnavailable(DomainError):  # noqa: N818 -- domain names are part of the service API
    status = 503
    code = "llm_not_configured"


def llm_error_code(exc: Exception) -> str:
    """Stable API/job error code for a failure of the LLM layer."""
    if isinstance(exc, BudgetExceeded | OrgBudgetExceeded):
        return "budget_exceeded"
    if isinstance(exc, ModelNotAllowed):
        return "model_not_allowed"
    if isinstance(exc, ModelTooExpensive):
        return "model_too_expensive"
    if isinstance(exc, LLMOutputInvalid):
        return "llm_output_invalid"
    if isinstance(exc, LLMNotConfigured):
        return "llm_not_configured"
    return "llm_error"


def llm_domain_error(exc: LLMError) -> DomainError:
    code = llm_error_code(exc)
    if code == "budget_exceeded":
        return PaymentRequired(code)
    if code in ("model_not_allowed", "model_too_expensive"):
        return Invalid(code)
    if code == "llm_not_configured":
        return ServiceUnavailable(code)
    return BadGateway(code)


def guard(model: str | None) -> None:
    if model is None:
        return
    try:
        guard_model(get_settings(), model)
    except LLMError as exc:
        raise llm_domain_error(exc) from None


def get_client() -> LLMClient:
    return llm.get_llm_client()


def enqueue(job_id: UUID, source_id: UUID, number: int, model: str | None, user_id: UUID) -> None:
    from qbank.worker import reextract_page  # noqa: PLC0415 -- avoids a worker import cycle.

    reextract_page.send(str(job_id), str(source_id), number, model, str(user_id))


def start_reextract(
    db: Session, user: User, source_id: UUID, number: int, model: str | None
) -> UUID:
    page = sources_service.page(db, user.org_id, source_id, number)
    if page.image_key is None:
        raise Conflict("page_not_rendered")
    guard(model)
    job = Job(org_id=user.org_id, kind="reextract", status="running", ref_id=source_id)
    db.add(job)
    save(db)
    enqueue(job.id, source_id, number, model, user.id)
    return job.id


def _page_context(db: Session, source: Source) -> tuple[str, str, str | None]:
    subject = db.get(Subject, source.subject_id)
    if subject is None:
        raise ValueError("Missing subject")
    return subject.name, subject.language.value, source.grade or subject.grade


def extract_region(  # noqa: PLR0913, PLR0917 -- request context and call inputs are independent
    db: Session,
    client: LLMClient,
    user: User,
    source_id: UUID,
    number: int,
    data: ExtractRegionIn,
) -> DraftQuestion:
    source = sources_service.source(db, user.org_id, source_id)
    page = sources_service.page(db, user.org_id, source_id, number)
    if page.image_key is None:
        raise Conflict("page_not_rendered")
    guard(data.model)
    try:
        image, _, _ = render_crop(source, page, data.box, trim=False, image_format="PNG")
    except ValueError:
        raise Invalid("empty_region") from None
    subject, language, grade = _page_context(db, source)
    settings = get_settings()
    try:
        result, cost = extract_page(
            client,
            image,
            subject=subject,
            language=language,
            grade=grade,
            org_id=user.org_id,
            source_id=source.id,
            max_side=settings.extract_image_max_side,
            fallback_threshold=settings.extract_fallback_threshold,
            model_override=data.model,
        )
    except LLMError as exc:
        raise llm_domain_error(exc) from None
    db.execute(
        update(Source).where(Source.id == source.id).values(cost_usd=Source.cost_usd + float(cost))
    )
    db.commit()
    if not result.parsed.questions:
        raise Invalid("no_question_found")
    first = result.parsed.questions[0].model_copy(deep=True)
    first.stem = normalize_blanks(first.stem)
    for choice in first.choices:
        choice.content = normalize_blanks(choice.content)
    return DraftQuestion.model_validate(first.model_dump())


# --- proposals --------------------------------------------------------------------------------


def _proposal(
    db: Session, org_id: UUID, proposal_id: UUID
) -> tuple[PageProposal, SourcePage, Source]:
    row = db.execute(
        select(PageProposal, SourcePage, Source)
        .join(SourcePage, PageProposal.page_id == SourcePage.id)
        .join(Source, SourcePage.source_id == Source.id)
        .where(PageProposal.id == proposal_id, Source.org_id == org_id)
        .with_for_update(of=PageProposal)
    ).first()
    if row is None:
        raise NotFound()
    return row[0], row[1], row[2]


def _out(proposal: PageProposal, page: SourcePage) -> PageProposalOut:
    return PageProposalOut(
        id=proposal.id,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        page_id=page.id,
        source_id=page.source_id,
        page_number=page.page_number,
        model=proposal.model,
        cost_usd=float(proposal.cost_usd),
        created_by=proposal.created_by,
        status=proposal.status,
        extraction=proposal.extraction,
    )


def _strip_refs(text: str) -> str:
    return ASSET_REF.sub("", text).strip()


def _proposed(question: ExtractedQuestion) -> dict[str, Any]:
    labels = question.answer.labels if question.answer else []
    return {
        "type": question.type,
        "stem": normalize_blanks(question.stem).strip(),
        "choices": [
            {"label": c.label, "content": normalize_blanks(c.content)} for c in question.choices
        ],
        "answer": question.answer.text if question.answer else None,
        "correct_labels": sorted(labels),
    }


def _current(question: Question) -> dict[str, Any]:
    return {
        "type": question.type,
        "stem": _strip_refs(question.stem),
        "choices": [
            {"label": c.get("label"), "content": c.get("content")} for c in question.choices
        ],
        "answer": question.answer,
        "correct_labels": sorted(
            str(c.get("label")) for c in question.choices if c.get("is_correct")
        ),
    }


def _page_questions(db: Session, page: SourcePage) -> list[Question]:
    rows = db.scalars(
        select(Question)
        .where(Question.source_id == page.source_id)
        .order_by(Question.position, Question.id)
    )
    return [q for q in rows if any(r.get("page") == str(page.id) for r in q.regions)]


def compute_diff(db: Session, page: SourcePage, extraction: dict[str, object]) -> ProposalDiff:
    proposed = PageExtraction.model_validate(extraction).questions
    existing: dict[str, Question] = {}
    for live in _page_questions(db, page):
        existing.setdefault(live.number_label, live)
    changed: list[ChangedItem] = []
    added: list[AddedItem] = []
    unchanged: list[str] = []
    for item in proposed:
        question = existing.pop(item.number_label, None)
        new = _proposed(item)
        if question is None:
            added.append(AddedItem(number_label=item.number_label, question=new))
            continue
        old = _current(question)
        fields = {
            name: FieldChange(before=old[name], after=new[name])
            for name in FIELDS
            if old[name] != new[name]
        }
        if fields:
            changed.append(
                ChangedItem(
                    number_label=item.number_label,
                    question_id=question.id,
                    status=question.status,
                    fields=fields,
                )
            )
        else:
            unchanged.append(item.number_label)
    removed = [
        RemovedItem(number_label=label, question_id=q.id, status=q.status)
        for label, q in existing.items()
    ]
    return ProposalDiff(changed=changed, added=added, removed=removed, unchanged=unchanged)


def detail(db: Session, user: User, proposal_id: UUID) -> ProposalDetail:
    proposal, page, _ = _proposal(db, user.org_id, proposal_id)
    return ProposalDetail(
        proposal=_out(proposal, page), diff=compute_diff(db, page, proposal.extraction)
    )


def _choices(item: ExtractedQuestion) -> list[dict[str, object]]:
    labels = item.answer.labels if item.answer else []
    return [
        {
            "label": c.label,
            "content": normalize_blanks(c.content),
            "is_correct": c.label in labels if item.answer else None,
            "pinned": pinned(c.content),
        }
        for c in item.choices
    ]


def _apply_changed(db: Session, user: User, question: Question, item: ExtractedQuestion) -> None:
    before = snapshot(question)
    refs = ASSET_REF.findall(question.stem)
    question.type = item.type
    question.stem = normalize_blanks(item.stem) + "".join(refs)
    question.choices = _choices(item)
    question.answer = item.answer.text if item.answer else None
    question.confidence = item.confidence
    question.metadata_json = {**question.metadata_json, "model_confidence": item.confidence}
    question.version += 1
    revalidate(db, question)
    record(db, question, user, "reextract_accept", field_diff(before, snapshot(question)))


def _create_added(
    db: Session, user: User, source: Source, page: SourcePage, item: ExtractedQuestion
) -> Question:
    siblings = _page_questions(db, page)
    anchor = (
        siblings[-1].position
        if siblings
        else (
            db.scalar(
                select(Question.position)
                .where(Question.source_id == source.id)
                .order_by(Question.position.desc())
                .limit(1)
            )
            or 0
        )
    )
    db.execute(
        update(Question)
        .where(Question.source_id == source.id, Question.position > anchor)
        .values(position=Question.position + 1)
    )
    subject = found(db.get(Subject, source.subject_id))
    stem = normalize_blanks(item.stem)
    for figure in item.figures:
        stem += "\n" + crop(db, source, page, figure.box_2d)
    question = Question(
        id=new_uuid(),
        org_id=source.org_id,
        subject_id=source.subject_id,
        source_id=source.id,
        position=anchor + 1,
        number_label=item.number_label,
        type=item.type,
        stem=stem,
        choices=_choices(item),
        answer=item.answer.text if item.answer else None,
        language=subject.language,
        regions=[{"page": str(page.id), "box": to_region_box(item.box_2d)}],
        status="draft",
        confidence=item.confidence,
        version=1,
        metadata_json={"model_confidence": item.confidence, "notes": ["Added by re-extraction"]},
    )
    db.add(question)
    db.flush()
    revalidate(db, question)
    record(db, question, user, "reextract_add", field_diff({}, snapshot(question)))
    return question


def accept(db: Session, user: User, proposal_id: UUID, data: AcceptIn) -> AcceptOut:
    proposal, page, source = _proposal(db, user.org_id, proposal_id)
    if proposal.status != "pending":
        raise Conflict("proposal_not_pending")
    diff = compute_diff(db, page, proposal.extraction)
    items = {
        q.number_label: q for q in PageExtraction.model_validate(proposal.extraction).questions
    }
    known = {
        *(i.number_label for i in diff.changed),
        *(i.number_label for i in diff.added),
        *(i.number_label for i in diff.removed),
    }
    wanted = set(data.number_labels) if data.number_labels is not None else known
    applied: list[str] = []
    skipped = [
        SkippedItem(number_label=label, reason="not_in_proposal")
        for label in sorted(wanted - known)
    ]
    for entry in diff.changed:
        if entry.number_label not in wanted:
            continue
        question = found(db.get(Question, entry.question_id))
        if question.status == "approved":
            skipped.append(SkippedItem(number_label=entry.number_label, reason="approved"))
            continue
        _apply_changed(db, user, question, items[entry.number_label])
        applied.append(entry.number_label)
    for new in diff.added:
        if new.number_label in wanted:
            _create_added(db, user, source, page, items[new.number_label])
            applied.append(new.number_label)
    for gone in diff.removed:
        if gone.number_label not in wanted:
            continue
        question = found(db.get(Question, gone.question_id))
        if question.status == "approved":
            skipped.append(SkippedItem(number_label=gone.number_label, reason="approved"))
            continue
        try:
            with db.begin_nested():
                db.execute(
                    update(Question)
                    .where(Question.duplicate_of_id == question.id)
                    .values(duplicate_of_id=None)
                )
                db.delete(question)
                db.flush()
        except IntegrityError:
            skipped.append(SkippedItem(number_label=gone.number_label, reason="in_use"))
        else:
            applied.append(gone.number_label)
    if data.number_labels is None and not skipped:
        page.extraction = proposal.extraction
        page.model = proposal.model
        page.prompt_version = PROMPT_VERSION
    proposal.status = "accepted"
    save(db)
    return AcceptOut(proposal=_out(proposal, page), applied=applied, skipped=skipped)


def discard(db: Session, user: User, proposal_id: UUID) -> PageProposalOut:
    proposal, page, _ = _proposal(db, user.org_id, proposal_id)
    if proposal.status != "pending":
        raise Conflict("proposal_not_pending")
    proposal.status = "discarded"
    save(db)
    return _out(proposal, page)


# --- worker side ------------------------------------------------------------------------------


def run_reextract(  # noqa: PLR0913, PLR0917 -- job identity and call controls are independent
    db: Session,
    client: LLMClient,
    job_id: UUID,
    source_id: UUID,
    number: int,
    model: str | None,
    user_id: UUID,
) -> None:
    """Extract one page again and store the result as a pending proposal; never raises."""
    job = db.get(Job, job_id)
    source = db.get(Source, source_id)
    page = db.scalar(
        select(SourcePage).where(
            SourcePage.source_id == source_id, SourcePage.page_number == number
        )
    )
    if job is None or source is None or page is None:
        return

    def fail(code: str, cost: Decimal = Decimal(0)) -> None:
        db.rollback()
        job.status, job.error = "failed", code
        if cost:
            source.cost_usd = source.cost_usd + float(cost)
        db.commit()

    try:
        subject, language, grade = _page_context(db, source)
        settings = get_settings()
        result, cost = extract_page(
            client,
            get_store().get_bytes(keys.page(source.org_id, source.id, number, hires=True)),
            subject=subject,
            language=language,
            grade=grade,
            org_id=source.org_id,
            source_id=source.id,
            max_side=settings.extract_image_max_side,
            fallback_threshold=settings.extract_fallback_threshold,
            model_override=model,
        )
    except LLMError as exc:
        fail(
            llm_error_code(exc),
            exc.cost_usd
            if isinstance(exc, LLMOutputInvalid | BudgetExceeded | OrgBudgetExceeded)
            else Decimal(0),
        )
        return
    proposal = PageProposal(
        page_id=page.id,
        extraction=result.parsed.model_dump(mode="json"),
        model=result.model,
        cost_usd=cost,
        created_by=user_id,
        status="pending",
    )
    db.add(proposal)
    db.flush()
    job.status = "ready"
    job.progress = {"proposal_id": str(proposal.id)}
    source.cost_usd = source.cost_usd + float(cost)
    db.commit()
