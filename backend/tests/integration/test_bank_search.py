from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
    Chapter,
    Language,
    Lesson,
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
    ValidationIssue,
)
from qbank.text.normalize import content_hash, question_normalized_text


def _login(client: TestClient, email: str) -> None:
    client.raise_server_exceptions = True
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "password"})
    assert response.status_code == HTTPStatus.OK, response.text
    client.headers["X-CSRF-Token"] = client.cookies["qbank_csrf"]


def _make_question(  # noqa: PLR0913 -- test helper for constructing Question rows
    *,
    org_id: UUID,
    subject_id: UUID,
    source_id: UUID,
    position: int,
    number_label: str,
    stem: str,
    choices: list[dict[str, object]] | None = None,
    answer: str | None = None,
    qtype: str = "mcq_single",
    difficulty: int | None = 3,
    tags: list[str] | None = None,
    status: str = "approved",
    chapter_id: UUID | None = None,
    lesson_id: UUID | None = None,
    stimulus_id: UUID | None = None,
    regions: list[dict[str, object]] | None = None,
    duplicate_of_id: UUID | None = None,
    metadata_json: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> Question:
    actual_choices = (
        choices
        if choices is not None
        else [
            {"label": "أ", "content": "اختيار أول", "is_correct": True, "pinned": False},
            {"label": "ب", "content": "اختيار ثان", "is_correct": False, "pinned": False},
        ]
    )
    norm = question_normalized_text(stem, actual_choices)
    q = Question(
        org_id=org_id,
        subject_id=subject_id,
        source_id=source_id,
        chapter_id=chapter_id,
        lesson_id=lesson_id,
        stimulus_id=stimulus_id,
        position=position,
        number_label=number_label,
        type=qtype,
        stem=stem,
        choices=actual_choices,
        answer=answer,
        difficulty=difficulty,
        language=Language.ar,
        tags=tags if tags is not None else [],
        regions=regions if regions is not None else [],
        status=status,
        confidence=0.95,
        normalized_text=norm,
        content_hash=content_hash(norm),
        duplicate_of_id=duplicate_of_id,
        metadata_json=metadata_json if metadata_json is not None else {},
    )
    if created_at is not None:
        q.created_at = created_at
    return q


@pytest.fixture
def bank_env(database: str, app: FastAPI) -> Iterator[dict[str, Any]]:  # noqa: PLR0915 -- test fixture populating dataset
    engine = create_engine(database)
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    with Session(engine) as db:
        org_a = Organization(name="Org A")
        org_b = Organization(name="Org B")
        db.add_all([org_a, org_b])
        db.flush()

        users = [
            User(
                org_id=org_a.id,
                email="admin@a.com",
                name="Admin A",
                role=Role.admin,
                password_hash=hasher.hash("password"),
                is_active=True,
            ),
            User(
                org_id=org_a.id,
                email="editor@a.com",
                name="Editor A",
                role=Role.editor,
                password_hash=hasher.hash("password"),
                is_active=True,
            ),
            User(
                org_id=org_a.id,
                email="teacher@a.com",
                name="Teacher A",
                role=Role.teacher,
                password_hash=hasher.hash("password"),
                is_active=True,
            ),
            User(
                org_id=org_b.id,
                email="admin@b.com",
                name="Admin B",
                role=Role.admin,
                password_hash=hasher.hash("password"),
                is_active=True,
            ),
        ]
        db.add_all(users)

        sub_bio = Subject(org_id=org_a.id, name="الأحياء", language=Language.ar, grade="3")
        sub_phys = Subject(org_id=org_a.id, name="الفيزياء", language=Language.ar, grade="3")
        sub_b = Subject(org_id=org_b.id, name="الأحياء B", language=Language.ar, grade="3")
        db.add_all([sub_bio, sub_phys, sub_b])
        db.flush()

        ch1 = Chapter(subject_id=sub_bio.id, title="الدعامة والحركة", position=1)
        ch2 = Chapter(subject_id=sub_bio.id, title="التنسيق الهرموني", position=2)
        ch_phys = Chapter(subject_id=sub_phys.id, title="الكهرباء", position=1)
        ch_b = Chapter(subject_id=sub_b.id, title="فصل B", position=1)
        db.add_all([ch1, ch2, ch_phys, ch_b])
        db.flush()

        les1 = Lesson(chapter_id=ch1.id, title="الدعامة في النبات", position=1)
        les2 = Lesson(chapter_id=ch1.id, title="الهيكل العظمي", position=2)
        les3 = Lesson(chapter_id=ch2.id, title="الغدد الصماء", position=1)
        les_phys = Lesson(chapter_id=ch_phys.id, title="قانون أوم", position=1)
        les_b = Lesson(chapter_id=ch_b.id, title="درس B", position=1)
        db.add_all([les1, les2, les3, les_phys, les_b])
        db.flush()

        src1 = Source(
            org_id=org_a.id,
            subject_id=sub_bio.id,
            title="كتاب الامتحان أحياء",
            file_key="s1.pdf",
            status=SourceStatus.ready,
        )
        src2 = Source(
            org_id=org_a.id,
            subject_id=sub_bio.id,
            title="مذكرة المراجعة النهائية",
            file_key="s2.pdf",
            status=SourceStatus.ready,
        )
        src_phys = Source(
            org_id=org_a.id,
            subject_id=sub_phys.id,
            title="كتاب الفيزياء",
            file_key="sp.pdf",
            status=SourceStatus.ready,
        )
        src_b = Source(
            org_id=org_b.id,
            subject_id=sub_b.id,
            title="مصدر B",
            file_key="sb.pdf",
            status=SourceStatus.ready,
        )
        db.add_all([src1, src2, src_phys, src_b])
        db.flush()

        page1 = SourcePage(
            source_id=src1.id,
            page_number=7,
            status=PageStatus.validated,
        )
        db.add(page1)
        db.flush()

        stim1 = Stimulus(
            org_id=org_a.id,
            source_id=src1.id,
            kind="passage",
            content="نص القراءة المشترك",
            regions=[],
            status="approved",
        )
        db.add(stim1)
        db.flush()

        # Question 1: Tashkeel, alef variants (إبراهيم / أحمد), digits (25), figure, stimulus
        q1_stem = (
            "مَا هِيَ وَظِيفَةُ الْخَلِيَّةِ النَّبَاتِيَّةِ فِي إِبْرَاهِيمَ عِنْدَ دَرَجَةِ 25 مئوية؟ "
            "![](asset:11111111-1111-1111-1111-111111111111) " + ("شرح إضافي " * 25)
        )
        q1 = _make_question(
            org_id=org_a.id,
            subject_id=sub_bio.id,
            source_id=src1.id,
            position=1,
            number_label="\u0661",
            stem=q1_stem,
            qtype="mcq_single",
            difficulty=2,
            tags=["نبات", "دعامة", "خلية"],
            status="approved",
            chapter_id=ch1.id,
            lesson_id=les1.id,
            stimulus_id=stim1.id,
            regions=[{"page": str(page1.id), "box": [0.1, 0.1, 0.9, 0.4]}],
            metadata_json={"exam_title": "الاختبار الأول"},
            created_at=base_time + timedelta(minutes=1),
        )

        # Question 2: English + Arabic mixed, essay, no answer, difficulty 4
        q2 = _make_question(
            org_id=org_a.id,
            subject_id=sub_bio.id,
            source_id=src1.id,
            position=2,
            number_label="٢",
            stem="اشرح دور هرمون الإنسولين وميتوكوندريا mitochondria في تنظيم السكر.",
            choices=[],
            answer=None,
            qtype="essay",
            difficulty=4,
            tags=["هرمونات", "طاقة"],
            status="approved",
            chapter_id=ch2.id,
            lesson_id=les3.id,
            metadata_json={"exam_title": "الاختبار الثاني"},
            created_at=base_time + timedelta(minutes=2),
        )

        # Question 3: Approved question in lesson 2, source 2, difficulty 1
        q3 = _make_question(
            org_id=org_a.id,
            subject_id=sub_bio.id,
            source_id=src2.id,
            position=1,
            number_label="٣",
            stem="كم عدد عظام الجمجمة في الإنسان البالغ؟",
            choices=[],
            answer="٢٢ عظمة",
            qtype="short_answer",
            difficulty=1,
            tags=["تشريح", "دعامة"],
            status="approved",
            chapter_id=ch1.id,
            lesson_id=les2.id,
            created_at=base_time + timedelta(minutes=3),
        )

        # Question 4: Draft question (not visible to teachers)
        q4 = _make_question(
            org_id=org_a.id,
            subject_id=sub_bio.id,
            source_id=src2.id,
            position=2,
            number_label="٤",
            stem="سؤال مسودة قيد المراجعة عن الغضاريف والمفاصل الزلالية.",
            qtype="true_false",
            difficulty=5,
            tags=["مفاصل", "دعامة"],
            status="draft",
            chapter_id=ch1.id,
            lesson_id=les2.id,
            created_at=base_time + timedelta(minutes=4),
        )

        # Question 5: Duplicate of q1 (hidden when exclude_duplicates=true)
        db.add_all([q1, q2, q3, q4])
        db.flush()

        q5 = _make_question(
            org_id=org_a.id,
            subject_id=sub_bio.id,
            source_id=src2.id,
            position=3,
            number_label="\u0665",
            stem=q1_stem,
            qtype="mcq_single",
            difficulty=2,
            tags=["نبات"],
            status="approved",
            chapter_id=ch1.id,
            lesson_id=les1.id,
            duplicate_of_id=q1.id,
            created_at=base_time + timedelta(minutes=5),
        )

        # Question in Org B (for cross-org isolation test)
        q_org_b = _make_question(
            org_id=org_b.id,
            subject_id=sub_b.id,
            source_id=src_b.id,
            position=1,
            number_label="1",
            stem="سؤال خاص بالمؤسسة الثانية عن الخلية النباتية.",
            qtype="mcq_single",
            difficulty=3,
            tags=["نبات"],
            status="approved",
            chapter_id=ch_b.id,
            lesson_id=les_b.id,
            created_at=base_time + timedelta(minutes=6),
        )

        db.add_all([q5, q_org_b])
        db.flush()

        # Validation issues on q1 (1 unresolved error, 2 unresolved warnings, 1 resolved error)
        db.add_all(
            [
                ValidationIssue(
                    question_id=q1.id,
                    code="latex_syntax_error",
                    severity="error",
                    message="err",
                ),
                ValidationIssue(
                    question_id=q1.id,
                    code="low_confidence",
                    severity="warning",
                    message="warn 1",
                ),
                ValidationIssue(
                    question_id=q1.id,
                    code="missing_answer",
                    severity="warning",
                    message="warn 2",
                ),
                ValidationIssue(
                    question_id=q1.id,
                    code="old_error",
                    severity="error",
                    message="resolved err",
                    resolved_at=base_time,
                ),
            ]
        )
        db.commit()

        env_data = {
            "org_a": org_a.id,
            "org_b": org_b.id,
            "sub_bio": sub_bio.id,
            "sub_phys": sub_phys.id,
            "sub_b": sub_b.id,
            "ch1": ch1.id,
            "ch2": ch2.id,
            "ch_phys": ch_phys.id,
            "les1": les1.id,
            "les2": les2.id,
            "les3": les3.id,
            "les_phys": les_phys.id,
            "src1": src1.id,
            "src2": src2.id,
            "stim1": stim1.id,
            "q1": q1.id,
            "q2": q2.id,
            "q3": q3.id,
            "q4": q4.id,
            "q5": q5.id,
            "q_org_b": q_org_b.id,
        }

    def override() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield env_data
    engine.dispose()


@pytest.mark.integration
def test_fts_tashkeel_alef_digits_english_and_prefix(
    bank_env: dict[str, Any], client: TestClient
) -> None:
    _login(client, "editor@a.com")
    q1_id = str(bank_env["q1"])
    q2_id = str(bank_env["q2"])
    q3_id = str(bank_env["q3"])

    # 1. With and without tashkeel matching the same question
    res_with = client.get("/api/v1/bank/questions", params={"q": "الْخَلِيَّةِ النَّبَاتِيَّةِ"}).json()
    res_without = client.get("/api/v1/bank/questions", params={"q": "الخلية النباتية"}).json()
    assert res_with["match_mode"] == "fts"
    assert res_without["match_mode"] == "fts"
    assert [i["id"] for i in res_with["items"]] == [q1_id]
    assert [i["id"] for i in res_without["items"]] == [q1_id]

    # Verify item structure and 200-char original stem preview preserving diacritics
    item = res_without["items"][0]
    assert len(item["stem_preview"]) == 200  # noqa: PLR2004
    assert "الْخَلِيَّةِ" in item["stem_preview"]
    assert item["number_label"] == "\u0661"
    assert item["type"] == "mcq_single"
    assert item["choices_count"] == 2  # noqa: PLR2004
    assert item["difficulty"] == 2  # noqa: PLR2004
    assert set(item["tags"]) == {"نبات", "دعامة", "خلية"}
    assert item["status"] == "approved"
    assert item["chapter_id"] == str(bank_env["ch1"])
    assert item["chapter_title"] == "الدعامة والحركة"
    assert item["lesson_id"] == str(bank_env["les1"])
    assert item["lesson_title"] == "الدعامة في النبات"
    assert item["source_id"] == str(bank_env["src1"])
    assert item["source_title"] == "كتاب الامتحان أحياء"
    assert item["source_page"] == 7  # noqa: PLR2004
    assert item["stimulus_id"] == str(bank_env["stim1"])
    assert item["has_figure"] is True
    assert item["issues_count"] == {"error": 1, "warning": 2}

    # 2. Alef variants (إبراهيم searched as ابراهيم and أبراهيم and آبرهيم)
    for variant in ("ابراهيم", "أبراهيم", "إبراهيم"):
        res_alef = client.get("/api/v1/bank/questions", params={"q": variant}).json()
        assert [i["id"] for i in res_alef["items"]] == [q1_id]

    # 3. Arabic-Indic digits in query matching ASCII digits in stem (٢٥ -> 25) and vice versa
    res_digits_ar = client.get("/api/v1/bank/questions", params={"q": "٢٥"}).json()
    assert [i["id"] for i in res_digits_ar["items"]] == [q1_id]
    res_digits_ascii = client.get("/api/v1/bank/questions", params={"q": "25"}).json()
    assert [i["id"] for i in res_digits_ascii["items"]] == [q1_id]
    res_skull = client.get("/api/v1/bank/questions", params={"q": "عظام الجمجمه"}).json()
    assert [i["id"] for i in res_skull["items"]] == [q3_id]

    # 4. English query (case-insensitive)
    res_en = client.get("/api/v1/bank/questions", params={"q": "MITOCHONDRIA"}).json()
    assert res_en["match_mode"] == "fts"
    assert [i["id"] for i in res_en["items"]] == [q2_id]

    # 5. Prefix match on the last token (search-as-you-type)
    res_prefix_ar = client.get("/api/v1/bank/questions", params={"q": "الخلية النب"}).json()
    assert res_prefix_ar["match_mode"] == "fts"
    assert [i["id"] for i in res_prefix_ar["items"]] == [q1_id]

    res_prefix_en = client.get("/api/v1/bank/questions", params={"q": "هرمون mitochond"}).json()
    assert res_prefix_en["match_mode"] == "fts"
    assert [i["id"] for i in res_prefix_en["items"]] == [q2_id]


@pytest.mark.integration
def test_fuzzy_fallback_with_typo(bank_env: dict[str, Any], client: TestClient) -> None:
    _login(client, "editor@a.com")
    q3_id = str(bank_env["q3"])

    # Typo in query: FTS returns nothing because "عضام" != "عظام",
    # so trigram similarity (> 0.3) kicks in and returns match_mode == "fuzzy".
    res = client.get(
        "/api/v1/bank/questions",
        params={"q": "كم عدد عضام الجمجمه في الانسان البالغ"},
    ).json()
    assert res["match_mode"] == "fuzzy"
    assert res["total"] >= 1
    assert res["items"][0]["id"] == q3_id


@pytest.mark.integration
def test_all_filters_and_teacher_role_and_org_isolation(
    bank_env: dict[str, Any], client: TestClient
) -> None:
    q1_id = str(bank_env["q1"])
    q2_id = str(bank_env["q2"])
    q3_id = str(bank_env["q3"])
    q4_id = str(bank_env["q4"])
    q5_id = str(bank_env["q5"])

    _login(client, "editor@a.com")

    # Default exclude_duplicates=true hides q5; exclude_duplicates=false includes q5
    all_no_dups = client.get("/api/v1/bank/questions").json()
    assert {i["id"] for i in all_no_dups["items"]} == {q1_id, q2_id, q3_id, q4_id}
    assert str(bank_env["q_org_b"]) not in {i["id"] for i in all_no_dups["items"]}

    all_with_dups = client.get(
        "/api/v1/bank/questions", params={"exclude_duplicates": False}
    ).json()
    assert {i["id"] for i in all_with_dups["items"]} == {q1_id, q2_id, q3_id, q4_id, q5_id}

    # subject_id filter
    res_sub = client.get(
        "/api/v1/bank/questions", params={"subject_id": str(bank_env["sub_phys"])}
    ).json()
    assert res_sub["items"] == []

    # chapter_ids filter (and bracket syntax chapter_ids[])
    res_ch = client.get(
        "/api/v1/bank/questions", params={"chapter_ids": [str(bank_env["ch2"])]}
    ).json()
    assert [i["id"] for i in res_ch["items"]] == [q2_id]

    res_ch_bracket = client.get(f"/api/v1/bank/questions?chapter_ids[]={bank_env['ch2']}").json()
    assert [i["id"] for i in res_ch_bracket["items"]] == [q2_id]

    # lesson_ids filter
    res_les = client.get(
        "/api/v1/bank/questions", params={"lesson_ids": [str(bank_env["les1"])]}
    ).json()
    assert [i["id"] for i in res_les["items"]] == [q1_id]

    # types filter
    res_type = client.get(
        "/api/v1/bank/questions", params={"types": ["essay", "short_answer"]}
    ).json()
    assert {i["id"] for i in res_type["items"]} == {q2_id, q3_id}

    # difficulty_min and difficulty_max
    res_diff = client.get(
        "/api/v1/bank/questions", params={"difficulty_min": 2, "difficulty_max": 4}
    ).json()
    assert {i["id"] for i in res_diff["items"]} == {q1_id, q2_id}

    # statuses filter (for editor)
    res_draft = client.get("/api/v1/bank/questions", params={"statuses": ["draft"]}).json()
    assert [i["id"] for i in res_draft["items"]] == [q4_id]

    # source_ids filter
    res_src = client.get(
        "/api/v1/bank/questions", params={"source_ids": [str(bank_env["src1"])]}
    ).json()
    assert {i["id"] for i in res_src["items"]} == {q1_id, q2_id}

    # tags filter (match any)
    res_tags = client.get("/api/v1/bank/questions", params={"tags": ["هرمونات", "تشريح"]}).json()
    assert {i["id"] for i in res_tags["items"]} == {q2_id, q3_id}

    # has_figure filter
    res_fig_true = client.get("/api/v1/bank/questions", params={"has_figure": True}).json()
    assert [i["id"] for i in res_fig_true["items"]] == [q1_id]
    res_fig_false = client.get("/api/v1/bank/questions", params={"has_figure": False}).json()
    assert {i["id"] for i in res_fig_false["items"]} == {q2_id, q3_id, q4_id}

    # has_answer filter: q1 has correct choice, q3 has text answer,
    # q4 has correct choice; q2 has neither
    res_ans_true = client.get("/api/v1/bank/questions", params={"has_answer": True}).json()
    assert {i["id"] for i in res_ans_true["items"]} == {q1_id, q3_id, q4_id}
    res_ans_false = client.get("/api/v1/bank/questions", params={"has_answer": False}).json()
    assert [i["id"] for i in res_ans_false["items"]] == [q2_id]

    # exam_title filter
    res_exam = client.get("/api/v1/bank/questions", params={"exam_title": "الاختبار الأول"}).json()
    assert [i["id"] for i in res_exam["items"]] == [q1_id]

    # Teacher role: forced to approved even when statuses=['draft'] is passed
    _login(client, "teacher@a.com")
    res_teacher = client.get(
        "/api/v1/bank/questions", params={"statuses": ["draft"], "facets": True}
    ).json()
    assert {i["id"] for i in res_teacher["items"]} == {q1_id, q2_id, q3_id}
    assert res_teacher["facets"]["statuses"] == {"approved": 3}

    # Org B isolation
    _login(client, "admin@b.com")
    res_b = client.get("/api/v1/bank/questions", params={"facets": True}).json()
    assert [i["id"] for i in res_b["items"]] == [str(bank_env["q_org_b"])]
    assert res_b["total"] == 1


@pytest.mark.integration
def test_facets_exclude_own_dimension(bank_env: dict[str, Any], client: TestClient) -> None:
    _login(client, "editor@a.com")

    # Apply filters on type=['mcq_single'], chapter_ids=[ch1],
    # difficulty_min=2, difficulty_max=2, statuses=['approved'], source_ids=[src1],
    # tags=['نبات'] -> only q1 matches ALL filters (total=1),
    # but each dimension's facet excludes its own filter!
    res = client.get(
        "/api/v1/bank/questions",
        params={
            "facets": True,
            "types": ["mcq_single"],
            "statuses": ["approved"],
        },
    ).json()
    assert res["total"] == 1
    facets = res["facets"]
    assert facets["total"] == 1
    # types facet excludes the types=['mcq_single'] filter ( keeping statuses=['approved'] )
    assert facets["types"] == {"mcq_single": 1, "essay": 1, "short_answer": 1}
    # statuses facet excludes the statuses=['approved'] filter ( keeping types=['mcq_single'] )
    assert facets["statuses"] == {"approved": 1}

    # Now filter by chapter_ids=[ch2] only with facets=true
    res_ch = client.get(
        "/api/v1/bank/questions",
        params={"facets": True, "chapter_ids": [str(bank_env["ch2"])]},
    ).json()
    assert res_ch["total"] == 1
    ch_counts = {c["id"]: c["count"] for c in res_ch["facets"]["chapters"]}
    # chapters facet excludes chapter_ids filter, so ch1 (3 questions) and
    # ch2 (1 question) both show up!
    assert ch_counts == {str(bank_env["ch1"]): 3, str(bank_env["ch2"]): 1}
    # lessons facet DOES keep chapter_ids=[ch2] filter, so only les3 shows up!
    les_counts = {les["id"]: les["count"] for les in res_ch["facets"]["lessons"]}
    assert les_counts == {str(bank_env["les3"]): 1}


@pytest.mark.integration
def test_pagination_stability_for_each_sort(bank_env: dict[str, Any], client: TestClient) -> None:
    _login(client, "editor@a.com")
    q1_id = str(bank_env["q1"])
    q2_id = str(bank_env["q2"])
    q3_id = str(bank_env["q3"])
    q4_id = str(bank_env["q4"])

    for sort_mode, expected_order in [
        ("newest", [q4_id, q3_id, q2_id, q1_id]),
        ("difficulty", [q3_id, q1_id, q2_id, q4_id]),
        ("source_order", [q1_id, q2_id, q3_id, q4_id]),
        ("relevance", [q4_id, q3_id, q2_id, q1_id]),
    ]:
        collected: list[str] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"sort": sort_mode, "limit": 2}
            if cursor is not None:
                params["cursor"] = cursor
            page = client.get("/api/v1/bank/questions", params=params).json()
            collected.extend(item["id"] for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert collected == expected_order, f"Failed for sort={sort_mode}"

    # Invalid cursor -> 422
    bad = client.get("/api/v1/bank/questions", params={"sort": "newest", "cursor": "bad-cursor"})
    assert bad.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad.json()["code"] == "invalid_cursor"


@pytest.mark.integration
def test_tags_autocomplete_and_stats(bank_env: dict[str, Any], client: TestClient) -> None:
    _login(client, "editor@a.com")

    # All tags for editor (includes draft q4's "دعامة" and "مفاصل")
    tags = client.get("/api/v1/bank/tags").json()
    tag_map = {t["tag"]: t["count"] for t in tags}
    assert tag_map["دعامة"] == 3  # noqa: PLR2004
    assert tag_map["مفاصل"] == 1

    # Autocomplete query with Arabic normalization (searching "دعامه" matches "دعامة")
    tags_q = client.get("/api/v1/bank/tags", params={"q": "دعامه"}).json()
    assert [t["tag"] for t in tags_q] == ["دعامة"]

    # Teacher only sees tags from approved questions
    _login(client, "teacher@a.com")
    teacher_tags = client.get("/api/v1/bank/tags").json()
    teacher_tag_map = {t["tag"]: t["count"] for t in teacher_tags}
    assert teacher_tag_map["دعامة"] == 2  # noqa: PLR2004
    assert "مفاصل" not in teacher_tag_map

    # Stats for editor
    _login(client, "editor@a.com")
    stats = client.get("/api/v1/bank/stats", params={"subject_id": str(bank_env["sub_bio"])}).json()
    assert stats["total"] == 4  # noqa: PLR2004
    assert stats["by_status"] == {"approved": 3, "draft": 1}
    assert stats["by_type"] == {
        "mcq_single": 1,
        "essay": 1,
        "short_answer": 1,
        "true_false": 1,
    }
    assert stats["by_difficulty"] == {"1": 1, "2": 1, "4": 1, "5": 1}
    # Approved per chapter/lesson counts only approved questions
    # (q1 in les1/ch1, q3 in les2/ch1, q2 in les3/ch2)
    ch_approved = {c["id"]: c["count"] for c in stats["approved_by_chapter"]}
    assert ch_approved == {str(bank_env["ch1"]): 2, str(bank_env["ch2"]): 1}
    les_approved = {les["id"]: les["count"] for les in stats["approved_by_lesson"]}
    assert les_approved == {
        str(bank_env["les1"]): 1,
        str(bank_env["les2"]): 1,
        str(bank_env["les3"]): 1,
    }


@pytest.mark.integration
def test_delete_checks_move_and_taxonomy_merge(  # noqa: PLR0915 -- exercises full move and merge scenario
    bank_env: dict[str, Any], database: str, client: TestClient
) -> None:
    # Teacher cannot move or merge
    _login(client, "teacher@a.com")
    assert (
        client.post(
            "/api/v1/questions/move",
            json={"ids": [str(bank_env["q1"])], "lesson_id": str(bank_env["les3"])},
        ).status_code
        == HTTPStatus.FORBIDDEN
    )
    assert (
        client.post(
            f"/api/v1/lessons/{bank_env['les1']}/merge",
            json={"into_lesson_id": str(bank_env["les2"])},
        ).status_code
        == HTTPStatus.FORBIDDEN
    )
    assert (
        client.post(
            f"/api/v1/chapters/{bank_env['ch1']}/merge",
            json={"into_chapter_id": str(bank_env["ch2"])},
        ).status_code
        == HTTPStatus.FORBIDDEN
    )

    _login(client, "editor@a.com")

    # 1. Delete checks now count questions!
    # les1 has q1 (and q5) -> deleting les1 fails with 409 not_empty
    del_les = client.delete(f"/api/v1/lessons/{bank_env['les1']}")
    assert del_les.status_code == HTTPStatus.CONFLICT
    assert del_les.json()["code"] == "not_empty"

    # Create a chapter with no lessons, move q1 to a lesson or assign chapter_id directly,
    # and verify chapter delete check
    empty_ch = client.post(
        f"/api/v1/subjects/{bank_env['sub_bio']}/chapters", json={"title": "فصل مؤقت"}
    ).json()
    engine = create_engine(database)
    with Session(engine) as db:
        q1_row = db.get(Question, bank_env["q1"])
        assert q1_row is not None
        q1_row.chapter_id = UUID(empty_ch["id"])
        q1_row.lesson_id = None
        db.commit()
    # empty_ch has 0 lessons, but 1 question -> delete_chapter must return 409 not_empty!
    del_ch = client.delete(f"/api/v1/chapters/{empty_ch['id']}")
    assert del_ch.status_code == HTTPStatus.CONFLICT
    assert del_ch.json()["code"] == "not_empty"

    # Move q1 back to les1 via POST /api/v1/questions/move
    move_res = client.post(
        "/api/v1/questions/move",
        json={"ids": [str(bank_env["q1"])], "lesson_id": str(bank_env["les1"])},
    )
    assert move_res.status_code == HTTPStatus.OK
    assert move_res.json() == {"moved": 1}

    # Now empty_ch has 0 questions and 0 lessons -> delete succeeds!
    assert client.delete(f"/api/v1/chapters/{empty_ch['id']}").status_code == HTTPStatus.NO_CONTENT

    # Cross-subject move rejected
    bad_move = client.post(
        "/api/v1/questions/move",
        json={"ids": [str(bank_env["q1"])], "lesson_id": str(bank_env["les_phys"])},
    )
    assert bad_move.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert bad_move.json()["code"] == "cross_subject_move"

    # Cross-subject lesson merge rejected
    bad_les_merge = client.post(
        f"/api/v1/lessons/{bank_env['les1']}/merge",
        json={"into_lesson_id": str(bank_env["les_phys"])},
    )
    assert bad_les_merge.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Cross-subject chapter merge rejected
    bad_ch_merge = client.post(
        f"/api/v1/chapters/{bank_env['ch1']}/merge",
        json={"into_chapter_id": str(bank_env["ch_phys"])},
    )
    assert bad_ch_merge.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Merge lesson les1 into les3 (which is in ch2): moves q1 & q5 to les3 & ch2, and deletes les1!
    merge_les_res = client.post(
        f"/api/v1/lessons/{bank_env['les1']}/merge",
        json={"into_lesson_id": str(bank_env["les3"])},
    )
    assert merge_les_res.status_code == HTTPStatus.OK
    assert merge_les_res.json()["id"] == str(bank_env["les3"])

    with Session(engine) as db:
        assert db.get(Lesson, bank_env["les1"]) is None
        q1_after = db.get(Question, bank_env["q1"])
        assert q1_after is not None
        assert q1_after.lesson_id == bank_env["les3"]
        assert q1_after.chapter_id == bank_env["ch2"]

    # Merge chapter ch1 into ch2: moves remaining lesson (les2) and its questions (q3, q4)
    # into ch2, deletes ch1!
    merge_ch_res = client.post(
        f"/api/v1/chapters/{bank_env['ch1']}/merge",
        json={"into_chapter_id": str(bank_env["ch2"])},
    )
    assert merge_ch_res.status_code == HTTPStatus.OK
    assert merge_ch_res.json()["id"] == str(bank_env["ch2"])

    with Session(engine) as db:
        assert db.get(Chapter, bank_env["ch1"]) is None
        les2_after = db.get(Lesson, bank_env["les2"])
        assert les2_after is not None
        assert les2_after.chapter_id == bank_env["ch2"]
        q3_after = db.get(Question, bank_env["q3"])
        assert q3_after is not None
        assert q3_after.chapter_id == bank_env["ch2"]

    # Verify ensure_deletable_subject returns false when only a question references the subject
    sub_temp = client.post(
        "/api/v1/subjects", json={"name": "كيمياء مؤقتة", "language": "ar"}
    ).json()
    sub_temp_id = UUID(sub_temp["id"])
    with Session(engine) as db:
        # Temporarily point q4 to sub_temp_id (while src2 is on sub_bio)
        # so sub_temp has 0 chapters and 0 sources, but 1 question
        q4_row = db.get(Question, bank_env["q4"])
        assert q4_row is not None
        q4_row.subject_id = sub_temp_id
        q4_row.chapter_id = None
        q4_row.lesson_id = None
        db.commit()

    del_sub = client.delete(f"/api/v1/subjects/{sub_temp_id}")
    assert del_sub.status_code == HTTPStatus.CONFLICT
    assert del_sub.json()["code"] == "not_empty"
    engine.dispose()
