"""Dramatiq render actors."""

from io import BytesIO
from uuid import UUID

import dramatiq
import pymupdf
from dramatiq.brokers.redis import RedisBroker
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from qbank.config import get_settings
from qbank.db import get_engine
from qbank.models import Job, LLMCall, PageStatus, Source, SourcePage, SourceStatus
from qbank.pipeline import orchestrator
from qbank.pipeline.orchestrator import page_done
from qbank.pipeline.pdf_cache import get_pdf_cache
from qbank.services import exports as exports_service
from qbank.services import proposals
from qbank.storage import get_store, keys

dramatiq.set_broker(RedisBroker(url=get_settings().redis_url))  # type: ignore[no-untyped-call]  # Dramatiq lacks constructor types.


def fail_source(source_id: UUID, error: str) -> None:
    with Session(get_engine()) as db:
        failed = db.scalar(
            update(Source)
            .where(
                Source.id == source_id,
                Source.stage == "render",
                Source.status == SourceStatus.rendering,
            )
            .values(status=SourceStatus.failed, error=error)
            .returning(Source.id)
        )
        if failed:
            db.execute(
                update(Job).where(Job.ref_id == source_id).values(status="failed", error=error)
            )
        db.commit()


@dramatiq.actor(max_retries=3)
def source_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)):
        raise ValueError("Invalid message arguments")
    fail_source(UUID(str(args[0])), "storage_error: retries exhausted")


@dramatiq.actor(max_retries=3, on_retry_exhausted="source_failed")
def render_source(source_id: str) -> None:
    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        if source is None or source.stage != "render":
            return
        file_key = source.file_key
    # Storage errors propagate to Dramatiq for retry.
    with get_pdf_cache().acquire(file_key, get_store()) as path:
        try:
            with pymupdf.open(str(path)) as document:  # type: ignore[no-untyped-call]  # PyMuPDF constructor is untyped.
                count = document.page_count
        except Exception as exc:
            fail_source(sid, str(exc))
            return
    if count > get_settings().max_pages:
        fail_source(sid, "too_many_pages")
        return
    with Session(get_engine()) as db:
        source = db.scalar(select(Source).where(Source.id == sid).with_for_update())
        if source is None or source.stage != "render":
            return
        source.page_count = count
        existing = set(
            db.scalars(select(SourcePage.page_number).where(SourcePage.source_id == sid))
        )
        for number in range(1, count + 1):
            if number not in existing:
                db.add(SourcePage(source_id=sid, page_number=number, status=PageStatus.pending))
        db.commit()
        pending = list(
            db.scalars(
                select(SourcePage.page_number).where(
                    SourcePage.source_id == sid, SourcePage.status == PageStatus.pending
                )
            )
        )
    batch_size = get_settings().render_batch_size
    for offset in range(0, len(pending), batch_size):
        render_pages.send(source_id, pending[offset : offset + batch_size])
    if not pending:
        page_done(sid, "render")


@dramatiq.actor(max_retries=3)
def render_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)):
        raise ValueError("Invalid message arguments")
    sid = UUID(str(args[0]))
    numbers = args[1]
    if not isinstance(numbers, (list, tuple)):
        raise ValueError("Invalid page numbers")
    options = message.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("Invalid message options")
    trace = str(options.get("traceback", "storage failure")).strip().splitlines()[-1]
    with Session(get_engine()) as db:
        db.execute(
            update(SourcePage)
            .where(
                SourcePage.source_id == sid,
                SourcePage.page_number.in_(numbers),
                SourcePage.status == PageStatus.pending,
            )
            .values(status=PageStatus.failed, error=f"storage_error: {trace}")
        )
        db.commit()
    page_done(sid, "render")


@dramatiq.actor(max_retries=3, on_retry_exhausted="render_failed")
def render_pages(source_id: str, numbers: list[int]) -> None:
    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        if source is None or source.stage != "render":
            return
        org, file_key = source.org_id, source.file_key
    with (
        get_pdf_cache().acquire(file_key, get_store()) as path,
        pymupdf.open(str(path)) as document,  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
    ):
        for number in numbers:
            render_one(sid, org, number, document)


