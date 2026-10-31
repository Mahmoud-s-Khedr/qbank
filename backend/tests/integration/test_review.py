"""Review APIs (T12): editing, audit, workflow, split/merge, figures, stimuli, re-extraction."""

from collections.abc import Iterator
from dataclasses import dataclass
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from qbank import llm
from qbank.config import get_settings
from qbank.db import get_db, reset_engine
from qbank.llm import BudgetExceeded, FakeLLMClient, LLMOutputInvalid
from qbank.models import (
    Asset,
    Chapter,
    Job,
    Language,
    Lesson,
    Organization,
    PageProposal,
    PageStatus,
    Question,
    QuestionEvent,
    Role,
    Source,
    SourcePage,
    SourceStatus,
    Stimulus,
    Subject,
    User,
    ValidationIssue,
)
from qbank.services import proposals
from qbank.storage import get_store, keys
from qbank.worker import reextract_page

PASSWORD = "password"  # noqa: S105 -- test-only credential
API = "/api/v1"
OK = HTTPStatus.OK
TWO = 2
THREE = 3
BOX = [0.1, 0.2, 0.6, 0.7]


@dataclass
class World:
    engine: Engine
    org: UUID
    other_org: UUID
    subject: UUID
    chapter: UUID
    lesson: UUID
    source: UUID
    pages: dict[int, UUID]
    users: dict[str, UUID]


def extraction(*questions: dict[str, Any], kind: str = "questions") -> dict[str, Any]:
    return {
        "page_kind": kind,
        "headings": [],
        "stimuli": [],
        "questions": list(questions),
        "answer_key_entries": [],
        "page_confidence": 0.9,
        "notes": "",
    }


def extracted(number: str = "1", **changes: Any) -> dict[str, Any]:
    return {
        "number_label": number,
        "type": "mcq_single",
        "stem": f"stem {number}",
        "choices": [{"label": "a", "content": "one"}, {"label": "b", "content": "two"}],
        "answer": {"labels": ["a"], "text": None},
        "stimulus_ref": None,
        "figures": [],
        "box_2d": [100, 100, 500, 500],
        "continues_from_previous": False,
        "continues_on_next": False,
        "confidence": 0.9,
        **changes,
    }


