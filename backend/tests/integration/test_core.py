from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from uuid import uuid4

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from qbank.auth import hasher
from qbank.cli import seed_dev
from qbank.config import Settings, get_settings
from qbank.db import get_db
from qbank.models import Organization, Role, User


@pytest.fixture
def setup_core(database: str, app: FastAPI) -> Iterator[dict[str, str]]:
    engine = create_engine(database)
    with Session(engine) as db:
        a, b = Organization(name="A"), Organization(name="B")
        db.add_all([a, b])
        db.flush()
        users = [
            User(
                org_id=org.id,
                email=email,
                name=email,
                role=role,
                password_hash=hasher.hash("password"),
                is_active=active,
            )
            for org, email, role, active in [
                (a, "a@example.com", Role.admin, True),
                (b, "b@example.com", Role.admin, True),
                (a, "editor@example.com", Role.editor, True),
                (a, "teacher@example.com", Role.teacher, True),
                (a, "off@example.com", Role.teacher, False),
            ]
        ]
        db.add_all(users)
        db.commit()
        ids = {u.email: str(u.id) for u in users}
        ids["org"] = str(a.id)

    def override() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield ids
    engine.dispose()


def login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "password"})
    assert response.status_code == HTTPStatus.OK, response.text
    client.headers["X-CSRF-Token"] = client.cookies["qbank_csrf"]


@pytest.mark.integration
def test_auth_roles_and_csrf(setup_core: dict[str, str], client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED
    for email in ("off@example.com", "missing@example.com", "a@example.com"):
        response = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.json()["code"] == "invalid_credentials"
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "off@example.com", "password": "password"}
        ).status_code
        == HTTPStatus.UNAUTHORIZED
    )
    login(client, "teacher@example.com")
    assert client.get("/api/v1/auth/me").json()["role"] == "teacher"
    assert (
        client.post("/api/v1/subjects", json={"name": "A", "language": "ar"}).status_code
        == HTTPStatus.FORBIDDEN
    )
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/v1/auth/logout").json()["code"] == "csrf_failed"
    client.headers["X-CSRF-Token"] = "wrong"
    assert client.post("/api/v1/auth/logout").status_code == HTTPStatus.FORBIDDEN
    client.headers["X-CSRF-Token"] = client.cookies["qbank_csrf"]
    assert client.post("/api/v1/auth/logout").status_code == HTTPStatus.NO_CONTENT
    assert client.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED
    login(client, "editor@example.com")
    assert client.get("/api/v1/users").status_code == HTTPStatus.FORBIDDEN
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": setup_core["a@example.com"],
            "org": setup_core["org"],
            "role": "admin",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": str(uuid4()),
        },
        get_settings().jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    client.cookies.set("qbank_session", expired, domain="testserver.local", path="/")
    assert client.get("/api/v1/auth/me").status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.integration
