from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from qbank.api.deps import DB, Admin
from qbank.config import get_settings
from qbank.llm.pricing import prices
from qbank.models import Organization
from qbank.services.errors import Invalid
from qbank.services.exam_templates import check_exam_template
from qbank.services.unit_of_work import found, save

router = APIRouter(prefix="/api/v1/org", tags=["organization"])


class OrgSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    llm_monthly_cap_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    verify_policy: Literal["off", "low_confidence", "all"] = "low_confidence"
    default_digits: Literal["arabic", "western"] = "arabic"
    default_template_id: UUID | None = None
    extract_model: str


class OrgSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    llm_monthly_cap_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    verify_policy: Literal["off", "low_confidence", "all"] | None = None
    default_digits: Literal["arabic", "western"] | None = None
    default_template_id: UUID | None = None
    extract_model: str | None = None


def output(org: Organization) -> OrgSettings:
    return OrgSettings.model_validate(
        {
            **{
                key: value for key, value in org.settings.items() if key in OrgSettings.model_fields
            },
            "name": org.name,
            "extract_model": org.settings.get(
                "extract_model", get_settings().llm_stage_models["extract"].model
            ),
        }
    )


@router.get("/settings", response_model=OrgSettings)
def get_org_settings(db: DB, user: Admin) -> OrgSettings:
    return output(found(db.get(Organization, user.org_id)))


@router.patch("/settings", response_model=OrgSettings)
def update_org_settings(data: OrgSettingsPatch, db: DB, user: Admin) -> OrgSettings:
    org = found(db.get(Organization, user.org_id))
    changes = data.model_dump(exclude_unset=True, mode="json")
    for key in ("name", "verify_policy", "default_digits", "extract_model"):
        if key in changes and changes[key] is None:
            raise Invalid("invalid_settings")
    if data.extract_model is not None:
        settings = get_settings()
        if data.extract_model not in settings.llm_allowed_models:
            raise Invalid("invalid_model")
        price_in, price_out = prices(data.extract_model)
        if price_in > Decimal(str(settings.llm_max_price_in_per_m)) or price_out > Decimal(
            str(settings.llm_max_price_out_per_m)
        ):
            raise Invalid("invalid_model")
    if "default_template_id" in changes:
        check_exam_template(db, user.org_id, data.default_template_id)
    if data.name is not None:
        org.name = data.name
    changes.pop("name", None)
    org.settings = {**org.settings, **changes}
    save(db)
    return output(org)
