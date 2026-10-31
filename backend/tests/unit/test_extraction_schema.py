from decimal import Decimal
from io import BytesIO
from typing import TypedDict
from uuid import UUID, uuid4

import pytest
from PIL import Image
from pydantic import ValidationError

from qbank.llm import BudgetExceeded, FakeLLMClient, LLMOutputInvalid
from qbank.pipeline.extract import extract_page
from qbank.pipeline.schema import PageExtraction, to_region_box


def test_region_conversion() -> None:
    assert to_region_box((100, 200, 800, 900)) == [0.2, 0.1, 0.9, 0.8]
    assert to_region_box((1200, 900, -5, 100)) == [0.1, 0.0, 0.9, 1.0]


def test_required_fields_and_confidence() -> None:
    page = {
        "page_kind": "blank",
        "headings": [],
        "stimuli": [],
        "questions": [],
        "answer_key_entries": [],
        "page_confidence": 0.9,
        "notes": "",
    }
    assert PageExtraction.model_validate(page).page_kind == "blank"
    with pytest.raises(ValidationError):
        PageExtraction.model_validate({**page, "page_confidence": 1.1})
    del page["notes"]
    with pytest.raises(ValidationError):
        PageExtraction.model_validate(page)


class ExtractArgs(TypedDict):
    subject: str
    language: str
    grade: str | None
    org_id: UUID
    source_id: UUID
    max_side: int
    fallback_threshold: float


def test_extract_fallback() -> None:
    image = BytesIO()
    Image.new("RGB", (4, 4), "white").save(image, format="PNG")
    page = {
        "page_kind": "blank",
        "headings": [],
        "stimuli": [],
        "questions": [],
        "answer_key_entries": [],
        "page_confidence": 0.2,
        "notes": "",
    }
    client = FakeLLMClient()
    client.queue("extract", page)
    client.queue("extract_strong", {**page, "page_confidence": 0.8})
    args: ExtractArgs = {
        "subject": "Math",
        "language": "en",
        "grade": "1",
        "org_id": uuid4(),
        "source_id": uuid4(),
        "max_side": 1600,
        "fallback_threshold": 0.5,
    }
    result, _ = extract_page(client, image.getvalue(), **args)
    assert result.parsed.page_confidence == pytest.approx(0.8)
    client.queue("extract", LLMOutputInvalid("invalid", cost_usd=Decimal("0.01")))
    client.queue("extract_strong", page)
    result, cost = extract_page(client, image.getvalue(), **args)
    assert cost == Decimal("0.01")
    assert result.parsed.page_confidence == pytest.approx(0.2)
    client.queue("extract", {**page, "page_confidence": 0.4})
    client.queue("extract_strong", page)
    result, _ = extract_page(client, image.getvalue(), **args)
    assert result.parsed.page_confidence == pytest.approx(0.4)
    client.queue("extract", page)
    client.queue("extract_strong", LLMOutputInvalid("invalid strong"))
    result, _ = extract_page(client, image.getvalue(), **args)
    assert result.parsed.page_confidence == pytest.approx(0.2)
    client.queue("extract", LLMOutputInvalid("invalid", cost_usd=Decimal("0.01")))
    client.queue("extract_strong", BudgetExceeded())
    with pytest.raises(BudgetExceeded) as budget:
        extract_page(client, image.getvalue(), **args)
    assert budget.value.cost_usd == Decimal("0.01")
    assert [call["stage"] for call in client.calls] == [
        "extract",
        "extract_strong",
        "extract",
        "extract_strong",
        "extract",
        "extract_strong",
        "extract",
        "extract_strong",
        "extract",
        "extract_strong",
    ]


def test_normalize_blanks_turns_dot_runs_into_qmd_blanks() -> None:
    from qbank.pipeline.materialize import normalize_blanks  # noqa: PLC0415 -- keeps import local to this test

    assert normalize_blanks("عظمة القص تتصف بأنها..........") == "عظمة القص تتصف بأنها____"
    assert normalize_blanks("x = ......... و ……") == "x = ____ و ____"
    assert normalize_blanks("ينتهي بنقطة.") == "ينتهي بنقطة."
    assert normalize_blanks("ثلاث نقاط... فقط") == "ثلاث نقاط... فقط"
