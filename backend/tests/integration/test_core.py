from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from qbank.auth import hasher
from qbank.cli import seed_dev
from qbank.config import Settings, get_settings
from qbank.db import get_db, get_engine
from qbank.models import Organization, Role, SourceStatus, User
from qbank.pipeline import orchestrator
from qbank.services import auth
from qbank.services.taxonomy import tree
from qbank.storage import get_store
from qbank.worker import render_page, render_source


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


@pytest.mark.integration
def test_created_email_is_normalized_and_can_login(
    setup_core: dict[str, str], client: TestClient
) -> None:
    login(client, "a@example.com")
    for email in ("bad", "a@", "@example.com", "x y@example.com"):
        response = client.post(
            "/api/v1/users",
            json={"email": email, "name": "New", "password": "password", "role": "teacher"},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    response = client.post(
        "/api/v1/users",
        json={"email": "  Foo@X.com  ", "name": "New", "password": "password", "role": "teacher"},
    )
    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["email"] == "foo@x.com"
    assert client.post("/api/v1/auth/logout").status_code == HTTPStatus.NO_CONTENT
    login(client, "FOO@x.COM")
    assert client.get("/api/v1/auth/me").json()["email"] == "foo@x.com"


@pytest.mark.integration
def test_unknown_user_performs_dummy_password_check(
    setup_core: dict[str, str], client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked: list[str] = []
    original = auth.verify_password

    def verify(password: str, encoded: str) -> bool:
        checked.append(encoded)
        return original(password, encoded)

    monkeypatch.setattr(auth, "verify_password", verify)
    response = client.post(
        "/api/v1/auth/login", json={"email": "missing@example.com", "password": "password"}
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert checked == [auth.DUMMY_HASH]
    assert not auth.hasher.check_needs_rehash(checked[0])


@pytest.mark.integration
def test_tree_query_count_is_constant(
    setup_core: dict[str, str], database: str, client: TestClient
) -> None:
    login(client, "a@example.com")
    sid = client.post("/api/v1/subjects", json={"name": "Tree", "language": "ar"}).json()["id"]
    for i in range(4):
        chapter = client.post(f"/api/v1/subjects/{sid}/chapters", json={"title": str(i)}).json()[
            "id"
        ]
        client.post(f"/api/v1/chapters/{chapter}/lessons", json={"title": "L"})
    engine = create_engine(database)
    statements: list[str] = []

    def count_queries(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", count_queries)
    with Session(engine) as db:
        result = tree(UUID(sid), db, UUID(setup_core["org"]))
        assert len(cast(list[object], result["chapters"])) == len(range(4))
    event.remove(engine, "before_cursor_execute", count_queries)
    engine.dispose()
    assert len(statements) == len(("subject", "chapters", "lessons"))


@pytest.mark.integration
def test_upload_render_and_images(
    setup_core: dict[str, str],
    database: str,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setenv("QBANK_STORAGE_BACKEND", "local")
    monkeypatch.setenv("QBANK_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("QBANK_RENDER_DPI_DISPLAY", "24")
    monkeypatch.setenv("QBANK_RENDER_DPI_HIRES", "36")
    get_settings.cache_clear()
    get_store.cache_clear()
    get_engine.cache_clear()
    queued: list[str] = []
    monkeypatch.setattr(
        orchestrator,
        "STAGES",
        [orchestrator.Stage("render", queued.append, SourceStatus.rendering)],
    )
    pages: list[int] = []
    monkeypatch.setattr(render_page, "send", lambda sid, number: pages.append(number))
    login(client, "a@example.com")
    subject = client.post("/api/v1/subjects", json={"name": "Render", "language": "ar"}).json()[
        "id"
    ]
    pdf = Path("../fixtures/pdfs/test-2027.pdf").read_bytes()
    response = client.post(
        "/api/v1/sources",
        data={"subject_id": subject, "title": "Book"},
        files={"file": ("book.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == HTTPStatus.ACCEPTED, response.text
    job_id = response.json()["job_id"]
    sid = response.json()["source"]["id"]
    assert queued == [sid]
    assert client.delete(f"/api/v1/subjects/{subject}").status_code == HTTPStatus.CONFLICT
    render_source.fn(sid)
    assert pages == [1, 2]
    for number in pages:
        render_page.fn(sid, number)
    response = client.get(f"/api/v1/sources/{sid}")
    assert response.json()["status"] == "ready"
    assert response.json()["page_counts"] == {"rendered": 2}
    render_page.fn(sid, 1)
    render_source.fn(sid)
    assert len(client.get(f"/api/v1/sources/{sid}/pages").json()) == len(pages)
    assert (
        len(
            client.get("/api/v1/sources", params={"subject_id": subject, "status": "ready"}).json()[
                "items"
            ]
        )
        == 1
    )
    assert (
        client.get(f"/api/v1/sources/{sid}/pages/1/image?variant=hires").headers["content-type"]
        == "image/png"
    )
    image = client.get(f"/api/v1/sources/{sid}/pages/1/image")
    assert image.headers["content-type"] == "image/webp"
    assert (
        client.get(
            f"/api/v1/sources/{sid}/pages/1/image", headers={"If-None-Match": image.headers["etag"]}
        ).status_code
        == HTTPStatus.NOT_MODIFIED
    )
    assert "event: progress" in client.get(f"/api/v1/sources/{sid}/events").text
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "ready"
    login(client, "b@example.com")
    assert client.get(f"/api/v1/sources/{sid}").status_code == HTTPStatus.NOT_FOUND
    assert client.get(f"/api/v1/sources/{sid}/pages/1/image").status_code == HTTPStatus.NOT_FOUND
    login(client, "a@example.com")
    assert client.delete(f"/api/v1/sources/{sid}").status_code == HTTPStatus.NO_CONTENT
    assert client.get(f"/api/v1/sources/{sid}").status_code == HTTPStatus.NOT_FOUND
    assert not list(Path(str(tmp_path)).rglob("*.pdf"))
    get_engine.cache_clear()
    get_store.cache_clear()
    get_settings.cache_clear()


@pytest.mark.integration
def test_upload_validation_and_roles(
    setup_core: dict[str, str], client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QBANK_STORAGE_BACKEND", "local")
    monkeypatch.setenv("QBANK_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("QBANK_MAX_UPLOAD_MB", "0")
    get_settings.cache_clear()
    get_store.cache_clear()
    login(client, "a@example.com")
    subject = client.post("/api/v1/subjects", json={"name": "Input", "language": "ar"}).json()["id"]
    data = {"subject_id": subject, "title": "Book"}
    bad = client.post("/api/v1/sources", data=data, files={"file": ("bad.pdf", b"bad")})
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad.json()["code"] == "invalid_pdf"
    large = client.post("/api/v1/sources", data=data, files={"file": ("large.pdf", b"%PDF-1")})
    assert large.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert large.json()["code"] == "file_too_large"
    login(client, "teacher@example.com")
    assert (
        client.post("/api/v1/sources", data=data, files={"file": ("x.pdf", b"%PDF-1")}).status_code
        == HTTPStatus.FORBIDDEN
    )
    login(client, "b@example.com")
    assert (
        client.post("/api/v1/sources", data=data, files={"file": ("x.pdf", b"%PDF-1")}).status_code
        == HTTPStatus.NOT_FOUND
    )
    get_store.cache_clear()
    get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.slow
def test_damaged_pdf_render(
    setup_core: dict[str, str], client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QBANK_STORAGE_BACKEND", "local")
    monkeypatch.setenv("QBANK_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("QBANK_RENDER_DPI_DISPLAY", "12")
    monkeypatch.setenv("QBANK_RENDER_DPI_HIRES", "12")
    get_settings.cache_clear()
    get_store.cache_clear()
    get_engine.cache_clear()
    monkeypatch.setattr(
        orchestrator,
        "STAGES",
        [orchestrator.Stage("render", lambda sid: None, SourceStatus.rendering)],
    )
    pages: list[int] = []
    monkeypatch.setattr(render_page, "send", lambda sid, number: pages.append(number))
    login(client, "a@example.com")
    subject = client.post("/api/v1/subjects", json={"name": "Damaged", "language": "ar"}).json()[
        "id"
    ]
    pdf = Path("../fixtures/pdfs/test-exams.pdf").read_bytes()
    response = client.post(
        "/api/v1/sources",
        data={"subject_id": subject, "title": "Damaged"},
        files={"file": ("damaged.pdf", pdf)},
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    sid = response.json()["source"]["id"]
    render_source.fn(sid)
    for number in pages:
        render_page.fn(sid, number)
    result = client.get(f"/api/v1/sources/{sid}/pages").json()
    assert all(page["status"] == "rendered" for page in result[:60])
    assert all(page["status"] == "failed" and page["error"] for page in result[60:])
    assert client.get(f"/api/v1/sources/{sid}").json()["status"] == "ready"
    get_engine.cache_clear()
    get_store.cache_clear()
    get_settings.cache_clear()


@pytest.mark.integration
def test_stage_transition_compare_and_set(
    setup_core: dict[str, str], client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415 -- test-only concurrency helper

    monkeypatch.setenv("QBANK_STORAGE_BACKEND", "local")
    monkeypatch.setenv("QBANK_STORAGE_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()
    get_store.cache_clear()
    get_engine.cache_clear()
    monkeypatch.setattr(
        orchestrator,
        "STAGES",
        [orchestrator.Stage("render", lambda sid: None, SourceStatus.rendering)],
    )
    login(client, "a@example.com")
    subject = client.post("/api/v1/subjects", json={"name": "CAS", "language": "ar"}).json()["id"]
    response = client.post(
        "/api/v1/sources",
        data={"subject_id": subject, "title": "CAS"},
        files={"file": ("x.pdf", b"%PDF-1")},
    )
    sid = UUID(response.json()["source"]["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: orchestrator.advance(sid, "render"), range(2)))
    assert sorted(results) == [False, True]
    get_engine.cache_clear()
    get_store.cache_clear()
    get_settings.cache_clear()


@pytest.mark.integration
def test_source_exceeding_page_limit_fails(
    setup_core: dict[str, str], client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QBANK_STORAGE_BACKEND", "local")
    monkeypatch.setenv("QBANK_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("QBANK_MAX_PAGES", "1")
    get_settings.cache_clear()
    get_store.cache_clear()
    get_engine.cache_clear()
    monkeypatch.setattr(
        orchestrator,
        "STAGES",
        [orchestrator.Stage("render", lambda sid: None, SourceStatus.rendering)],
    )
    login(client, "a@example.com")
    subject = client.post("/api/v1/subjects", json={"name": "Limit", "language": "ar"}).json()["id"]
    pdf = Path("../fixtures/pdfs/test-2027.pdf").read_bytes()
    response = client.post(
        "/api/v1/sources",
        data={"subject_id": subject, "title": "Limit"},
        files={"file": ("book.pdf", pdf)},
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    sid = response.json()["source"]["id"]
    job_id = response.json()["job_id"]
    render_source.fn(sid)
    source = client.get(f"/api/v1/sources/{sid}").json()
    assert source["status"] == "failed"
    assert source["error"] == "too_many_pages"
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "failed"
    get_engine.cache_clear()
    get_store.cache_clear()
    get_settings.cache_clear()
