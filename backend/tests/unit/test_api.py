from collections.abc import Iterator
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from qbank.config import Settings, get_settings
from qbank.db import get_db, new_uuid


def test_health_down(app: FastAPI, client: TestClient) -> None:
    session = MagicMock(spec=Session)
    session.execute.side_effect = OperationalError("select", {}, Exception("offline"))

    def override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override
    response = client.get("/api/v1/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok", "version": app.version, "db": "down"}
    assert response.headers["x-request-id"]


def test_not_found(client: TestClient) -> None:
    response = client.get("/missing")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == HTTPStatus.NOT_FOUND


def test_validation(app: FastAPI, client: TestClient) -> None:
    @app.get("/validate")
    def validate(value: int) -> int:
        return value

    response = client.get("/validate", params={"value": "bad"})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "validation_error"


def test_unhandled(app: FastAPI, client: TestClient) -> None:
    @app.get("/fail")
    def fail() -> None:
        raise ValueError("private details")

    response = client.get("/fail")
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "private details" not in response.text


def test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QBANK_ENV", "test")
    monkeypatch.setenv("QBANK_CORS_ORIGINS", '["https://example.com"]')
    monkeypatch.setenv("QBANK_JWT_SECRET", "secret")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.env == "test"
    assert settings.cors_origins == ["https://example.com"]
    assert settings.jwt_secret.get_secret_value() == "secret"
    assert "secret" not in repr(settings.jwt_secret)
    assert isinstance(Settings(), Settings)
    get_settings.cache_clear()


def test_uuid() -> None:
    expected_version = 7
    assert new_uuid().version == expected_version