def render_one(sid: UUID, org: UUID, page_number: int, document: pymupdf.Document) -> None:
    with Session(get_engine()) as db:
        page = db.scalar(
            select(SourcePage).where(
                SourcePage.source_id == sid, SourcePage.page_number == page_number
            )
        )
        if page is None or page.status != PageStatus.pending:
            return
    settings = get_settings()
    try:
        pdf_page = document.load_page(page_number - 1)  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
        display = pdf_page.get_pixmap(dpi=settings.render_dpi_display, alpha=False)
        hires = pdf_page.get_pixmap(dpi=settings.render_dpi_hires, alpha=False)
        image = Image.frombytes("RGB", (display.width, display.height), display.samples)
        output = BytesIO()
        image.save(output, format="WEBP")
        display_data = output.getvalue()
        hires_data = hires.tobytes("png")
    except Exception as exc:
        with Session(get_engine()) as db:
            db.execute(
                update(SourcePage)
                .where(
                    SourcePage.source_id == sid,
                    SourcePage.page_number == page_number,
                    SourcePage.status == PageStatus.pending,
                )
                .values(status=PageStatus.failed, error=str(exc))
            )
            db.commit()
        page_done(sid, "render")
        return
    display_key = keys.page(org, sid, page_number)
    get_store().put_bytes(display_key, display_data, "image/webp")
    get_store().put_bytes(keys.page(org, sid, page_number, hires=True), hires_data, "image/png")
    with Session(get_engine()) as db:
        db.execute(
            update(SourcePage)
            .where(
                SourcePage.source_id == sid,
                SourcePage.page_number == page_number,
                SourcePage.status == PageStatus.pending,
            )
            .values(
                status=PageStatus.rendered,
                image_key=display_key,
                width_px=display.width,
                height_px=display.height,
                dpi=settings.render_dpi_display,
            )
        )
        db.commit()
    page_done(sid, "render")


@dramatiq.actor(max_retries=3)
def extract_source(source_id: str) -> None:
    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        if source is None or source.stage != "extract" or source.status != SourceStatus.extracting:
            return
        pending = list(
            db.scalars(
                select(SourcePage.page_number)
                .where(SourcePage.source_id == sid, SourcePage.status == PageStatus.rendered)
                .order_by(SourcePage.page_number)
            )
        )
    batch_size = get_settings().render_batch_size
    for offset in range(0, len(pending), batch_size):
        extract_pages.send(source_id, pending[offset : offset + batch_size])
    if not pending:
        page_done(sid, "extract")


@dramatiq.actor(max_retries=3, on_retry_exhausted="extract_failed")
def extract_pages(source_id: str, numbers: list[int]) -> None:
    from qbank.llm import BudgetExceeded, LLMOutputInvalid, OrgBudgetExceeded, get_llm_client  # noqa: PLC0415
    from qbank.models import Organization, Subject  # noqa: PLC0415
    from qbank.pipeline.extract import PROMPT_VERSION, extract_page  # noqa: PLC0415

    sid = UUID(source_id)
    client = get_llm_client()
    for number in numbers:
        with Session(get_engine()) as db:
            source = db.get(Source, sid)
            page = db.scalar(
                select(SourcePage).where(
                    SourcePage.source_id == sid, SourcePage.page_number == number
                )
            )
            if (
                source is None
                or source.stage != "extract"
                or source.status != SourceStatus.extracting
            ):
                return
            if page is None or page.status != PageStatus.rendered:
                continue
            subject = db.get(Subject, source.subject_id)
            if subject is None:
                raise ValueError("Missing subject")
            org = db.get(Organization, source.org_id)
            configured_model = (source.pipeline_config or {}).get(
                "extract_model", (org.settings or {}).get("extract_model") if org else None
            )
            model_override = configured_model if isinstance(configured_model, str) else None
            org_id, subject_name, language, grade = (
                source.org_id,
                subject.name,
                subject.language.value,
                source.grade or subject.grade,
            )
        try:
            data = get_store().get_bytes(keys.page(org_id, sid, number, hires=True))
            result, cost = extract_page(
                client,
                data,
                subject=subject_name,
                language=language,
                grade=grade,
                org_id=org_id,
                source_id=sid,
                model_override=model_override,
                max_side=get_settings().extract_image_max_side,
                fallback_threshold=get_settings().extract_fallback_threshold,
            )
        except (BudgetExceeded, OrgBudgetExceeded) as exc:
            with Session(get_engine()) as db:
                updated = db.scalar(
                    update(SourcePage)
                    .where(
                        SourcePage.source_id == sid,
                        SourcePage.page_number == number,
                        SourcePage.status == PageStatus.rendered,
                    )
                    .values(cost_usd=SourcePage.cost_usd + float(exc.cost_usd))
                    .returning(SourcePage.id)
                )
                db.execute(
                    update(Source)
                    .where(Source.id == sid, Source.stage == "extract")
                    .values(
                        status=SourceStatus.paused,
                        error=type(exc).__name__,
                        cost_usd=Source.cost_usd + (float(exc.cost_usd) if updated else 0),
                    )
                )
                db.execute(
                    update(Job)
                    .where(Job.ref_id == sid, Job.kind == "ingest")
                    .values(status="paused", error=type(exc).__name__)
                )
                db.commit()
            return
        except Exception as exc:
            with Session(get_engine()) as db:
                failed_cost = float(exc.cost_usd) if isinstance(exc, LLMOutputInvalid) else 0.0
                updated = db.scalar(
                    update(SourcePage)
                    .where(
                        SourcePage.source_id == sid,
                        SourcePage.page_number == number,
                        SourcePage.status == PageStatus.rendered,
                    )
                    .values(
                        status=PageStatus.failed,
                        error=str(exc),
                        cost_usd=SourcePage.cost_usd + failed_cost,
                    )
                    .returning(SourcePage.id)
                )
                if updated and failed_cost:
                    db.execute(
                        update(Source)
                        .where(Source.id == sid)
                        .values(cost_usd=Source.cost_usd + failed_cost)
                    )
                db.commit()
        else:
            with Session(get_engine()) as db:
                updated = db.scalar(
                    update(SourcePage)
                    .where(
                        SourcePage.source_id == sid,
                        SourcePage.page_number == number,
                        SourcePage.status == PageStatus.rendered,
                    )
                    .values(
                        status=PageStatus.extracted,
                        extraction=result.parsed.model_dump(mode="json"),
                        page_kind=result.parsed.page_kind,
                        prompt_version=PROMPT_VERSION,
                        model=result.model,
                        cost_usd=SourcePage.cost_usd + float(cost),
                        error=None,
                    )
                    .returning(SourcePage.id)
                )
                if updated:
                    db.execute(
                        update(Source)
                        .where(Source.id == sid)
                        .values(cost_usd=Source.cost_usd + float(cost))
                    )
                    _record_non_live_call(
                        db, client, "extract", PROMPT_VERSION, result, org_id, sid
                    )
                db.commit()
        page_done(sid, "extract")


