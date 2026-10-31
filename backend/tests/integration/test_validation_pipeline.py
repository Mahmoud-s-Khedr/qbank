"""Integration tests for dedup, validation, verifier, classification, full stage chain, and API."""

from datetime import UTC, datetime
from decimal import Decimal
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

import qbank.pipeline.materialize as materialize_module
import qbank.pipeline.verify as verify_module
from qbank import llm, worker
from qbank.api.deps import current_user
from qbank.api.routers import sources as sources_router
from qbank.db import get_engine
from qbank.llm import BudgetExceeded, FakeLLMClient, OrgBudgetExceeded
from qbank.models import (
    Job,
    Language,
    Organization,
    PageStatus,
    Question,
    Role,
    Source,
    SourcePage,
    SourceStatus,
    Subject,
    User,
    ValidationIssue,
)
from qbank.pipeline import orchestrator
from qbank.pipeline.classify import classify_source as run_classify_source
from qbank.pipeline.dedup import CONFIRM_RATIO_THRESHOLD, dedup_question, dedup_source
from qbank.pipeline.validate import ValidationContext, validate_question, validate_source
from qbank.storage import LocalStore, keys
from qbank.text.normalize import content_hash, question_normalized_text

EXPECTED_TWO = 2
DIFFICULTY_EASY = 2
DIFFICULTY_MED = 3
DIFFICULTY_HARD = 4
DIFFICULTY_HUMAN = 5


def _choice_set() -> list[dict[str, object]]:
    return [
        {"label": "أ", "content": "القاهرة", "is_correct": True, "pinned": False},
        {"label": "ب", "content": "الإسكندرية", "is_correct": False, "pinned": False},
        {"label": "ج", "content": "أسوان", "is_correct": False, "pinned": False},
        {"label": "د", "content": "الأقصر", "is_correct": False, "pinned": False},
    ]


