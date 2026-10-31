import re
import zipfile
from collections.abc import Iterator
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

import pymupdf
import pytest
from docx import Document
from docx.document import Document as DocxDocument
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from qbank.auth import hasher
from qbank.config import get_settings
from qbank.db import get_db
from qbank.export.builder import StoreAssets, build_view
from qbank.export.render import render_answer_key
from qbank.export.view import arabic_digits, format_number
from qbank.models import (
    Asset,
    Exam,
    ExamVersion,
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
from qbank.services import exam_generation
from qbank.storage import get_store
from qbank.worker import render_exports

pytestmark = [pytest.mark.integration, pytest.mark.pdf]

URL = "/api/v1"
TITLE = "اختبار الرياضيات"
A4 = (595.0, 842.0)
TOLERANCE = 2
MIN_PDF_BYTES = 1000
EXPORTS_REQUESTED = 4


def choices(correct: int, contents: list[str]) -> list[dict[str, object]]:
    return [
        {"label": "abcd"[i], "content": c, "is_correct": i == correct, "pinned": False}
        for i, c in enumerate(contents)
    ]


@pytest.fixture
def ids(
    database: str, app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, Any]]:
    monkeypatch.setenv("QBANK_STORAGE_BACKEND", "local")
    monkeypatch.setenv("QBANK_STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    get_store.cache_clear()
    engine = create_engine(database)
    with Session(engine) as db:
        org, other = Organization(name="A"), Organization(name="B")
        db.add_all([org, other])
        db.flush()
        users = {
            email: User(
                org_id=o.id,
                email=email,
                name=email,
                role=role,
                password_hash=hasher.hash("password"),
            )
            for o, email, role in [
                (org, "admin@a.com", Role.admin),
                (org, "t1@a.com", Role.teacher),
                (org, "t2@a.com", Role.teacher),
            ]
        }
        db.add_all(users.values())
        subject = Subject(org_id=org.id, name="رياضيات", language=Language.ar, grade="3")
        db.add(subject)
        db.flush()
        source = Source(
            org_id=org.id,
            subject_id=subject.id,
            title="s",
            file_key="k",
            status=SourceStatus.ready,
        )
        db.add(source)
        db.flush()
        image_key = f"orgs/{org.id}/assets/figure.png"
        buffer = BytesIO()
        Image.new("RGB", (240, 140), (30, 90, 200)).save(buffer, "PNG")
        get_store().put_bytes(image_key, buffer.getvalue(), "image/png")
        figure = Asset(
            org_id=org.id,
            kind="figure",
            image_key=image_key,
            region=[0, 0, 1, 1],
            width=240,
            height=140,
        )
        logo = Asset(
            org_id=org.id,
            kind="logo",
            image_key=image_key,
            region=[0, 0, 1, 1],
            width=240,
            height=140,
        )
        db.add_all([figure, logo])
        stimulus = Stimulus(
            org_id=org.id,
            source_id=source.id,
            kind="passage",
            content="يقطع القطار مسافة $120$ كم في ساعتين.",
            regions=[],
        )
        db.add(stimulus)
        db.flush()
        counter = 0

        def question(**kw: Any) -> Question:
            nonlocal counter
            counter += 1
            values: dict[str, Any] = {
                "org_id": org.id,
                "subject_id": subject.id,
                "source_id": source.id,
                "position": counter,
                "number_label": str(counter),
                "type": "mcq_single",
                "stem": f"سؤال {counter}",
                "choices": choices(counter % 4, ["1", "2", "3", "4"]),
                "language": Language.ar,
                "regions": [],
                "status": "approved",
                "confidence": 1.0,
                "tags": [],
            }
            values.update(kw)
            q = Question(**values)
            db.add(q)
            db.flush()
            return q

        mcqs = [
            question(
                stem="ما ناتج $\\frac{1}{2}+\\frac{1}{4}$ ؟",
                choices=choices(0, ["$\\frac{3}{4}$", "$1$", "$\\frac{1}{8}$", "$2$"]),
            ),
            question(stem=f"انظر الشكل ثم أجب:\n\n![شكل](asset:{figure.id})"),
            question(
                stem="املأ الفراغ: ____ عاصمة مصر", choices=choices(2, ["أ", "ب", "القاهرة", "د"])
            ),
        ]
        essay = question(
            type="essay",
            stem="اكتب معادلة تكوين الماء: $\\ce{2H2 + O2 -> 2H2O}$",
            choices=[],
            answer="لأن القوة تساوي الكتلة في العجلة",
        )
        group = [
            question(
                stimulus_id=stimulus.id,
                stimulus_position=p,
                choices=choices(p, ["1", "2", "3", "4"]),
            )
            for p in (1, 2)
        ]
        db.commit()
        out = {
            "subject": str(subject.id),
            "mcq": [str(q.id) for q in mcqs] + [str(q.id) for q in group],
            "essay": str(essay.id),
            "logo": str(logo.id),
            "org": org.id,
        }

    def override() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield out
    engine.dispose()
    get_store.cache_clear()


def login(client: TestClient, email: str) -> None:
    response = client.post(f"{URL}/auth/login", json={"email": email, "password": "password"})
    assert response.status_code == HTTPStatus.OK, response.text
    client.headers["X-CSRF-Token"] = client.cookies["qbank_csrf"]


def make_exam(
    client: TestClient, ids: dict[str, Any], questions: list[str], **settings: Any
) -> str:
    body: dict[str, Any] = {"title": TITLE, "subject_id": ids["subject"]}
    if settings:
        body["settings"] = settings
    response = client.post(f"{URL}/exams", json=body)
    assert response.status_code == HTTPStatus.CREATED, response.text
    exam_id = str(response.json()["id"])
    added = client.post(
        f"{URL}/exams/{exam_id}/items", json={"question_ids": questions, "points": 2}
    )
    assert added.status_code == HTTPStatus.CREATED, added.text
    versions = client.post(f"{URL}/exams/{exam_id}/versions", json={"count": 2, "seed": 7})
    assert versions.status_code == HTTPStatus.CREATED, versions.text
    return exam_id


def run_actor(ids_: list[str]) -> None:
    render_exports.fn(ids_)


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[UUID]:
    sent: list[UUID] = []
    monkeypatch.setattr("qbank.services.exports.enqueue", sent.extend)
    return sent


def drain(queued: list[UUID]) -> None:
    run_actor([str(i) for i in queued])
    queued.clear()


def pdf_of(response: Any) -> pymupdf.Document:
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    return pymupdf.open(stream=response.content, filetype="pdf")  # type: ignore[no-untyped-call]


def pages(document: pymupdf.Document) -> list[pymupdf.Page]:
    return [document[i] for i in range(document.page_count)]


def fonts(document: pymupdf.Document) -> set[str]:
    # PyMuPDF page methods are untyped.
    return {
        font[3]
        for page in pages(document)
        for font in page.get_fonts()  # type: ignore[no-untyped-call]
    }


def test_real_pdfs_for_arabic_exam_with_math_and_figure(
    ids: dict[str, Any], client: TestClient, queued: list[UUID]
) -> None:
    login(client, "t1@a.com")
    exam_id = make_exam(client, ids, ids["mcq"] + [ids["essay"]])
    response = client.post(
        f"{URL}/exams/{exam_id}/exports",
        json={"versions": "all", "kinds": ["pdf", "answer_key_pdf"]},
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    assert len(response.json()["exports"]) == EXPORTS_REQUESTED
    drain(queued)
    listing = client.get(f"{URL}/exams/{exam_id}/exports").json()
    assert {e["status"] for e in listing} == {"ready"}
    assert {e["version_label"] for e in listing} == {"أ", "ب"}
    exam_pdf = next(e for e in listing if e["kind"] == "pdf" and e["version_label"] == "أ")
    key_pdf = next(
        e for e in listing if e["kind"] == "answer_key_pdf" and e["version_label"] == "أ"
    )

    exam = pdf_of(client.get(f"{URL}/exports/{exam_pdf['id']}/download"))
    assert exam.page_count >= 1
    assert abs(exam[0].rect.width - A4[0]) < TOLERANCE
    assert abs(exam[0].rect.height - A4[1]) < TOLERANCE
    assert any("NotoNaskh" in f for f in fonts(exam))
    assert any("KaTeX" in f for f in fonts(exam))  # math was typeset
    assert any(
        page.get_images()  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
        for page in pages(exam)
    )  # the figure
    assert exam_pdf["size_bytes"] > MIN_PDF_BYTES
    footer = "".join(
        page.get_text()  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
        for page in pages(exam)
    )
    assert "1" in footer

    key = pdf_of(client.get(f"{URL}/exports/{key_pdf['id']}/download"))
    assert key.page_count >= 1
    assert any("NotoNaskh" in f for f in fonts(key))


def test_bubble_sheet_pdf_and_mcq_only_rule(
    ids: dict[str, Any], client: TestClient, queued: list[UUID]
) -> None:
    login(client, "t1@a.com")
    mixed = make_exam(client, ids, ids["mcq"] + [ids["essay"]])
    refused = client.post(
        f"{URL}/exams/{mixed}/exports", json={"versions": ["أ"], "kinds": ["bubble_sheet_pdf"]}
    )
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert queued == []
    only = make_exam(client, ids, ids["mcq"])
    accepted = client.post(
        f"{URL}/exams/{only}/exports", json={"versions": ["أ"], "kinds": ["bubble_sheet_pdf"]}
    )
    assert accepted.status_code == HTTPStatus.ACCEPTED
    drain(queued)
    (row,) = client.get(f"{URL}/exams/{only}/exports").json()
    assert row["status"] == "ready"
    sheet = pdf_of(client.get(f"{URL}/exports/{row['id']}/download"))
    assert sheet.page_count == 1
    assert abs(sheet[0].rect.width - A4[0]) < TOLERANCE
    assert any("NotoNaskh" in f for f in fonts(sheet))


def test_export_flow_download_stale_regenerate_and_delete(
    ids: dict[str, Any], client: TestClient, queued: list[UUID]
) -> None:
    login(client, "t1@a.com")
    exam_id = make_exam(client, ids, ids["mcq"][:3])
    created = client.post(
        f"{URL}/exams/{exam_id}/exports", json={"versions": ["أ"], "kinds": ["pdf"]}
    )
    assert created.status_code == HTTPStatus.ACCEPTED
    (pending,) = created.json()["exports"]
    assert pending["status"] == "pending"
    not_ready = client.get(f"{URL}/exports/{pending['id']}/download")
    assert not_ready.status_code == HTTPStatus.CONFLICT
    drain(queued)

    (row,) = client.get(f"{URL}/exams/{exam_id}/exports").json()
    assert row["status"] == "ready"
    assert row["stale"] is False
    download = client.get(f"{URL}/exports/{row['id']}/download")
    assert download.status_code == HTTPStatus.OK
    disposition = download.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f"filename*=UTF-8''{quote(f'{TITLE}-أ-pdf.pdf', safe='')}" in disposition
    assert disposition.isascii()
    assert int(download.headers["content-length"]) == len(download.content) == row["size_bytes"]

    edited = client.patch(f"{URL}/exams/{exam_id}", json={"title": "عنوان جديد"})
    assert edited.status_code == HTTPStatus.OK
    (row,) = client.get(f"{URL}/exams/{exam_id}/exports").json()
    assert row["stale"] is True

    client.post(f"{URL}/exams/{exam_id}/exports", json={"versions": ["أ"], "kinds": ["pdf"]})
    drain(queued)
    (fresh,) = client.get(f"{URL}/exams/{exam_id}/exports").json()
    assert fresh["id"] != row["id"]  # the superseded export is replaced
    assert fresh["stale"] is False
    assert client.delete(f"{URL}/exports/{fresh['id']}").status_code == HTTPStatus.NO_CONTENT
    assert client.get(f"{URL}/exports/{fresh['id']}/download").status_code == HTTPStatus.NOT_FOUND
    assert client.get(f"{URL}/exams/{exam_id}/exports").json() == []


def test_scoping_validation_and_failures(
    ids: dict[str, Any],
    client: TestClient,
    queued: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login(client, "t1@a.com")
    exam_id = make_exam(client, ids, ids["mcq"][:2])
    body = {"versions": ["أ"], "kinds": ["pdf"]}
    assert client.post(
        f"{URL}/exams/{exam_id}/exports", json={**body, "versions": ["ز"]}
    ).status_code == (HTTPStatus.NOT_FOUND)
    assert client.post(
        f"{URL}/exams/{exam_id}/exports", json={**body, "kinds": ["pptx"]}
    ).status_code == (HTTPStatus.UNPROCESSABLE_ENTITY)
    empty = client.post(f"{URL}/exams", json={"title": "x", "subject_id": ids["subject"]}).json()[
        "id"
    ]
    assert client.post(f"{URL}/exams/{empty}/exports", json={"kinds": ["pdf"]}).status_code == (
        HTTPStatus.UNPROCESSABLE_ENTITY
    )

    def boom(*_: object, **__: object) -> bytes:
        raise RuntimeError("chromium crashed")

    monkeypatch.setattr("qbank.services.exports.render_export", boom)
    client.post(f"{URL}/exams/{exam_id}/exports", json=body)
    drain(queued)
    (failed,) = client.get(f"{URL}/exams/{exam_id}/exports").json()
    assert failed["status"] == "failed"
    assert failed["error"] == "export_failed"
    assert client.get(f"{URL}/exports/{failed['id']}/download").status_code == HTTPStatus.CONFLICT

    login(client, "t2@a.com")  # another teacher cannot see the exam, so neither its exports
    assert client.get(f"{URL}/exams/{exam_id}/exports").status_code == HTTPStatus.NOT_FOUND
    assert client.get(f"{URL}/exports/{failed['id']}/download").status_code == HTTPStatus.NOT_FOUND
    assert client.delete(f"{URL}/exports/{failed['id']}").status_code == HTTPStatus.NOT_FOUND
    login(client, "admin@a.com")  # admins see everything in their organization
    assert client.get(f"{URL}/exams/{exam_id}/exports").status_code == HTTPStatus.OK
    # Re-running a finished export is a no-op.
    run_actor([failed["id"], "00000000-0000-0000-0000-000000000000"])


def test_templates_crud_and_header_defaults(ids: dict[str, Any], client: TestClient) -> None:
    login(client, "t1@a.com")
    body = {
        "name": "مدرسة النور",
        "header": {"school_name": "مدرسة النور", "instructions": "اكتب بوضوح", "grade": "9"},
        "logo_asset_id": ids["logo"],
    }
    assert client.post(f"{URL}/exam-templates", json=body).status_code == HTTPStatus.FORBIDDEN
    login(client, "admin@a.com")
    created = client.post(f"{URL}/exam-templates", json=body)
    assert created.status_code == HTTPStatus.CREATED, created.text
    template = created.json()
    assert template["header"]["school_name"] == "مدرسة النور"
    missing_logo = client.post(
        f"{URL}/exam-templates",
        json={**body, "logo_asset_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing_logo.status_code == HTTPStatus.NOT_FOUND
    patched = client.patch(
        f"{URL}/exam-templates/{template['id']}", json={"name": "جديد", "logo_asset_id": None}
    )
    assert patched.json()["name"] == "جديد"
    assert patched.json()["logo_asset_id"] is None
    assert (
        client.patch(
            f"{URL}/exam-templates/{template['id']}", json={"logo_asset_id": ids["logo"]}
        ).status_code
        == HTTPStatus.OK
    )
    login(client, "t1@a.com")
    assert client.get(f"{URL}/exam-templates").json()["items"][0]["id"] == template["id"]
    assert client.get(f"{URL}/exam-templates/{template['id']}").status_code == HTTPStatus.OK
    assert (
        client.get(f"{URL}/exam-templates?cursor=bad").status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )

    unknown = client.post(
        f"{URL}/exams",
        json={
            "title": "t",
            "subject_id": ids["subject"],
            "settings": {"template_id": "00000000-0000-0000-0000-000000000000"},
        },
    )
    assert unknown.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    exam_id = make_exam(
        client,
        ids,
        ids["mcq"][:2],
        template_id=template["id"],
        header={"grade": "الثالث", "exam_title": "عنوان خاص"},
    )
    engine = create_engine(get_settings().database_url)
    with Session(engine) as db:
        exam = db.get(Exam, UUID(exam_id))
        version = db.scalar(select(ExamVersion).where(ExamVersion.exam_id == UUID(exam_id)))
        assert exam is not None
        assert version is not None
        view = build_view(db, exam, version, StoreAssets(db, exam.org_id, get_store()))
    assert view.header.school_name == "مدرسة النور"  # from the template
    assert view.header.instructions == "اكتب بوضوح"
    assert view.header.grade == "الثالث"  # the exam's own value wins
    assert view.header.exam_title == "عنوان خاص"
    assert view.header.logo_uri is not None
    assert view.header.logo_uri.startswith("data:image/png;base64,")
    engine.dispose()
    login(client, "admin@a.com")
    assert (
        client.delete(f"{URL}/exam-templates/{template['id']}").status_code == HTTPStatus.NO_CONTENT
    )
    assert client.get(f"{URL}/exam-templates/{template['id']}").status_code == HTTPStatus.NOT_FOUND


def test_answer_key_pdf_matches_answer_key_endpoint(
    ids: dict[str, Any], client: TestClient
) -> None:
    login(client, "t1@a.com")
    exam_id = make_exam(client, ids, ids["mcq"] + [ids["essay"]])
    endpoint = client.get(f"{URL}/exams/{exam_id}/versions/ب/answer-key").json()
    engine = create_engine(get_settings().database_url)
    with Session(engine) as db:
        exam = db.get(Exam, UUID(exam_id))
        version = db.scalar(
            select(ExamVersion).where(
                ExamVersion.exam_id == UUID(exam_id), ExamVersion.label == "ب"
            )
        )
        assert exam is not None
        assert version is not None
        key = exam_generation.key_for(db, exam, version)
        view = build_view(db, exam, version, StoreAssets(db, exam.org_id, get_store()))
        html = render_answer_key(view.with_key(key))
    engine.dispose()
    assert key.model_dump(mode="json") == endpoint
    for item in endpoint["items"]:
        for label in item["correct"] or []:
            assert label in html
    assert "لأن القوة تساوي الكتلة في العجلة" in html
    assert html.count("<tr>") == len(endpoint["items"]) + 2  # header + rows + total


DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
QUESTIONS_IN_DOCX = 6


def docx_parts(response: Any) -> tuple[zipfile.ZipFile, DocxDocument]:
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == DOCX_TYPE
    assert response.content.startswith(b"PK")
    archive = zipfile.ZipFile(BytesIO(response.content))
    return archive, Document(BytesIO(response.content))


def test_real_docx_for_arabic_exam_with_math_chemistry_and_figure(
    ids: dict[str, Any], client: TestClient, queued: list[UUID]
) -> None:
    login(client, "t1@a.com")
    exam_id = make_exam(client, ids, ids["mcq"] + [ids["essay"]])
    response = client.post(
        f"{URL}/exams/{exam_id}/exports",
        json={"versions": ["ب"], "kinds": ["docx", "answer_key_docx"]},
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    drain(queued)
    listing = client.get(f"{URL}/exams/{exam_id}/exports").json()
    assert {e["status"] for e in listing} == {"ready"}
    exam_row = next(e for e in listing if e["kind"] == "docx")
    key_row = next(e for e in listing if e["kind"] == "answer_key_docx")

    download = client.get(f"{URL}/exports/{exam_row['id']}/download")
    archive, document = docx_parts(download)
    disposition = download.headers["content-disposition"]
    assert f"filename*=UTF-8''{quote(f'{TITLE}-ب-docx.docx', safe='')}" in disposition
    assert disposition.isascii()
    assert (
        int(download.headers["content-length"]) == len(download.content) == exam_row["size_bytes"]
    )

    xml = archive.read("word/document.xml").decode()
    assert xml.count("<m:oMath>") >= QUESTIONS_IN_DOCX - 2  # fractions, group stimulus, chemistry
    assert "\\ce" not in xml
    media = [n for n in archive.namelist() if n.startswith("word/media/")]
    assert len(media) == 1  # only the figure: equations are not images
    assert media[0].endswith(".png")
    assert xml.count("<w:bidi/>") >= QUESTIONS_IN_DOCX
    assert "w:bidiVisual" in xml

    engine = create_engine(get_settings().database_url)
    with Session(engine) as db:
        exam = db.get(Exam, UUID(exam_id))
        version = db.scalar(
            select(ExamVersion).where(
                ExamVersion.exam_id == UUID(exam_id), ExamVersion.label == "ب"
            )
        )
        assert exam is not None
        assert version is not None
        view = build_view(db, exam, version, StoreAssets(db, exam.org_id, get_store()))
    engine.dispose()
    questions = view.questions
    assert len(questions) == QUESTIONS_IN_DOCX
    numbers = [
        p.text.split("-")[0]
        for p in document.paragraphs
        if p.style is not None and p.style.name == "Question" and re.match(r"\d+-", p.text)
    ]
    assert numbers == [arabic_digits(str(q.number)) for q in questions]
    tables = [t for t in document.tables if t.style is not None and t.style.name == "PlainTable"]
    shown = [
        [c.text.split(" ")[0] for r in t.rows for c in r.cells if c.text]
        for t in tables[1:]  # the first is the student-fields table
    ]
    assert shown == [[c.label for c in q.choices] for q in questions if q.choices]
    header = " ".join(c.text for c in document.tables[0]._cells)
    assert view.header.subject in header
    assert "النموذج: ب" in header
    assert any(p.text == TITLE for p in document.paragraphs)

    key = client.get(f"{URL}/exams/{exam_id}/versions/ب/answer-key").json()
    _, key_doc = docx_parts(client.get(f"{URL}/exports/{key_row['id']}/download"))
    (key_table,) = key_doc.tables
    rows = [[c.text for c in r.cells] for r in key_table.rows]
    assert len(rows) == len(key["items"]) + 2  # header + rows + total
    for item, row in zip(key["items"], rows[1:-1], strict=True):
        assert row[0] == arabic_digits(str(item["number"]))
        assert row[2] == arabic_digits(format_number(item["points"]))
        for label in item["correct"] or []:
            assert label in row[1]


def test_english_docx_is_left_to_right(
    ids: dict[str, Any], client: TestClient, queued: list[UUID]
) -> None:
    login(client, "t1@a.com")
    exam_id = make_exam(client, ids, ids["mcq"][:2], language="en")
    response = client.post(
        f"{URL}/exams/{exam_id}/exports", json={"versions": "all", "kinds": ["docx", "docx"]}
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    assert [e["kind"] for e in response.json()["exports"]] == [
        "docx",
        "docx",
    ]  # kinds de-duplicated
    drain(queued)
    for row in client.get(f"{URL}/exams/{exam_id}/exports").json():
        archive, _ = docx_parts(client.get(f"{URL}/exports/{row['id']}/download"))
        assert "<w:bidi" not in archive.read("word/document.xml").decode()


def test_template_logo_upload(ids: dict[str, Any], client: TestClient) -> None:
    login(client, "admin@a.com")
    template = client.post(f"{URL}/exam-templates", json={"name": "Logo"}).json()
    image = BytesIO()
    Image.new("RGB", (1200, 300)).save(image, "JPEG")
    path = f"{URL}/exam-templates/{template['id']}/logo"
    response = client.post(path, files={"file": ("logo.jpg", image.getvalue(), "image/jpeg")})
    assert response.status_code == HTTPStatus.OK
    asset_id = response.json()["logo_asset_id"]
    result = client.get(f"{URL}/assets/{asset_id}/image")
    with Image.open(BytesIO(result.content)) as decoded:
        assert decoded.format == "PNG"
        assert decoded.size == (600, 150)
    assert (
        client.post(path, files={"file": ("x.png", b"invalid", "image/png")}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    assert (
        client.post(
            path, files={"file": ("large.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")}
        ).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    assert (
        client.post(path, files={"file": ("logo.gif", image.getvalue(), "image/gif")}).status_code
        == HTTPStatus.UNPROCESSABLE_ENTITY
    )
    login(client, "t1@a.com")
    assert (
        client.post(path, files={"file": ("logo.jpg", image.getvalue(), "image/jpeg")}).status_code
        == HTTPStatus.FORBIDDEN
    )
