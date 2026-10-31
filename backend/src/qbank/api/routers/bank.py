from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request

from qbank.api.deps import DB, Current, Writer
from qbank.schemas.bank import (
    BankSearchOut,
    BankStatsOut,
    QuestionsMove,
    QuestionsMoveOut,
    TagCount,
)
from qbank.services import bank as service
from qbank.services.errors import Invalid

router = APIRouter(prefix="/api/v1", tags=["bank"])


def _resolve_uuid_list(
    request: Request, values: list[UUID] | None, bracket_key: str
) -> list[UUID] | None:
    if values is not None:
        return values
    raw = request.query_params.getlist(bracket_key)
    if not raw:
        return None
    try:
        return [UUID(v) for v in raw]
    except ValueError as exc:
        raise Invalid("validation_error") from exc


def _resolve_str_list(
    request: Request, values: list[str] | None, bracket_key: str
) -> list[str] | None:
    if values is not None:
        return values
    raw = request.query_params.getlist(bracket_key)
    return raw if raw else None


@router.get("/bank/questions", response_model=BankSearchOut)
def search_questions(  # noqa: PLR0913, PLR0917 -- query parameters for bank search
    request: Request,
    db: DB,
    user: Current,
    q: str | None = None,
    subject_id: UUID | None = None,
    chapter_ids: Annotated[list[UUID] | None, Query()] = None,
    lesson_ids: Annotated[list[UUID] | None, Query()] = None,
    types: Annotated[list[str] | None, Query()] = None,
    difficulty_min: Annotated[int | None, Query(ge=1, le=5)] = None,
    difficulty_max: Annotated[int | None, Query(ge=1, le=5)] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    source_ids: Annotated[list[UUID] | None, Query()] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    has_figure: bool | None = None,
    has_answer: bool | None = None,
    exam_title: str | None = None,
    exclude_duplicates: bool = True,
    facets: bool = False,
    sort: Literal["relevance", "newest", "difficulty", "source_order"] | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> BankSearchOut:
    return service.search_questions(
        db=db,
        org_id=user.org_id,
        role=user.role,
        q=q,
        subject_id=subject_id,
        chapter_ids=_resolve_uuid_list(request, chapter_ids, "chapter_ids[]"),
        lesson_ids=_resolve_uuid_list(request, lesson_ids, "lesson_ids[]"),
        types=_resolve_str_list(request, types, "types[]"),
        difficulty_min=difficulty_min,
        difficulty_max=difficulty_max,
        statuses=_resolve_str_list(request, statuses, "statuses[]"),
        source_ids=_resolve_uuid_list(request, source_ids, "source_ids[]"),
        tags=_resolve_str_list(request, tags, "tags[]"),
        has_figure=has_figure,
        has_answer=has_answer,
        exam_title=exam_title,
        exclude_duplicates=exclude_duplicates,
        facets=facets,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )


@router.get("/bank/tags", response_model=list[TagCount])
def autocomplete_tags(
    db: DB,
    user: Current,
    subject_id: UUID | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> list[TagCount]:
    return service.autocomplete_tags(
        db=db,
        org_id=user.org_id,
        role=user.role,
        subject_id=subject_id,
        q=q,
        limit=limit,
    )


@router.get("/bank/stats", response_model=BankStatsOut)
def bank_stats(
    db: DB,
    user: Current,
    subject_id: UUID | None = None,
) -> BankStatsOut:
    return service.bank_stats(
        db=db,
        org_id=user.org_id,
        role=user.role,
        subject_id=subject_id,
    )


@router.post("/questions/move", response_model=QuestionsMoveOut)
def move_questions(
    data: QuestionsMove,
    db: DB,
    user: Writer,
) -> QuestionsMoveOut:
    return service.move_questions(db=db, org_id=user.org_id, data=data)
