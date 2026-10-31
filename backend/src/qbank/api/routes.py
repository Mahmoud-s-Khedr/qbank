from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qbank.api.deps import current_user, error, require_role
from qbank.api.pagination import paginate
from qbank.auth import create_token, hasher, verify_password
from qbank.config import get_settings
from qbank.db import get_db
from qbank.models import Chapter, Language, Lesson, Role, Subject, User
from qbank.services.core import ensure_deletable_chapter, ensure_deletable_subject, get, scoped

router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_db)]
Current = Annotated[User, Depends(current_user)]
Admin = Annotated[User, Depends(require_role(Role.admin))]
Writer = Annotated[User, Depends(require_role(Role.admin, Role.editor))]


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class UserOut(Output):
    org_id: UUID
    email: str
    name: str
    role: Role
    is_active: bool
    last_login_at: datetime | None


class Login(BaseModel):
    email: str
    password: str


class UserCreate(Login):
    name: str
    role: Role


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    is_active: bool | None = None


class SubjectIn(BaseModel):
    name: str
    language: Language
    grade: str | None = None


class SubjectUpdate(BaseModel):
    name: str | None = None
    language: Language | None = None
    grade: str | None = None


class SubjectOut(Output, SubjectIn):
    org_id: UUID


class ItemIn(BaseModel):
    title: str


class ItemUpdate(BaseModel):
    title: str | None = None
    position: int | None = None


class LessonUpdate(ItemUpdate):
    chapter_id: UUID | None = None


class ChapterOut(Output):
    subject_id: UUID
    title: str
    position: int


class LessonOut(Output):
    chapter_id: UUID
    title: str
    position: int


class ChapterTree(ChapterOut):
    lessons: list[LessonOut]


class SubjectTree(SubjectOut):
    chapters: list[ChapterTree]


class Reorder(BaseModel):
    ids: list[UUID]


T = TypeVar("T")


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


def save(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise error(409, "conflict") from None


def found[T](value: T | None) -> T:
    if value is None:
        raise error(404, "not_found")
    return value


def update(obj: object, values: BaseModel) -> None:
    for key, value in values.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)


@router.post("/auth/login", response_model=UserOut)
def login(data: Login, response: Response, db: DB) -> User:
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if user is None or not verify_password(data.password, user.password_hash) or not user.is_active:
        raise error(401, "invalid_credentials")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(data.password)
    user.last_login_at = datetime.now(UTC)
    save(db)
    settings = get_settings()
    response.set_cookie(
        "qbank_session",
        create_token(user),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "qbank_csrf",
        token_urlsafe(32),
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie("qbank_session", path="/")
    response.delete_cookie("qbank_csrf", path="/")


@router.get("/auth/me", response_model=UserOut)
def me(user: Current) -> User:
    return user


@router.get("/users", response_model=Page[UserOut])
def users(
    db: DB, user: Admin, cursor: str | None = None, limit: int = Query(50, ge=1, le=100)
) -> dict[str, object]:
    try:
        items, next_cursor = paginate(
            db, scoped(select(User), User, user.org_id), User, cursor, limit
        )
    except ValueError:
        raise error(422, "invalid_cursor") from None
    return {"items": items, "next_cursor": next_cursor}


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: DB, user: Admin) -> User:
    item = User(
        org_id=user.org_id,
        email=data.email,
        name=data.name,
        role=data.role,
        password_hash=hasher.hash(data.password),
    )
    db.add(item)
    save(db)
    return item


@router.patch("/users/{id}", response_model=UserOut)
def edit_user(id: UUID, data: UserUpdate, db: DB, user: Admin) -> User:
    item = found(get(db, User, user.org_id, id))
    if id == user.id and (
        data.is_active is False or (data.role is not None and data.role != Role.admin)
    ):
        raise error(422, "self_change_forbidden")
    update(item, data)
    save(db)
    return item


@router.get("/subjects", response_model=Page[SubjectOut])
def subjects(
    db: DB, user: Current, cursor: str | None = None, limit: int = Query(50, ge=1, le=100)
) -> dict[str, object]:
    try:
        items, next_cursor = paginate(
            db, scoped(select(Subject), Subject, user.org_id), Subject, cursor, limit
        )
    except ValueError:
        raise error(422, "invalid_cursor") from None
    return {"items": items, "next_cursor": next_cursor}


@router.post("/subjects", response_model=SubjectOut, status_code=201)
def create_subject(data: SubjectIn, db: DB, user: Writer) -> Subject:
    item = Subject(org_id=user.org_id, **data.model_dump())
    db.add(item)
    save(db)
    return item


@router.get("/subjects/{id}", response_model=SubjectOut)
def subject(id: UUID, db: DB, user: Current) -> Subject:
    return found(get(db, Subject, user.org_id, id))


@router.patch("/subjects/{id}", response_model=SubjectOut)
def edit_subject(id: UUID, data: SubjectUpdate, db: DB, user: Writer) -> Subject:
    item = found(get(db, Subject, user.org_id, id))
    update(item, data)
    save(db)
    return item


