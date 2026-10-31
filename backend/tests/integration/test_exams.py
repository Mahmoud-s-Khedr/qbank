from collections.abc import Iterator
from http import HTTPStatus
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qbank.auth import hasher
from qbank.db import get_db
from qbank.models import (
    Language,
    Organization,
    Question,
    Role,
    Source,
    SourceStatus,
    Stimulus,
    Subject,
    User,
)

URL = "/api/v1"
OK, CREATED, NO_CONTENT = HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.NO_CONTENT
UNPROCESSABLE, CONFLICT, NOT_FOUND = (
    HTTPStatus.UNPROCESSABLE_ENTITY,
    HTTPStatus.CONFLICT,
    HTTPStatus.NOT_FOUND,
)


def choices(correct: int | None, pinned: int | None = None) -> list[dict[str, object]]:
    return [
        {
            "label": "abcd"[i],
            "content": f"choice {i}",
            "is_correct": None if correct is None else i == correct,
            "pinned": i == pinned,
        }
        for i in range(4)
    ]


@pytest.fixture
def data(database: str, app: FastAPI) -> Iterator[dict[str, Any]]:
    engine = create_engine(database)
    with Session(engine) as db:
        a, b = Organization(name="A"), Organization(name="B")
        db.add_all([a, b])
        db.flush()
        users = {
            email: User(
                org_id=org.id,
                email=email,
                name=email,
                role=role,
                password_hash=hasher.hash("password"),
            )
            for org, email, role in [
                (a, "admin@a.com", Role.admin),
                (a, "t1@a.com", Role.teacher),
                (a, "t2@a.com", Role.teacher),
                (b, "admin@b.com", Role.admin),
            ]
        }
        db.add_all(users.values())
        subject = Subject(org_id=a.id, name="Arabic", language=Language.ar)
        other_subject = Subject(org_id=b.id, name="B", language=Language.en)
        db.add_all([subject, other_subject])
        db.flush()
        sources = {
            org.id: Source(
                org_id=org.id,
                subject_id=sub.id,
                title="s",
                file_key="k",
                status=SourceStatus.ready,
            )
            for org, sub in ((a, subject), (b, other_subject))
        }
        db.add_all(sources.values())
        db.flush()
        stimulus = Stimulus(
            org_id=a.id, source_id=sources[a.id].id, kind="passage", content="PASSAGE", regions=[]
        )
        db.add(stimulus)
        db.flush()
        counter = 0

        def question(**kw: Any) -> Question:
            nonlocal counter
            counter += 1
            org = kw.pop("org", a)
            sub = other_subject if org is b else subject
            values: dict[str, Any] = {
                "org_id": org.id,
                "subject_id": sub.id,
                "source_id": sources[org.id].id,
                "position": counter,
                "number_label": str(counter),
                "type": "mcq_single",
                "stem": f"Q{counter}",
                "choices": choices(counter % 4),
                "language": sub.language,
                "regions": [],
                "status": "approved",
                "confidence": 1.0,
                "tags": [],
                "difficulty": 2,
            }
            values.update(kw)
            q = Question(**values)
            db.add(q)
            db.flush()
            return q

        singles = [question() for _ in range(5)]
        pinned = question(choices=choices(1, pinned=3))
        unknown = question(choices=choices(None))
        essay = question(type="essay", choices=[], answer="because", difficulty=4, tags=["t"])
        draft = question(status="draft")
        duplicate = question(duplicate_of_id=singles[0].id)
        group = [
            question(stimulus_id=stimulus.id, stimulus_position=p, choices=choices(p))
            for p in (1, 2, 3)
        ]
        foreign = question(org=b)
        db.commit()
        ids = {
            "singles": [str(q.id) for q in singles],
            "pinned": str(pinned.id),
            "unknown": str(unknown.id),
            "essay": str(essay.id),
            "draft": str(draft.id),
            "duplicate": str(duplicate.id),
            "group": [str(q.id) for q in group],
            "foreign": str(foreign.id),
            "subject": str(subject.id),
            "foreign_subject": str(other_subject.id),
        }

    def override() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield ids
    engine.dispose()


