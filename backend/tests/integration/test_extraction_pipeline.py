from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

import qbank.pipeline.materialize as materialize_module
from qbank import llm, worker
from qbank.api.deps import current_user
from qbank.api.routers import sources as sources_router
from qbank.db import get_engine
from qbank.llm import BudgetExceeded, FakeLLMClient
from qbank.models import (
    Asset,
    Language,
    Organization,
    PageStatus,
    Question,
    Role,
    Source,
    SourcePage,
    SourceStatus,
    Stimulus,
    Subject,
    User,
)
from qbank.pipeline import orchestrator
from qbank.pipeline.materialize import materialize, pinned, stitch
from qbank.pipeline.schema import Stimulus as ExtractedStimulus
from qbank.storage import LocalStore, keys
from qbank.worker import extract_pages, render_one


def page_data(kind: str = "questions") -> dict[str, object]:
    return {
        "page_kind": kind,
        "headings": [],
        "stimuli": [],
        "questions": [],
        "answer_key_entries": [],
        "page_confidence": 0.9,
        "notes": "",
    }


def question(**changes: object) -> dict[str, object]:
    return {
        "number_label": "1",
        "type": "mcq_single",
        "stem": "first",
        "choices": [{"label": "a", "content": "all of the above"}],
        "answer": {"labels": ["a"], "text": None},
        "stimulus_ref": "s",
        "figures": [],
        "box_2d": [100, 100, 500, 500],
        "continues_from_previous": False,
        "continues_on_next": False,
        "confidence": 0.9,
        **changes,
    }


