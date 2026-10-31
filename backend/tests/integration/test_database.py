from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qbank.db import get_db


@pytest.mark.integration
def test_health_and_migrations(database: str, app: FastAPI, client: TestClient) -> None:
    engine = create_engine(database)

    def override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    try:
        response = client.get("/api/v1/health")
        assert response.json() == {"status": "ok", "version": app.version, "db": "ok"}
        command.check(Config("alembic.ini"))
    finally:
        engine.dispose()