@pytest.mark.integration
def test_dedup_exact_near_below_threshold_and_cross_org(database: str) -> None:
    with Session(get_engine()) as db:
        org_a = Organization(name="Org A")
        org_b = Organization(name="Org B")
        db.add_all([org_a, org_b])
        db.flush()

        sub_a = Subject(org_id=org_a.id, name="Arabic", language=Language.ar)
        sub_b = Subject(org_id=org_b.id, name="Arabic", language=Language.ar)
        db.add_all([sub_a, sub_b])
        db.flush()

        src_a1 = Source(
            org_id=org_a.id,
            subject_id=sub_a.id,
            title="Upload 1",
            file_key="u1.pdf",
            status=SourceStatus.ready,
        )
        src_a2 = Source(
            org_id=org_a.id,
            subject_id=sub_a.id,
            title="Upload 2",
            file_key="u2.pdf",
            status=SourceStatus.ready,
        )
        src_a3 = Source(
            org_id=org_a.id,
            subject_id=sub_a.id,
            title="Upload 3",
            file_key="u3.pdf",
            status=SourceStatus.ready,
        )
        src_b = Source(
            org_id=org_b.id,
            subject_id=sub_b.id,
            title="Org B Upload",
            file_key="ub.pdf",
            status=SourceStatus.ready,
        )
        db.add_all([src_a1, src_a2, src_a3, src_b])
        db.flush()

        stem_base = "اختر الإجابة الصحيحة من بين البدائل التالية لتحديد عاصمة جمهورية مصر العربية:"
        norm_base = question_normalized_text(stem_base, _choice_set())

        q_orig = Question(
            org_id=org_a.id,
            subject_id=sub_a.id,
            source_id=src_a1.id,
            position=0,
            number_label="1",
            type="mcq_single",
            stem=stem_base,
            choices=_choice_set(),
            language=Language.ar,
            regions=[],
            status="draft",
            confidence=0.95,
            normalized_text=norm_base,
            content_hash=content_hash(norm_base),
        )
        db.add(q_orig)
        db.flush()

        stem_exact = "اخْتَرِ الإِجَابَةَ الصَّحِيحَةَ مِنْ بَيْنِ البَدَائِلِ التَّالِيَةِ لِتَحْدِيدِ عَاصِمَةِ جُمْهُورِيَّةِ مِصْرَ العَرَبِيَّةِ:"
        q_exact = Question(
            org_id=org_a.id,
            subject_id=sub_a.id,
            source_id=src_a2.id,
            position=0,
            number_label="1",
            type="mcq_single",
            stem=stem_exact,
            choices=_choice_set(),
            language=Language.ar,
            regions=[],
            status="draft",
            confidence=0.95,
        )
        db.add(q_exact)
        db.flush()

        dup_id, ratio = dedup_question(db, q_exact)
        assert dup_id == q_orig.id
        assert ratio == 1.0
        assert q_exact.duplicate_of_id == q_orig.id

        stem_near = "اختر الإجابة الصحيحة من بين البدائل الآتية لتحديد عاصمة جمهورية مصر العربية:"
        q_near = Question(
            org_id=org_a.id,
            subject_id=sub_a.id,
            source_id=src_a3.id,
            position=0,
            number_label="1",
            type="mcq_single",
            stem=stem_near,
            choices=_choice_set(),
            language=Language.ar,
            regions=[],
            status="draft",
            confidence=0.95,
        )
        db.add(q_near)
        db.flush()

        dup_near_id, ratio_near = dedup_question(db, q_near)
        assert dup_near_id == q_orig.id
        assert ratio_near >= CONFIRM_RATIO_THRESHOLD
        assert q_near.duplicate_of_id == q_orig.id

        q_different = Question(
            org_id=org_a.id,
            subject_id=sub_a.id,
            source_id=src_a3.id,
            position=1,
            number_label="2",
            type="mcq_single",
            stem="احسب السرعة المتوسطة لجسم يقطع مسافة مائة متر في عشر ثوان فقط.",
            choices=[
                {"label": "أ", "content": "10 م/ث", "is_correct": True, "pinned": False},
                {"label": "ب", "content": "20 م/ث", "is_correct": False, "pinned": False},
            ],
            language=Language.ar,
            regions=[],
            status="draft",
            confidence=0.95,
        )
        db.add(q_different)
        db.flush()

        dup_diff_id, _ = dedup_question(db, q_different)
        assert dup_diff_id is None
        assert q_different.duplicate_of_id is None

        q_other_org = Question(
            org_id=org_b.id,
            subject_id=sub_b.id,
            source_id=src_b.id,
            position=0,
            number_label="1",
            type="mcq_single",
            stem=stem_base,
            choices=_choice_set(),
            language=Language.ar,
            regions=[],
            status="draft",
            confidence=0.95,
        )
        db.add(q_other_org)
        db.flush()

        dup_org_b_id, _ = dedup_question(db, q_other_org)
        assert dup_org_b_id is None
        assert q_other_org.duplicate_of_id is None
        db.commit()


@pytest.mark.integration
def test_same_page_uploaded_twice_flags_all_questions_and_preserves_resolved_issues(
    database: str,
) -> None:
    with Session(get_engine()) as db:
        org = Organization(name="School")
        db.add(org)
        db.flush()
        sub = Subject(org_id=org.id, name="Biology", language=Language.ar)
        db.add(sub)
        db.flush()

        first_source = Source(
            org_id=org.id,
            subject_id=sub.id,
            title="First Upload",
            file_key="first.pdf",
            status=SourceStatus.validating,
        )
        second_source = Source(
            org_id=org.id,
            subject_id=sub.id,
            title="Second Upload",
            file_key="second.pdf",
            status=SourceStatus.validating,
        )
        db.add_all([first_source, second_source])
        db.flush()

        stems = [
            "ما الوظيفة الأساسية للميتوكوندريا داخل الخلية الحية في الكائنات حقيقية النواة؟",
            "أي من العضيات التالية مسؤولة عن عملية البناء الضوئي في الخلية النباتية؟",
            "حدد دور الشبكة الإندوبلازمية الخشنة في تصنيع البروتينات داخل الخلية.",
        ]
        first_questions: list[Question] = []
        for idx, stem in enumerate(stems):
            q = Question(
                org_id=org.id,
                subject_id=sub.id,
                source_id=first_source.id,
                position=idx,
                number_label=str(idx + 1),
                type="mcq_single",
                stem=stem,
                choices=_choice_set(),
                language=Language.ar,
                regions=[],
                status="draft",
                confidence=0.95,
            )
            db.add(q)
            first_questions.append(q)
        db.flush()
        validate_source(db, first_source)
        db.commit()

        second_questions: list[Question] = []
        for idx, stem in enumerate(stems):
            q = Question(
                org_id=org.id,
                subject_id=sub.id,
                source_id=second_source.id,
                position=idx,
                number_label=str(idx + 1),
                type="mcq_single",
                stem=stem,
                choices=_choice_set(),
                language=Language.ar,
                regions=[],
                status="draft",
                confidence=0.95,
            )
            db.add(q)
            second_questions.append(q)
        db.flush()
        validate_source(db, second_source)
        db.commit()

        for q1, q2 in zip(first_questions, second_questions, strict=True):
            assert q1.duplicate_of_id is None
            assert q2.duplicate_of_id == q1.id
            codes = [i.code for i in q2.issues]
            assert "duplicate_of" in codes

        target_q = second_questions[0]
        dup_issue = next(i for i in target_q.issues if i.code == "duplicate_of")
        resolved_time = datetime.now(UTC)
        dup_issue.resolved_at = resolved_time
        resolved_issue_id = dup_issue.id
        db.commit()

        validate_question(db, target_q, ValidationContext(questions=second_questions))
        db.commit()

        reloaded_issues = list(
            db.scalars(select(ValidationIssue).where(ValidationIssue.question_id == target_q.id))
        )
        kept = next(i for i in reloaded_issues if i.code == "duplicate_of")
        assert kept.id == resolved_issue_id
        assert kept.resolved_at == resolved_time

        target_q.duplicate_of_id = None
        validate_question(db, target_q, ValidationContext(questions=second_questions))
        db.commit()
        after_clear = list(
            db.scalars(select(ValidationIssue).where(ValidationIssue.question_id == target_q.id))
        )
        assert all(i.code != "duplicate_of" for i in after_clear)


