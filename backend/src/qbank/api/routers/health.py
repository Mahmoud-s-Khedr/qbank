from importlib.metadata import version

from fastapi import APIRouter

from qbank.api.deps import DB
from qbank.schemas.common import Health
from qbank.services.health import database_ok

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health(db: DB) -> Health:
    return Health(version=version("qbank"), db="ok" if database_ok(db) else "down")