@pytest.mark.integration
def test_synthetic_pipeline(  # noqa: PLR0915 -- exercises the full ingestion sequence
    database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalStore(tmp_path)
    monkeypatch.setattr(worker, "get_store", lambda: store)
    monkeypatch.setattr(materialize_module, "get_store", lambda: store)
    monkeypatch.setattr(orchestrator, "page_done", lambda *args: None)
    monkeypatch.setattr(worker, "page_done", lambda *args: None)
    fake = FakeLLMClient()
    monkeypatch.setattr(llm, "get_llm_client", lambda: fake)
    with Session(get_engine()) as db:
        org = Organization(name="test")
        db.add(org)
        db.flush()
        subject = Subject(org_id=org.id, name="Arabic", language=Language.ar, grade="3")
        db.add(subject)
        db.flush()
        source = Source(
            org_id=org.id,
            subject_id=subject.id,
            title="test",
            file_key="input.pdf",
            status=SourceStatus.extracting,
            stage="extract",
        )
        db.add(source)
        db.flush()
        sid, org_id = source.id, org.id
        for number in range(1, 4):
            db.add(SourcePage(source_id=sid, page_number=number, status=PageStatus.pending))
        db.commit()
    document = pymupdf.open()  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
    for _ in range(3):
        page = document.new_page(width=300, height=400)
        page.insert_text((30, 40), "synthetic workbook")
        page.draw_rect(
            pymupdf.Rect(40, 80, 130, 170),  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
            color=(0, 0, 0),
        )
    for number in range(1, 4):
        render_one(sid, org_id, number, document)
    document.close()  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
    p1 = page_data()
    p1["stimuli"] = [
        {
            "ref": "s",
            "kind": "passage",
            "intro": None,
            "content": "passage",
            "box_2d": [20, 20, 80, 800],
            "continues_from_previous": False,
            "continues_on_next": False,
        }
    ]
    p1["questions"] = [
        question(
            continues_on_next=True,
            answer=None,
            figures=[{"box_2d": [180, 120, 450, 450], "kind": "diagram"}],
        )
    ]
    p2 = page_data()
    p2["questions"] = [
        question(
            stem="second", choices=[], figures=[], stimulus_ref=None, continues_from_previous=True
        )
    ]
    for value in (p1, p2, page_data("blank")):
        fake.queue("extract", value)
    extract_pages(str(sid), [1, 2, 3])
    with Session(get_engine()) as db:
        loaded = db.get(Source, sid)
        assert loaded is not None
        pages = list(
            db.scalars(
                select(SourcePage)
                .where(SourcePage.source_id == sid)
                .order_by(SourcePage.page_number)
            )
        )
        assert all(page.status == PageStatus.extracted for page in pages)
        materialize(db, loaded)
        db.commit()
        questions = list(db.scalars(select(Question).where(Question.source_id == sid)))
        assert len(questions) == 1
        item = questions[0]
        assert item.stem.startswith("first\nsecond")
        assert "![](asset:" in item.stem
        assert [r["page"] for r in item.regions] == [str(pages[0].id), str(pages[1].id)]
        assert item.choices[0]["pinned"] is True
        assert item.choices[0]["is_correct"] is True
        assert item.stimulus_id is not None
        assert db.scalar(select(Stimulus).where(Stimulus.id == item.stimulus_id)) is not None
        asset = db.scalar(select(Asset))
        assert asset is not None
        assert store.exists(asset.image_key)
        item.status = "approved"
        db.commit()
        materialize(db, loaded)
        db.commit()
        assert len(list(db.scalars(select(Question).where(Question.source_id == sid)))) == len(
            ["approved", "draft"]
        )
        assert store.exists(asset.image_key)
        draft = db.scalar(
            select(Question).where(Question.source_id == sid, Question.status == "draft")
        )
        assert draft is not None
        draft_id, approved_id = draft.id, item.id
        old_keys = materialize(db, loaded)
        db.commit()
        for old_key in old_keys:
            store.delete(old_key)
        assert db.get(Question, approved_id) is not None
        assert db.get(Question, draft_id) is None
        assert len(list(db.scalars(select(Question).where(Question.source_id == sid)))) == len(
            ["approved", "draft"]
        )
        assert store.exists(asset.image_key)
    assert pinned("كل ما سبق")
    assert not pinned("a choice")


@pytest.mark.integration
def test_budget_and_failure(database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalStore(tmp_path)
    monkeypatch.setattr(worker, "get_store", lambda: store)
    monkeypatch.setattr(worker, "page_done", lambda *args: None)
    fake = FakeLLMClient()
    monkeypatch.setattr(llm, "get_llm_client", lambda: fake)
    with Session(get_engine()) as db:
        org = Organization(name="test")
        db.add(org)
        db.flush()
        subject = Subject(org_id=org.id, name="English", language=Language.en)
        db.add(subject)
        db.flush()
        source = Source(
            org_id=org.id,
            subject_id=subject.id,
            title="test",
            file_key="x",
            status=SourceStatus.extracting,
            stage="extract",
        )
        db.add(source)
        db.flush()
        sid, org_id = source.id, org.id
        for n in range(1, 4):
            db.add(SourcePage(source_id=sid, page_number=n, status=PageStatus.rendered))
        db.commit()

    image = BytesIO()
    Image.new("RGB", (10, 10), "white").save(image, format="PNG")
    for n in range(1, 4):
        store.put_bytes(keys.page(org_id, sid, n, hires=True), image.getvalue(), "image/png")
    fake.queue("extract", page_data())
    fake.queue("extract", BudgetExceeded())
    extract_pages(str(sid), [1, 2, 3])
    with Session(get_engine()) as db:
        loaded = db.get(Source, sid)
        assert loaded is not None
        assert loaded.status == SourceStatus.paused
        pages = list(
            db.scalars(
                select(SourcePage)
                .where(SourcePage.source_id == sid)
                .order_by(SourcePage.page_number)
            )
        )
        assert [p.status for p in pages] == [
            PageStatus.extracted,
            PageStatus.rendered,
            PageStatus.rendered,
        ]
        loaded.status = SourceStatus.extracting
        db.commit()
    fake.queue("extract", ValueError("broken"))
    fake.queue("extract", page_data("blank"))
    extract_pages(str(sid), [2, 3])
    with Session(get_engine()) as db:
        pages = list(
            db.scalars(
                select(SourcePage)
                .where(SourcePage.source_id == sid)
                .order_by(SourcePage.page_number)
            )
        )
        assert [p.status for p in pages] == [
            PageStatus.extracted,
            PageStatus.failed,
            PageStatus.extracted,
        ]


@pytest.mark.integration
def test_resume_and_read_api(
    database: str, app: FastAPI, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalStore(tmp_path)
    monkeypatch.setattr(sources_router, "get_store", lambda: store)
    started: list[str] = []
    monkeypatch.setattr(
        orchestrator,
        "STAGES",
        [
            orchestrator.Stage(
                "extract", started.append, SourceStatus.extracting, PageStatus.rendered
            ),
            orchestrator.Stage(
                "materialize",
                worker.materialize_source,
                SourceStatus.extracting,
                PageStatus.extracted,
            ),
        ],
    )
    with Session(get_engine()) as db:
        org = Organization(name="API")
        db.add(org)
        db.flush()
        subject = Subject(org_id=org.id, name="English", language=Language.en)
        db.add(subject)
        db.flush()
        user = User(
            org_id=org.id,
            email="editor@test.local",
            name="Editor",
            password_hash="test-only",  # noqa: S106 -- unused test credential
            role=Role.editor,
            is_active=True,
        )
        source = Source(
            org_id=org.id,
            subject_id=subject.id,
            title="test",
            file_key="x",
            status=SourceStatus.paused,
            stage="extract",
            error="BudgetExceeded",
        )
        db.add_all([user, source])
        db.flush()
        page = SourcePage(
            source_id=source.id,
            page_number=1,
            status=PageStatus.rendered,
            extraction=page_data("blank"),
        )
        db.add(page)
        db.flush()
        asset = Asset(
            org_id=org.id,
            source_page_id=None,
            kind="figure",
            image_key="asset.webp",
            region=[0.0, 0.0, 1.0, 1.0],
            width=2,
            height=2,
        )
        db.add(asset)
        db.commit()
        source_id, asset_id, org_id = source.id, asset.id, org.id
        db.refresh(user)
        db.expunge(user)
    app.dependency_overrides[current_user] = lambda: user
    store.put_bytes("asset.webp", b"image", "image/webp")
    response = client.post(f"/api/v1/sources/{source_id}/resume")
    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json()["status"] == "extracting"
    assert started == [str(source_id)]
    image = BytesIO()
    Image.new("RGB", (10, 10), "white").save(image, format="PNG")
    store.put_bytes(keys.page(org_id, source_id, 1, hires=True), image.getvalue(), "image/png")
    fake = FakeLLMClient()
    fake.queue("extract", page_data("blank"))
    monkeypatch.setattr(llm, "get_llm_client", lambda: fake)
    monkeypatch.setattr(worker, "get_store", lambda: store)
    monkeypatch.setattr(materialize_module, "get_store", lambda: store)
    worker.extract_pages(str(source_id), [1])
    assert client.get(f"/api/v1/sources/{source_id}").json()["status"] == "ready"
    assert (
        client.get(f"/api/v1/sources/{source_id}/pages/1").json()["extraction"]["page_kind"]
        == "blank"
    )
    assert client.get(f"/api/v1/sources/{source_id}/questions").json() == []
    assert client.get(f"/api/v1/sources/{source_id}/stimuli").json() == []
    response = client.get(f"/api/v1/assets/{asset_id}/image")
    assert response.content == b"image"
    assert (
        client.get(
            f"/api/v1/assets/{asset_id}/image", headers={"If-None-Match": response.headers["etag"]}
        ).status_code
        == HTTPStatus.NOT_MODIFIED
    )
    app.dependency_overrides.clear()


def test_stimulus_continuation_and_unmatched_notes() -> None:
    p1, p2 = page_data(), page_data()
    stimulus = {
        "ref": "s",
        "kind": "passage",
        "intro": None,
        "content": "first",
        "box_2d": [0, 0, 100, 100],
        "continues_from_previous": False,
        "continues_on_next": True,
    }
    p1["stimuli"] = [stimulus]
    p2["stimuli"] = [
        {
            **stimulus,
            "content": "second",
            "continues_from_previous": True,
            "continues_on_next": False,
        }
    ]
    p2["questions"] = [question(continues_from_previous=True)]
    pages = [
        SourcePage(
            id=uuid4(), source_id=uuid4(), page_number=1, status=PageStatus.extracted, extraction=p1
        ),
        SourcePage(
            id=uuid4(), source_id=uuid4(), page_number=2, status=PageStatus.extracted, extraction=p2
        ),
    ]
    stimuli, questions = stitch(pages)
    assert len(stimuli) == 1
    assert len(stimuli[0].regions) == len(pages)
    assert isinstance(stimuli[0].value, ExtractedStimulus)
    assert stimuli[0].value.content == "first\nsecond"
    assert questions[0].notes == ["Unmatched continuation from previous page"]