@dramatiq.actor(max_retries=3)
def extract_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)) or not isinstance(args[1], (list, tuple)):
        raise ValueError("Invalid message arguments")
    sid = UUID(str(args[0]))
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        if source is None or source.stage != "extract" or source.status != SourceStatus.extracting:
            return
        db.execute(
            update(SourcePage)
            .where(
                SourcePage.source_id == sid,
                SourcePage.page_number.in_(args[1]),
                SourcePage.status == PageStatus.rendered,
            )
            .values(status=PageStatus.failed, error="extract_error: retries exhausted")
        )
        db.commit()
    page_done(sid, "extract")


@dramatiq.actor(max_retries=3)
def materialize_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)):
        raise ValueError("Invalid message arguments")
    sid = UUID(str(args[0]))
    with Session(get_engine()) as db:
        failed = db.scalar(
            update(Source)
            .where(
                Source.id == sid,
                Source.stage == "materialize",
                Source.status == SourceStatus.extracting,
            )
            .values(status=SourceStatus.failed, error="materialize_error: retries exhausted")
            .returning(Source.id)
        )
        if failed:
            db.execute(
                update(Job)
                .where(Job.ref_id == sid, Job.kind == "ingest")
                .values(status="failed", error="materialize_error: retries exhausted")
            )
        db.commit()


@dramatiq.actor(max_retries=3, on_retry_exhausted="materialize_failed")
def materialize_source(source_id: str) -> None:
    from qbank.pipeline.materialize import materialize  # noqa: PLC0415 -- avoid import cycle

    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.scalar(select(Source).where(Source.id == sid).with_for_update())
        if (
            source is None
            or source.stage != "materialize"
            or source.status != SourceStatus.extracting
        ):
            return
        old_keys = materialize(db, source)
        db.commit()
    for key in old_keys:
        get_store().delete(key)
    orchestrator.advance(sid, "materialize")


def _fail_validating_stage(source_id: UUID, stage: str, error: str) -> None:
    with Session(get_engine()) as db:
        failed = db.scalar(
            update(Source)
            .where(
                Source.id == source_id,
                Source.stage == stage,
                Source.status == SourceStatus.validating,
            )
            .values(status=SourceStatus.failed, error=error)
            .returning(Source.id)
        )
        if failed:
            db.execute(
                update(Job)
                .where(Job.ref_id == source_id, Job.kind == "ingest")
                .values(status="failed", error=error)
            )
        db.commit()


