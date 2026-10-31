from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.api.pagination import paginate
from qbank.models import Asset, ExamTemplate, User
from qbank.schemas.exports import TemplateIn, TemplateOut, TemplateUpdate
from qbank.services.errors import Invalid, NotFound
from qbank.services.unit_of_work import found, save


def _out(template: ExamTemplate) -> TemplateOut:
    return TemplateOut.model_validate(template, from_attributes=True)


def template_for(db: Session, org_id: UUID, template_id: UUID) -> ExamTemplate:
    return found(
        db.scalar(
            select(ExamTemplate).where(
                ExamTemplate.id == template_id, ExamTemplate.org_id == org_id
            )
        )
    )


def _check_logo(db: Session, org_id: UUID, asset_id: UUID | None) -> None:
    if asset_id is not None and (
        db.scalar(select(Asset.id).where(Asset.id == asset_id, Asset.org_id == org_id)) is None
    ):
        raise NotFound("logo_not_found")


def check_exam_template(db: Session, org_id: UUID, template_id: UUID | None) -> None:
    """A template referenced from exam settings must exist in the caller's organization."""
    if template_id is not None:
        try:
            template_for(db, org_id, template_id)
        except NotFound:
            raise Invalid("template_not_found") from None


def listing(db: Session, user: User, cursor: str | None, limit: int) -> dict[str, object]:
    stmt = select(ExamTemplate).where(ExamTemplate.org_id == user.org_id)
    try:
        items, next_cursor = paginate(db, stmt, ExamTemplate, cursor, limit)
    except ValueError:
        raise Invalid("invalid_cursor") from None
    return {"items": [_out(t) for t in items], "next_cursor": next_cursor}


def get(db: Session, user: User, template_id: UUID) -> TemplateOut:
    return _out(template_for(db, user.org_id, template_id))


def create(db: Session, user: User, data: TemplateIn) -> TemplateOut:
    _check_logo(db, user.org_id, data.logo_asset_id)
    template = ExamTemplate(
        org_id=user.org_id,
        name=data.name,
        header=data.header.model_dump(mode="json"),
        logo_asset_id=data.logo_asset_id,
    )
    db.add(template)
    save(db)
    return _out(template)


def edit(db: Session, user: User, template_id: UUID, data: TemplateUpdate) -> TemplateOut:
    template = template_for(db, user.org_id, template_id)
    fields = data.model_fields_set
    if "name" in fields and data.name is not None:
        template.name = data.name
    if "header" in fields and data.header is not None:
        template.header = data.header.model_dump(mode="json")
    if "logo_asset_id" in fields:
        _check_logo(db, user.org_id, data.logo_asset_id)
        template.logo_asset_id = data.logo_asset_id
    save(db)
    return _out(template)


def delete(db: Session, user: User, template_id: UUID) -> None:
    db.delete(template_for(db, user.org_id, template_id))
    save(db)
