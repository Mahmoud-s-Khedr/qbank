"""AI-assisted composition. The model sees references, never writable question IDs."""

import json
import logging
from collections import Counter
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qbank.exams.sampler import Candidate, Row, clusters, matches, sample
from qbank.llm import BudgetExceeded, LLMOutputInvalid, OrgBudgetExceeded, get_llm_client
from qbank.models import Chapter, Exam, ExamItem, ExamProposal, ExamSection, Lesson, Question, User
from qbank.schemas.exams import (
    BlueprintRow,
    ComposeIn,
    ComposePlan,
    ComposeSection,
    ComposeSelection,
    ExamDetail,
    ExamProposalOut,
    ExamSettings,
    ProposalApply,
)
from qbank.services import exams
from qbank.services.errors import BadGateway, Conflict, Invalid, PaymentRequired
from qbank.services.unit_of_work import found, save

logger = logging.getLogger(__name__)
MAX_CANDIDATES = 120
MAX_CANDIDATE_BYTES = 6000


class StoredSelection(BaseModel):
    rows: list[list[UUID]]
    warnings: list[str]


def _candidate(q: Question) -> Candidate:
    return Candidate(
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


def _row(row: BlueprintRow) -> Row:
    return Row(
        count=row.count,
        chapter_ids=row.chapter_ids,
        lesson_ids=row.lesson_ids,
        types=row.types,
        difficulty_min=row.difficulty_min,
        difficulty_max=row.difficulty_max,
        tags_any=row.tags_any,
    )


def _out(p: ExamProposal) -> ExamProposalOut:
    stored = StoredSelection.model_validate(p.selection)
    return ExamProposalOut(
        proposal_id=p.id,
        blueprint=ComposePlan.model_validate(p.plan),
        selection=stored.rows,
        rationale=p.rationale,
        warnings=stored.warnings,
        cost_usd=float(p.cost_usd),
        status=p.status,
    )


def compose(db: Session, user: User, exam_id: UUID, data: ComposeIn) -> ExamProposalOut:  # noqa: PLR0912, PLR0915 -- orchestration of the two calls and validation
    exam = exams.exam_for(db, user, exam_id)
    chapters = list(db.scalars(select(Chapter).where(Chapter.subject_id == exam.subject_id)))
    lessons = list(
        db.scalars(select(Lesson).where(Lesson.chapter_id.in_([c.id for c in chapters])))
    )
    inventory = db.execute(
        select(Question.lesson_id, Question.type, Question.difficulty, func.count())
        .where(
            Question.org_id == user.org_id,
            Question.subject_id == exam.subject_id,
            Question.status == "approved",
        )
        .group_by(Question.lesson_id, Question.type, Question.difficulty)
    ).all()
    tree = [
        {
            "id": str(c.id),
            "title": c.title,
            "lessons": [
                {"id": str(lesson.id), "title": lesson.title}
                for lesson in lessons
                if lesson.chapter_id == c.id
            ],
        }
        for c in chapters
    ]
    # lesson_id None = approved questions not filed under any lesson (common for real
    # workbooks whose headings are exam titles rather than chapters).
    counts = [
        {"lesson_id": str(a) if a else None, "type": b, "difficulty": c, "count": d}
        for a, b, c, d in inventory
    ]
    client = get_llm_client()
    try:
        plan_result = client.complete_json(
            stage="compose",
            org_id=user.org_id,
            schema=ComposePlan,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Plan an exam using only the supplied taxonomy and inventory. "
                        "Never write questions. A row with empty chapter_ids and lesson_ids "
                        "selects from the whole subject, including questions whose lesson_id "
                        "is null in the inventory; use such rows when the requested questions "
                        "are not filed under lessons. Never target a chapter or lesson whose "
                        "inventory count is zero."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "prompt": data.prompt,
                            "language": data.language,
                            "tree": tree,
                            "inventory": counts,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        plan = plan_result.parsed
        original_rows = [row.model_copy() for section in plan.sections for row in section.rows]
        questions = list(
            db.scalars(
                select(Question).where(
                    Question.org_id == user.org_id,
                    Question.subject_id == exam.subject_id,
                    Question.status == "approved",
                )
            )
        )
        pool = [_candidate(q) for q in questions]
        chapter_ids, lesson_ids = {c.id for c in chapters}, {lesson.id for lesson in lessons}
        warnings: list[str] = []
        rows = []
        for section in plan.sections:
            kept = []
            for row in section.rows:
                if set(row.chapter_ids) - chapter_ids or set(row.lesson_ids) - lesson_ids:
                    warnings.append("unknown_taxonomy_id")
                    continue
                row.section_id = None
                available = sum(matches(q, _row(row)) for q in pool)
                if available < row.count:
                    warnings.append("count_clamped")
                    if not available:
                        continue
                    row.count = available
                kept.append(row)
                rows.append(row)
            section.rows = kept
        if not rows:
            # Deterministic fallback: every planned row was empty or unusable. Offer one
            # subject-wide row (keeping the first planned row's types) instead of nothing.
            wanted = sum(r.count for r in original_rows) or 10
            types = original_rows[0].types if original_rows else []
            fallback = BlueprintRow(types=types, count=1)
            available = sum(matches(q, _row(fallback)) for q in pool)
            if available:
                fallback.count = min(wanted, available)
                warnings.append("fallback_subject_wide")
                if not plan.sections:
                    plan.sections = [ComposeSection(title=plan.title or "1", rows=[])]
                plan.sections[0].rows = [fallback]
                rows.append(fallback)
        fixed = [i.question_id for i, _ in exams.rows_of(db, exam.id)]
        sampled = [sample(pool, [_row(row)], seed=0, fixed=fixed, oversample=3)[0] for row in rows]
        by_id = {q.id: q for q in questions}
        lookup = {q.id: q for q in pool}
        group_sizes = Counter(q.stimulus_id for q in pool if q.stimulus_id)
        refs: dict[str, UUID] = {}
        candidates: list[dict[str, object]] = []
        # Bound UTF-8 bytes as well as candidate count, including Arabic text.
        for result in sampled:
            for qid in result.selected:
                if qid in refs.values():
                    continue
                q = by_id[qid]
                ref = f"c{len(refs) + 1}"
                entry: dict[str, object] = {
                    "ref": ref,
                    "type": q.type,
                    "difficulty": q.difficulty,
                    "lesson": str(q.lesson_id) if q.lesson_id else None,
                    "tags": q.tags[:4],
                    "stem_preview": " ".join(q.stem.split())[:140],
                    "group_size": group_sizes[q.stimulus_id] if q.stimulus_id else 1,
                }
                if (
                    len(candidates) >= MAX_CANDIDATES
                    or len(json.dumps([*candidates, entry], ensure_ascii=False).encode())
                    > MAX_CANDIDATE_BYTES
                ):
                    break
                candidates.append(entry)
                refs[ref] = qid
        selection_result = client.complete_json(
            stage="compose",
            org_id=user.org_id,
            schema=ComposeSelection,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Select only supplied refs, one row per plan row. Keep stimulus groups "
                        "whole. Rationale at most 80 words in the requested language."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "language": data.language,
                            "plan": plan.model_dump(mode="json"),
                            "candidates": candidates,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
    except (BudgetExceeded, OrgBudgetExceeded) as exc:
        raise PaymentRequired() from exc
    except (LLMOutputInvalid, ValidationError) as exc:
        raise BadGateway("compose_failed") from exc
    logger.info(
        "compose tokens plan=%s/%s selection=%s/%s",
        plan_result.input_tokens,
        plan_result.output_tokens,
        selection_result.input_tokens,
        selection_result.output_tokens,
    )
    selected: list[list[UUID]] = []
    used: set[UUID] = set(fixed)
    cluster = clusters(pool)
    used_clusters = {cluster[x] for x in used if x in cluster}
    for index, row in enumerate(rows):
        allowed = set(sampled[index].selected) & set(refs.values())
        model_refs = (
            selection_result.parsed.rows[index].refs
            if index < len(selection_result.parsed.rows)
            else []
        )
        if any(ref not in refs for ref in model_refs):
            warnings.append("unknown_ref")
        preferred = [refs[ref] for ref in model_refs if ref in refs and refs[ref] in allowed]
        remaining = [
            qid for qid in sampled[index].selected if qid in allowed and qid not in preferred
        ]
        previous_used = set(used)
        previous_clusters = set(used_clusters)
        picked: list[UUID] = []
        for qid in [*preferred, *remaining]:
            candidate = lookup[qid]
            unit = (
                [
                    x
                    for x in sampled[index].selected
                    if lookup[x].stimulus_id == candidate.stimulus_id
                ]
                if candidate.stimulus_id
                else [qid]
            )
            if (
                len(unit) != (group_sizes[candidate.stimulus_id] if candidate.stimulus_id else 1)
                or not set(unit) <= allowed
                or len(picked) + len(unit) > row.count
                or set(unit) & used
                or {cluster[x] for x in unit} & used_clusters
            ):
                continue
            picked.extend(unit)
            used.update(unit)
            used_clusters.update(cluster[x] for x in unit)
        if len(picked) < row.count:
            fallback = sample(
                pool,
                [_row(row)],
                seed=0,
                fixed=previous_used,
                excluded={q.id for q in pool} - allowed,
            )[0].selected
            if len(fallback) > len(picked):
                picked = fallback
                used = previous_used | set(picked)
                used_clusters = previous_clusters | {cluster[x] for x in picked}
        if len(picked) < row.count or any(x not in preferred for x in picked):
            warnings.append("selection_filled_or_shortfall")
        selected.append(picked)
    rationale = " ".join(selection_result.parsed.rationale.split()[:80])
    proposal = ExamProposal(
        exam_id=exam.id,
        user_id=user.id,
        prompt=data.prompt,
        plan=plan.model_dump(mode="json"),
        selection={"rows": [[str(x) for x in r] for r in selected], "warnings": warnings},
        rationale=rationale,
        cost_usd=plan_result.cost_usd + selection_result.cost_usd,
    )
    db.add(proposal)
    save(db)
    return _out(proposal)


def listing(db: Session, user: User, exam_id: UUID) -> list[ExamProposalOut]:
    exams.exam_for(db, user, exam_id)
    return [
        _out(p)
        for p in db.scalars(
            select(ExamProposal)
            .where(ExamProposal.exam_id == exam_id)
            .order_by(ExamProposal.created_at.desc())
        )
    ]


def _get(db: Session, user: User, proposal_id: UUID) -> tuple[ExamProposal, Exam]:
    proposal = found(db.get(ExamProposal, proposal_id, with_for_update=True))
    exam = exams.exam_for(db, user, proposal.exam_id)
    if proposal.status != "pending":
        raise Conflict("proposal_not_pending")
    return proposal, exam


def discard(db: Session, user: User, proposal_id: UUID) -> ExamProposalOut:
    proposal, _ = _get(db, user, proposal_id)
    proposal.status = "discarded"
    save(db)
    return _out(proposal)


def apply(db: Session, user: User, proposal_id: UUID, data: ProposalApply) -> ExamDetail:  # noqa: PLR0912 -- validate edits and apply the plan atomically
    proposal, exam = _get(db, user, proposal_id)
    plan = ComposePlan.model_validate(proposal.plan)
    selected = StoredSelection.model_validate(proposal.selection).rows
    if not plan.sections:
        raise Invalid("empty_plan")
    removed = set(data.edits.remove_question_ids)
    if not removed <= {qid for row in selected for qid in row}:
        raise Invalid("invalid_question_selection")
    ids = [
        qid for row in selected for qid in row if qid not in removed
    ] + data.edits.add_question_ids
    questions = list(
        db.scalars(
            select(Question).where(
                Question.org_id == user.org_id,
                Question.subject_id == exam.subject_id,
                Question.status == "approved",
            )
        )
    )
    pool = [_candidate(q) for q in questions]
    by_id = {q.id: q for q in pool}
    fixed = {i.question_id for i, _ in exams.rows_of(db, exam.id)}
    if len(ids) != len(set(ids)) or not set(ids) <= set(by_id) or set(ids) & fixed:
        raise Invalid("invalid_question_selection")
    cluster = clusters(pool)
    all_ids = [*fixed, *ids]
    if len({cluster[x] for x in all_ids if x in cluster}) != len(all_ids):
        raise Invalid("duplicate_question")
    for qid in ids:
        sid = by_id[qid].stimulus_id
        if sid and not {q.id for q in pool if q.stimulus_id == sid} <= set(ids):
            raise Invalid("stimulus_group")
    section_position = len(exams.sections_of(db, exam.id))
    row_index = 0
    for section_index, section in enumerate(plan.sections):
        created = ExamSection(exam_id=exam.id, title=section.title, position=section_position)
        db.add(created)
        db.flush()
        position = 0
        for row in section.rows:
            for qid in selected[row_index]:
                if qid not in removed:
                    db.add(
                        ExamItem(
                            exam_id=exam.id,
                            section_id=created.id,
                            question_id=qid,
                            position=position,
                            points=row.points,
                            origin="ai",
                        )
                    )
                    position += 1
            row_index += 1
        if section_index == len(plan.sections) - 1:
            additions = sorted(
                data.edits.add_question_ids,
                key=lambda qid: (
                    str(by_id[qid].stimulus_id or qid),
                    by_id[qid].stimulus_position or 0,
                    qid,
                ),
            )
            for qid in additions:
                db.add(
                    ExamItem(
                        exam_id=exam.id,
                        section_id=created.id,
                        question_id=qid,
                        position=position,
                        points=1,
                        origin="ai",
                    )
                )
                position += 1
        section_position += 1
    if plan.title:
        exam.title = plan.title
    if plan.duration_minutes:
        settings = ExamSettings.model_validate(exam.settings)
        settings.header.duration_minutes = plan.duration_minutes
        exam.settings = settings.model_dump(mode="json")
    exam.blueprint = {**plan.model_dump(mode="json"), "proposal_id": str(proposal.id)}
    proposal.status = "applied"
    exams.touch(exam)
    save(db)
    return exams.detail(db, exam)