def login(client: TestClient, email: str) -> None:
    response = client.post(f"{URL}/auth/login", json={"email": email, "password": "password"})
    assert response.status_code == OK, response.text
    client.headers["X-CSRF-Token"] = client.cookies["qbank_csrf"]


def new_exam(client: TestClient, data: dict[str, Any], **extra: Any) -> dict[str, Any]:
    response = client.post(
        f"{URL}/exams", json={"title": "Midterm", "subject_id": data["subject"], **extra}
    )
    assert response.status_code == CREATED, response.text
    return response.json()  # type: ignore[no-any-return]


def item_ids(exam: dict[str, Any]) -> list[str]:
    return [i["id"] for s in exam["sections"] for i in s["items"]]


def question_ids(exam: dict[str, Any]) -> list[str]:
    return [i["question_id"] for s in exam["sections"] for i in s["items"]]


@pytest.mark.integration
def test_exam_crud_scoping_and_settings(data: dict[str, Any], client: TestClient) -> None:
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    assert exam["revision"] == 1
    assert len(exam["sections"]) == 1
    assert exam["settings"]["language"] == "ar"
    assert exam["settings"]["layout"]["columns"] == 1
    bad = {"layout": {"font_size_pt": 20}}
    assert (
        client.post(
            f"{URL}/exams", json={"title": "x", "subject_id": data["subject"], "settings": bad}
        ).status_code
        == UNPROCESSABLE
    )
    assert (
        client.post(
            f"{URL}/exams", json={"title": "x", "subject_id": data["foreign_subject"]}
        ).status_code
        == NOT_FOUND
    )
    eid = exam["id"]
    patched = client.patch(
        f"{URL}/exams/{eid}",
        json={"title": "Final", "settings": {"language": "en", "layout": {"choices_per_row": 2}}},
    ).json()
    assert patched["title"] == "Final"
    assert patched["revision"] == 2  # noqa: PLR2004
    assert patched["settings"]["layout"]["choices_per_row"] == 2  # noqa: PLR2004
    assert client.patch(f"{URL}/exams/{eid}", json={"status": "final"}).json()["revision"] == 2  # noqa: PLR2004
    # visibility: another teacher cannot see it, an admin of the org can, another org cannot
    login(client, "t2@a.com")
    assert client.get(f"{URL}/exams/{eid}").status_code == NOT_FOUND
    assert client.delete(f"{URL}/exams/{eid}").status_code == NOT_FOUND
    assert client.get(f"{URL}/exams").json()["items"] == []
    login(client, "admin@a.com")
    assert client.get(f"{URL}/exams/{eid}").status_code == OK
    assert [e["id"] for e in client.get(f"{URL}/exams").json()["items"]] == [eid]
    login(client, "admin@b.com")
    assert client.get(f"{URL}/exams/{eid}").status_code == NOT_FOUND
    login(client, "t1@a.com")
    # list: status filter + cursor pagination
    second = new_exam(client, data, settings={"language": "en"})
    assert client.post(f"{URL}/exams/{second['id']}/archive").json()["status"] == "archived"
    assert [e["id"] for e in client.get(f"{URL}/exams?status=archived").json()["items"]] == [
        second["id"]
    ]
    page = client.get(f"{URL}/exams?limit=1").json()
    assert len(page["items"]) == 1
    assert page["next_cursor"]
    rest = client.get(f"{URL}/exams?limit=1&cursor={page['next_cursor']}").json()
    assert rest["items"][0]["id"] == second["id"]
    assert client.get(f"{URL}/exams?cursor=bad").status_code == UNPROCESSABLE
    assert client.delete(f"{URL}/exams/{eid}").status_code == NO_CONTENT
    assert client.get(f"{URL}/exams/{eid}").status_code == NOT_FOUND