def test_taxonomy_and_isolation(setup_core: dict[str, str], client: TestClient) -> None:
    login(client, "a@example.com")
    url = "/api/v1"
    subject = client.post(f"{url}/subjects", json={"name": "Arabic", "language": "ar"}).json()
    sid = subject["id"]
    chapters = [
        client.post(f"{url}/subjects/{sid}/chapters", json={"title": str(i)}).json()["id"]
        for i in range(2)
    ]
    lesson = client.post(f"{url}/chapters/{chapters[0]}/lessons", json={"title": "L"}).json()["id"]
    assert client.delete(f"{url}/subjects/{sid}").json()["code"] == "not_empty"
    assert client.delete(f"{url}/chapters/{chapters[0]}").json()["code"] == "not_empty"
    assert (
        client.post(
            f"{url}/subjects/{sid}/chapters/reorder", json={"ids": [chapters[0]]}
        ).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    assert (
        client.post(
            f"{url}/subjects/{sid}/chapters/reorder", json={"ids": chapters[::-1]}
        ).status_code
        == HTTPStatus.NO_CONTENT
    )
    assert [
        c["id"] for c in client.get(f"{url}/subjects/{sid}/tree").json()["chapters"]
    ] == chapters[::-1]
    assert (
        client.patch(f"{url}/lessons/{lesson}", json={"chapter_id": chapters[1]}).json()[
            "chapter_id"
        ]
        == chapters[1]
    )
    assert (
        client.post(
            f"{url}/chapters/{chapters[1]}/lessons/reorder", json={"ids": [lesson]}
        ).status_code
        == HTTPStatus.NO_CONTENT
    )
    assert (
        client.patch(f"{url}/chapters/{chapters[0]}", json={"title": "renamed"}).status_code
        == HTTPStatus.OK
    )
    assert client.patch(f"{url}/subjects/{sid}", json={"grade": "3"}).status_code == HTTPStatus.OK
    assert (
        client.patch(
            f"{url}/users/{setup_core['a@example.com']}", json={"role": "teacher"}
        ).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    login(client, "b@example.com")
    assert client.get(f"{url}/subjects/{sid}").status_code == HTTPStatus.NOT_FOUND
    assert (
        client.patch(f"{url}/chapters/{chapters[0]}", json={"title": "x"}).status_code
        == HTTPStatus.NOT_FOUND
    )
    assert (
        client.patch(f"{url}/lessons/{lesson}", json={"title": "x"}).status_code
        == HTTPStatus.NOT_FOUND
    )
    assert (
        client.patch(f"{url}/users/{setup_core['a@example.com']}", json={"name": "x"}).status_code
        == HTTPStatus.NOT_FOUND
    )
    assert client.get(f"{url}/subjects").json()["items"] == []
    assert len(client.get(f"{url}/users").json()["items"]) == 1
    login(client, "a@example.com")
    assert client.delete(f"{url}/lessons/{lesson}").status_code == HTTPStatus.NO_CONTENT
    for chapter in chapters:
        assert client.delete(f"{url}/chapters/{chapter}").status_code == HTTPStatus.NO_CONTENT
    assert client.delete(f"{url}/subjects/{sid}").status_code == HTTPStatus.NO_CONTENT


@pytest.mark.integration
def test_pagination_and_seed(setup_core: dict[str, str], database: str, client: TestClient) -> None:
    login(client, "a@example.com")
    for name in ("one", "two", "three"):
        assert (
            client.post("/api/v1/subjects", json={"name": name, "language": "en"}).status_code
            == HTTPStatus.CREATED
        )
    first = client.get("/api/v1/subjects?limit=2").json()
    last = client.get(
        "/api/v1/subjects", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert len(first["items"]) == len({"one", "two"})
    assert len(last["items"]) == 1
    assert last["next_cursor"] is None
    assert client.get("/api/v1/subjects?cursor=bad").status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    engine = create_engine(database)
    with Session(engine) as db:
        seed_dev(db)
        seed_dev(db)
        assert (
            len(
                db.scalars(
                    select(Organization).where(Organization.name == "Demo School / مدرسة تجريبية")
                ).all()
            )
            == 1
        )
    engine.dispose()


def test_prod_settings() -> None:
    with pytest.raises(ValueError, match="Production requires"):
        Settings(env="prod")


@pytest.mark.integration
def test_user_management_and_invalid_moves(setup_core: dict[str, str], client: TestClient) -> None:
    login(client, "a@example.com")
    prefix = "/api/v1"
    response = client.post(
        f"{prefix}/users",
        json={"email": "NEW@EXAMPLE.COM", "name": "New", "password": "password", "role": "teacher"},
    )
    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["email"] == "new@example.com"
    uid = response.json()["id"]
    response = client.patch(f"{prefix}/users/{uid}", json={"role": "editor", "is_active": False})
    assert response.json()["role"] == "editor"
    assert response.json()["is_active"] is False
    assert (
        client.post(
            f"{prefix}/users",
            json={
                "email": "new@example.com",
                "name": "New",
                "password": "password",
                "role": "teacher",
            },
        ).status_code
        == HTTPStatus.CONFLICT
    )
    subject_ids = [
        client.post(f"{prefix}/subjects", json={"name": name, "language": "en"}).json()["id"]
        for name in ("A", "B")
    ]
    chapter_ids = [
        client.post(f"{prefix}/subjects/{sid}/chapters", json={"title": "C"}).json()["id"]
        for sid in subject_ids
    ]
    lesson = client.post(f"{prefix}/chapters/{chapter_ids[0]}/lessons", json={"title": "L"}).json()[
        "id"
    ]
    response = client.patch(f"{prefix}/lessons/{lesson}", json={"chapter_id": chapter_ids[1]})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "invalid_move"
    assert (
        client.post(
            f"{prefix}/chapters/{chapter_ids[0]}/lessons/reorder", json={"ids": [lesson, lesson]}
        ).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )


@pytest.mark.integration
def test_login_rehashes_password(
    setup_core: dict[str, str], database: str, client: TestClient
) -> None:
    engine = create_engine(database)
    old_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("password")
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == "a@example.com"))
        assert user is not None
        user.password_hash = old_hash
        db.commit()
    login(client, "a@example.com")
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == "a@example.com"))
        assert user is not None
        assert user.password_hash != old_hash
        assert not hasher.check_needs_rehash(user.password_hash)
    engine.dispose()
