#!/usr/bin/env python3
"""Question bank search benchmark: seeds N synthetic Arabic questions and runs 50 queries.

Measures p50 and p95 latency against a throwaway database.
Target: p95 < 300 ms at 100k questions.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

# Ensure backend/src is on the import path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from qbank.config import get_settings
from qbank.db import reset_engine
from qbank.models import (
    Chapter,
    Language,
    Lesson,
    Organization,
    Question,
    Role,
    Source,
    SourceStatus,
    Subject,
)
from qbank.services.bank import autocomplete_tags, bank_stats, search_questions
from qbank.text.normalize import content_hash, question_normalized_text

TOPICS = [
    "الخلية النباتية",
    "الميتوكوندريا وعملية إنتاج الطاقة",
    "الانقسام الميتوزي والخلوي",
    "الهيكل العظمي والدعامة في الإنسان",
    "الهرمونات وتنظيم السكر والإنسولين",
    "قوانين مندل والوراثة الجزيئية",
    "الجهاز المناعي والأجسام المضادة",
    "التركيب الضوئي والبلاستيدات الخضراء",
    "المركبات الكيميائية والروابط التساهمية",
    "التيار الكهربي وقانون أوم والمقاومة",
    "السرعة والتسارع وقوانين نيوتن للحركة",
    "الموجات الكهرومغناطيسية والضوء والصوت",
    "الحمض النووي DNA وتضاعف الجينات",
    "الدورة الدموية وعضلة القلب والشرايين",
    "التنفس الخلوي ودورة كريبس وسلسلة نقل الإلكترون",
    "التفاعلات الإنزيمية والعوامل المؤثرة على نشاطها",
    "التوازن الأسموزي والامتصاص في الجذور",
    "المفاصل الزلالية والغضاريف والأوتار",
    "الغدد الصماء وهرمون النمو والثيروكسين",
    "الطفرات الجينية وتأثيرها على البروتينات",
]

TAG_POOL = [
    "خلية",
    "نبات",
    "حيوان",
    "وراثة",
    "جينات",
    "كروموسومات",
    "انقسام",
    "ميتوزي",
    "طاقة",
    "تنفس",
    "تغذية",
    "دعامة",
    "حركة",
    "هرمونات",
    "إنسولين",
    "مناعة",
    "أعصاب",
    "تكاثر",
    "بيئة",
    "إنزيمات",
    "بروتينات",
    "كربوهيدرات",
    "dna",
    "تركيب_ضوئي",
    "ميتوكوندريا",
    "ريبوسومات",
    "جهاز_جولجي",
    "امتصاص",
    "أسموزية",
    "ضغط",
    "حرارة",
    "كهرباء",
    "مقاومة",
    "جهد",
    "تيار",
    "سرعة",
    "تسارع",
    "قوة",
    "نيوتن",
    "موجات",
    "ضوء",
    "صوت",
    "انكسار",
    "كيمياء",
    "فيزياء",
    "أحياء",
    "تشريح",
    "فسيولوجيا",
    "تجارب",
    "معادلات",
]

STEM_TEMPLATES = [
    "ما هي وظيفة {topic} في الكائنات الحية عند الظروف المعيارية؟",
    "علل: يعتبر {topic} من أهم العوامل المؤثرة على استقرار العمليات الحيوية.",
    "قارن بين دور {topic} والآليات البديلة من حيث الكفاءة واستهلاك الطاقة.",
    "أي العبارات التالية تصف دور {topic} داخل الأنسجة بصورة دقيقة؟",
    "في تجربة عملية لدراسة تأثير {topic}، ما هو المتغير التابع الأكثر وضوحاً؟",
    "ما العلاقة البيانية بين تركيز {topic} ومعدل النشاط الحيوي المقاس؟",
    "وضح آلية انتقال الإشارات المرتبطة بـ {topic} عبر الأغشية الخلوية.",
    "ما النتيجة المتوقعة في حال حدوث خلل وظيفي مفاجئ في {topic}؟",
    "اختر الإجابة الصحيحة: يعتمد عمل {topic} على توفر المركبات الأساسية التالية.",
    "اشرح بالتفصيل المسار الأيضي المسؤول عن تنظيم مستويات {topic}.",
]

EXAM_TITLES = [
    "امتحان نصف العام 2025",
    "امتحان نهاية العام 2025",
    "المراجعة الشاملة الأولى",
    "المراجعة الشاملة الثانية",
    "اختبار تجريبي مارس",
    "اختبار تجريبي مايو",
]


def create_throwaway_db(base_url: str) -> tuple[str, str]:
    url = make_url(base_url)
    db_name = f"qbank_bench_{uuid4().hex[:12]}"
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()
    bench_url = url.set(database=db_name).render_as_string(hide_password=False)
    return db_name, bench_url


def drop_throwaway_db(base_url: str, db_name: str) -> None:
    reset_engine()
    url = make_url(base_url)
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
    admin_engine.dispose()


def run_migrations(bench_url: str) -> None:
    os.environ["QBANK_DATABASE_URL"] = bench_url
    reset_engine()
    get_settings.cache_clear()
    alembic_ini = REPO_ROOT / "backend" / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "src" / "qbank" / "db" / "migrations"))
    command.upgrade(cfg, "head")


def seed_taxonomy(engine: Any) -> dict[str, Any]:
    with Session(engine) as db:
        org = Organization(name="Benchmark Organization")
        db.add(org)
        db.flush()

        sub_bio = Subject(org_id=org.id, name="الأحياء الثانوية", language=Language.ar, grade="3")
        sub_phys = Subject(org_id=org.id, name="الفيزياء العامة", language=Language.ar, grade="3")
        db.add_all([sub_bio, sub_phys])
        db.flush()

        ch_bio_1 = Chapter(subject_id=sub_bio.id, title="الدعامة والحركة", position=1)
        ch_bio_2 = Chapter(subject_id=sub_bio.id, title="التنسيق الهرموني", position=2)
        ch_bio_3 = Chapter(subject_id=sub_bio.id, title="التكاثر والوراثة", position=3)
        ch_phys_1 = Chapter(subject_id=sub_phys.id, title="الفيزياء الكهربية", position=1)
        ch_phys_2 = Chapter(subject_id=sub_phys.id, title="المغناطيسية", position=2)
        ch_phys_3 = Chapter(subject_id=sub_phys.id, title="الفيزياء الحديثة", position=3)
        chapters = [ch_bio_1, ch_bio_2, ch_bio_3, ch_phys_1, ch_phys_2, ch_phys_3]
        db.add_all(chapters)
        db.flush()

        lessons: list[Lesson] = []
        for ch in chapters:
            for l_pos in range(1, 5):
                les = Lesson(chapter_id=ch.id, title=f"درس {l_pos} من {ch.title}", position=l_pos)
                lessons.append(les)
        db.add_all(lessons)
        db.flush()

        src1 = Source(
            org_id=org.id,
            subject_id=sub_bio.id,
            title="كتاب الامتحان أحياء 2026",
            file_key="src1.pdf",
            status=SourceStatus.ready,
        )
        src2 = Source(
            org_id=org.id,
            subject_id=sub_bio.id,
            title="مذكرة التفوق في الأحياء",
            file_key="src2.pdf",
            status=SourceStatus.ready,
        )
        src3 = Source(
            org_id=org.id,
            subject_id=sub_phys.id,
            title="كتاب الفيزياء الحديثة",
            file_key="src3.pdf",
            status=SourceStatus.ready,
        )
        src4 = Source(
            org_id=org.id,
            subject_id=sub_phys.id,
            title="دليل المعلم فيزياء",
            file_key="src4.pdf",
            status=SourceStatus.ready,
        )
        sources = [src1, src2, src3, src4]
        db.add_all(sources)
        db.commit()

        return {
            "org_id": org.id,
            "subjects": [sub_bio.id, sub_phys.id],
            "chapters": [c.id for c in chapters],
            "bio_chapters": [ch_bio_1.id, ch_bio_2.id, ch_bio_3.id],
            "lessons": [les.id for les in lessons],
            "sources": [s.id for s in sources],
        }


def seed_questions(engine: Any, tax: dict[str, Any], n: int, batch_size: int = 5000) -> None:
    print(f"Seeding {n:,} questions in batches of {batch_size:,}...")
    org_id: UUID = tax["org_id"]
    subjects: list[UUID] = tax["subjects"]
    chapters: list[UUID] = tax["chapters"]
    lessons: list[UUID] = tax["lessons"]
    sources: list[UUID] = tax["sources"]

    base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    rng = random.Random(42)

    total_inserted = 0
    t0 = time.perf_counter()

    for batch_start in range(0, n, batch_size):
        batch_count = min(batch_size, n - batch_start)
        rows: list[dict[str, Any]] = []

        for idx in range(batch_start, batch_start + batch_count):
            sub_id = subjects[0] if (idx % 2 == 0) else subjects[1]
            ch_id = chapters[idx % len(chapters)]
            les_id = lessons[idx % len(lessons)]
            src_id = sources[idx % len(sources)]

            topic = TOPICS[idx % len(TOPICS)]
            template = STEM_TEMPLATES[idx % len(STEM_TEMPLATES)]
            has_fig = (idx % 7 == 0)
            fig_snippet = " ![](asset:00000000-0000-0000-0000-000000000001) " if has_fig else ""

            tag_count = (idx % 4) + 1
            start_tag = (idx * 3) % len(TAG_POOL)
            tags = [TAG_POOL[(start_tag + t) % len(TAG_POOL)] for t in range(tag_count)]

            tag_keywords = " ".join(tags)
            stem = (
                template.format(topic=topic)
                + f" (موضوع: {tag_keywords})"
                + fig_snippet
                + f" (سؤال رقم {idx})"
            )

            qtype_roll = idx % 100
            if qtype_roll < 70:
                qtype = "mcq_single"
            elif qtype_roll < 80:
                qtype = "mcq_multi"
            elif qtype_roll < 90:
                qtype = "essay"
            elif qtype_roll < 95:
                qtype = "short_answer"
            else:
                qtype = "true_false"

            choices = [
                {"label": "أ", "content": f"خيار أول متعلق بـ {topic}", "is_correct": True, "pinned": False},
                {"label": "ب", "content": f"خيار ثان بديل لـ {topic}", "is_correct": False, "pinned": False},
                {"label": "ج", "content": f"خيار ثالث متعلق بـ {topic}", "is_correct": False, "pinned": False},
                {"label": "د", "content": "جميع ما سبق غير صحيح", "is_correct": False, "pinned": False},
            ] if qtype.startswith("mcq") else []

            ans = f"إجابة نموذجية للسؤال رقم {idx} حول {topic}" if (idx % 3 != 0) else None
            status_roll = idx % 100
            status = "approved" if status_roll < 85 else ("draft" if status_roll < 95 else "archived")
            difficulty = (idx % 5) + 1

            exam_title = EXAM_TITLES[idx % len(EXAM_TITLES)] if (idx % 4 == 0) else None
            meta = {"exam_title": exam_title} if exam_title else {}

            norm = question_normalized_text(stem, choices)
            created_at = base_time + timedelta(minutes=idx)

            rows.append({
                "id": uuid4(),
                "org_id": org_id,
                "subject_id": sub_id,
                "source_id": src_id,
                "chapter_id": ch_id,
                "lesson_id": les_id,
                "stimulus_id": None,
                "stimulus_position": None,
                "position": (idx % 1000) + 1,
                "number_label": str((idx % 1000) + 1),
                "type": qtype,
                "stem": stem,
                "choices": choices,
                "answer": ans,
                "difficulty": difficulty,
                "language": Language.ar,
                "tags": tags,
                "regions": [{"page": (idx % 50) + 1, "box": [0.1, 0.1, 0.9, 0.4]}],
                "status": status,
                "confidence": 0.95,
                "normalized_text": norm,
                "content_hash": content_hash(norm),
                "duplicate_of_id": None,
                "metadata_json": meta,
                "created_at": created_at,
                "updated_at": created_at,
            })

        with Session(engine) as db:
            db.execute(insert(Question), rows)
            db.commit()

        total_inserted += len(rows)
        pct = (total_inserted / n) * 100
        elapsed = time.perf_counter() - t0
        rate = total_inserted / elapsed if elapsed > 0 else 0
        print(f"  Inserted {total_inserted:,}/{n:,} ({pct:.0f}%) — {rate:,.0f} rows/s", end="\r")

    print(f"\nDone seeding {n:,} rows in {time.perf_counter() - t0:.2f}s.")
    print("Running ANALYZE questions...")
    with engine.connect() as conn:
        conn.execute(text("ANALYZE questions;"))
        conn.commit()


def build_representative_queries(tax: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    sub_bio = tax["subjects"][0]
    sub_phys = tax["subjects"][1]
    ch1 = tax["chapters"][0]
    ch2 = tax["chapters"][1]
    les1 = tax["lessons"][0]
    les2 = tax["lessons"][1]
    src1 = tax["sources"][0]

    queries: list[tuple[str, dict[str, Any]]] = [
        # 1-10: Arabic full-text search with common terms and prefixes
        ("FTS 1-word 'خلية'", {"q": "خلية", "subject_id": sub_bio, "limit": 20}),
        ("FTS 1-word 'نبات'", {"q": "نبات", "subject_id": sub_bio, "limit": 20}),
        ("FTS 1-word 'ميتوكوندريا'", {"q": "ميتوكوندريا", "limit": 20}),
        ("FTS 1-word 'طاقة'", {"q": "طاقة", "limit": 20}),
        ("FTS 1-word 'هرمونات'", {"q": "هرمونات", "limit": 20}),
        ("FTS 2-word 'الخلية النباتية'", {"q": "الخلية النباتية", "subject_id": sub_bio, "limit": 20}),
        ("FTS 2-word 'إنتاج الطاقة'", {"q": "إنتاج الطاقة", "limit": 20}),
        ("FTS 3-word 'الانقسام الميتوزي والخلوي'", {"q": "الانقسام الميتوزي والخلوي", "limit": 20}),
        ("FTS prefix 'الخلي*'", {"q": "الخلي", "limit": 20}),
        ("FTS prefix 'الميتوكو*'", {"q": "الميتوكو", "limit": 20}),
        # 11-15: Tashkeel, digits, English and typo fallback
        ("FTS tashkeel 'الْخَلِيَّةِ النَّبَاتِيَّةِ'", {"q": "الْخَلِيَّةِ النَّبَاتِيَّةِ", "limit": 20}),
        ("FTS English 'DNA'", {"q": "DNA", "limit": 20}),
        ("FTS Arabic digits 'سؤال رقم ٢٥'", {"q": "سؤال رقم ٢٥", "limit": 20}),
        ("Fuzzy typo 'ما وظيفة الميتوكندريا وعملية إنتاج الطاقة'", {"q": "ما وظيفة الميتوكندريا وعملية إنتاج الطاقة", "limit": 20}),
        ("Fuzzy typo 'الانقسام الميتوزى'", {"q": "الانقسام الميتوزى", "limit": 20}),
        # 16-25: Filters without facets (standard page browsing)
        ("Filter by subject only", {"subject_id": sub_bio, "limit": 50}),
        ("Filter by chapter", {"chapter_ids": [ch1], "limit": 50}),
        ("Filter by 2 chapters", {"chapter_ids": [ch1, ch2], "limit": 50}),
        ("Filter by lesson", {"lesson_ids": [les1], "limit": 50}),
        ("Filter by type mcq_single", {"subject_id": sub_bio, "types": ["mcq_single"], "limit": 50}),
        ("Filter by types mcq + essay", {"types": ["mcq_single", "essay"], "limit": 50}),
        ("Filter difficulty 2-4", {"difficulty_min": 2, "difficulty_max": 4, "limit": 50}),
        ("Filter tags overlap", {"tags": ["خلية", "وراثة"], "limit": 50}),
        ("Filter has_figure=true", {"has_figure": True, "subject_id": sub_bio, "limit": 50}),
        ("Filter has_answer=true", {"has_answer": True, "limit": 50}),
        # 26-30: Sort modes and pagination
        ("Sort newest", {"sort": "newest", "subject_id": sub_bio, "limit": 50}),
        ("Sort difficulty", {"sort": "difficulty", "subject_id": sub_bio, "limit": 50}),
        ("Sort source_order", {"sort": "source_order", "subject_id": sub_bio, "limit": 50}),
        ("Sort relevance", {"q": "خلية", "sort": "relevance", "limit": 50}),
        ("Filter exam_title", {"exam_title": EXAM_TITLES[0], "limit": 50}),
        # 31-45: Faceted search (text + multiple filters + facets=true)
        ("Facets all questions", {"facets": True, "subject_id": sub_bio, "limit": 20}),
        ("Facets + text 'خلية'", {"q": "خلية", "facets": True, "subject_id": sub_bio, "limit": 20}),
        ("Facets + text 'طاقة'", {"q": "طاقة", "facets": True, "limit": 20}),
        ("Facets + chapter filter", {"facets": True, "chapter_ids": [ch1], "limit": 20}),
        ("Facets + lesson filter", {"facets": True, "lesson_ids": [les1], "limit": 20}),
        ("Facets + type filter", {"facets": True, "types": ["mcq_single"], "limit": 20}),
        ("Facets + difficulty filter", {"facets": True, "difficulty_min": 3, "difficulty_max": 5, "limit": 20}),
        ("Facets + status filter", {"facets": True, "statuses": ["approved"], "limit": 20}),
        ("Facets + source filter", {"facets": True, "source_ids": [src1], "limit": 20}),
        ("Facets + tags filter", {"facets": True, "tags": ["نبات", "طاقة"], "limit": 20}),
        ("Facets + text + chapter + type", {"q": "خلية", "facets": True, "chapter_ids": [ch1], "types": ["mcq_single"], "limit": 20}),
        ("Facets + text + diff + status", {"q": "هرمون", "facets": True, "difficulty_min": 2, "statuses": ["approved"], "limit": 20}),
        ("Facets + figure + answer", {"facets": True, "has_figure": True, "has_answer": True, "limit": 20}),
        ("Facets teacher role", {"facets": True, "subject_id": sub_bio, "role": Role.teacher, "limit": 20}),
        ("Facets physics subject", {"facets": True, "subject_id": sub_phys, "limit": 20}),
        # 46-50: Autocomplete tags and stats endpoints
        ("Tags autocomplete empty", {"type": "tags_autocomplete", "subject_id": sub_bio}),
        ("Tags autocomplete q='خل'", {"type": "tags_autocomplete", "subject_id": sub_bio, "q": "خل"}),
        ("Tags autocomplete q='طاق'", {"type": "tags_autocomplete", "q": "طاق"}),
        ("Bank stats subject bio", {"type": "stats", "subject_id": sub_bio}),
        ("Bank stats subject phys", {"type": "stats", "subject_id": sub_phys}),
    ]
    return queries


def run_benchmark(engine: Any, tax: dict[str, Any]) -> tuple[float, float, list[tuple[str, float]]]:
    queries = build_representative_queries(tax)
    org_id = tax["org_id"]
    latencies: list[tuple[str, float]] = []

    print(f"\nRunning {len(queries)} representative search queries...")

    # Warm-up run with 3 queries
    with Session(engine) as db:
        search_questions(db, org_id=org_id, role=Role.editor, q="خلية", limit=10)
        search_questions(db, org_id=org_id, role=Role.editor, subject_id=tax["subjects"][0], facets=True, limit=10)
        search_questions(db, org_id=org_id, role=Role.editor, facets=True, limit=10)

    for i, (name, q_params) in enumerate(queries, 1):
        with Session(engine) as db:
            role = q_params.get("role", Role.editor)
            q_type = q_params.get("type")

            t0 = time.perf_counter()
            if q_type == "tags_autocomplete":
                autocomplete_tags(
                    db=db,
                    org_id=org_id,
                    role=role,
                    subject_id=q_params.get("subject_id"),
                    q=q_params.get("q"),
                    limit=50,
                )
            elif q_type == "stats":
                bank_stats(
                    db=db,
                    org_id=org_id,
                    role=role,
                    subject_id=q_params.get("subject_id"),
                )
            else:
                search_questions(
                    db=db,
                    org_id=org_id,
                    role=role,
                    q=q_params.get("q"),
                    subject_id=q_params.get("subject_id"),
                    chapter_ids=q_params.get("chapter_ids"),
                    lesson_ids=q_params.get("lesson_ids"),
                    types=q_params.get("types"),
                    difficulty_min=q_params.get("difficulty_min"),
                    difficulty_max=q_params.get("difficulty_max"),
                    statuses=q_params.get("statuses"),
                    source_ids=q_params.get("source_ids"),
                    tags=q_params.get("tags"),
                    has_figure=q_params.get("has_figure"),
                    has_answer=q_params.get("has_answer"),
                    exam_title=q_params.get("exam_title"),
                    facets=q_params.get("facets", False),
                    sort=q_params.get("sort"),
                    limit=q_params.get("limit", 50),
                )
            t1 = time.perf_counter()
            latency_ms = (t1 - t0) * 1000.0
            latencies.append((name, latency_ms))
            print(f"  [{i:02d}/50] {latency_ms:6.1f} ms — {name}")

    durations = sorted(d for _, d in latencies)
    n_queries = len(durations)
    p50_idx = int(n_queries * 0.50)
    p95_idx = int(n_queries * 0.95)
    p50 = durations[p50_idx]
    p95 = durations[p95_idx]
    return p50, p95, latencies


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark question bank search performance at scale.")
    parser.add_argument("--n", type=int, default=100000, help="Number of questions to seed (default: 100,000)")
    parser.add_argument("--db-url", type=str, default=None, help="Base Postgres database URL")
    parser.add_argument("--keep-db", action="store_true", help="Keep the throwaway database after benchmark")
    args = parser.parse_args()

    base_url = args.db_url or get_settings().database_url
    print(f"Starting search benchmark with N={args.n:,}")
    db_name, bench_url = create_throwaway_db(base_url)
    print(f"Created throwaway database: {db_name}")

    try:
        print("Running Alembic migrations...")
        run_migrations(bench_url)

        engine = create_engine(bench_url)
        print("Seeding taxonomy...")
        tax = seed_taxonomy(engine)

        seed_questions(engine, tax, n=args.n)

        p50, p95, _ = run_benchmark(engine, tax)
        engine.dispose()

        print("\n" + "=" * 50)
        print(f"SEARCH BENCHMARK RESULTS (N = {args.n:,})")
        print("=" * 50)
        print(f"p50: {p50:.1f} ms")
        print(f"p95: {p95:.1f} ms")
        print(f"Target: p95 < 300 ms — {'PASS' if p95 < 300 else 'FAIL'}")
        print("=" * 50)

    finally:
        if not args.keep_db:
            print(f"Dropping throwaway database: {db_name}...")
            drop_throwaway_db(base_url, db_name)
        else:
            print(f"Preserving throwaway database: {db_name}")


if __name__ == "__main__":
    main()
