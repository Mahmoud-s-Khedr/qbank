"""Offline prices and manually refreshed OpenRouter price cache."""

import json
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen

from qbank.config import get_settings

PRICES = {
    "google/gemini-3.8-flash": (Decimal("0.83"), Decimal("4.12")),
    "qwen/qwen3.8-flash": (Decimal("0.15"), Decimal("0.47")),
    "openai/gpt-6-luna": (Decimal("0.10"), Decimal("0.50")),
    "anthropic/claude-haiku-5.5": (Decimal("0.10"), Decimal("0.50")),
    "nvidia/nemotron-3.5-super-vl:free": (Decimal(0), Decimal(0)),
}
CACHE = Path(".data/llm-prices.json")


def prices(model: str) -> tuple[Decimal, Decimal]:
    static = PRICES[model]
    if CACHE.exists():
        cached = json.loads(CACHE.read_text()).get(model)
        if cached is not None:
            return max(static[0], Decimal(cached[0])), max(static[1], Decimal(cached[1]))
    return static


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    inp, out = prices(model)
    return (inp * input_tokens + out * output_tokens) / 1_000_000


def refresh_prices() -> None:
    url = get_settings().openrouter_base_url.rstrip("/") + "/models"
    with urlopen(url, timeout=30) as response:  # noqa: S310 -- configured OpenRouter endpoint
        data = json.load(response)
    result = {}
    for item in data["data"]:
        if item["id"] in PRICES:
            result[item["id"]] = [
                str(Decimal(item["pricing"][key]) * 1_000_000) for key in ("prompt", "completion")
            ]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(result, indent=2))