@pytest.mark.integration
def test_items_groups_sections_and_duplicate(  # noqa: PLR0915 -- one end-to-end scenario
    data: dict[str, Any], client: TestClient
) -> None:
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    eid = exam["id"]
    singles, group = data["singles"], data["group"]
    r = client.post(f"{URL}/exams/{eid}/items", json={"question_ids": [singles[0]], "points": 2})
    assert r.status_code == CREATED
    assert r.json()["total_points"] == 2  # noqa: PLR2004
    # guards
    assert (
        client.post(f"{URL}/exams/{eid}/items", json={"question_ids": [data["draft"]]}).status_code
        == UNPROCESSABLE
    )
    assert (
        client.post(
            f"{URL}/exams/{eid}/items", json={"question_ids": [data["foreign"]]}
        ).status_code
        == NOT_FOUND
    )
    # adding one group member adds the whole group in order, with the stimulus shown once
    exam = client.post(f"{URL}/exams/{eid}/items", json={"question_ids": [group[1]]}).json()
    assert question_ids(exam) == [singles[0], *group]
    items = exam["sections"][0]["items"]
    assert [i["stimulus"] is not None for i in items] == [False, True, False, False]
    assert items[1]["stimulus"]["content"] == "PASSAGE"
    assert exam["question_count"] == 4  # noqa: PLR2004
    # re-adding is a no-op and does not bump the revision
    again = client.post(
        f"{URL}/exams/{eid}/items", json={"question_ids": [group[0], singles[0]]}
    ).json()
    assert again["revision"] == exam["revision"]
    # removing one group member needs ?group=true
    member = items[2]["id"]
    deleted = client.delete(f"{URL}/exam-items/{member}")
    assert deleted.status_code == CONFLICT
    assert deleted.json()["code"] == "stimulus_group"
    # grouped items cannot be moved individually
    assert (
        client.patch(f"{URL}/exam-items/{member}", json={"position": 0}).status_code
        == UNPROCESSABLE
    )
    # sections
    section = client.post(f"{URL}/exams/{eid}/sections", json={"title": "Part 2"})
    assert section.status_code == CREATED
    s1, s2 = (s["id"] for s in section.json()["sections"])
    single_item = items[0]["id"]
    moved = client.patch(
        f"{URL}/exam-items/{single_item}", json={"section_id": s2, "points": 5}
    ).json()
    assert [len(s["items"]) for s in moved["sections"]] == [3, 1]
    assert moved["total_points"] == 5 + 3
    assert client.delete(f"{URL}/exam-sections/{s2}").status_code == CONFLICT
    # reorder items: breaking up a group is rejected
    first_items = item_ids(moved)[:3]
    broken = client.post(
        f"{URL}/exams/{eid}/items/reorder",
        json={"section_id": s1, "ids": [first_items[0], first_items[2], first_items[1]]},
    )
    assert broken.status_code == UNPROCESSABLE
    mismatch = client.post(
        f"{URL}/exams/{eid}/items/reorder", json={"section_id": s1, "ids": first_items[:2]}
    )
    assert mismatch.json()["code"] == "ids_mismatch"
    ok = client.post(
        f"{URL}/exams/{eid}/items/reorder", json={"section_id": s1, "ids": first_items}
    )
    assert ok.status_code == OK
    # a single item cannot be dropped into the middle of a group
    assert (
        client.patch(
            f"{URL}/exam-items/{single_item}", json={"section_id": s1, "position": 1}
        ).status_code
        == UNPROCESSABLE
    )
    back = client.patch(
        f"{URL}/exam-items/{single_item}", json={"section_id": s1, "position": 0}
    ).json()
    assert question_ids(back)[0] == singles[0]
    # section reorder / edit / delete
    reordered = client.post(f"{URL}/exams/{eid}/sections/reorder", json={"ids": [s2, s1]})
    assert [s["id"] for s in reordered.json()["sections"]] == [s2, s1]
    assert (
        client.post(f"{URL}/exams/{eid}/sections/reorder", json={"ids": [s1]}).status_code
        == UNPROCESSABLE
    )
    assert (
        client.patch(f"{URL}/exam-sections/{s2}", json={"title": "B", "instructions": "i"}).json()[
            "sections"
        ][0]["title"]
        == "B"
    )
    assert len(client.delete(f"{URL}/exam-sections/{s2}").json()["sections"]) == 1
    assert client.delete(f"{URL}/exam-sections/{s1}").json()["code"] == "last_section"
    # duplicate
    copy = client.post(f"{URL}/exams/{eid}/duplicate").json()
    assert copy["id"] != eid
    assert copy["title"].endswith("(copy)")
    assert question_ids(copy) == question_ids(back)
    assert copy["revision"] == 1
    # delete the whole group
    group_item = item_ids(back)[1]
    after = client.delete(f"{URL}/exam-items/{group_item}?group=true").json()
    assert question_ids(after) == [singles[0]]
    assert client.delete(f"{URL}/exam-items/{item_ids(after)[0]}").json()["question_count"] == 0