@pytest.mark.integration
def test_classification_batches_of_twenty_and_human_preservation(database: str) -> None:
    fake = FakeLLMClient()
    with Session(get_engine()) as db:
        org = Organization(name="Batch Org")
        db.add(org)
        db.flush()
        sub = Subject(org_id=org.id, name="Math", language=Language.ar)
        db.add(sub)
        db.flush()
        src = Source(
            org_id=org.id,
            subject_id=sub.id,
            title="25 Questions",
            file_key="25.pdf",
            status=SourceStatus.validating,
            stage="classify",
        )
        db.add(src)
        db.flush()

        questions: list[Question] = []
        for idx in range(25):
            is_human = idx == 0
            q = Question(
                org_id=org.id,
                subject_id=sub.id,
                source_id=src.id,
                position=idx,
                number_label=str(idx + 1),
                type="mcq_single",
                stem=f"أوجد مجموعة حل المعادلة التربيعية رقم {idx + 1} في مجموعة الأعداد الحقيقية.",
                choices=_choice_set(),
                language=Language.ar,
                regions=[],
                status="draft",
                confidence=0.9,
                difficulty=DIFFICULTY_HUMAN if is_human else None,
                difficulty_reason="تحديد المعلم" if is_human else None,
                difficulty_source="human" if is_human else None,
                tags=["يدوي"] if is_human else [],
            )
            db.add(q)
            questions.append(q)
        db.commit()

        non_human = questions[1:]
        batch1_resp = [
            {
                "id": str(q.id),
                "difficulty": DIFFICULTY_EASY,
                "difficulty_reason": "تطبيق مباشر للقانون",
                "tags": ["جبر", "معادلات"],
            }
            for q in non_human[:20]
        ]
        batch2_resp = [
            {
                "id": str(q.id),
                "difficulty": DIFFICULTY_HARD,
                "difficulty_reason": "مسألة مركبة",
                "tags": ["تفاضل"],
            }
            for q in non_human[20:]
        ]
        fake.queue("classify", (batch1_resp, "0.001"))
        fake.queue("classify", (batch2_resp, "0.0005"))

        cost = run_classify_source(db, src, client=fake)
        db.commit()

        assert len(fake.calls) == EXPECTED_TWO
        assert cost == Decimal("0.0015")
        assert questions[0].difficulty == DIFFICULTY_HUMAN
        assert questions[0].difficulty_reason == "تحديد المعلم"
        assert questions[0].difficulty_source == "human"
        assert questions[0].tags == ["يدوي"]
        assert all(
            q.difficulty == DIFFICULTY_EASY and q.difficulty_source == "ai" for q in non_human[:20]
        )
        assert all(
            q.difficulty == DIFFICULTY_HARD and q.difficulty_source == "ai" for q in non_human[20:]
        )


