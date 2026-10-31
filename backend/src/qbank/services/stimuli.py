"""Stimulus (shared passage/figure) editing."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.models import Question, Stimulus, User
from qbank.pipeline.materialize import crop_region, normalize_blanks
from qbank.schemas.review import StimulusCreate, StimulusPatch
from qbank.services.audit import revalidate
from qbank.services.errors import Conflict, Invalid
from qbank.services.figures import page_and_source
from qbank.services.unit_of_work import found, save


def get_stimulus(db: Session, org_id: UUID, stimulus_id: UUID) -> Stimulus:
    return found(
        db.scalar(select(Stimulus).where(Stimulus.id == stimulus_id, Stimulus.org_id == org_id))
    )


def create(db: Session, user: User, data: StimulusCreate) -> Stimulus:
    page, source = page_and_source(db, user.org_id, data.page_id)
    if source.id != data.source_id:
        raise Invalid("page_source_mismatch")
    content = normalize_blanks(data.content)
    if data.kind == "figure" and not content:
        try:
            asset = crop_region(db, source, page, data.box, pipeline_generated=False)
        except ValueError:
            raise Invalid("empty_region") from None
        content = f"![](asset:{asset.id})"
    stimulus = Stimulus(
        org_id=user.org_id,
        source_id=source.id,
        kind=data.kind,
        content=content,
        regions=[{"page": str(page.id), "box": data.box}],
        status="draft",
        metadata_json={"notes": [], "intro": data.intro, "manual": True},
    )
    db.add(stimulus)
    save(db)
    return stimulus


def patch(db: Session, user: User, stimulus_id: UUID, data: StimulusPatch) -> Stimulus:
    stimulus = get_stimulus(db, user.org_id, stimulus_id)
    fields = data.model_fields_set
    if "content" in fields and data.content is not None:
        stimulus.content = normalize_blanks(data.content)
    if "kind" in fields and data.kind is not None:
        stimulus.kind = data.kind
    if "intro" in fields:
        stimulus.metadata_json = {**stimulus.metadata_json, "intro": data.intro}
        for question in db.scalars(select(Question).where(Question.stimulus_id == stimulus.id)):
            revalidate(db, question)
    save(db)
    return stimulus


def set_status(db: Session, user: User, stimulus_id: UUID, status: str) -> Stimulus:
    stimulus = get_stimulus(db, user.org_id, stimulus_id)
    stimulus.status = status
    save(db)
    return stimulus


def delete(db: Session, user: User, stimulus_id: UUID) -> None:
    stimulus = get_stimulus(db, user.org_id, stimulus_id)
    if db.scalar(select(Question.id).where(Question.stimulus_id == stimulus.id).limit(1)):
        raise Conflict("stimulus_in_use")
    db.delete(stimulus)
    save(db)