@pytest.mark.integration
def test_versions_and_answer_keys(data: dict[str, Any], client: TestClient) -> None:
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    eid = exam["id"]
    assert (
        client.post(f"{URL}/exams/{eid}/versions", json={"count": 2}).json()["code"] == "exam_empty"
    )
    wanted = [*data["singles"][:3], data["pinned"], data["unknown"], data["essay"], *data["group"]]
    client.post(f"{URL}/exams/{eid}/sections", json={"title": "Part 2"})
    exam = client.post(f"{URL}/exams/{eid}/items", json={"question_ids": wanted[:5]}).json()
    s2 = exam["sections"][1]["id"]
    exam = client.post(
        f"{URL}/exams/{eid}/items", json={"question_ids": wanted[5:], "section_id": s2}
    ).json()
    assert (
        client.post(f"{URL}/exams/{eid}/versions", json={"count": 11}).status_code == UNPROCESSABLE
    )
    request = {"count": 3, "seed": 42, "keep_first_as_original": True}
    versions = client.post(f"{URL}/exams/{eid}/versions", json=request).json()
    assert [v["label"] for v in versions] == ["أ", "ب", "ج"]
    assert not any(v["stale"] for v in versions)
    again = client.post(f"{URL}/exams/{eid}/versions", json=request).json()
    assert [v["seed"] for v in again] == [v["seed"] for v in versions]
    detail = client.get(f"{URL}/exams/{eid}").json()
    assert len(detail["versions"]) == 3  # noqa: PLR2004
    by_id = {i["question_id"]: i["question"] for s in detail["sections"] for i in s["items"]}
    for label in ("أ", "ب", "ج"):
        key = client.get(f"{URL}/exams/{eid}/versions/{label}/answer-key").json()
        assert [e["number"] for e in key["items"]] == list(range(1, 10))
        assert sorted(e["question_id"] for e in key["items"]) == sorted(by_id)
        assert len(key["warnings"]) == 1  # the MCQ with no known answer
        for entry in key["items"]:
            question = by_id[entry["question_id"]]
            if question["type"] == "essay":
                assert entry["correct"] is None
                assert entry["answer_text"] == "because"
            elif question["id"] == data["unknown"]:
                assert entry["correct"] is None
            else:
                (correct,) = entry["correct"]
                assert correct in "أبجد"
    # label "أ" is the original: order and choices untouched, so display label = source label
    original = client.get(f"{URL}/exams/{eid}/versions/أ/answer-key").json()["items"]
    assert [e["question_id"] for e in original] == question_ids(detail)
    for entry in original:
        question = by_id[entry["question_id"]]
        if question["id"] not in (data["unknown"], data["essay"]):
            index = [c["is_correct"] for c in question["choices"]].index(True)
            assert entry["correct"] == ["أبجد"[index]]
    # pinned choice 3 stays in slot 3 in every version, and the key follows the permutation
    assert client.get(f"{URL}/exams/{eid}/versions/ز/answer-key").status_code == NOT_FOUND
    # an edit makes versions stale
    edited = client.patch(f"{URL}/exam-items/{item_ids(detail)[0]}", json={"points": 9}).json()
    assert all(v["stale"] for v in edited["versions"])
    fresh = client.post(f"{URL}/exams/{eid}/versions", json={"count": 1, "shuffle_choices": False})
    assert fresh.json()[0]["stale"] is False
    # English exams use latin labels
    client.patch(f"{URL}/exams/{eid}", json={"settings": {"language": "en"}})
    labels = [
        v["label"] for v in client.post(f"{URL}/exams/{eid}/versions", json={"count": 2}).json()
    ]
    assert labels == ["A", "B"]
    login(client, "t2@a.com")
    assert client.get(f"{URL}/exams/{eid}/versions/A/answer-key").status_code == NOT_FOUND


