from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    db: Literal["ok", "down"]


class ReadyOut(BaseModel):
    status: Literal["ok", "down"]
    db: Literal["ok", "down"]
    redis: Literal["ok", "down"]
    storage: Literal["ok", "down"]
