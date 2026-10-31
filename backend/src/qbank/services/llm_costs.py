"""Queries over the durable LLM usage ledger."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qbank.models import LLMCall


def total_spend(db: Session) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0))) or Decimal(0)


def org_month_spend(db: Session, org_id: UUID | None = None) -> Decimal:
    now = datetime.now(UTC)
    stmt = select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(
        LLMCall.created_at >= now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    if org_id is not None:
        stmt = stmt.where(LLMCall.org_id == org_id)
    return db.scalar(stmt) or Decimal(0)


def spend_by(db: Session, group: Literal["stage", "model", "source"]) -> dict[str, Decimal]:
    column = {"stage": LLMCall.stage, "model": LLMCall.model, "source": LLMCall.source_id}[group]
    rows = db.execute(select(column, func.sum(LLMCall.cost_usd)).group_by(column))
    return {str(key): value for key, value in rows}