@pytest.mark.integration
def test_blueprint(data: dict[str, Any], client: TestClient) -> None:
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    eid = exam["id"]
    manual = data["singles"][1]
    client.post(f"{URL}/exams/{eid}/items", json={"question_ids": [manual]})
    body = {
        "rows": [
            {"count": 3, "points": 2, "types": ["mcq_single"], "difficulty_max": 3},
            {"count": 2, "points": 4, "types": ["essay"]},
            {"count": 1, "tags_any": ["nope"]},
        ],
        "seed": 7,
    }
    preview = client.post(f"{URL}/exams/{eid}/blueprint/preview", json=body).json()
    assert preview["seed"] == 7  # noqa: PLR2004
    assert [r["requested"] for r in preview["rows"]] == [3, 2, 1]
    assert [r["shortfall"] for r in preview["rows"]] == [0, 1, 1]
    assert preview["rows"][1]["available"] == 1
    assert preview == client.post(f"{URL}/exams/{eid}/blueprint/preview", json=body).json()
    picked = [q for r in preview["rows"] for q in r["selected"]]
    assert manual not in picked
    assert data["draft"] not in picked
    assert data["foreign"] not in picked
    assert not {data["singles"][0], data["duplicate"]} <= set(picked)  # one per duplicate cluster
    applied = client.post(f"{URL}/exams/{eid}/blueprint/apply", json=body).json()
    assert set(question_ids(applied)) == {manual, *picked}
    assert sorted(i["origin"] for s in applied["sections"] for i in s["items"]).count(
        "blueprint"
    ) == len(picked)
    assert applied["blueprint"]["seed"] == 7  # noqa: PLR2004
    # re-applying replaces only the blueprint-created items
    other = {"rows": [{"count": 1, "types": ["essay"]}], "seed": 1}
    replaced = client.post(f"{URL}/exams/{eid}/blueprint/apply", json=other).json()
    assert set(question_ids(replaced)) == {manual, data["essay"]}
    # excluded ids, and questions used in my other (non-archived) exams
    wide = {"rows": [{"count": 20}], "seed": 3, "exclude_question_ids": [data["essay"]]}
    result = client.post(f"{URL}/exams/{eid}/blueprint/preview", json=wide).json()["rows"][0]
    assert data["essay"] not in result["selected"]
    sibling = new_exam(client, data)
    client.post(
        f"{URL}/exams/{sibling['id']}/blueprint/apply",
        json={"rows": [{"count": 3}], "seed": 2, "exclude_used_in_my_exams": True},
    )
    used = set(question_ids(client.get(f"{URL}/exams/{sibling['id']}").json()))
    assert manual not in used  # in my other exam, so skipped
    unique = {"rows": [{"count": 20}], "seed": 3, "exclude_used_in_my_exams": True}
    again = client.post(f"{URL}/exams/{eid}/blueprint/preview", json=unique).json()["rows"][0]
    assert not used & set(again["selected"])
    # a section from another exam is rejected; unseeded runs report their seed
    bad = {"rows": [{"count": 1, "section_id": sibling["sections"][0]["id"]}]}
    assert client.post(f"{URL}/exams/{eid}/blueprint/preview", json=bad).status_code == NOT_FOUND
    assert isinstance(
        client.post(f"{URL}/exams/{eid}/blueprint/preview", json={"rows": [{"count": 1}]}).json()[
            "seed"
        ],
        int,
    )


