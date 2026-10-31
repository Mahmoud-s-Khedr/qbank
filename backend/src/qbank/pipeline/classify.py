"""Batched text-only question classification (difficulty 1-5, reason, and tags)."""

import json
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from jinja2 import StrictUndefined, Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.llm import LLMClient, LLMResult, get_llm_client
from qbank.models import Question, Source, Subject
from qbank.pipeline.schema import Classification, QuestionClassification

PROMPT_VERSION = "classify-v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / "classify_v1.md"
BATCH_SIZE = 20


def _compact_batch_json(questions: Sequence[Question | dict[str, object]]) -> str:
    payload: list[dict[str, object]] = []
    for item in questions:
        if isinstance(item, dict):
            payload.append(item)
        else:
            payload.append(
                {
                    "id": str(item.id),
                    "type": item.type,
                    "language": item.language.value
                    if hasattr(item.language, "value")
                    else str(item.language),
                    "stem": item.stem,
                    "choices": [
                        {"label": c.get("label"), "content": c.get("content")} for c in item.choices
                    ],
                    "answer": item.answer,
                }
            )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def classify_batch(  # noqa: PLR0913 -- independent call context parameters
    client: LLMClient,
    questions: Sequence[Question | dict[str, object]],
    *,
    subject: str = "اللغة العربية",
    language: str = "ar",
    org_id: UUID | None = None,
    source_id: UUID | None = None,
    model_override: str | None = None,
) -> tuple[LLMResult[Classification], Decimal]:
    """Classify a batch of up to 20 questions (text-only)."""
    questions_json = _compact_batch_json(questions)
    prompt = Template(PROMPT_PATH.read_text(), undefined=StrictUndefined).render(
        subject=subject,
        language=language,
        questions_json=questions_json,
    )
    messages = [{"role": "user", "content": prompt}]
    result = client.complete_json(
        stage="classify",
        messages=messages,
        schema=Classification,
        org_id=org_id,
        source_id=source_id,
        model_override=model_override,
    )
    return result, result.cost_usd


def apply_classifications(
    questions: Sequence[Question],
    items: Sequence[QuestionClassification],
) -> int:
    """Apply LLM classification items to questions where difficulty_source != 'human'."""
    by_id: dict[str, Question] = {str(q.id): q for q in questions if q.id is not None}
    updated = 0
    for idx, item in enumerate(items):
        target = by_id.get(item.id)
        if target is None and len(items) == len(questions):
            target = questions[idx]
        if target is None or target.difficulty_source == "human":
            continue
        target.difficulty = item.difficulty
        target.difficulty_reason = item.difficulty_reason
        target.difficulty_source = "ai"
        target.tags = list(item.tags)
        updated += 1
    return updated


def pending_classification_questions(questions: Sequence[Question]) -> list[Question]:
    """Return questions that do not have human difficulty or completed AI classification."""
    return [q for q in questions if q.difficulty_source not in ("human", "ai")]


def classify_source(
    db: Session,
    source: Source,
    *,
    client: LLMClient | None = None,
    batch_size: int = BATCH_SIZE,
) -> Decimal:
    """Classify all eligible questions in a source in batches of 20."""
    llm_client = client or get_llm_client()
    subject = db.get(Subject, source.subject_id)
    subject_name = subject.name if subject else "اللغة العربية"
    language = subject.language.value if subject else "ar"

    all_questions = list(
        db.scalars(
            select(Question)
            .where(Question.source_id == source.id)
            .order_by(Question.position.asc(), Question.id.asc())
        )
    )
    to_classify = pending_classification_questions(all_questions)
    total_cost = Decimal(0)

    for offset in range(0, len(to_classify), batch_size):
        batch = to_classify[offset : offset + batch_size]
        result, cost = classify_batch(
            llm_client,
            batch,
            subject=subject_name,
            language=language,
            org_id=source.org_id,
            source_id=source.id,
        )
        total_cost += cost
        source.cost_usd = float(source.cost_usd or 0.0) + float(cost)
        apply_classifications(batch, result.parsed.items)
        db.flush()

    return total_cost