def _record_non_live_call(  # noqa: PLR0913, PLR0917 -- ledger attributes
    db: Session,
    client: object,
    stage: str,
    prompt_version: str,
    result: object,
    org_id: UUID | None,
    source_id: UUID | None,
) -> None:
    if type(client).__name__ == "OpenRouterClient":
        return
    db.add(
        LLMCall(
            org_id=org_id,
            source_id=source_id,
            stage=stage,
            model=str(getattr(result, "model", "")),
            prompt_version=prompt_version,
            input_tokens=int(getattr(result, "input_tokens", 0)),
            output_tokens=int(getattr(result, "output_tokens", 0)),
            reasoning_tokens=int(getattr(result, "reasoning_tokens", 0)),
            cost_usd=getattr(result, "cost_usd", 0),
            latency_ms=int(getattr(result, "latency_ms", 0)),
            status="success",
            request_hash=str(getattr(result, "request_hash", "")),
        )
    )


def _pause_source_on_budget(
    db: Session,
    sid: UUID,
    stage: str,
    error_name: str,
    extra_cost: float = 0.0,
) -> None:
    db.execute(
        update(Source)
        .where(Source.id == sid, Source.stage == stage)
        .values(
            status=SourceStatus.paused,
            error=error_name,
            cost_usd=Source.cost_usd + extra_cost,
        )
    )
    db.execute(
        update(Job)
        .where(Job.ref_id == sid, Job.kind == "ingest")
        .values(status="paused", error=error_name)
    )
    db.commit()


@dramatiq.actor(max_retries=3)
def structure_source(source_id: str) -> None:
    from qbank.pipeline.structure import structure_source as run_structure  # noqa: PLC0415

    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.scalar(select(Source).where(Source.id == sid))
        if (
            source is None
            or source.stage != "structure"
            or source.status != SourceStatus.validating
        ):
            return
        run_structure(db, source)
        db.commit()
    orchestrator.advance(sid, "structure")


@dramatiq.actor(max_retries=3)
def answer_keys_source(source_id: str) -> None:
    from qbank.pipeline.answer_keys import answer_keys_source as run_answer_keys  # noqa: PLC0415

    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.scalar(select(Source).where(Source.id == sid).with_for_update())
        if (
            source is None
            or source.stage != "answer_keys"
            or source.status != SourceStatus.validating
        ):
            return
        run_answer_keys(db, source)
        db.commit()
    orchestrator.advance(sid, "answer_keys")


@dramatiq.actor(max_retries=3)
def validate_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)):
        raise ValueError("Invalid message arguments")
    _fail_validating_stage(UUID(str(args[0])), "validate", "validate_error: retries exhausted")


@dramatiq.actor(max_retries=3, on_retry_exhausted="validate_failed")
def validate_source(source_id: str) -> None:
    from qbank.pipeline.validate import validate_source as run_validate  # noqa: PLC0415

    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.scalar(select(Source).where(Source.id == sid).with_for_update())
        if source is None or source.stage != "validate" or source.status != SourceStatus.validating:
            return
        run_validate(db, source, run_dedup=True)
        db.commit()
    orchestrator.advance(sid, "validate")


@dramatiq.actor(max_retries=3)
def verify_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)):
        raise ValueError("Invalid message arguments")
    _fail_validating_stage(UUID(str(args[0])), "verify", "verify_error: retries exhausted")