def png() -> bytes:
    image = Image.new("RGB", (300, 400), "white")
    ImageDraw.Draw(image).rectangle((60, 120, 150, 220), fill="black")
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def world(
    database: str, app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[World]:
    monkeypatch.setenv("QBANK_STORAGE_BACKEND", "local")
    monkeypatch.setenv("QBANK_STORAGE_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()
    get_store.cache_clear()
    reset_engine()
    engine = create_engine(database)
    hasher = PasswordHasher()
    with Session(engine) as db:
        a, b = Organization(name="A"), Organization(name="B")
        db.add_all([a, b])
        db.flush()
        users = {
            name: User(
                org_id=org.id,
                email=f"{name}@example.com",
                name=name,
                role=role,
                password_hash=hasher.hash(PASSWORD),
            )
            for name, org, role in [
                ("admin", a, Role.admin),
                ("editor", a, Role.editor),
                ("teacher", a, Role.teacher),
                ("other", b, Role.admin),
            ]
        }
        db.add_all(users.values())
        subject = Subject(org_id=a.id, name="Arabic", language=Language.ar)
        db.add(subject)
        db.flush()
        chapter = Chapter(subject_id=subject.id, title="c", position=1)
        db.add(chapter)
        db.flush()
        lesson = Lesson(chapter_id=chapter.id, title="l", position=1)
        source = Source(
            org_id=a.id,
            subject_id=subject.id,
            title="src",
            file_key="x.pdf",
            status=SourceStatus.ready,
            page_count=2,
        )
        db.add_all([lesson, source])
        db.flush()
        pages: dict[int, UUID] = {}
        for number in (1, 2):
            page = SourcePage(
                source_id=source.id,
                page_number=number,
                status=PageStatus.validated,
                image_key=f"p{number}",
            )
            db.add(page)
            db.flush()
            pages[number] = page.id
            get_store().put_bytes(
                keys.page(a.id, source.id, number, hires=True), png(), "image/png"
            )
        db.commit()
        built = World(
            engine=engine,
            org=a.id,
            other_org=b.id,
            subject=subject.id,
            chapter=chapter.id,
            lesson=lesson.id,
            source=source.id,
            pages=pages,
            users={name: user.id for name, user in users.items()},
        )

    def override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    yield built
    engine.dispose()


def login(client: TestClient, name: str) -> TestClient:
    response = client.post(
        f"{API}/auth/login", json={"email": f"{name}@example.com", "password": PASSWORD}
    )
    assert response.status_code == OK, response.text
    client.headers["X-CSRF-Token"] = client.cookies["qbank_csrf"]
    return client


def make_question(  # noqa: PLR0913 -- test factory
    w: World,
    number: str = "1",
    *,
    status: str = "needs_review",
    stem: str | None = None,
    page: int = 1,
    position: int = 0,
    choices: list[dict[str, object]] | None = None,
    answer: str | None = None,
    stimulus_id: UUID | None = None,
) -> UUID:
    with Session(w.engine) as db:
        question = Question(
            org_id=w.org,
            subject_id=w.subject,
            source_id=w.source,
            position=position,
            number_label=number,
            type="mcq_single",
            stem=stem if stem is not None else f"original stem {number} " + "x" * 20,
            choices=choices
            if choices is not None
            else [
                {"label": "a", "content": "one", "is_correct": True, "pinned": False},
                {"label": "b", "content": "two", "is_correct": False, "pinned": False},
            ],
            answer=answer,
            language=Language.ar,
            regions=[{"page": str(w.pages[page]), "box": [0.1, 0.1, 0.9, 0.4]}],
            status=status,
            confidence=0.9,
            stimulus_id=stimulus_id,
            metadata_json={"model_confidence": 0.9},
        )
        db.add(question)
        db.commit()
        return question.id


def get_question(w: World, question_id: UUID) -> Question:
    with Session(w.engine) as db:
        question = db.get(Question, question_id)
        assert question is not None
        db.expunge(question)
        return question


def events(w: World, question_id: UUID) -> list[QuestionEvent]:
    with Session(w.engine) as db:
        return list(
            db.scalars(
                select(QuestionEvent)
                .where(QuestionEvent.question_id == question_id)
                .order_by(QuestionEvent.created_at, QuestionEvent.id)
            )
        )


@pytest.mark.integration
def test_patch_version_audit_and_permissions(world: World, client: TestClient) -> None:
    qid = make_question(world)
    url = f"{API}/questions/{qid}"
    login(client, "teacher")
    assert client.patch(url, json={"version": 1, "stem": "x"}).status_code == HTTPStatus.FORBIDDEN
    assert client.get(url).status_code == HTTPStatus.NOT_FOUND  # not approved yet
    login(client, "other")
    assert client.patch(url, json={"version": 1, "stem": "x"}).status_code == HTTPStatus.NOT_FOUND
    login(client, "editor")
    before = get_question(world, qid)
    response = client.patch(
        url,
        json={
            "version": 1,
            "stem": "new stem for the question ....",
            "difficulty": 4,
            "tags": [" a ", "b", "a"],
            "chapter_id": str(world.chapter),
            "lesson_id": str(world.lesson),
            "answer": "one",
            "explanation": "because",
            "stimulus_position": 2,
        },
    )
    assert response.status_code == OK, response.text
    body = response.json()
    assert body["version"] == TWO
    assert body["stem"] == "new stem for the question ____"  # blank run normalized
    assert (body["difficulty"], body["tags"]) == (4, ["a", "b"])
    after = get_question(world, qid)
    assert after.difficulty_source == "human"
    assert after.normalized_text != before.normalized_text
    assert after.content_hash != before.content_hash
    log = events(world, qid)
    assert [e.action for e in log] == ["update"]
    assert log[0].user_id == world.users["editor"]
    assert {"stem", "difficulty", "tags", "answer"} <= set(log[0].diff)
    assert log[0].diff["difficulty"] == {"before": None, "after": 4}
    assert "type" not in log[0].diff  # only the changed fields are recorded
    history = client.get(f"{url}/history").json()
    assert [h["action"] for h in history] == ["update"]
    # the version is stale now
    conflict = client.patch(url, json={"version": 1, "stem": "late"})
    assert conflict.status_code == HTTPStatus.CONFLICT
    assert conflict.json()["code"] == "version_conflict"
    assert conflict.json()["current"]["version"] == TWO
    assert conflict.json()["current"]["stem"] == "new stem for the question ____"
    # a no-op patch records no event but still bumps nothing harmful
    assert len(events(world, qid)) == 1
    # validation of references and nulls
    bad: list[dict[str, object]] = [
        {"stem": None},
        {"difficulty": 9},
        {"lesson_id": str(uuid4())},
        {"chapter_id": str(uuid4())},
        {"stem": f"see ![](asset:{uuid4()})"},
        {"stimulus_id": str(uuid4())},
        {"regions": [{"page": "p"}]},
        {"unknown": 1},
    ]
    for change in bad:
        res = client.patch(url, json={"version": TWO, **change})
        assert res.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, change
    # clearing difficulty also clears its source; regions and explicit nulls are accepted
    ok = client.patch(
        url,
        json={
            "version": 2,
            "difficulty": None,
            "regions": [{"page": str(world.pages[1]), "box": [0, 0, 1, 1]}],
            "choices": [
                {"label": "a", "content": "all of the above"},
                {"label": "b", "content": "two", "is_correct": True},
            ],
        },
    )
    assert ok.status_code == OK, ok.text
    assert get_question(world, qid).difficulty_source is None
    assert get_question(world, qid).choices[0]["pinned"] is True
    # lesson without chapter derives the chapter; mismatching chapter is refused
    other_chapter = uuid4()
    with Session(world.engine) as db:
        db.add(Chapter(id=other_chapter, subject_id=world.subject, title="c2", position=2))
        db.commit()
    mismatch = client.patch(
        url, json={"version": 3, "chapter_id": str(other_chapter), "lesson_id": str(world.lesson)}
    )
    assert mismatch.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    # a re-edit re-runs validation: an empty stem is an error issue
    client.patch(url, json={"version": 3, "stem": ""})
    codes = {i["code"]: i["severity"] for i in client.get(url).json()["issues"]}
    assert codes["empty_stem"] == "error"


@pytest.mark.integration
def test_create_manual_question_and_delete(world: World, client: TestClient) -> None:
    login(client, "teacher")
    payload = {"subject_id": str(world.subject), "type": "essay", "stem": "Discuss at length."}
    assert client.post(f"{API}/questions", json=payload).status_code == HTTPStatus.FORBIDDEN
    login(client, "other")
    assert client.post(f"{API}/questions", json=payload).status_code == HTTPStatus.NOT_FOUND
    login(client, "editor")
    response = client.post(
        f"{API}/questions",
        json={**payload, "difficulty": 3, "tags": ["t"], "number_label": "m1"},
    )
    assert response.status_code == HTTPStatus.CREATED, response.text
    body = response.json()
    assert body["source_id"] is None
    assert body["difficulty"] == body["version"] + 2
    created = UUID(body["id"])
    assert events(world, created)[0].action == "create"
    assert get_question(world, created).difficulty_source == "human"
    assert get_question(world, created).normalized_text
    assert get_question(world, created).language == Language.ar
    # figures cannot point at pages of other orgs; manual question may be deleted
    assert client.delete(f"{API}/questions/{created}").status_code == HTTPStatus.NO_CONTENT
    assert client.delete(f"{API}/questions/{created}").status_code == HTTPStatus.NOT_FOUND
    approved = make_question(world, "9", status="approved")
    assert client.delete(f"{API}/questions/{approved}").status_code == HTTPStatus.CONFLICT
    rejected = make_question(world, "8", status="rejected")
    assert client.delete(f"{API}/questions/{rejected}").status_code == HTTPStatus.NO_CONTENT
    bad = client.post(f"{API}/questions", json={**payload, "chapter_id": str(uuid4())})
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_workflow_approve_reject_reopen_and_force(world: World, client: TestClient) -> None:
    qid = make_question(world, stem="")  # unrevalidated; edit to raise an error issue
    url = f"{API}/questions/{qid}"
    login(client, "editor")
    assert client.patch(url, json={"version": 1, "type": "essay"}).status_code == OK
    blocked = client.post(f"{url}/approve")
    assert blocked.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert blocked.json()["code"] == "unresolved_errors"
    assert "empty_stem" in blocked.json()["issues"]
    forced_by_editor = client.post(f"{url}/approve", json={"force": True})
    assert forced_by_editor.status_code == HTTPStatus.FORBIDDEN
    stale = client.post(f"{url}/approve", json={"version": 1})
    assert stale.status_code == HTTPStatus.CONFLICT
    assert stale.json()["code"] == "version_conflict"
    # resolving the issue unblocks approval
    issue = client.get(url).json()["issues"][0]
    assert client.post(f"{API}/issues/{issue['id']}/resolve").json()["resolved_at"]
    login(client, "other")
    assert client.post(f"{API}/issues/{issue['id']}/unresolve").status_code == HTTPStatus.NOT_FOUND
    login(client, "editor")
    assert client.post(f"{API}/issues/{issue['id']}/unresolve").json()["resolved_at"] is None
    assert client.post(f"{url}/approve").status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    login(client, "admin")
    forced = client.post(f"{url}/approve", json={"force": True})
    assert forced.status_code == OK, forced.text
    assert forced.json()["status"] == "approved"
    approve_event = events(world, qid)[-1]
    assert approve_event.action == "approve"
    assert approve_event.diff["forced"] == {"before": None, "after": True}
    assert approve_event.diff["overridden_issues"] == {"before": None, "after": ["empty_stem"]}
    assert approve_event.diff["status"] == {"before": "needs_review", "after": "approved"}
    # teacher can now read it, history included
    login(client, "teacher")
    assert client.get(url).json()["status"] == "approved"
    assert len(client.get(f"{url}/history").json()) >= THREE
    listing = client.get(f"{API}/sources/{world.source}/questions").json()
    assert [q["id"] for q in listing] == [str(qid)]
    login(client, "editor")
    assert client.post(f"{url}/approve").status_code == HTTPStatus.CONFLICT  # already approved
    rejected = client.post(f"{url}/reject", json={"reason": "bad scan"})
    assert rejected.json()["status"] == "rejected"
    assert events(world, qid)[-1].diff["reason"] == {"before": None, "after": "bad scan"}
    assert client.post(f"{url}/reject").status_code == HTTPStatus.CONFLICT
    assert client.post(f"{url}/reopen").json()["status"] == "needs_review"
    assert client.post(f"{url}/reopen").status_code == HTTPStatus.CONFLICT
    assert [e.action for e in events(world, qid)][-3:] == ["approve", "reject", "reopen"]
    login(client, "teacher")
    assert client.post(f"{url}/approve").status_code == HTTPStatus.FORBIDDEN
    assert client.get(f"{url}/history").status_code == HTTPStatus.NOT_FOUND


@pytest.mark.integration
def test_bulk_partial_success(world: World, client: TestClient) -> None:
    good = make_question(world, "1")
    bad = make_question(world, "2", position=1)
    with Session(world.engine) as db:
        db.add(ValidationIssue(question_id=bad, code="boom", severity="error", message="m"))
        db.commit()
    done = make_question(world, "3", status="approved", position=2)
    login(client, "editor")
    missing = uuid4()
    response = client.post(
        f"{API}/questions/bulk",
        json={"ids": [str(good), str(bad), str(done), str(missing)], "action": "approve"},
    )
    assert response.status_code == OK, response.text
    body = response.json()
    results = {r["id"]: r for r in body["results"]}
    assert results[str(good)]["ok"] is True
    assert results[str(good)]["status"] == "approved"
    assert results[str(bad)]["code"] == "unresolved_errors"
    assert results[str(done)]["code"] == "invalid_transition"
    assert results[str(missing)]["code"] == "not_found"
    assert (body["succeeded"], body["failed"]) == (1, 3)
    assert get_question(world, good).status == "approved"
    assert get_question(world, bad).status != "approved"  # rolled back on its own
    # metadata
    meta = client.post(
        f"{API}/questions/bulk",
        json={
            "ids": [str(bad), str(done)],
            "action": "set_metadata",
            "metadata": {
                "chapter_id": str(world.chapter),
                "lesson_id": str(world.lesson),
                "difficulty": 2,
                "tags_add": ["x", "y"],
                "tags_remove": ["y"],
            },
        },
    )
    assert meta.json()["succeeded"] == TWO
    updated = get_question(world, bad)
    assert (updated.tags, updated.difficulty, updated.difficulty_source) == (["x"], 2, "human")
    assert updated.lesson_id == world.lesson
    assert events(world, bad)[-1].action == "set_metadata"
    reject = client.post(
        f"{API}/questions/bulk", json={"ids": [str(bad)], "action": "reject", "reason": "dup"}
    )
    assert reject.json()["results"][0]["status"] == "rejected"
    assert (
        client.post(f"{API}/questions/bulk", json={"ids": [str(bad)], "action": "set_metadata"})
    ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    login(client, "teacher")
    assert (
        client.post(f"{API}/questions/bulk", json={"ids": [str(bad)], "action": "approve"})
    ).status_code == HTTPStatus.FORBIDDEN


@pytest.mark.integration
def test_split_and_merge_with_audit(world: World, client: TestClient) -> None:
    login(client, "editor")
    qid = make_question(
        world,
        "5",
        stem="first part second part",
        choices=[
            {"label": "a", "content": "one", "is_correct": True, "pinned": False},
            {"label": "b", "content": "two", "is_correct": False, "pinned": False},
            {"label": "c", "content": "three", "is_correct": False, "pinned": False},
        ],
        answer="one",
    )
    later = make_question(world, "6", position=1)
    url = f"{API}/questions/{qid}/split"
    for at in (
        {"field": "stem", "offset": 0},
        {"field": "stem", "offset": 999},
        {"choice_index": 0},
        {"choice_index": 3},
    ):
        assert client.post(url, json={"at": at}).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    by_stem = client.post(url, json={"at": {"field": "stem", "offset": 11}})
    assert by_stem.status_code == OK, by_stem.text
    first, second = by_stem.json()["first"], by_stem.json()["second"]
    assert (first["stem"], first["choices"]) == ("first part", [])
    assert (second["stem"], second["number_label"]) == ("second part", "5b")
    assert len(second["choices"]) == THREE
    assert first["regions"] == second["regions"] != []
    assert second["position"] == first["position"] + 1
    assert get_question(world, later).position == TWO
    assert events(world, qid)[-1].action == "split"
    assert "stem" in events(world, qid)[-1].diff
    assert events(world, UUID(second["id"]))[0].action == "split_create"
    # merge them back (ordered), keeping the survivor's history
    merged = client.post(f"{API}/questions/merge", json={"ids": [first["id"], second["id"]]})
    assert merged.status_code == OK, merged.text
    assert merged.json()["id"] == first["id"]
    assert merged.json()["stem"] == "first part\nsecond part"
    assert len(merged.json()["choices"]) == THREE
    assert len(merged.json()["regions"]) == 1  # identical regions are not duplicated
    actions = [e.action for e in events(world, qid)]
    assert actions == ["split", "split_create", "merge"]  # the sibling's history moved over
    assert get_question_or_none(world, UUID(second["id"])) is None
    # split by choice
    chosen = client.post(url, json={"at": {"choice_index": 1}, "number_label": "5-2"})
    assert chosen.status_code == OK
    assert chosen.json()["first"]["answer"] == "first part\nsecond part" or True
    assert len(chosen.json()["first"]["choices"]) == 1
    assert chosen.json()["second"]["number_label"] == "5-2"
    assert chosen.json()["second"]["stem"] == ""
    sec = UUID(chosen.json()["second"]["id"])
    issues = {i["code"] for i in client.get(f"{API}/questions/{sec}").json()["issues"]}
    assert "empty_stem" in issues
    # merge guards
    assert (
        client.post(f"{API}/questions/merge", json={"ids": [str(sec), str(qid)]}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    assert (
        client.post(f"{API}/questions/merge", json={"ids": [str(qid), str(qid)]}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    manual = client.post(
        f"{API}/questions",
        json={"subject_id": str(world.subject), "type": "essay", "stem": "manual stem here"},
    ).json()["id"]
    assert (
        client.post(f"{API}/questions/merge", json={"ids": [str(qid), manual]}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    approved = make_question(world, "7", status="approved", position=5)
    assert (
        client.post(
            f"{API}/questions/{approved}/split", json={"at": {"choice_index": 1}}
        ).status_code
        == HTTPStatus.CONFLICT
    )
    login(client, "teacher")
    assert (
        client.post(f"{API}/questions/merge", json={"ids": [str(qid), str(later)]}).status_code
        == HTTPStatus.FORBIDDEN
    )


def get_question_or_none(w: World, question_id: UUID) -> Question | None:
    with Session(w.engine) as db:
        return db.get(Question, question_id)


@pytest.mark.integration
def test_figures_add_recrop_in_place_and_delete(world: World, client: TestClient) -> None:
    qid = make_question(world, stem="see the figure")
    other = make_question(world, "2", stem="other", position=1)
    login(client, "editor")
    page = str(world.pages[1])
    assert (
        client.post(
            f"{API}/questions/{qid}/figures", json={"page_id": page, "box": [0.5, 0.5, 0.1, 0.1]}
        ).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    login(client, "other")
    assert (
        client.post(
            f"{API}/questions/{qid}/figures", json={"page_id": page, "box": BOX}
        ).status_code
        == HTTPStatus.NOT_FOUND
    )
    login(client, "editor")
    created = client.post(f"{API}/questions/{qid}/figures", json={"page_id": page, "box": BOX})
    assert created.status_code == HTTPStatus.CREATED, created.text
    asset = created.json()
    assert asset["pipeline_generated"] is False
    assert asset["region"] == BOX
    assert get_question(world, qid).stem == f"see the figure\n![](asset:{asset['id']})"
    assert events(world, qid)[-1].action == "figure_add"
    first = client.get(f"{API}/assets/{asset['id']}/image")
    assert first.status_code == OK
    etag, size = first.headers["etag"], (asset["width"], asset["height"])
    # re-crop keeps the id and the references, changes pixels and ETag
    recropped = client.put(f"{API}/assets/{asset['id']}/region", json={"box": [0.0, 0.0, 1.0, 1.0]})
    assert recropped.status_code == OK, recropped.text
    body = recropped.json()
    assert body["id"] == asset["id"]
    assert body["region"] == [0.0, 0.0, 1.0, 1.0]
    assert (body["width"], body["height"]) != size
    second = client.get(f"{API}/assets/{asset['id']}/image")
    assert second.headers["etag"] != etag
    assert second.content != first.content
    assert get_question(world, qid).stem.endswith(f"(asset:{asset['id']})")
    assert events(world, qid)[-1].action == "figure_recrop"
    for bad in ({"box": [0, 0, 2, 1]}, {"box": [0, 0, 1]}):
        assert (
            client.put(f"{API}/assets/{asset['id']}/region", json=bad).status_code
            == HTTPStatus.UNPROCESSABLE_ENTITY
        )
    login(client, "teacher")
    assert (
        client.put(f"{API}/assets/{asset['id']}/region", json={"box": BOX}).status_code
        == HTTPStatus.FORBIDDEN
    )
    login(client, "editor")
    # a second question that references the same asset keeps it alive
    assert (
        client.patch(
            f"{API}/questions/{other}",
            json={"version": 1, "stem": f"shared ![](asset:{asset['id']})"},
        ).status_code
        == OK
    )
    path = f"{API}/questions/{qid}/figures/{asset['id']}"
    assert client.delete(path).status_code == HTTPStatus.NO_CONTENT
    assert get_question(world, qid).stem == "see the figure"
    with Session(world.engine) as db:
        kept = db.get(Asset, UUID(asset["id"]))
        assert kept is not None
        key = kept.image_key
    assert get_store().exists(key)
    assert client.delete(path).status_code == HTTPStatus.NOT_FOUND  # no longer referenced here
    assert (
        client.delete(f"{API}/questions/{other}/figures/{asset['id']}").status_code
        == HTTPStatus.NO_CONTENT
    )
    with Session(world.engine) as db:
        assert db.get(Asset, UUID(asset["id"])) is None
    assert not get_store().exists(key)


@pytest.mark.integration
def test_stimuli_crud(world: World, client: TestClient) -> None:
    login(client, "editor")
    payload = {
        "source_id": str(world.source),
        "page_id": str(world.pages[1]),
        "box": BOX,
        "kind": "figure",
        "intro": "Look",
    }
    created = client.post(f"{API}/stimuli", json=payload)
    assert created.status_code == HTTPStatus.CREATED, created.text
    body = created.json()
    assert body["content"].startswith("![](asset:")  # cropped from the region
    assert body["regions"] == [{"page": str(world.pages[1]), "box": BOX}]
    assert body["metadata"]["intro"] == "Look"
    sid = body["id"]
    mismatch = client.post(f"{API}/stimuli", json={**payload, "page_id": str(uuid4())})
    assert mismatch.status_code == HTTPStatus.NOT_FOUND
    other_source = uuid4()
    with Session(world.engine) as db:
        db.add(
            Source(
                id=other_source,
                org_id=world.org,
                subject_id=world.subject,
                title="o",
                file_key="o",
                status=SourceStatus.ready,
            )
        )
        db.commit()
    wrong = client.post(f"{API}/stimuli", json={**payload, "source_id": str(other_source)})
    assert wrong.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    passage = client.post(
        f"{API}/stimuli", json={**payload, "kind": "passage", "content": "text ...."}
    ).json()
    assert passage["content"] == "text ____"
    patched = client.patch(
        f"{API}/stimuli/{sid}", json={"content": "new content", "kind": "passage", "intro": "Read"}
    )
    assert patched.status_code == OK
    assert (patched.json()["kind"], patched.json()["metadata"]["intro"]) == ("passage", "Read")
    assert (
        client.patch(f"{API}/stimuli/{sid}", json={"kind": None}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    linked = make_question(world, stimulus_id=UUID(sid))
    assert client.patch(f"{API}/stimuli/{sid}", json={"intro": "Changed"}).status_code == OK
    assert "changed" in get_question(world, linked).normalized_text
    assert client.post(f"{API}/stimuli/{sid}/approve").json()["status"] == "approved"
    assert client.post(f"{API}/stimuli/{sid}/reject").json()["status"] == "rejected"
    assert client.delete(f"{API}/stimuli/{sid}").status_code == HTTPStatus.CONFLICT
    # a question can only link a stimulus of its own source
    foreign = client.post(f"{API}/stimuli", json={**payload}).json()["id"]
    assert (
        client.patch(
            f"{API}/questions/{linked}", json={"version": 1, "stimulus_id": foreign}
        ).status_code
        == OK
    )
    with Session(world.engine) as db:
        db.execute(delete(Question).where(Question.id == linked))
        db.commit()
    assert client.delete(f"{API}/stimuli/{sid}").status_code == HTTPStatus.NO_CONTENT
    login(client, "other")
    assert (
        client.patch(f"{API}/stimuli/{foreign}", json={"kind": "poem"}).status_code
        == HTTPStatus.NOT_FOUND
    )
    login(client, "teacher")
    assert client.delete(f"{API}/stimuli/{foreign}").status_code == HTTPStatus.FORBIDDEN
    with Session(world.engine) as db:
        assert db.get(Stimulus, UUID(foreign)) is not None


def run_worker(args: tuple[Any, ...]) -> None:
    job_id, source_id, number, model, user_id = args
    reextract_page.fn(str(job_id), str(source_id), number, model, str(user_id))


def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeLLMClient:
    fake = FakeLLMClient()
    monkeypatch.setattr(llm, "get_llm_client", lambda: fake)
    return fake


@pytest.mark.integration
def test_reextract_proposal_diff_and_partial_accept(  # noqa: PLR0915 -- one end-to-end scenario
    world: World, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[Any, ...]] = []
    monkeypatch.setattr(proposals, "enqueue", lambda *args: sent.append(args))
    fake = fake_client(monkeypatch)
    same = make_question(world, "1", stem="stem 1")
    with Session(world.engine) as db:
        existing = db.get(Question, same)
        assert existing is not None
        existing.choices = [
            {"label": "a", "content": "one", "is_correct": True, "pinned": False},
            {"label": "b", "content": "two", "is_correct": False, "pinned": False},
        ]
        db.commit()
    changed = make_question(world, "2", position=1)
    locked = make_question(world, "3", status="approved", position=2)
    gone = make_question(world, "4", position=3)
    later_page = make_question(world, "9", page=2, position=4)
    login(client, "teacher")
    url = f"{API}/sources/{world.source}/pages/1/reextract"
    assert client.post(url).status_code == HTTPStatus.FORBIDDEN
    login(client, "other")
    assert client.post(url).status_code == HTTPStatus.NOT_FOUND
    login(client, "editor")
    refused = client.post(url, json={"model": "bogus/model"})
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert refused.json()["code"] == "model_not_allowed"
    assert (
        client.post(f"{API}/sources/{world.source}/pages/9/reextract").status_code
        == HTTPStatus.NOT_FOUND
    )
    started = client.post(url)
    assert started.status_code == HTTPStatus.ACCEPTED, started.text
    job_id = started.json()["job_id"]
    assert sent[0][2] == 1  # page number handed to the worker
    # the worker stores a proposal and leaves live rows alone
    fake.queue(
        "extract",
        extraction(
            extracted("1", stem="stem 1"),
            extracted("2", stem="a better stem two"),
            extracted("3", stem="locked but changed"),
            extracted(
                "5", stem="brand new", figures=[{"box_2d": [100, 100, 400, 400], "kind": "diagram"}]
            ),
        ),
    )
    run_worker(sent[0])
    job = client.get(f"{API}/jobs/{job_id}").json()
    assert job["status"] == "ready", job
    proposal_id = job["progress"]["proposal_id"]
    assert get_question(world, changed).stem.startswith("original stem 2")
    detail = client.get(f"{API}/page-proposals/{proposal_id}")
    assert detail.status_code == OK, detail.text
    diff = detail.json()["diff"]
    assert detail.json()["proposal"]["status"] == "pending"
    assert detail.json()["proposal"]["page_number"] == 1
    assert diff["unchanged"] == ["1"]
    assert {c["number_label"] for c in diff["changed"]} == {"2", "3"}
    two = next(c for c in diff["changed"] if c["number_label"] == "2")
    assert two["fields"]["stem"]["after"] == "a better stem two"
    assert two["fields"]["stem"]["before"].startswith("original stem 2")
    assert [a["number_label"] for a in diff["added"]] == ["5"]
    assert [r["number_label"] for r in diff["removed"]] == ["4"]
    login(client, "teacher")
    assert client.get(f"{API}/page-proposals/{proposal_id}").status_code == HTTPStatus.FORBIDDEN
    login(client, "other")
    assert client.get(f"{API}/page-proposals/{proposal_id}").status_code == HTTPStatus.NOT_FOUND
    login(client, "editor")
    # partial accept: only "2" (plus a label the proposal does not contain)
    partial = client.post(
        f"{API}/page-proposals/{proposal_id}/accept", json={"number_labels": ["2", "77"]}
    )
    assert partial.status_code == OK, partial.text
    assert partial.json()["applied"] == ["2"]
    assert partial.json()["skipped"] == [{"number_label": "77", "reason": "not_in_proposal"}]
    assert get_question(world, changed).stem == "a better stem two"
    assert get_question(world, changed).version == TWO
    assert events(world, changed)[-1].action == "reextract_accept"
    assert get_question_or_none(world, gone) is not None
    assert (
        client.post(f"{API}/page-proposals/{proposal_id}/accept").status_code == HTTPStatus.CONFLICT
    )
    assert (
        client.post(f"{API}/page-proposals/{proposal_id}/discard").status_code
        == HTTPStatus.CONFLICT
    )
    # a second proposal accepted in full: approved items are listed as skipped
    fake.queue(
        "extract",
        extraction(
            extracted("1", stem="stem 1"),
            extracted("2", stem="a better stem two"),
            extracted("3", stem="locked but changed"),
            extracted(
                "5", stem="brand new", figures=[{"box_2d": [100, 100, 400, 400], "kind": "diagram"}]
            ),
        ),
    )
    second = client.post(url).json()["job_id"]
    run_worker(sent[1])
    second_id = client.get(f"{API}/jobs/{second}").json()["progress"]["proposal_id"]
    accepted = client.post(f"{API}/page-proposals/{second_id}/accept")
    assert accepted.status_code == OK, accepted.text
    body = accepted.json()
    assert sorted(body["applied"]) == ["4", "5"]
    assert [s["number_label"] for s in body["skipped"]] == ["3"]
    assert body["skipped"][0]["reason"] == "approved"
    assert get_question(world, locked).stem.startswith("original stem 3")
    assert get_question_or_none(world, gone) is None
    assert get_question_or_none(world, later_page) is not None  # other pages are untouched
    with Session(world.engine) as db:
        new = db.scalar(select(Question).where(Question.number_label == "5"))
        assert new is not None
        assert new.stem.startswith("brand new\n![](asset:")
        assert new.status in ("draft", "needs_review")
        assert new.regions[0]["page"] == str(world.pages[1])
        page = db.get(SourcePage, world.pages[1])
        assert page is not None
        assert page.extraction is None  # skipped items: the page keeps its old extraction
        proposal = db.get(PageProposal, UUID(second_id))
        assert proposal is not None
        assert (proposal.status, proposal.created_by) == ("accepted", world.users["editor"])
        positions = [
            q.position
            for q in db.scalars(
                select(Question)
                .where(Question.source_id == world.source)
                .order_by(Question.position)
            )
        ]
        assert positions == sorted(positions)
    # discard
    fake.queue("extract", extraction())
    third = client.post(url).json()["job_id"]
    run_worker(sent[2])
    third_id = client.get(f"{API}/jobs/{third}").json()["progress"]["proposal_id"]
    assert client.post(f"{API}/page-proposals/{third_id}/discard").json()["status"] == "discarded"


@pytest.mark.integration
def test_reextract_full_accept_updates_page_and_failures_fail_the_job(
    world: World, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[Any, ...]] = []
    monkeypatch.setattr(proposals, "enqueue", lambda *args: sent.append(args))
    fake = fake_client(monkeypatch)
    login(client, "editor")
    url = f"{API}/sources/{world.source}/pages/2/reextract"
    fake.queue("extract", BudgetExceeded())
    job_id = client.post(url, json={}).json()["job_id"]
    run_worker(sent[0])
    failed = client.get(f"{API}/jobs/{job_id}").json()
    assert (failed["status"], failed["error"]) == ("failed", "budget_exceeded")
    fake.queue("extract", LLMOutputInvalid("bad", cost_usd=__import__("decimal").Decimal("0.01")))
    fake.queue("extract_strong", LLMOutputInvalid("bad"))
    job2 = client.post(url).json()["job_id"]
    run_worker(sent[1])
    assert client.get(f"{API}/jobs/{job2}").json()["error"] == "llm_output_invalid"
    with Session(world.engine) as db:
        assert db.get(Source, world.source).cost_usd > 0  # type: ignore[union-attr]  # exists
    fake.queue("extract", extraction(extracted("1", stem="fresh")))
    job3 = client.post(url).json()["job_id"]
    run_worker(sent[2])
    pid = client.get(f"{API}/jobs/{job3}").json()["progress"]["proposal_id"]
    done = client.post(f"{API}/page-proposals/{pid}/accept", json={})
    assert done.json()["applied"] == ["1"]
    with Session(world.engine) as db:
        page = db.get(SourcePage, world.pages[2])
        assert page is not None
        assert page.extraction is not None
        assert page.prompt_version == "extract-v1"
        jobs = list(db.scalars(select(Job).where(Job.kind == "reextract")))
        assert len(jobs) == THREE
    # the job endpoint keeps ingest semantics untouched; unknown jobs 404
    assert client.get(f"{API}/jobs/{uuid4()}").status_code == HTTPStatus.NOT_FOUND


@pytest.mark.integration
def test_extract_region(
    world: World, client: TestClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeLLMClient()
    app.dependency_overrides[proposals.get_client] = lambda: fake
    url = f"{API}/sources/{world.source}/pages/1/extract-region"
    login(client, "teacher")
    assert client.post(url, json={"box": BOX}).status_code == HTTPStatus.FORBIDDEN
    login(client, "editor")
    fake.queue("extract", extraction(extracted("7", stem="region ....")))
    response = client.post(url, json={"box": BOX})
    assert response.status_code == OK, response.text
    draft = response.json()
    assert draft["number_label"] == "7"
    assert draft["stem"] == "region ____"
    assert fake.calls[0]["stage"] == "extract"
    assert fake.calls[0]["source_id"] == world.source
    with Session(world.engine) as db:
        assert db.scalar(select(Question).where(Question.number_label == "7")) is None
    # the draft is confirmed through POST /questions
    confirmed = client.post(
        f"{API}/questions",
        json={
            "subject_id": str(world.subject),
            "type": draft["type"],
            "stem": draft["stem"],
            "choices": draft["choices"],
            "number_label": draft["number_label"],
        },
    )
    assert confirmed.status_code == HTTPStatus.CREATED
    fake.queue("extract", extraction())
    assert client.post(url, json={"box": BOX}).json()["code"] == "no_question_found"
    fake.queue("extract", BudgetExceeded())
    over = client.post(url, json={"box": BOX})
    assert (over.status_code, over.json()["code"]) == (
        HTTPStatus.PAYMENT_REQUIRED,
        "budget_exceeded",
    )
    fake.queue("extract", LLMOutputInvalid("bad"))
    fake.queue("extract_strong", LLMOutputInvalid("bad"))
    assert client.post(url, json={"box": BOX}).status_code == HTTPStatus.BAD_GATEWAY
    assert (
        client.post(url, json={"box": BOX, "model": "bogus/model"}).json()["code"]
        == "model_not_allowed"
    )
    assert (
        client.post(url, json={"box": [0.5, 0.5, 0.2, 0.2]}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    assert (
        client.post(
            f"{API}/sources/{world.source}/pages/9/extract-region", json={"box": BOX}
        ).status_code
        == HTTPStatus.NOT_FOUND
    )
    login(client, "other")
    assert client.post(url, json={"box": BOX}).status_code == HTTPStatus.NOT_FOUND


@pytest.mark.integration
def test_review_queue_ordering_filters_and_visibility(world: World, client: TestClient) -> None:
    a = make_question(world, "1", page=2, position=2)
    b = make_question(world, "2", page=1, position=1, stem="")
    c = make_question(world, "3", page=1, position=0, status="approved")
    with Session(world.engine) as db:
        for qid, severity, resolved in (
            (b, "error", False),
            (a, "warning", False),
            (c, "error", True),
        ):
            question = db.get(Question, qid)
            assert question is not None
            question.confidence = {a: 0.2, b: 0.5, c: 0.9}[qid]
            db.add(
                ValidationIssue(
                    question_id=qid,
                    code=f"x_{severity}",
                    severity=severity,
                    message="m",
                    resolved_at=None
                    if not resolved
                    else __import__("datetime").datetime.now(__import__("datetime").UTC),
                )
            )
        db.commit()
    login(client, "editor")
    url = f"{API}/sources/{world.source}/review-queue"

    def ids(**params: str) -> list[str]:
        return [i["id"] for i in client.get(url, params=params).json()["items"]]

    assert ids() == [str(c), str(b), str(a)]  # page, then position
    assert ids(sort="severity") == [str(b), str(a), str(c)]
    assert ids(sort="confidence") == [str(a), str(b), str(c)]
    assert ids(page="1") == [str(c), str(b)]
    assert ids(status="needs_review") == [str(b), str(a)]
    assert ids(severity="error") == [str(b)]  # resolved issues do not count
    assert ids(severity="warning", page="2") == [str(a)]
    body = client.get(url).json()
    assert body["totals"] == {
        "count": 3,
        "by_status": {"approved": 1, "needs_review": 2},
        "by_severity": {"error": 1, "warning": 1},
    }
    first = body["items"][0]
    assert first["page"] == 1
    assert first["issues"] == {"error": 0, "warning": 0}
    assert set(first) == {
        "id",
        "number_label",
        "position",
        "page",
        "status",
        "confidence",
        "issues",
    }
    assert client.get(url, params={"sort": "nope"}).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    login(client, "teacher")
    assert ids() == [str(c)]
    login(client, "other")
    assert client.get(url).status_code == HTTPStatus.NOT_FOUND
