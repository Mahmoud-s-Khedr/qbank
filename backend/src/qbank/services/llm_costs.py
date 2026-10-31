"""Queries over the durable LLM usage ledger."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from qbank.config import Settings
from qbank.db import get_engine
from qbank.llm.errors import BudgetExceeded, OrgBudgetExceeded
from qbank.models import LLMCall, Organization


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


# One transaction-scoped lock serializes both global and per-organization reservations.
BUDGET_LOCK = 0x5142414E4B


def _lock_budget(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": BUDGET_LOCK})


def _reap_locked(db: Session, settings: Settings) -> int:
    cutoff = datetime.now(UTC) - timedelta(
        seconds=settings.llm_timeout_s * (settings.llm_max_retries + 1) + 60
    )
    result = db.execute(
        update(LLMCall)
        .where(LLMCall.status == "reserved", LLMCall.created_at < cutoff)
        .values(
            status="abandoned",
            cost_usd=LLMCall.reserved_usd,
            reserved_usd=0,
            error_code="ReservationAbandoned",
        )
        .returning(LLMCall.id)
    )
    return len(result.all())


def reap_reservations(settings: Settings) -> int:
    with Session(get_engine()) as db, db.begin():
        _lock_budget(db)
        return _reap_locked(db, settings)


def reserve_call(  # noqa: PLR0913 -- ledger attributes are explicit
    settings: Settings,
    *,
    org_id: UUID | None,
    source_id: UUID | None,
    stage: str,
    model: str,
    request_hash: str,
    reserve: Decimal,
) -> UUID:
    # Round up to the ledger's precision so a reservation never loses a fraction of a cent.
    reserve = reserve.quantize(Decimal("0.000000001"), rounding=ROUND_CEILING)
    with Session(get_engine()) as db, db.begin():
        _lock_budget(db)
        _reap_locked(db, settings)
        amount = LLMCall.cost_usd + LLMCall.reserved_usd
        committed = db.scalar(select(func.coalesce(func.sum(amount), 0))) or Decimal(0)
        if committed + reserve > Decimal(str(settings.llm_budget_usd)):
            raise BudgetExceeded()
        if org_id is not None:
            org = db.get(Organization, org_id)
            if org is None:
                raise ValueError("Unknown organization")
            cap = org.settings.get("llm_monthly_cap_usd")
            now = datetime.now(UTC)
            month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            org_committed = db.scalar(
                select(func.coalesce(func.sum(amount), 0)).where(
                    LLMCall.org_id == org_id, LLMCall.created_at >= month
                )
            ) or Decimal(0)
            if cap is not None and org_committed + reserve > Decimal(str(cap)):
                raise OrgBudgetExceeded()
        call = LLMCall(
            org_id=org_id,
            source_id=source_id,
            stage=stage,
            model=model,
            request_hash=request_hash,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cost_usd=Decimal(0),
            reserved_usd=reserve,
            attempts=0,
            latency_ms=0,
            status="reserved",
        )
        db.add(call)
        db.flush()
        return call.id