@dramatiq.actor(max_retries=3, on_retry_exhausted="verify_failed")
def verify_source(source_id: str) -> None:  # noqa: PLR0915 -- page loop + budget/invalid handling
    from qbank.llm import BudgetExceeded, LLMOutputInvalid, OrgBudgetExceeded, get_llm_client  # noqa: PLC0415
    from qbank.models import Organization, Question  # noqa: PLC0415
    from qbank.pipeline.validate import validate_source as run_validate  # noqa: PLC0415
    from qbank.pipeline.verify import (  # noqa: PLC0415
        apply_discrepancies,
        get_verify_policy,
        is_page_verified,
        questions_for_page,
        select_pages_to_verify,
        verify_page,
    )

    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        if source is None or source.stage != "verify" or source.status != SourceStatus.validating:
            return
        policy = get_verify_policy(source, db.get(Organization, source.org_id))
        if policy == "off":
            orchestrator.advance(sid, "verify")
            return
        pages = list(
            db.scalars(
                select(SourcePage)
                .where(SourcePage.source_id == sid)
                .order_by(SourcePage.page_number.asc())
            )
        )
        questions = list(
            db.scalars(
                select(Question)
                .where(Question.source_id == sid)
                .order_by(Question.position.asc(), Question.id.asc())
            )
        )
        target_page_numbers = [
            p.page_number
            for p in select_pages_to_verify(
                pages,
                questions,
                policy=policy,
                review_threshold=get_settings().review_threshold,
            )
        ]

    client = get_llm_client()
    store = get_store()
    for page_number in target_page_numbers:
        with Session(get_engine()) as db:
            source = db.get(Source, sid)
            page = db.scalar(
                select(SourcePage).where(
                    SourcePage.source_id == sid, SourcePage.page_number == page_number
                )
            )
            if (
                source is None
                or source.stage != "verify"
                or source.status != SourceStatus.validating
            ):
                return
            if page is None or page.status == PageStatus.failed:
                continue
            questions = list(
                db.scalars(
                    select(Question)
                    .where(Question.source_id == sid)
                    .order_by(Question.position.asc(), Question.id.asc())
                )
            )
            page_qs = questions_for_page(page, questions)
            if not page_qs or is_page_verified(page_qs):
                continue
            org_id = source.org_id
            payload = [
                {
                    "number_label": q.number_label,
                    "type": q.type,
                    "stem": q.stem,
                    "choices": [
                        {
                            "label": c.get("label"),
                            "content": c.get("content"),
                            "is_correct": c.get("is_correct"),
                        }
                        for c in q.choices
                    ],
                    "answer": q.answer,
                }
                for q in page_qs
            ]
        try:
            hires_key = keys.page(org_id, sid, page_number, hires=True)
            display_key = keys.page(org_id, sid, page_number, hires=False)
            data = (
                store.get_bytes(hires_key)
                if store.exists(hires_key)
                else store.get_bytes(display_key)
            )
            result, cost = verify_page(
                client,
                data,
                payload,
                org_id=org_id,
                source_id=sid,
                max_side=get_settings().extract_image_max_side,
            )
        except (BudgetExceeded, OrgBudgetExceeded) as exc:
            with Session(get_engine()) as db:
                db.execute(
                    update(SourcePage)
                    .where(SourcePage.source_id == sid, SourcePage.page_number == page_number)
                    .values(cost_usd=SourcePage.cost_usd + float(exc.cost_usd))
                )
                _pause_source_on_budget(db, sid, "verify", type(exc).__name__, float(exc.cost_usd))
            return
        except LLMOutputInvalid as exc:
            with Session(get_engine()) as db:
                failed_cost = float(exc.cost_usd)
                db.execute(
                    update(SourcePage)
                    .where(SourcePage.source_id == sid, SourcePage.page_number == page_number)
                    .values(cost_usd=SourcePage.cost_usd + failed_cost)
                )
                if failed_cost:
                    db.execute(
                        update(Source)
                        .where(Source.id == sid)
                        .values(cost_usd=Source.cost_usd + failed_cost)
                    )
                db.commit()
        else:
            with Session(get_engine()) as db:
                source = db.get(Source, sid)
                page = db.scalar(
                    select(SourcePage).where(
                        SourcePage.source_id == sid, SourcePage.page_number == page_number
                    )
                )
                if source is None or page is None:
                    return
                page.cost_usd = float(page.cost_usd or 0.0) + float(cost)
                source.cost_usd = float(source.cost_usd or 0.0) + float(cost)
                _record_non_live_call(db, client, "verify", "verify-v1", result, org_id, sid)
                questions = list(
                    db.scalars(
                        select(Question)
                        .where(Question.source_id == sid)
                        .order_by(Question.position.asc(), Question.id.asc())
                    )
                )
                page_qs = questions_for_page(page, questions)
                apply_discrepancies(page_qs, result.parsed.discrepancies)
                page_q_ids = {q.id for q in page_qs if q.id is not None}
                run_validate(db, source, question_ids=page_q_ids, run_dedup=False)
                db.commit()
    orchestrator.advance(sid, "verify")


@dramatiq.actor(max_retries=3)
def classify_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)):
        raise ValueError("Invalid message arguments")
    _fail_validating_stage(UUID(str(args[0])), "classify", "classify_error: retries exhausted")


