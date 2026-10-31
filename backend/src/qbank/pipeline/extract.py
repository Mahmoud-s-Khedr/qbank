"""Page extraction prompt and confidence-based model fallback."""

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from jinja2 import StrictUndefined, Template

from qbank.llm import LLMClient, LLMOutputInvalid, LLMResult, image_part
from qbank.pipeline.schema import PageExtraction

PROMPT_VERSION = "extract-v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_v1.md"


def extract_page(  # noqa: PLR0913 -- page context and call controls are independent
    client: LLMClient,
    image: bytes,
    *,
    subject: str,
    language: str,
    grade: str | None,
    org_id: UUID,
    source_id: UUID,
    max_side: int,
    fallback_threshold: float,
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

    def call(stage: str) -> LLMResult[PageExtraction]:
        return client.complete_json(
            stage=stage,
            messages=messages,
            schema=PageExtraction,
            org_id=org_id,
            source_id=source_id,
        )

    try:
        first = call("extract")
    except LLMOutputInvalid:
        strong = call("extract_strong")
        return strong, strong.cost_usd
    if first.parsed.page_confidence >= fallback_threshold:
        return first, first.cost_usd
    strong = call("extract_strong")
    best = strong if strong.parsed.page_confidence > first.parsed.page_confidence else first
    return best, first.cost_usd + strong.cost_usd
