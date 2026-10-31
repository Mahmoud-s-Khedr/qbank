import asyncio
from collections.abc import Callable
from importlib.metadata import version
from typing import Literal

from fastapi import APIRouter, Response

from qbank.api.deps import DB
from qbank.schemas.common import HealthOut, ReadyOut
from qbank.services import health as health_service
from qbank.services.health import database_ok

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health(db: DB) -> HealthOut:
    return HealthOut(version=version("qbank"), db="ok" if database_ok(db) else "down")


@router.get("/ready", response_model=ReadyOut)
async def ready(response: Response) -> ReadyOut:
    async def check(fn: Callable[[], bool]) -> Literal["ok", "down"]:
        try:
            ok = await asyncio.wait_for(asyncio.to_thread(fn), timeout=2)
        except Exception:
            ok = False
        return "ok" if ok else "down"

    db, redis, storage = await asyncio.gather(
        check(health_service.readiness_database_ok),
        check(health_service.redis_ok),
        check(health_service.storage_ok),
    )
    status: Literal["ok", "down"] = "ok" if db == redis == storage == "ok" else "down"
    if status == "down":
        response.status_code = 503
    return ReadyOut(status=status, db=db, redis=redis, storage=storage)
