import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Event

import httpx
import pytest
from PIL import Image
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.config import Settings
from qbank.db import get_engine
from qbank.llm import (
    BudgetExceeded,
    FakeLLMClient,
    LLMOutputInvalid,
    ModelNotAllowed,
    ModelTooExpensive,
    OpenRouterClient,
    OrgBudgetExceeded,
    RecordedLLMClient,
    image_part,
    pricing,
)
from qbank.llm import client as llm_client
from qbank.llm.pricing import estimate_cost
from qbank.models import LLMCall, Organization
from qbank.services.llm_costs import reap_reservations


class Answer(BaseModel):
    answer: str


def test_fake_and_image() -> None:
    client = FakeLLMClient(Settings())
    client.queue("verify", {"answer": "yes"})
    result = client.complete_json(stage="verify", messages=[], schema=Answer, org_id=None)
    assert result.parsed.answer == "yes"
    with pytest.raises(ModelNotAllowed):
        client.complete_json(
            stage="verify", messages=[], schema=Answer, org_id=None, model_override="unknown"
        )
    assert estimate_cost("openai/gpt-6-luna", 1000, 1000) == Decimal("0.0006")
    buffer = BytesIO()
    Image.new("RGB", (2000, 1000)).save(buffer, format="PNG")
    url = image_part(buffer.getvalue())["image_url"]["url"]
    with Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1]))) as image:
        assert image.size == (1600, 800)


@pytest.mark.integration
def test_live_request_and_repair(database: str) -> None:
    requests: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        content = '{"answer": 1}' if len(requests) == 1 else '{"answer": "yes"}'
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "openai/gpt-6-luna",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "completion_tokens_details": {"reasoning_tokens": 3},
                    "cost": 0.001,
                },
            },
        )

    settings = Settings(openrouter_api_key=SecretStr("test"))
    client = OpenRouterClient(settings, httpx.Client(transport=httpx.MockTransport(reply)))
    result = client.complete_json(
        stage="verify", messages=[{"role": "user", "content": "hi"}], schema=Answer, org_id=None
    )
    assert result.parsed.answer == "yes"
    assert len(requests) == 2  # noqa: PLR2004 -- one call and one repair
    body = json.loads(requests[0].content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["reasoning"] == {"enabled": False}
    assert body["usage"] == {"include": True}
    assert requests[0].headers["x-title"] == "Qbank"
    with Session(get_engine()) as db:
        calls = list(db.scalars(select(LLMCall)))
        assert len(calls) == 2  # noqa: PLR2004 -- one row per attempt
        assert calls[0].reasoning_tokens == 3  # noqa: PLR2004 -- fixture usage
        assert sum(call.cost_usd for call in calls) == Decimal("0.002")


@pytest.mark.integration
def test_guards_before_network(database: str) -> None:
    seen: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise AssertionError("guard failed")

    settings = Settings(openrouter_api_key=SecretStr("test"))
    client = OpenRouterClient(settings, httpx.Client(transport=httpx.MockTransport(reply)))
    with pytest.raises(ModelNotAllowed):
        client.complete_json(
            stage="verify", messages=[], schema=Answer, org_id=None, model_override="unknown"
        )
    settings.llm_max_price_in_per_m = 0
    with pytest.raises(ModelTooExpensive):
        client.complete_json(stage="verify", messages=[], schema=Answer, org_id=None)
    settings.llm_max_price_in_per_m = 1
    settings.llm_budget_usd = 0
    with pytest.raises(BudgetExceeded):
        client.complete_json(stage="verify", messages=[], schema=Answer, org_id=None)
    settings.llm_budget_usd = 1
    with Session(get_engine()) as db:
        org = Organization(name="test", settings={"llm_monthly_cap_usd": 0})
        db.add(org)
        db.commit()
        org_id = org.id
    with pytest.raises(OrgBudgetExceeded):
        client.complete_json(stage="verify", messages=[], schema=Answer, org_id=org_id)
    assert not seen


def test_recorded_missing() -> None:
    with pytest.raises(FileNotFoundError, match="Missing LLM fixture"):
        RecordedLLMClient(Settings()).complete_json(
            stage="verify", messages=[], schema=Answer, org_id=None
        )


@pytest.mark.integration
def test_invalid_and_timeout_are_logged(database: str) -> None:
    def invalid(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "openai/gpt-6-luna",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "{}"},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    settings = Settings(openrouter_api_key=SecretStr("test"), llm_max_retries=0)
    client = OpenRouterClient(settings, httpx.Client(transport=httpx.MockTransport(invalid)))
    with pytest.raises(LLMOutputInvalid):
        client.complete_json(stage="verify", messages=[], schema=Answer, org_id=None)

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = OpenRouterClient(settings, httpx.Client(transport=httpx.MockTransport(timeout)))
    with pytest.raises(Exception, match="timed out"):
        client.complete_text(stage="verify", messages=[], org_id=None)
    with Session(get_engine()) as db:
        calls = list(db.scalars(select(LLMCall)))
        assert [call.status for call in calls] == ["failed", "failed", "failed"]


def test_recorded_replay_and_price_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path
    monkeypatch.setattr(
        llm_client, "fixture_path", lambda stage, digest: directory / f"{digest}.json"
    )
    settings = Settings()
    model = settings.llm_stage_models["verify"].model
    digest = llm_client.request_hash(model, "verify", [], "Answer")
    (directory / f"{digest}.json").write_text(
        json.dumps(
            {
                "raw_text": '{"answer":"ok"}',
                "input_tokens": 1,
                "output_tokens": 2,
                "reasoning_tokens": 0,
                "cost_usd": "0.01",
                "latency_ms": 10,
            }
        )
    )
    result = RecordedLLMClient(settings).complete_json(
        stage="verify", messages=[], schema=Answer, org_id=None
    )
    assert result.parsed.answer == "ok"
    assert result.request_hash == digest
    cache = directory / "prices.json"
    cache.write_text(json.dumps({model: ["2", "0"]}))
    monkeypatch.setattr(pricing, "CACHE", cache)
    with pytest.raises(ModelTooExpensive):
        FakeLLMClient(settings).complete_json(
            stage="verify", messages=[], schema=Answer, org_id=None
        )


@pytest.mark.integration
def test_rate_limit_retry(database: str) -> None:
    requests: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={"error": "limited"})
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "openai/gpt-6-luna",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    settings = Settings(openrouter_api_key=SecretStr("test"))
    client = OpenRouterClient(settings, httpx.Client(transport=httpx.MockTransport(reply)))
    result = client.complete_text(stage="verify", messages=[], org_id=None)
    assert result.parsed == "ok"
    assert len(requests) == 2  # noqa: PLR2004 -- rate limit followed by success
    with Session(get_engine()) as db:
        call = db.scalar(select(LLMCall))
        assert call is not None
        assert call.attempts == 2  # noqa: PLR2004 -- both HTTP attempts are counted
        assert call.reserved_usd == 0


