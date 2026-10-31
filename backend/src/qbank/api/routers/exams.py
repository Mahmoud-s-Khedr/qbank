from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from qbank.api.deps import DB, Current
from qbank.schemas.common import Page
from qbank.schemas.exams import (
    AnswerKey,
    Blueprint,
    BlueprintResult,
    ComposeIn,
    ExamDetail,
    ExamIn,
    ExamProposalOut,
    ExamSummary,
    ExamUpdate,
    ItemsIn,
    ItemUpdate,
    ProposalApply,
    ReorderItems,
    ReorderSections,
    SectionIn,
    SectionUpdate,
    VersionOut,
    VersionsIn,
)
from qbank.security.ratelimit import user_limit
from qbank.services import compose_ai
from qbank.services import exam_generation as generation
from qbank.services import exams as service

router = APIRouter(prefix="/api/v1", tags=["exams"])


@router.post("/exams", response_model=ExamDetail, status_code=201)
def create_exam(data: ExamIn, db: DB, user: Current) -> ExamDetail:
    return service.create(db, user, data)


@router.get("/exams", response_model=Page[ExamSummary])
def list_exams(
    db: DB,
    user: Current,
    status: Literal["draft", "final", "archived"] | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, object]:
    return service.listing(db, user, status, cursor, limit)


@router.get("/exams/{id}", response_model=ExamDetail)
def get_exam(id: UUID, db: DB, user: Current) -> ExamDetail:
    return service.get_detail(db, user, id)


@router.patch("/exams/{id}", response_model=ExamDetail)
def edit_exam(id: UUID, data: ExamUpdate, db: DB, user: Current) -> ExamDetail:
    return service.edit(db, user, id, data)


@router.delete("/exams/{id}", status_code=204)
def delete_exam(id: UUID, db: DB, user: Current) -> None:
    service.delete(db, user, id)


@router.post("/exams/{id}/duplicate", response_model=ExamDetail, status_code=201)
def duplicate_exam(id: UUID, db: DB, user: Current) -> ExamDetail:
    return service.duplicate(db, user, id)


@router.post("/exams/{id}/archive", response_model=ExamDetail)
def archive_exam(id: UUID, db: DB, user: Current) -> ExamDetail:
    return service.archive(db, user, id)


@router.post("/exams/{id}/sections", response_model=ExamDetail, status_code=201)
def add_section(id: UUID, data: SectionIn, db: DB, user: Current) -> ExamDetail:
    return service.add_section(db, user, id, data)


@router.post("/exams/{id}/sections/reorder", response_model=ExamDetail)
def reorder_sections(id: UUID, data: ReorderSections, db: DB, user: Current) -> ExamDetail:
    return service.reorder_sections(db, user, id, data)


@router.patch("/exam-sections/{id}", response_model=ExamDetail)
def edit_section(id: UUID, data: SectionUpdate, db: DB, user: Current) -> ExamDetail:
    return service.edit_section(db, user, id, data)


@router.delete("/exam-sections/{id}", response_model=ExamDetail)
def delete_section(id: UUID, db: DB, user: Current) -> ExamDetail:
    return service.delete_section(db, user, id)


@router.post("/exams/{id}/items", response_model=ExamDetail, status_code=201)
def add_items(id: UUID, data: ItemsIn, db: DB, user: Current) -> ExamDetail:
    return service.add_items(db, user, id, data)


@router.post("/exams/{id}/items/reorder", response_model=ExamDetail)
def reorder_items(id: UUID, data: ReorderItems, db: DB, user: Current) -> ExamDetail:
    return service.reorder_items(db, user, id, data)


@router.patch("/exam-items/{id}", response_model=ExamDetail)
def edit_item(id: UUID, data: ItemUpdate, db: DB, user: Current) -> ExamDetail:
    return service.edit_item(db, user, id, data)


@router.delete("/exam-items/{id}", response_model=ExamDetail)
def delete_item(id: UUID, db: DB, user: Current, group: bool = False) -> ExamDetail:
    return service.delete_item(db, user, id, group)


@router.post("/exams/{id}/blueprint/preview", response_model=BlueprintResult)
def blueprint_preview(id: UUID, data: Blueprint, db: DB, user: Current) -> BlueprintResult:
    return generation.blueprint_preview(db, user, id, data)


@router.post("/exams/{id}/blueprint/apply", response_model=ExamDetail)
def blueprint_apply(id: UUID, data: Blueprint, db: DB, user: Current) -> ExamDetail:
    return generation.blueprint_apply(db, user, id, data)


@router.post("/exams/{id}/versions", response_model=list[VersionOut], status_code=201)
def generate_versions(id: UUID, data: VersionsIn, db: DB, user: Current) -> list[VersionOut]:
    return generation.generate_versions(db, user, id, data)


@router.get("/exams/{id}/versions/{label}/answer-key", response_model=AnswerKey)
def answer_key(id: UUID, label: str, db: DB, user: Current) -> AnswerKey:
    return generation.answer_key(db, user, id, label)


@router.post("/exams/{id}/compose", response_model=ExamProposalOut)
def compose_exam(id: UUID, data: ComposeIn, db: DB, user: Current) -> ExamProposalOut:
    user_limit("ai", user.id)
    return compose_ai.compose(db, user, id, data)


@router.get("/exams/{id}/proposals", response_model=list[ExamProposalOut])
def list_proposals(id: UUID, db: DB, user: Current) -> list[ExamProposalOut]:
    return compose_ai.listing(db, user, id)


@router.post("/exam-proposals/{id}/apply", response_model=ExamDetail)
def apply_proposal(id: UUID, data: ProposalApply, db: DB, user: Current) -> ExamDetail:
    return compose_ai.apply(db, user, id, data)


@router.post("/exam-proposals/{id}/discard", response_model=ExamProposalOut)
def discard_proposal(id: UUID, db: DB, user: Current) -> ExamProposalOut:
    return compose_ai.discard(db, user, id)
