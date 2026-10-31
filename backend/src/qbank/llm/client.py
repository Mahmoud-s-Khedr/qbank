"""Guarded OpenRouter calls and deterministic test clients."""

import base64
import hashlib
import json
import math
import os
import random
import time
from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast
from uuid import UUID

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from PIL import Image
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from qbank.config import Settings, get_settings
from qbank.db import get_engine
from qbank.llm.errors import (
    LLMNotConfigured,
    LLMOutputInvalid,
    ModelNotAllowed,
    ModelTooExpensive,
)
from qbank.llm.pricing import PRICES, estimate_cost, prices, reasoning_payload
from qbank.models import LLMCall

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult[T]:
    parsed: T
    raw_text: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: Decimal
    latency_ms: int
    request_hash: str


class LLMClient(Protocol):
    def complete_json(  # noqa: PLR0913 -- task-specified call parameters
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        org_id: UUID | None,
        source_id: UUID | None = None,
        model_override: str | None = None,
    ) -> LLMResult[T]: ...

    def complete_text(
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        org_id: UUID | None,
        source_id: UUID | None = None,
        model_override: str | None = None,
    ) -> LLMResult[str]: ...


def request_hash(model: str, stage: str, messages: list[dict[str, Any]], schema_name: str) -> str:
    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str) and value.startswith("data:image/"):
            return hashlib.sha256(base64.b64decode(value.split(",", 1)[1])).hexdigest()
        return value

    payload = json.dumps(
        [model, stage, scrub(messages), schema_name], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def image_part(
    data: bytes, *, max_side: int = 1600, fmt: str = "JPEG", quality: int = 85
) -> dict[str, Any]:
    with Image.open(BytesIO(data)) as image:
        image.thumbnail((max_side, max_side))
        converted = image.convert("RGB") if fmt.upper() == "JPEG" else image
        output = BytesIO()
        converted.save(output, format=fmt, quality=quality)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    mime = "jpeg" if fmt.upper() == "JPEG" else fmt.lower()
    return {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{encoded}"}}


def guard_model(settings: Settings, model: str) -> None:
    if model not in settings.llm_allowed_models or model not in PRICES:
        raise ModelNotAllowed(model)
    inp, out = prices(model)
    if inp > Decimal(str(settings.llm_max_price_in_per_m)) or out > Decimal(
        str(settings.llm_max_price_out_per_m)
    ):
        raise ModelTooExpensive(model)


def estimate_input_tokens(messages: list[dict[str, Any]], schema: type[BaseModel] | None) -> int:
    """Estimate text generously and count each image separately."""

    def measure(value: Any) -> tuple[int, int]:
        if isinstance(value, dict):
            if value.get("type") == "image_url":
                return (0, 1)
            parts = [measure(v) for v in value.values()]
        elif isinstance(value, list):
            parts = [measure(v) for v in value]
        elif isinstance(value, str):
            return (len(value), 0)
        else:
            return (0, 0)
        return (sum(x for x, _ in parts), sum(y for _, y in parts))

    length, images = measure(messages)
    if schema:
        length += len(json.dumps(schema.model_json_schema(), ensure_ascii=False))
    return math.ceil(length / 3.5) + images * 1300 + 100


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if isinstance(schema, dict):
        for value in schema.values():
            if isinstance(value, dict):
                strict_schema(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        strict_schema(item)
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            schema["required"] = list(schema.get("properties", {}))
        schema.pop("default", None)
    return schema


class OpenRouterClient:
    def __init__(
        self, settings: Settings | None = None, http_client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client

    def _call(  # noqa: PLR0913, PLR0917, PLR0912, PLR0915 -- request lifecycle and ledger are coupled
        self,
        stage: str,
        messages: list[dict[str, Any]],
        schema: type[T] | None,
        org_id: UUID | None,
        source_id: UUID | None,
        model_override: str | None,
    ) -> Any:
        from qbank.services.llm_costs import reserve_call  # noqa: PLC0415 -- avoid import cycle

        config = self.settings.llm_stage_models[stage]
        model = model_override or config.model
        digest = request_hash(model, stage, messages, schema.__name__ if schema else "text")
        guard_model(self.settings, model)
        key = self.settings.openrouter_api_key
        if not key or not key.get_secret_value():
            raise LLMNotConfigured()
        client = OpenAI(
            api_key=key.get_secret_value(),
            base_url=self.settings.openrouter_base_url,
            default_headers={"HTTP-Referer": "https://qbank.local", "X-Title": "Qbank"},
            timeout=self.settings.llm_timeout_s,
            max_retries=0,
            http_client=self.http_client,
        )
        conversation = list(messages)
        invalid_cost = Decimal(0)
        for attempt in range(2 if schema else 1):
            reserve = estimate_cost(
                model, estimate_input_tokens(conversation, schema), config.max_tokens
            )
            call_id = reserve_call(
                self.settings,
                org_id=org_id,
                source_id=source_id,
                stage=stage,
                model=model,
                request_hash=digest,
                reserve=reserve,
            )
            started = time.monotonic()
            inp = out = reasoning = 0
            cost = Decimal(0)
            error = None
            attempts = 0
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": conversation,
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "extra_body": {
                        "usage": {"include": True},
                        "reasoning": reasoning_payload(model, config.reasoning),
                    },
                }
                if schema:
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.__name__,
                            "strict": True,
                            "schema": strict_schema(schema.model_json_schema()),
                        },
                    }
                for retry in range(self.settings.llm_max_retries + 1):
                    attempts += 1
                    try:
                        response = client.chat.completions.create(**kwargs)
                        break
                    except (APIConnectionError, APITimeoutError, APIStatusError) as exc:
                        retryable = (
                            not isinstance(exc, APIStatusError)
                            or exc.status_code == HTTPStatus.TOO_MANY_REQUESTS
                            or exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
                        )
                        if not retryable or retry == self.settings.llm_max_retries:
                            raise
                        time.sleep(min(8.0, 0.5 * (2**retry)) * random.uniform(0.75, 1.0))  # noqa: S311 -- retry jitter is not security-sensitive
                usage = response.usage
                if usage is None:
                    # Unknown usage must not silently release the budget reservation.
                    cost = reserve
                if usage:
                    inp, out = usage.prompt_tokens, usage.completion_tokens
                    details = usage.completion_tokens_details
                    reasoning = details.reasoning_tokens or 0 if details else 0
                    provided = getattr(usage, "cost", None)
                    cost = (
                        Decimal(str(provided))
                        if provided is not None
                        else estimate_cost(model, inp, out)
                    )
                raw = response.choices[0].message.content or ""
                parsed = schema.model_validate_json(raw) if schema else raw
                result = LLMResult(
                    parsed,
                    raw,
                    model,
                    inp,
                    out,
                    reasoning,
                    cost,
                    int((time.monotonic() - started) * 1000),
                    digest,
                )
            except Exception as exc:
                error = type(exc).__name__
                if isinstance(exc, ValidationError) and attempt == 0:
                    invalid_cost += cost
                    conversation.extend(
                        [
                            {"role": "assistant", "content": raw},
                            {
                                "role": "user",
                                "content": f"Correct the JSON validation errors: {exc}",
                            },
                        ]
                    )
                elif isinstance(exc, ValidationError):
                    raise LLMOutputInvalid(str(exc), cost_usd=invalid_cost + cost) from exc
                else:
                    raise
            finally:
                with Session(get_engine()) as db:
                    call = db.get(LLMCall, call_id, with_for_update=True)
                    if call is None:
                        raise RuntimeError("Reserved LLM call disappeared")
                    # OpenRouter normally reports usage only for successful HTTP attempts;
                    # failed attempts therefore have no reported cost to add.
                    if call.status == "abandoned":
                        cost = max(cost, call.cost_usd)
                    call.input_tokens = inp
                    call.output_tokens = out
                    call.reasoning_tokens = reasoning
                    call.cost_usd = cost
                    call.reserved_usd = Decimal(0)
                    call.attempts = attempts
                    call.latency_ms = int((time.monotonic() - started) * 1000)
                    call.status = "failed" if error else "success"
                    call.error_code = error
                    db.commit()
            if not error:
                result.cost_usd += invalid_cost
                if os.environ.get("QBANK_LLM_RECORD") == "1":
                    path = fixture_path(stage, digest)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(
                            {
                                "raw_text": raw,
                                "model": model,
                                "input_tokens": inp,
                                "output_tokens": out,
                                "reasoning_tokens": reasoning,
                                "cost_usd": str(result.cost_usd),
                                "latency_ms": result.latency_ms,
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                return result
        raise LLMOutputInvalid("No valid response")

    def complete_json(  # noqa: PLR0913 -- task-specified call parameters
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        org_id: UUID | None,
        source_id: UUID | None = None,
        model_override: str | None = None,
    ) -> LLMResult[T]:
        return cast(
            LLMResult[T], self._call(stage, messages, schema, org_id, source_id, model_override)
        )

    def complete_text(
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        org_id: UUID | None,
        source_id: UUID | None = None,
        model_override: str | None = None,
    ) -> LLMResult[str]:
        return cast(
            LLMResult[str], self._call(stage, messages, None, org_id, source_id, model_override)
        )


def fixture_path(stage: str, digest: str) -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "llm"
        / stage
        / f"{digest}.json"
    )


class FakeLLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.scripts: dict[str, list[Any]] = {}
        self.calls: list[dict[str, Any]] = []

    def queue(self, stage: str, result: Any) -> None:
        self.scripts.setdefault(stage, []).append(result)

    def _run(  # noqa: PLR0913, PLR0917 -- task-specified call parameters
        self,
        stage: str,
        messages: list[dict[str, Any]],
        schema: type[T] | None,
        org_id: UUID | None,
        source_id: UUID | None,
        model_override: str | None,
    ) -> Any:
        model = model_override or self.settings.llm_stage_models[stage].model
        guard_model(self.settings, model)
        digest = request_hash(model, stage, messages, schema.__name__ if schema else "text")
        self.calls.append(
            {
                "stage": stage,
                "messages": messages,
                "schema": schema,
                "org_id": org_id,
                "source_id": source_id,
                "model": model,
                "request_hash": digest,
            }
        )
        value = self.scripts[stage].pop(0)
        if isinstance(value, Exception):
            raise value
        parsed: Any
        if schema:
            parsed = schema.model_validate(value)
            raw = parsed.model_dump_json()
        else:
            parsed = str(value)
            raw = parsed
        return LLMResult(parsed, raw, model, 0, 0, 0, Decimal(0), 0, digest)

    def complete_json(  # noqa: PLR0913 -- task-specified call parameters
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        org_id: UUID | None,
        source_id: UUID | None = None,
        model_override: str | None = None,
    ) -> LLMResult[T]:
        return cast(
            LLMResult[T], self._run(stage, messages, schema, org_id, source_id, model_override)
        )

    def complete_text(
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        org_id: UUID | None,
        source_id: UUID | None = None,
        model_override: str | None = None,
    ) -> LLMResult[str]:
        return cast(
            LLMResult[str], self._run(stage, messages, None, org_id, source_id, model_override)
        )


class RecordedLLMClient(FakeLLMClient):
    def _run(  # noqa: PLR0913, PLR0917 -- task-specified call parameters
        self,
        stage: str,
        messages: list[dict[str, Any]],
        schema: type[T] | None,
        org_id: UUID | None,
        source_id: UUID | None,
        model_override: str | None,
    ) -> Any:
        model = model_override or self.settings.llm_stage_models[stage].model
        guard_model(self.settings, model)
        digest = request_hash(model, stage, messages, schema.__name__ if schema else "text")
        path = fixture_path(stage, digest)
        if not path.is_file():
            raise FileNotFoundError(f"Missing LLM fixture: {path}")
        data = json.loads(path.read_text())
        raw = data["raw_text"]
        parsed = schema.model_validate_json(raw) if schema else raw
        return LLMResult(
            parsed,
            raw,
            model,
            data["input_tokens"],
            data["output_tokens"],
            data["reasoning_tokens"],
            Decimal(data["cost_usd"]),
            data["latency_ms"],
            digest,
        )


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_mode == "fake":
        return FakeLLMClient(settings)
    if settings.llm_mode == "recorded":
        return RecordedLLMClient(settings)
    return OpenRouterClient(settings)
