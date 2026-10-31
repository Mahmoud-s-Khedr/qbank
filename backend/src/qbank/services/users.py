from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.api.pagination import paginate
from qbank.auth import hasher
from qbank.models import Role, User
from qbank.schemas.users import UserCreate, UserUpdate
from qbank.services.errors import Invalid
from qbank.services.scoping import get, scoped
from qbank.services.unit_of_work import found, save, update


def users(
    db: Session, org_id: UUID, cursor: str | None = None, limit: int = 50
) -> dict[str, object]:
    try:
        items, next_cursor = paginate(db, scoped(select(User), User, org_id), User, cursor, limit)
    except ValueError:
        raise Invalid("invalid_cursor") from None
    return {"items": items, "next_cursor": next_cursor}


def create_user(data: UserCreate, db: Session, org_id: UUID) -> User:
    item = User(
        org_id=org_id,
        email=data.email,
        name=data.name,
        role=data.role,
        password_hash=hasher.hash(data.password),
    )
    db.add(item)
    save(db)
    return item


def edit_user(id: UUID, data: UserUpdate, db: Session, org_id: UUID, actor_id: UUID) -> User:
    item = found(get(db, User, org_id, id))
    if id == actor_id and (
        data.is_active is False or (data.role is not None and data.role != Role.admin)
    ):
        raise Invalid("self_change_forbidden")
    update(item, data)
    save(db)
    return item