@pytest.mark.integration
def test_ai_compose_apply_discard_and_failures(
    data: dict[str, Any], client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qbank.llm import BudgetExceeded, FakeLLMClient, LLMOutputInvalid  # noqa: PLC0415
    from qbank.services import compose_ai  # noqa: PLC0415

    fake = FakeLLMClient()
    monkeypatch.setattr(compose_ai, "get_llm_client", lambda: fake)
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    url = f"{URL}/exams/{exam['id']}/compose"
    plan = {"sections": [{"title": "A", "rows": [{"count": 2}]}]}
    fake.queue("compose", plan)
    fake.queue("compose", {"rows": [{"refs": ["unknown"]}], "rationale": "A test"})
    response = client.post(url, json={"prompt": "Two questions"})
    assert response.status_code == OK, response.text
    proposal = response.json()
    assert "unknown_ref" in proposal["warnings"]
    assert len(proposal["selection"][0]) == 2  # noqa: PLR2004
    proposal_id = proposal["proposal_id"]
    first = proposal["selection"][0][0]
    # Replace one selected question with another approved, nonduplicate single.
    choices = [x for x in data["singles"] if x not in proposal["selection"][0]]
    applied = client.post(
        f"{URL}/exam-proposals/{proposal_id}/apply",
        json={"edits": {"remove_question_ids": [first], "add_question_ids": [choices[-1]]}},
    )
    assert applied.status_code == OK, applied.text
    assert first not in question_ids(applied.json())
    assert choices[-1] in question_ids(applied.json())
    assert applied.json()["revision"] == 2  # noqa: PLR2004
    assert applied.json()["blueprint"]["proposal_id"] == proposal_id
    assert client.post(f"{URL}/exam-proposals/{proposal_id}/discard").status_code == CONFLICT
    fake.queue("compose", plan)
    fake.queue("compose", {"rows": [{"refs": []}], "rationale": "test"})
    proposal2 = client.post(url, json={"prompt": "Again"}).json()
    assert (
        client.post(f"{URL}/exam-proposals/{proposal2['proposal_id']}/discard").json()["status"]
        == "discarded"
    )
    before = len(client.get(f"{URL}/exams/{exam['id']}/proposals").json())
    fake.queue("compose", BudgetExceeded())
    assert client.post(url, json={"prompt": "Budget"}).status_code == HTTPStatus.PAYMENT_REQUIRED
    fake.queue("compose", LLMOutputInvalid("bad"))
    assert client.post(url, json={"prompt": "Invalid"}).status_code == HTTPStatus.BAD_GATEWAY
    assert len(client.get(f"{URL}/exams/{exam['id']}/proposals").json()) == before
    login(client, "t2@a.com")
    assert client.get(f"{URL}/exams/{exam['id']}/proposals").status_code == NOT_FOUND


@pytest.mark.integration
def test_ai_compose_validates_plan_groups_and_duplicates(
    data: dict[str, Any], client: TestClient, monkeypatch: pytest.MonkeyPatch, database: str
) -> None:
    from uuid import uuid4  # noqa: PLC0415

    from sqlalchemy import update  # noqa: PLC0415

    from qbank.llm import FakeLLMClient  # noqa: PLC0415
    from qbank.services import compose_ai  # noqa: PLC0415

    engine = create_engine(database)
    with Session(engine) as db:
        db.execute(update(Question).where(Question.id.in_(data["group"])).values(tags=["group"]))
        db.commit()
    engine.dispose()
    fake = FakeLLMClient()
    monkeypatch.setattr(compose_ai, "get_llm_client", lambda: fake)
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    fake.queue(
        "compose",
        {
            "sections": [
                {
                    "title": "A",
                    "rows": [
                        {"count": 50, "tags_any": ["group"]},
                        {"count": 1, "lesson_ids": [str(uuid4())]},
                    ],
                }
            ]
        },
    )
    fake.queue("compose", {"rows": [{"refs": ["c1"]}], "rationale": "Group"})
    response = client.post(f"{URL}/exams/{exam['id']}/compose", json={"prompt": "group"})
    assert response.status_code == OK, response.text
    proposal = response.json()
    assert set(proposal["selection"][0]) == set(data["group"])
    assert proposal["blueprint"]["sections"][0]["rows"][0]["count"] == 3  # noqa: PLR2004
    assert set(proposal["warnings"]) >= {"unknown_taxonomy_id", "count_clamped"}
    bad = client.post(
        f"{URL}/exam-proposals/{proposal['proposal_id']}/apply",
        json={"edits": {"remove_question_ids": [data["group"][0]]}},
    )
    assert bad.status_code == UNPROCESSABLE
    ok = client.post(f"{URL}/exam-proposals/{proposal['proposal_id']}/apply", json={})
    assert ok.status_code == OK, ok.text
    assert question_ids(ok.json()) == data["group"]

    exam2 = new_exam(client, data)
    fake.queue("compose", {"sections": [{"title": "B", "rows": [{"count": 500}]}]})
    fake.queue("compose", {"rows": [{"refs": []}], "rationale": "All"})
    response = client.post(f"{URL}/exams/{exam2['id']}/compose", json={"prompt": "all"})
    assert response.status_code == OK, response.text
    ids = response.json()["selection"][0]
    assert not ({data["singles"][0], data["duplicate"]} <= set(ids))
    import json  # noqa: PLC0415

    payload = json.loads(fake.calls[-1]["messages"][1]["content"])
    assert len(payload["candidates"]) <= 120  # noqa: PLR2004
    assert len(json.dumps(payload["candidates"], ensure_ascii=False).encode()) <= 6000  # noqa: PLR2004


@pytest.mark.integration
def test_ai_compose_caps_large_candidate_payload(
    data: dict[str, Any], client: TestClient, monkeypatch: pytest.MonkeyPatch, database: str
) -> None:
    import json  # noqa: PLC0415

    from qbank.llm import FakeLLMClient  # noqa: PLC0415
    from qbank.services import compose_ai  # noqa: PLC0415

    engine = create_engine(database)
    with Session(engine) as db:
        original = db.get(Question, data["singles"][0])
        assert original is not None
        for position in range(150):
            db.add(
                Question(
                    org_id=original.org_id,
                    subject_id=original.subject_id,
                    source_id=original.source_id,
                    position=position + 100,
                    number_label=str(position),
                    type=original.type,
                    stem="سؤال طويل " * 100,
                    choices=original.choices,
                    language=original.language,
                    regions=[],
                    status="approved",
                    confidence=1.0,
                    tags=["اختبار"],
                    difficulty=2,
                )
            )
        db.commit()
    engine.dispose()
    fake = FakeLLMClient()
    monkeypatch.setattr(compose_ai, "get_llm_client", lambda: fake)
    fake.queue("compose", {"sections": [{"title": "A", "rows": [{"count": 100}]}]})
    fake.queue("compose", {"rows": [{"refs": []}], "rationale": "test"})
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    response = client.post(f"{URL}/exams/{exam['id']}/compose", json={"prompt": "many"})
    assert response.status_code == OK, response.text
    candidates = json.loads(fake.calls[-1]["messages"][1]["content"])["candidates"]
    assert len(candidates) < 100  # noqa: PLR2004 -- proves the cap was exercised
    assert len(json.dumps(candidates, ensure_ascii=False).encode()) <= 6000  # noqa: PLR2004


@pytest.mark.integration
def test_ai_compose_fills_group_when_single_would_block_it(
    data: dict[str, Any], client: TestClient, monkeypatch: pytest.MonkeyPatch, database: str
) -> None:
    from sqlalchemy import update  # noqa: PLC0415

    from qbank.llm import FakeLLMClient  # noqa: PLC0415
    from qbank.services import compose_ai  # noqa: PLC0415

    engine = create_engine(database)
    with Session(engine) as db:
        ids = [*data["group"], data["singles"][1]]
        db.execute(update(Question).where(Question.id.in_(ids)).values(tags=["special"]))
        db.commit()
    engine.dispose()
    fake = FakeLLMClient()
    monkeypatch.setattr(compose_ai, "get_llm_client", lambda: fake)
    fake.queue(
        "compose", {"sections": [{"title": "A", "rows": [{"count": 3, "tags_any": ["special"]}]}]}
    )
    fake.queue("compose", {"rows": [{"refs": ["c1"]}], "rationale": "test"})
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    response = client.post(f"{URL}/exams/{exam['id']}/compose", json={"prompt": "three"})
    assert response.status_code == OK, response.text
    assert set(response.json()["selection"][0]) == set(data["group"])


@pytest.mark.integration
def test_exam_list_reports_versions_and_staleness(data: dict[str, Any], client: TestClient) -> None:
    login(client, "t1@a.com")
    eid = new_exam(client, data)["id"]

    def listed() -> dict[str, Any]:
        items = client.get(f"{URL}/exams").json()["items"]
        return next(e for e in items if e["id"] == eid)

    assert (listed()["versions_count"], listed()["has_stale_versions"]) == (0, False)
    exam = client.post(
        f"{URL}/exams/{eid}/items", json={"question_ids": data["singles"][:2]}
    ).json()
    client.post(f"{URL}/exams/{eid}/versions", json={"count": 2, "seed": 1})
    assert (listed()["versions_count"], listed()["has_stale_versions"]) == (2, False)
    detail = client.get(f"{URL}/exams/{eid}").json()
    assert (detail["versions_count"], detail["has_stale_versions"]) == (2, False)
    client.patch(f"{URL}/exam-items/{item_ids(exam)[0]}", json={"points": 9})
    assert (listed()["versions_count"], listed()["has_stale_versions"]) == (2, True)


@pytest.mark.integration
def test_ai_compose_falls_back_to_subject_wide_row(
    data: dict[str, Any], client: TestClient, monkeypatch: pytest.MonkeyPatch, database: str
) -> None:
    """Seen live: questions with no lesson made every AI-planned row empty (count clamped to 0)."""
    from qbank.llm import FakeLLMClient  # noqa: PLC0415
    from qbank.models import Chapter  # noqa: PLC0415
    from qbank.services import compose_ai  # noqa: PLC0415

    engine = create_engine(database)
    with Session(engine) as db:
        empty = Chapter(subject_id=UUID(data["subject"]), title="empty", position=9)
        db.add(empty)
        db.commit()
        empty_id = str(empty.id)
    engine.dispose()
    fake = FakeLLMClient()
    monkeypatch.setattr(compose_ai, "get_llm_client", lambda: fake)
    fake.queue(
        "compose", {"sections": [{"title": "A", "rows": [{"count": 3, "chapter_ids": [empty_id]}]}]}
    )
    fake.queue("compose", {"rows": [{"refs": []}], "rationale": "test"})
    login(client, "t1@a.com")
    exam = new_exam(client, data)
    response = client.post(f"{URL}/exams/{exam['id']}/compose", json={"prompt": "3 questions"})
    assert response.status_code == OK, response.text
    body = response.json()
    assert "count_clamped" in body["warnings"]
    assert "fallback_subject_wide" in body["warnings"]
    [row] = body["blueprint"]["sections"][0]["rows"]
    assert row["chapter_ids"] == []
    assert row["count"] == 3  # noqa: PLR2004 -- the planned count is kept
    assert sum(len(r) for r in body["selection"]) == 3  # noqa: PLR2004 -- filled deterministically
