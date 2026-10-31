from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel

from qbank.api.deps import Current
from qbank.config import get_settings
from qbank.llm.pricing import prices

router = APIRouter(prefix="/api/v1")


class ModelOut(BaseModel):
    id: str
    price_in_per_m: Decimal
    price_out_per_m: Decimal
    default_for_stages: list[str]


@router.get("/llm/models", response_model=list[ModelOut])
def models(user: Current) -> list[ModelOut]:
    """Models the server will accept (allowlist ∩ price ceiling), for pickers such as re-extract."""
    settings = get_settings()
    out = []
    for model in settings.llm_allowed_models:
        price_in, price_out = prices(model)
        if price_in > Decimal(str(settings.llm_max_price_in_per_m)) or price_out > Decimal(
            str(settings.llm_max_price_out_per_m)
        ):
            continue
        stages = sorted(s for s, cfg in settings.llm_stage_models.items() if cfg.model == model)
        out.append(
            ModelOut(
                id=model,
                price_in_per_m=price_in,
                price_out_per_m=price_out,
                default_for_stages=stages,
            )
        )
    return out