def _create_synthetic_pdf_bytes(num_pages: int = 2) -> bytes:
    pdf_bytes = BytesIO()
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    for idx in range(num_pages):
        p = doc.new_page(width=300, height=400)
        p.insert_text((30, 40), f"Synthetic page {idx + 1}")
        p.draw_rect(pymupdf.Rect(40, 80, 150, 180), color=(0, 0, 0))  # type: ignore[no-untyped-call]
    doc.save(pdf_bytes)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    return pdf_bytes.getvalue()


def _queue_synthetic_pipeline_llm_responses(fake: FakeLLMClient) -> None:
    p1_extract = {
        "page_kind": "questions",
        "headings": [],
        "stimuli": [],
        "questions": [
            {
                "number_label": "1",
                "type": "mcq_single",
                "stem": "ما وحدة قياس شدة التيار الكهربي في النظام الدولي للوحدات؟",
                "choices": [
                    {"label": "أ", "content": "الأمبير"},
                    {"label": "ب", "content": "الفولت"},
                    {"label": "ج", "content": "الأوم"},
                    {"label": "د", "content": "الواط"},
                ],
                "answer": {"labels": ["أ"], "text": None},
                "stimulus_ref": None,
                "figures": [],
                "box_2d": [100, 100, 400, 800],
                "continues_from_previous": False,
                "continues_on_next": False,
                "confidence": 0.92,
            }
        ],
        "answer_key_entries": [],
        "page_confidence": 0.92,
        "notes": "",
    }
    p2_extract = {
        "page_kind": "questions",
        "headings": [],
        "stimuli": [],
        "questions": [
            {
                "number_label": "2",
                "type": "mcq_single",
                "stem": "احسب المقاومة المكافئة للدائرة الكهربية الموضحة.",
                "choices": [
                    {"label": "أ", "content": "5 أوم"},
                    {"label": "ب", "content": "10 أوم"},
                ],
                "answer": None,
                "stimulus_ref": None,
                "figures": [],
                "box_2d": [100, 100, 400, 800],
                "continues_from_previous": False,
                "continues_on_next": False,
                "confidence": 0.70,
            }
        ],
        "answer_key_entries": [],
        "page_confidence": 0.75,
        "notes": "",
    }
    fake.queue("extract", (p1_extract, "0.005"))
    fake.queue("extract", (p2_extract, "0.005"))

    # Page 2 has confidence < 0.75 (0.70 * 0.85 = 0.595), triggering verify on page 2 only.
    fake.queue(
        "verify",
        (
            [
                {
                    "number_label": "2",
                    "field": "answer",
                    "problem": "الإجابة الصحيحة ملونة في الصفحة وهي ب",
                    "suggested_fix": "ب",
                    "severity": "warning",
                }
            ],
            "0.001",
        ),
    )
    fake.queue(
        "classify",
        (
            [
                {
                    "id": "q1",
                    "difficulty": 1,
                    "difficulty_reason": "تذكر مباشر للوحدة القياسية",
                    "tags": ["كهربية", "وحدات"],
                },
                {
                    "id": "q2",
                    "difficulty": DIFFICULTY_MED,
                    "difficulty_reason": "حساب مقاومة مكافئة",
                    "tags": ["كهربية", "مقاومات"],
                },
            ],
            "0.001",
        ),
    )


def _seed_synthetic_source(store: LocalStore) -> tuple[UUID, User]:
    with Session(get_engine()) as db:
        org = Organization(name="Synthetic Org")
        db.add(org)
        db.flush()
        sub = Subject(org_id=org.id, name="Physics", language=Language.ar, grade="3")
        user = User(
            org_id=org.id,
            email="editor@synthetic.local",
            name="Editor",
            password_hash="test-only",  # noqa: S106
            role=Role.editor,
            is_active=True,
        )
        db.add_all([sub, user])
        db.flush()
        file_key = keys.original(org.id, sub.id)
        store.put_bytes(file_key, _create_synthetic_pdf_bytes(), "application/pdf")
        src = Source(
            org_id=org.id,
            subject_id=sub.id,
            title="Synthetic Workbook",
            grade="3",
            file_key=file_key,
            status=SourceStatus.rendering,
            stage="render",
            pipeline_config={"verify": "low_confidence"},
        )
        db.add(src)
        db.flush()
        db.add(Job(org_id=org.id, kind="ingest", status="running", ref_id=src.id))
        db.commit()
        source_id = src.id
        db.refresh(user)
        db.expunge(user)
        return source_id, user


