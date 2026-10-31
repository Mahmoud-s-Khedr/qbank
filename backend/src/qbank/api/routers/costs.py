from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from qbank.api.deps import DB, Admin
from qbank.models import LLMCall, Organization, Source
from qbank.services.unit_of_work import found

router = APIRouter(prefix="/api/v1/costs", tags=["costs"])


class CostGroup(BaseModel):
    name: str
    cost_usd: Decimal


class SourceCost(BaseModel):
    source_id: UUID
    title: str
    cost_usd: Decimal
    pages: int
    cost_per_page: Decimal


class CostSummary(BaseModel):
    total_usd: Decimal
    this_month_usd: Decimal
    cap_usd: float | None
    average_cost_per_page: Decimal
    by_month: list[CostGroup]
    by_stage: list[CostGroup]
    by_model: list[CostGroup]
    top_sources: list[SourceCost]


@router.get("/summary", response_model=CostSummary)
def summary(db: DB, user: Admin, months: int = Query(6, ge=1, le=60)) -> CostSummary:
    now = datetime.now(UTC)
    month_index = now.year * 12 + now.month - 1
    labels = [
        f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(month_index - months + 1, month_index + 1)
    ]
    monthly: dict[str, Decimal] = dict.fromkeys(labels, Decimal(0))
    stages: dict[str, Decimal] = defaultdict(Decimal)
    models: dict[str, Decimal] = defaultdict(Decimal)
    sources: dict[UUID, Decimal] = defaultdict(Decimal)
    total = Decimal(0)
    for call in db.scalars(select(LLMCall).where(LLMCall.org_id == user.org_id)):
        cost = call.cost_usd
        total += cost
        month = call.created_at.strftime("%Y-%m")
        if month in monthly:
            monthly[month] += cost
        stages[call.stage] += cost
        models[call.model] += cost
        if call.source_id:
            sources[call.source_id] += cost
    source_rows = db.scalars(
        select(Source).where(Source.org_id == user.org_id, Source.id.in_(sources))
    )
    top = []
    for source in source_rows:
        pages = source.page_count or 0
        cost = sources[source.id]
        top.append(
            SourceCost(
                source_id=source.id,
                title=source.title,
                cost_usd=cost,
                pages=pages,
                cost_per_page=cost / pages if pages else Decimal(0),
            )
        )
    org = found(db.get(Organization, user.org_id))
    cap = org.settings.get("llm_monthly_cap_usd")
    return CostSummary(
        total_usd=total,
        this_month_usd=monthly[labels[-1]],
        cap_usd=float(str(cap)) if cap is not None else None,
        average_cost_per_page=(
            sum((s.cost_usd for s in top), Decimal(0)) / sum(s.pages for s in top)
            if sum(s.pages for s in top)
            else Decimal(0)
        ),
        by_month=[CostGroup(name=k, cost_usd=v) for k, v in monthly.items()],
        by_stage=[CostGroup(name=k, cost_usd=v) for k, v in sorted(stages.items())],
        by_model=[CostGroup(name=k, cost_usd=v) for k, v in sorted(models.items())],
        top_sources=sorted(top, key=lambda s: s.cost_usd, reverse=True)[:10],
    )
