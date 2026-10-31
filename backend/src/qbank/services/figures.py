"""Figure crops attached to questions and in-place re-cropping of assets."""

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import Session

from qbank.models import Asset, Question, Source, SourcePage, Stimulus, User
from qbank.pipeline.materialize import crop_region, render_crop
from qbank.schemas.review import FigureIn
from qbank.services.audit import load_question, record, revalidate, snapshot
from qbank.services.errors import Conflict, Invalid, NotFound
from qbank.services.unit_of_work import found, save
from qbank.storage import get_store


def page_and_source(db: Session, org_id: UUID, page_id: UUID) -> tuple[SourcePage, Source]:
    row = db.execute(
        select(SourcePage, Source)
        .join(Source, SourcePage.source_id == Source.id)
        .where(SourcePage.id == page_id, Source.org_id == org_id)
    ).first()
    if row is None:
        raise NotFound()
    page, source = row
    if page.image_key is None:
        raise Conflict("page_not_rendered")
    return page, source


def add_figure(db: Session, user: User, question_id: UUID, data: FigureIn) -> Asset:
    question = load_question(db, user.org_id, question_id, lock=True)
    page, source = page_and_source(db, user.org_id, data.page_id)
    before = snapshot(question)
    try:
        asset = crop_region(db, source, page, data.box, pipeline_generated=False)
    except ValueError:
        raise Invalid("empty_region") from None
    question.stem = f"{question.stem}\n![](asset:{asset.id})".lstrip("\n")
    question.version += 1
    revalidate(db, question)
    after = snapshot(question)
    record(
        db,
        question,
        user,
        "figure_add",
        {
            "stem": {"before": before["stem"], "after": after["stem"]},
            "asset": {"before": None, "after": str(asset.id)},
        },
    )
    save(db)
    db.refresh(asset)
    return asset


def get_asset(db: Session, org_id: UUID, asset_id: UUID) -> Asset:
    return found(db.scalar(select(Asset).where(Asset.id == asset_id, Asset.org_id == org_id)))


def recrop(db: Session, user: User, asset_id: UUID, box: list[float]) -> Asset:
    """Re-crop in place: same asset id and storage key, new pixels and a new ETag."""
    asset = found(db.scalar(select(Asset).where(Asset.id == asset_id, Asset.org_id == user.org_id)))
    if asset.source_page_id is None:
        raise Conflict("asset_without_page")
    page, source = page_and_source(db, user.org_id, asset.source_page_id)
    try:
        data, width, height = render_crop(source, page, box)
    except ValueError:
        raise Invalid("empty_region") from None
    old_region = list(asset.region)
    get_store().put_bytes(asset.image_key, data, "image/webp")
    asset.region, asset.width, asset.height = box, width, height
    asset.updated_at = datetime.now(UTC)  # the ETag is derived from this, even for an equal box
    for question in _referencing(db, user.org_id, asset.id):
        record(
            db,
            question,
            user,
            "figure_recrop",
            {
                "asset": {"before": str(asset.id), "after": str(asset.id)},
                "region": {"before": old_region, "after": box},
            },
        )
    save(db)
    db.refresh(asset)
    return asset


def _referencing(db: Session, org_id: UUID, asset_id: UUID) -> list[Question]:
    needle = f"asset:{asset_id}"
    return list(
        db.scalars(
            select(Question).where(
                Question.org_id == org_id,
                Question.stem.contains(needle, autoescape=True)
                | func.coalesce(Question.explanation, "").contains(needle, autoescape=True)
                | cast(Question.choices, Text).contains(needle, autoescape=True),
            )
        )
    )


def _remove_ref(text: str, asset_id: UUID) -> str:
    pattern = re.compile(rf"\n?!\[[^\]]*\]\(asset:{asset_id}\)")
    return pattern.sub("", text).strip("\n")


def delete_figure(db: Session, user: User, question_id: UUID, asset_id: UUID) -> None:
    question = load_question(db, user.org_id, question_id, lock=True)
    asset = found(db.scalar(select(Asset).where(Asset.id == asset_id, Asset.org_id == user.org_id)))
    before = snapshot(question)
    stem = _remove_ref(question.stem, asset.id)
    choices = [
        {**c, "content": _remove_ref(str(c.get("content", "")), asset.id)} for c in question.choices
    ]
    explanation = _remove_ref(question.explanation, asset.id) if question.explanation else None
    if (stem, choices, explanation) == (question.stem, question.choices, question.explanation):
        raise NotFound()
    question.stem, question.choices, question.explanation = stem, choices, explanation
    question.version += 1
    revalidate(db, question)
    record(
        db,
        question,
        user,
        "figure_delete",
        {
            "stem": {"before": before["stem"], "after": question.stem},
            "asset": {"before": str(asset.id), "after": None},
        },
    )
    db.flush()
    key = None
    others = [q for q in _referencing(db, user.org_id, asset.id) if q.id != question.id]
    in_stimulus = db.scalar(
        select(func.count())
        .select_from(Stimulus)
        .where(Stimulus.org_id == user.org_id, Stimulus.content.contains(f"asset:{asset.id}"))
    )
    if not others and not in_stimulus:
        key = asset.image_key
        db.delete(asset)
    save(db)
    if key:
        get_store().delete(key)