@pytest.mark.integration
def test_full_stage_chain_on_synthetic_pdf_and_api(
    database: str,
    app: FastAPI,
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalStore(tmp_path)
    monkeypatch.setattr(worker, "get_store", lambda: store)
    monkeypatch.setattr(materialize_module, "get_store", lambda: store)
    monkeypatch.setattr(verify_module, "get_store", lambda: store)
    monkeypatch.setattr(sources_router, "get_store", lambda: store)

    fake = FakeLLMClient()
    monkeypatch.setattr(llm, "get_llm_client", lambda: fake)
    monkeypatch.setattr(
        orchestrator,
        "STAGES",
        [
            orchestrator.Stage(
                "render", worker.render_source, SourceStatus.rendering, PageStatus.pending
            ),
            orchestrator.Stage(
                "extract", worker.extract_source, SourceStatus.extracting, PageStatus.rendered
            ),
            orchestrator.Stage(
                "materialize",
                worker.materialize_source,
                SourceStatus.extracting,
                PageStatus.extracted,
            ),
            orchestrator.Stage(
                "validate",
                worker.validate_source,
                SourceStatus.validating,
                PageStatus.extracted,
            ),
            orchestrator.Stage(
                "verify",
                worker.verify_source,
                SourceStatus.validating,
                PageStatus.extracted,
            ),
            orchestrator.Stage(
                "classify",
                worker.classify_source,
                SourceStatus.validating,
                PageStatus.extracted,
            ),
        ],
    )
    monkeypatch.setattr(worker.render_pages, "send", worker.render_pages)
    monkeypatch.setattr(worker.extract_pages, "send", worker.extract_pages)

    source_id, user = _seed_synthetic_source(store)

    _queue_synthetic_pipeline_llm_responses(fake)
    worker.render_source(str(source_id))

    app.dependency_overrides[current_user] = lambda: user
    try:
        src_resp = client.get(f"/api/v1/sources/{source_id}")
        assert src_resp.status_code == HTTPStatus.OK
        assert src_resp.json()["status"] == "ready"
        assert src_resp.json()["page_counts"] == {"validated": EXPECTED_TWO}

        qs_data = client.get(f"/api/v1/sources/{source_id}/questions").json()
        assert len(qs_data) == EXPECTED_TWO

        q1_out, q2_out = qs_data[0], qs_data[1]
        assert q1_out["status"] == "draft"
        assert q1_out["confidence"] == pytest.approx(0.92)
        assert q1_out["issues"] == []
        assert q1_out["difficulty"] == 1
        assert q1_out["tags"] == ["كهربية", "وحدات"]

        assert q2_out["status"] == "needs_review"
        assert {i["code"] for i in q2_out["issues"]} == {"missing_answer", "verifier_answer"}
        assert q2_out["confidence"] == pytest.approx(0.70 * 0.85 * 0.85)
        assert q2_out["difficulty"] == DIFFICULTY_MED
        assert q2_out["tags"] == ["كهربية", "مقاومات"]

        single_resp = client.get(f"/api/v1/questions/{q2_out['id']}")
        assert single_resp.status_code == HTTPStatus.OK
        assert {i["code"] for i in single_resp.json()["issues"]} == {
            "missing_answer",
            "verifier_answer",
        }

        summary_data = client.get(f"/api/v1/sources/{source_id}/summary").json()
        assert summary_data["question_counts"] == {"draft": 1, "needs_review": 1}
        assert summary_data["issues_by_code"] == {"missing_answer": 1, "verifier_answer": 1}
        assert summary_data["issues_by_severity"] == {"warning": EXPECTED_TWO}
        assert summary_data["spend_by_stage"]["extract"] == pytest.approx(0.01)
        assert summary_data["spend_by_stage"]["verify"] == pytest.approx(0.001)
        assert summary_data["spend_by_stage"]["classify"] == pytest.approx(0.001)
    finally:
        app.dependency_overrides.clear()


def _seed_budget_pause_source(store: LocalStore) -> tuple[UUID, UUID]:
    with Session(get_engine()) as db:
        org = Organization(name="Budget Org")
        db.add(org)
        db.flush()
        sub = Subject(org_id=org.id, name="Chemistry", language=Language.ar)
        db.add(sub)
        db.flush()
        src = Source(
            org_id=org.id,
            subject_id=sub.id,
            title="Budget Source",
            file_key="b.pdf",
            status=SourceStatus.validating,
            stage="verify",
            pipeline_config={"verify": "all"},
        )
        db.add(src)
        db.flush()
        db.add(Job(org_id=org.id, kind="ingest", status="running", ref_id=src.id))
        p1 = SourcePage(
            source_id=src.id,
            page_number=1,
            status=PageStatus.extracted,
        )
        db.add(p1)
        db.flush()
        q1 = Question(
            org_id=org.id,
            subject_id=sub.id,
            source_id=src.id,
            position=0,
            number_label="1",
            type="mcq_single",
            stem="ما الصيغة الكيميائية لحمض الكبريتيك المركز؟",
            choices=_choice_set(),
            language=Language.ar,
            regions=[{"page": str(p1.id), "box": [0.1, 0.1, 0.8, 0.4]}],
            status="draft",
            confidence=0.65,
            metadata_json={"model_confidence": 0.65},
        )
        db.add(q1)
        db.commit()
        sid, org_id, q1_id = src.id, org.id, q1.id

    img_buf = BytesIO()
    Image.new("RGB", (20, 20), "white").save(img_buf, format="PNG")
    store.put_bytes(keys.page(org_id, sid, 1, hires=True), img_buf.getvalue(), "image/png")
    return sid, q1_id


@pytest.mark.integration
def test_budget_pause_and_resume_in_verify_and_classify(
    database: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalStore(tmp_path)
    monkeypatch.setattr(worker, "get_store", lambda: store)
    monkeypatch.setattr(verify_module, "get_store", lambda: store)

    fake = FakeLLMClient()
    monkeypatch.setattr(llm, "get_llm_client", lambda: fake)
    monkeypatch.setattr(
        orchestrator,
        "STAGES",
        [
            orchestrator.Stage(
                "verify",
                worker.verify_source,
                SourceStatus.validating,
                PageStatus.extracted,
            ),
            orchestrator.Stage(
                "classify",
                worker.classify_source,
                SourceStatus.validating,
                PageStatus.extracted,
            ),
        ],
    )

    sid, q1_id = _seed_budget_pause_source(store)

    # 1. Verify raises BudgetExceeded -> pauses at stage 'verify'
    fake.queue("verify", BudgetExceeded())
    worker.verify_source(str(sid))

    with Session(get_engine()) as db:
        loaded = db.get(Source, sid)
        assert loaded is not None
        assert loaded.status == SourceStatus.paused
        assert loaded.stage == "verify"
        assert loaded.error == "BudgetExceeded"
        loaded.status = SourceStatus.validating
        loaded.error = None
        db.commit()

    # 2. Resume verify -> succeeds, advances to classify, which raises OrgBudgetExceeded
    fake.queue("verify", ([], "0.001"))
    fake.queue("classify", OrgBudgetExceeded())
    worker.verify_source(str(sid))

    with Session(get_engine()) as db:
        loaded = db.get(Source, sid)
        assert loaded is not None
        assert loaded.status == SourceStatus.paused
        assert loaded.stage == "classify"
        assert loaded.error == "OrgBudgetExceeded"
        loaded.status = SourceStatus.validating
        loaded.error = None
        db.commit()

    # 3. Resume classify -> succeeds and transitions source to 'ready'
    fake.queue(
        "classify",
        (
            [
                {
                    "id": str(q1_id),
                    "difficulty": DIFFICULTY_EASY,
                    "difficulty_reason": "صيغة كيميائية أساسية",
                    "tags": ["أحماض"],
                }
            ],
            "0.001",
        ),
    )
    worker.classify_source(str(sid))

    with Session(get_engine()) as db:
        loaded = db.get(Source, sid)
        assert loaded is not None
        assert loaded.status == SourceStatus.ready
        assert loaded.stage is None
        q_reloaded = db.get(Question, q1_id)
        assert q_reloaded is not None
        assert q_reloaded.difficulty == DIFFICULTY_EASY
        assert q_reloaded.tags == ["أحماض"]
        dedup_source(db, sid)