@dramatiq.actor(max_retries=3, on_retry_exhausted="classify_failed")
def classify_source(source_id: str) -> None:
    from qbank.llm import BudgetExceeded, LLMOutputInvalid, OrgBudgetExceeded, get_llm_client  # noqa: PLC0415
    from qbank.models import Question, Subject  # noqa: PLC0415
    from qbank.pipeline.classify import (  # noqa: PLC0415
        BATCH_SIZE,
        apply_classifications,
        classify_batch,
        pending_classification_questions,
    )

    sid = UUID(source_id)
    client = get_llm_client()
    while True:
        with Session(get_engine()) as db:
            source = db.get(Source, sid)
            if (
                source is None
                or source.stage != "classify"
                or source.status != SourceStatus.validating
            ):
                return
            subject = db.get(Subject, source.subject_id)
            subject_name = subject.name if subject else "اللغة العربية"
            language = subject.language.value if subject else "ar"
            org_id = source.org_id
            all_questions = list(
                db.scalars(
                    select(Question)
                    .where(Question.source_id == sid)
                    .order_by(Question.position.asc(), Question.id.asc())
                )
            )
            pending = pending_classification_questions(all_questions)
            if not pending:
                break
            batch = pending[:BATCH_SIZE]
            batch_ids = [q.id for q in batch]
            payload: list[dict[str, object]] = [
                {
                    "id": str(q.id),
                    "type": q.type,
                    "language": q.language.value,
                    "stem": q.stem,
                    "choices": [
                        {"label": c.get("label"), "content": c.get("content")} for c in q.choices
                    ],
                    "answer": q.answer,
                }
                for q in batch
            ]
        try:
            result, cost = classify_batch(
                client,
                payload,
                subject=subject_name,
                language=language,
                org_id=org_id,
                source_id=sid,
            )
        except (BudgetExceeded, OrgBudgetExceeded) as exc:
            with Session(get_engine()) as db:
                _pause_source_on_budget(
                    db, sid, "classify", type(exc).__name__, float(exc.cost_usd)
                )
            return
        except LLMOutputInvalid as exc:
            with Session(get_engine()) as db:
                failed_cost = float(exc.cost_usd)
                if failed_cost:
                    db.execute(
                        update(Source)
                        .where(Source.id == sid)
                        .values(cost_usd=Source.cost_usd + failed_cost)
                    )
                    db.commit()
            break
        else:
            with Session(get_engine()) as db:
                source = db.get(Source, sid)
                if source is None:
                    return
                source.cost_usd = float(source.cost_usd or 0.0) + float(cost)
                _record_non_live_call(db, client, "classify", "classify-v1", result, org_id, sid)
                batch_qs = list(
                    db.scalars(
                        select(Question)
                        .where(Question.id.in_(batch_ids))
                        .order_by(Question.position.asc(), Question.id.asc())
                    )
                )
                apply_classifications(batch_qs, result.parsed.items)
                # Mark batch questions processed even if omitted in a partial response.
                for q in batch_qs:
                    if q.difficulty_source != "human" and q.difficulty_source is None:
                        q.difficulty_source = "ai"
                db.commit()

    with Session(get_engine()) as db:
        db.execute(
            update(SourcePage)
            .where(SourcePage.source_id == sid, SourcePage.status == PageStatus.extracted)
            .values(status=PageStatus.validated)
        )
        db.commit()
    orchestrator.advance(sid, "classify")


if __name__ == "__main__":
    import sys

    from dramatiq.cli import main

    sys.argv = ["dramatiq", "qbank.worker"]
    main()  # type: ignore[no-untyped-call]  # Dramatiq CLI is untyped.


@dramatiq.actor(max_retries=0, time_limit=15 * 60 * 1000)
def render_exports(export_ids: list[str]) -> None:
    """Render pending exports one by one; each outcome is recorded on its own row."""
    for export_id in export_ids:
        with Session(get_engine()) as db:
            exports_service.render_one(db, UUID(export_id))


@dramatiq.actor(max_retries=0, time_limit=10 * 60 * 1000)
def reextract_page(
    job_id: str, source_id: str, number: int, model: str | None, user_id: str
) -> None:
    """Re-extract one page into a pending proposal (F4.6); live rows are never touched."""
    with Session(get_engine()) as db:
        proposals.run_reextract(
            db,
            proposals.get_client(),
            UUID(job_id),
            UUID(source_id),
            number,
            model,
            UUID(user_id),
        )
