"""Page extraction prompt and confidence-based model fallback."""

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from jinja2 import StrictUndefined, Template

from qbank.llm import (
    BudgetExceeded,
    LLMClient,
    LLMOutputInvalid,
    LLMResult,
    OrgBudgetExceeded,
    image_part,
)
from qbank.pipeline.schema import PageExtraction

PROMPT_VERSION = "extract-v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_v1.md"


def extract_page(  # noqa: PLR0913 -- page context and call controls are independent
    client: LLMClient,
    image: bytes,
    *,
    subject: str = "اللغة العربية",
    language: str = "ar",
    grade: str | None = None,
    org_id: UUID | None = None,
    source_id: UUID | None = None,
    max_side: int = 1600,
    fallback_threshold: float = 0.5,
    model_override: str | None = None,
    stage: str = "extract",
) -> tuple[LLMResult[PageExtraction], Decimal]:
    prompt = Template(PROMPT_PATH.read_text(), undefined=StrictUndefined).render(
        subject=subject, language=language, grade=grade or ""
    )
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": prompt}, image_part(image, max_side=max_side)],
        }
    ]

    def call(call_stage: str) -> LLMResult[PageExtraction]:
        return client.complete_json(
            stage=call_stage,
            messages=messages,
            schema=PageExtraction,
            org_id=org_id,
            source_id=source_id,
            model_override=model_override,
        )

    try:
        first = call(stage)
    except LLMOutputInvalid as exc:
        try:
            strong = call("extract_strong")
        except (BudgetExceeded, OrgBudgetExceeded, LLMOutputInvalid) as strong_exc:
            strong_exc.cost_usd += exc.cost_usd
            raise
        return strong, exc.cost_usd + strong.cost_usd
    if first.parsed.page_confidence >= fallback_threshold:
        return first, first.cost_usd
    try:
        strong = call("extract_strong")
    except LLMOutputInvalid as exc:
        return first, first.cost_usd + exc.cost_usd
    except (BudgetExceeded, OrgBudgetExceeded) as exc:
        exc.cost_usd += first.cost_usd
        raise
    best = strong if strong.parsed.page_confidence > first.parsed.page_confidence else first
    return best, first.cost_usd + strong.cost_usd
