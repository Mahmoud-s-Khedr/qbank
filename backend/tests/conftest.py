import os
from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Must run before any qbank import: importing qbank.api.main builds the app and caches Settings.
os.environ["QBANK_ENV"] = "test"
# Keep test state (rate-limit counters, broker keys) out of the developer's Redis DB 0.
os.environ["QBANK_REDIS_URL"] = (
    os.environ.get("QBANK_REDIS_URL", "redis://localhost:26379/0").rsplit("/", 1)[0] + "/15"
)
os.environ["QBANK_LLM_MODE"] = "fake"
# Shared Redis persists across integration databases; dedicated rate tests use explicit limits.
os.environ["QBANK_RATE_LOGIN_IP"] = "10000"
os.environ["QBANK_RATE_LOGIN_EMAIL"] = "10000"
os.environ["QBANK_JWT_SECRET"] = "test-only-secret-at-least-32-bytes-long"  # noqa: S105 -- test-only value

from qbank.api.main import create_app
from qbank.config import get_settings
from qbank.db import reset_engine
from qbank.export import pdf as pdf_export


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = make_url(get_settings().database_url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    name = f"qbank_test_{uuid4().hex}"
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    test_url = url.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("QBANK_DATABASE_URL", test_url)
    reset_engine()
    get_settings.cache_clear()
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "head")
        yield test_url
    finally:
        # Close pooled connections before the database is dropped, or they leak (ResourceWarning).
        reset_engine()
        get_settings.cache_clear()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: resource-intensive integration test")


@pytest.fixture
def fixture_pdf() -> Callable[[str], Path]:
    def resolve(name: str) -> Path:
        path = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs" / name
        if not path.is_file():
            pytest.skip(f"fixture {name} not available")
        return path

    return resolve


@pytest.fixture(scope="session", autouse=True)
def _close_pdf_browser() -> Iterator[None]:
    """Stop the shared Chromium (if a test started it) so the run ends without stray processes."""
    yield
    pdf_export.shutdown()