@pytest.mark.integration
def test_concurrent_reservations(database: str) -> None:
    entered = Event()
    release = Event()
    requests: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        entered.set()
        assert release.wait(10)
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "openai/gpt-6-luna",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                    "cost": 0.000001,
                },
            },
        )

    settings = Settings(openrouter_api_key=SecretStr("test"), llm_budget_usd=0.003)
    client = OpenRouterClient(settings, httpx.Client(transport=httpx.MockTransport(reply)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.complete_text, stage="verify", messages=[], org_id=None)
        try:
            assert entered.wait(10)
            second = pool.submit(client.complete_text, stage="verify", messages=[], org_id=None)
            with pytest.raises(BudgetExceeded):
                second.result(timeout=10)
            with Session(get_engine()) as db:
                row = db.scalar(select(LLMCall))
                assert row is not None
                assert row.status == "reserved"
                assert row.reserved_usd > 0
        finally:
            release.set()
        assert first.result(timeout=10).parsed == "ok"
    assert len(requests) == 1
    with Session(get_engine()) as db:
        row = db.scalar(select(LLMCall))
        assert row is not None
        assert row.status == "success"
        assert row.reserved_usd == 0
        assert row.cost_usd == Decimal("0.000001")
        assert row.attempts == 1


@pytest.mark.integration
def test_reap_stale_reservation(database: str) -> None:
    with Session(get_engine()) as db:
        db.add(
            LLMCall(
                stage="verify",
                model="openai/gpt-6-luna",
                request_hash="test",
                created_at=datetime.now(UTC) - timedelta(hours=2),
                input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal(0),
                reserved_usd=Decimal("0.01"),
                attempts=0,
                latency_ms=0,
                status="reserved",
            )
        )
        db.commit()
    assert reap_reservations(Settings()) == 1
    with Session(get_engine()) as db:
        row = db.scalar(select(LLMCall))
        assert row is not None
        assert row.status == "abandoned"
        assert row.cost_usd == Decimal("0.01")
        assert row.reserved_usd == 0


def test_reasoning_off_maps_to_minimal_effort_for_models_that_require_it() -> None:
    from qbank.llm.pricing import reasoning_payload  # noqa: PLC0415 -- local to keep the test self-contained

    assert reasoning_payload("google/gemini-3.8-flash", "off") == {"effort": "minimal"}
    assert reasoning_payload("openai/gpt-6-luna", "off") == {"enabled": False}
    assert reasoning_payload("openai/gpt-6-luna", "low") == {"effort": "low"}
