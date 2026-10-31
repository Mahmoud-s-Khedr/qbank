"""LLM verifier pass comparing page image against extracted questions."""

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

from jinja2 import StrictUndefined, Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.config import get_settings
from qbank.llm import LLMClient, LLMResult, get_llm_client, image_part
from qbank.models import Organization, PageStatus, Question, Source, SourcePage
from qbank.pipeline.schema import Discrepancy, Verification
from qbank.pipeline.validate import validate_source
from qbank.storage import ObjectStore, get_store, keys

PROMPT_VERSION = "verify-v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / "verify_v1.md"

VerifyPolicy = Literal["off", "low_confidence", "all"]


def get_verify_policy(source: Source, org: Organization | None = None) -> VerifyPolicy:
    """Use the source override before the organization default."""
    config = source.pipeline_config or {}
    raw = config.get("verify", (org.settings or {}).get("verify_policy") if org else None)
    if raw == "off":
        return "off"
    if raw == "all":
        return "all"
    return "low_confidence"


def _question_page_ids(question: Question) -> set[str]:
    result: set[str] = set()
    for region in question.regions or []:
        if isinstance(region, dict) and region.get("page") is not None:
            result.add(str(region["page"]))
    return result


def questions_for_page(page: SourcePage, questions: Sequence[Question]) -> list[Question]:
    """Return all questions in `questions` that appear on `page`."""
    pid = str(page.id)
    return [q for q in questions if pid in _question_page_ids(q)]


def select_pages_to_verify(
    pages: Sequence[SourcePage],
    questions: Sequence[Question],
    *,
    policy: VerifyPolicy = "low_confidence",
    review_threshold: float | None = None,
) -> list[SourcePage]:
    """Select pages that require verification under the given policy."""
    if policy == "off":
        return []
    threshold = (
        review_threshold if review_threshold is not None else get_settings().review_threshold
    )
    selected: list[SourcePage] = []
    for page in pages:
        if page.status == PageStatus.failed:
            continue
        page_qs = questions_for_page(page, questions)
        if not page_qs:
            continue
        if policy == "all" or any(q.confidence < threshold for q in page_qs):
            selected.append(page)
    return selected


def _compact_questions_json(questions: Sequence[Question | Mapping[str, object]]) -> str:
    payload: list[Mapping[str, object]] = []
    for item in questions:
        if isinstance(item, Mapping):
            payload.append(item)
        else:
            payload.append(
                {
                    "number_label": item.number_label,
                    "type": item.type,
                    "stem": item.stem,
                    "choices": [
                        {
                            "label": c.get("label"),
                            "content": c.get("content"),
                            "is_correct": c.get("is_correct"),
                        }
                        for c in item.choices
                    ],
                    "answer": item.answer,
                }
            )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def verify_page(  # noqa: PLR0913 -- independent call context parameters
    client: LLMClient,
    image: bytes,
    questions: Sequence[Question | Mapping[str, object]],
    *,
    org_id: UUID | None = None,
    source_id: UUID | None = None,
    max_side: int = 1600,
    model_override: str | None = None,
) -> tuple[LLMResult[Verification], Decimal]:
    """Run one LLM verification call for a page image and its extracted questions."""
    compact_json = _compact_questions_json(questions)
    prompt = Template(PROMPT_PATH.read_text(), undefined=StrictUndefined).render(
        questions_json=compact_json
    )
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": prompt}, image_part(image, max_side=max_side)],
        }
    ]
    result = client.complete_json(
        stage="verify",
        messages=messages,
        schema=Verification,
        org_id=org_id,
        source_id=source_id,
        model_override=model_override,
    )
    return result, result.cost_usd


def apply_discrepancies(
    page_questions: Sequence[Question],
    discrepancies: Sequence[Discrepancy],
) -> set[UUID]:
    """Attach verifier_* issue entries to matching page questions without editing content."""
    if not page_questions:
        return set()

    by_question: dict[int, list[dict[str, object]]] = {i: [] for i in range(len(page_questions))}
    affected_indices: set[int] = set()

    for disc in discrepancies:
        target_idx: int | None = None
        label = disc.number_label.strip()
        for idx, q in enumerate(page_questions):
            if q.number_label.strip() == label:
                target_idx = idx
                break
        if target_idx is None:
            target_idx = 0
        affected_indices.add(target_idx)
        by_question[target_idx].append(
            {
                "code": f"verifier_{disc.field}",
                "severity": disc.severity,
                "message": disc.problem,
                "details": {
                    "field": disc.field,
                    "number_label": disc.number_label,
                    "suggested_fix": disc.suggested_fix,
                },
            }
        )

    affected_ids: set[UUID] = set()
    for idx, q in enumerate(page_questions):
        meta = dict(q.metadata_json) if isinstance(q.metadata_json, dict) else {}
        meta["verifier_issues"] = by_question[idx]
        meta["verified_prompt_version"] = PROMPT_VERSION
        q.metadata_json = meta
        if idx in affected_indices and q.id is not None:
            affected_ids.add(q.id)
    return affected_ids


def is_page_verified(page_questions: Sequence[Question]) -> bool:
    """Return True if all questions on the page were already verified with PROMPT_VERSION."""
    return bool(page_questions) and all(
        isinstance(q.metadata_json, dict)
        and q.metadata_json.get("verified_prompt_version") == PROMPT_VERSION
        for q in page_questions
    )


def verify_source(
    db: Session,
    source: Source,
    *,
    client: LLMClient | None = None,
    store: ObjectStore | None = None,
) -> set[UUID]:
    """Run verifier pass on qualifying pages of a source and re-validate affected questions."""
    policy = get_verify_policy(source, db.get(Organization, source.org_id))
    if policy == "off":
        return set()

    llm_client = client or get_llm_client()
    obj_store = store or get_store()
    settings = get_settings()

    pages = list(
        db.scalars(
            select(SourcePage)
            .where(SourcePage.source_id == source.id)
            .order_by(SourcePage.page_number.asc())
        )
    )
    questions = list(
        db.scalars(
            select(Question)
            .where(Question.source_id == source.id)
            .order_by(Question.position.asc(), Question.id.asc())
        )
    )
    target_pages = select_pages_to_verify(
        pages, questions, policy=policy, review_threshold=settings.review_threshold
    )
    all_affected: set[UUID] = set()

    for page in target_pages:
        page_qs = questions_for_page(page, questions)
        if is_page_verified(page_qs):
            continue
        hires_key = keys.page(source.org_id, source.id, page.page_number, hires=True)
        display_key = keys.page(source.org_id, source.id, page.page_number, hires=False)
        image_bytes = (
            obj_store.get_bytes(hires_key)
            if obj_store.exists(hires_key)
            else obj_store.get_bytes(display_key)
        )
        result, cost = verify_page(
            llm_client,
            image_bytes,
            page_qs,
            org_id=source.org_id,
            source_id=source.id,
            max_side=settings.extract_image_max_side,
        )
        page.cost_usd = float(page.cost_usd or 0.0) + float(cost)
        source.cost_usd = float(source.cost_usd or 0.0) + float(cost)
        affected = apply_discrepancies(page_qs, result.parsed.discrepancies)
        page_q_ids = {q.id for q in page_qs if q.id is not None}
        all_affected.update(affected)
        validate_source(db, source, question_ids=page_q_ids, run_dedup=False)
        db.flush()

    return all_affected
