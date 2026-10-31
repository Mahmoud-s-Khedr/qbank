"""Database engine, sessions and model primitives."""

from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache
from uuid import UUID

from sqlalchemy import DateTime, MetaData, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from uuid_utils import uuid7

from qbank.config import get_settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def new_uuid() -> UUID:
    return UUID(str(uuid7()))


class UUIDPk:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_uuid)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, connect_args={"connect_timeout": 2})


def get_db() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
