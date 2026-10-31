from uuid import UUID

from fastapi import APIRouter, Query

from qbank.api.deps import DB, Admin
from qbank.models import User
from qbank.schemas.common import Page
from qbank.schemas.users import UserCreate, UserOut, UserUpdate
from qbank.services import users as service

router = APIRouter(prefix="/api/v1")


@router.get("/users", response_model=Page[UserOut])
def users(
    db: DB, user: Admin, cursor: str | None = None, limit: int = Query(50, ge=1, le=100)
) -> dict[str, object]:
    return service.users(db=db, org_id=user.org_id, cursor=cursor, limit=limit)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: DB, user: Admin) -> User:
    return service.create_user(data=data, db=db, org_id=user.org_id)


@router.patch("/users/{id}", response_model=UserOut)
def edit_user(id: UUID, data: UserUpdate, db: DB, user: Admin) -> User:
    return service.edit_user(id=id, data=data, db=db, org_id=user.org_id, actor_id=user.id)