@router.delete("/subjects/{id}", status_code=204)
def delete_subject(id: UUID, db: DB, user: Writer) -> None:
    item = found(get(db, Subject, user.org_id, id))
    if not ensure_deletable_subject(db, user.org_id, id):
        raise error(409, "not_empty")
    db.delete(item)
    save(db)


@router.get("/subjects/{id}/tree", response_model=SubjectTree)
def tree(id: UUID, db: DB, user: Current) -> dict[str, object]:
    item = found(get(db, Subject, user.org_id, id))
    chapters = db.scalars(
        scoped(select(Chapter), Chapter, user.org_id)
        .where(Chapter.subject_id == id)
        .order_by(Chapter.position, Chapter.id)
    ).all()
    result = []
    for chapter in chapters:
        lessons = db.scalars(
            scoped(select(Lesson), Lesson, user.org_id)
            .where(Lesson.chapter_id == chapter.id)
            .order_by(Lesson.position, Lesson.id)
        ).all()
        result.append({**ChapterOut.model_validate(chapter).model_dump(), "lessons": lessons})
    return {**SubjectOut.model_validate(item).model_dump(), "chapters": result}


def next_position(db: Session, model: type[Chapter] | type[Lesson], parent_id: UUID) -> int:
    field = Chapter.subject_id if model is Chapter else Lesson.chapter_id
    return (db.scalar(select(func.max(model.position)).where(field == parent_id)) or 0) + 1


@router.post("/subjects/{id}/chapters", response_model=ChapterOut, status_code=201)
def create_chapter(id: UUID, data: ItemIn, db: DB, user: Writer) -> Chapter:
    found(get(db, Subject, user.org_id, id))
    item = Chapter(subject_id=id, title=data.title, position=next_position(db, Chapter, id))
    db.add(item)
    save(db)
    return item


@router.patch("/chapters/{id}", response_model=ChapterOut)
def edit_chapter(id: UUID, data: ItemUpdate, db: DB, user: Writer) -> Chapter:
    item = found(get(db, Chapter, user.org_id, id))
    update(item, data)
    save(db)
    return item


@router.delete("/chapters/{id}", status_code=204)
def delete_chapter(id: UUID, db: DB, user: Writer) -> None:
    item = found(get(db, Chapter, user.org_id, id))
    if not ensure_deletable_chapter(db, user.org_id, id):
        raise error(409, "not_empty")
    db.delete(item)
    save(db)


@router.post("/chapters/{id}/lessons", response_model=LessonOut, status_code=201)
def create_lesson(id: UUID, data: ItemIn, db: DB, user: Writer) -> Lesson:
    found(get(db, Chapter, user.org_id, id))
    item = Lesson(chapter_id=id, title=data.title, position=next_position(db, Lesson, id))
    db.add(item)
    save(db)
    return item


@router.patch("/lessons/{id}", response_model=LessonOut)
def edit_lesson(id: UUID, data: LessonUpdate, db: DB, user: Writer) -> Lesson:
    item = found(get(db, Lesson, user.org_id, id))
    if data.chapter_id is not None and data.chapter_id != item.chapter_id:
        target = found(get(db, Chapter, user.org_id, data.chapter_id))
        source = found(get(db, Chapter, user.org_id, item.chapter_id))
        if source.subject_id != target.subject_id:
            raise error(422, "invalid_move")
        data.position = next_position(db, Lesson, target.id)
    update(item, data)
    save(db)
    return item


@router.delete("/lessons/{id}", status_code=204)
def delete_lesson(id: UUID, db: DB, user: Writer) -> None:
    item = found(get(db, Lesson, user.org_id, id))
    db.delete(item)
    save(db)


@router.post("/subjects/{id}/chapters/reorder", status_code=204)
def reorder_chapters(id: UUID, data: Reorder, db: DB, user: Writer) -> None:
    found(get(db, Subject, user.org_id, id))
    items = list(
        db.scalars(scoped(select(Chapter), Chapter, user.org_id).where(Chapter.subject_id == id))
    )
    if len(data.ids) != len(items) or set(data.ids) != {item.id for item in items}:
        raise error(422, "invalid_order")
    positions = {item_id: pos for pos, item_id in enumerate(data.ids, 1)}
    for item in items:
        item.position = positions[item.id]
    save(db)


@router.post("/chapters/{id}/lessons/reorder", status_code=204)
def reorder_lessons(id: UUID, data: Reorder, db: DB, user: Writer) -> None:
    found(get(db, Chapter, user.org_id, id))
    items = list(
        db.scalars(scoped(select(Lesson), Lesson, user.org_id).where(Lesson.chapter_id == id))
    )
    if len(data.ids) != len(items) or set(data.ids) != {item.id for item in items}:
        raise error(422, "invalid_order")
    positions = {item_id: pos for pos, item_id in enumerate(data.ids, 1)}
    for item in items:
        item.position = positions[item.id]
    save(db)
