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


def test_security_headers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QBANK_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    try:
        response = client.get("/missing")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "same-origin"
        assert response.headers["permissions-policy"] == (
            "camera=(), microphone=(), geolocation=()"
        )
        assert response.headers["strict-transport-security"].startswith("max-age=")
    finally:
        get_settings.cache_clear()


def test_access_log_does_not_include_credentials(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    import logging  # noqa: PLC0415

    client.cookies.set("private", "secret-cookie")
    with caplog.at_level(logging.INFO):
        response = client.post("/missing?password=secret-query")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert '"path": "/missing"' in caplog.text
    assert '"status": 404' in caplog.text
    assert '"request_id":' in caplog.text
    assert '"user_id":' in caplog.text
    assert '"org_id":' in caplog.text
    assert '"duration_ms":' in caplog.text
    access_log = " ".join(
        record.message for record in caplog.records if record.name == "qbank.api.main"
    )
    assert "secret-query" not in access_log
    assert "secret-cookie" not in access_log


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
    assert response.headers["x-frame-options"] == "DENY"


def test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QBANK_ENV", "test")
    monkeypatch.setenv("QBANK_CORS_ORIGINS", '["https://example.com"]')
    monkeypatch.setenv("QBANK_JWT_SECRET", "test-secret-at-least-32-characters-long")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.env == "test"
    assert settings.cors_origins == ["https://example.com"]
    assert settings.jwt_secret.get_secret_value() == "test-secret-at-least-32-characters-long"
    assert "secret" not in repr(settings.jwt_secret)
    assert isinstance(Settings(), Settings)
    get_settings.cache_clear()


def test_uuid() -> None:
    expected_version = 7
    assert new_uuid().version == expected_version


@pytest.mark.parametrize("down", [None, "db", "redis", "storage"])
def test_ready_dependencies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, down: str | None
) -> None:
    from qbank.services import health  # noqa: PLC0415

    for name, function in (
        ("db", "readiness_database_ok"),
        ("redis", "redis_ok"),
        ("storage", "storage_ok"),
    ):
        monkeypatch.setattr(health, function, lambda *, ok=name != down: ok)
    response = client.get("/api/v1/ready")
    assert response.status_code == (503 if down else 200)
    assert response.json() == {
        "status": "down" if down else "ok",
        **{name: "down" if name == down else "ok" for name in ("db", "redis", "storage")},
    }


def test_rate_limit_response_has_retry_after(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import HTTPException  # noqa: PLC0415

    from qbank.api.routers import auth  # noqa: PLC0415

    def reject(*args: object) -> None:
        raise HTTPException(
            429,
            detail={"code": "rate_limited", "message": "Rate limit exceeded"},
            headers={"Retry-After": "42"},
        )

    monkeypatch.setattr(auth, "login_limit", reject)
    response = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "redacted"}
    )
    assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert response.json()["code"] == "rate_limited"
    assert response.headers["Retry-After"] == "42"
