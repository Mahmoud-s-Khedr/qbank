"""Review endpoints: question editing, audit, figures, stimuli, re-extraction, review queue."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from qbank.api.deps import DB, Current, Writer
from qbank.llm import LLMClient
from qbank.models import Question, Stimulus, ValidationIssue
from qbank.schemas.bank import QuestionOut, StimulusOut, ValidationIssueOut
from qbank.schemas.review import (
    AcceptIn,
    AcceptOut,
    ApproveIn,
    AssetOut,
    BulkIn,
    BulkOut,
    DraftQuestion,
    ExtractRegionIn,
    FigureIn,
    MergeIn,
    PageProposalOut,
    ProposalDetail,
    QuestionCreate,
    QuestionEventOut,
    QuestionPatch,
    ReextractIn,
    ReextractOut,
    Region,
    RejectIn,
    ReopenIn,
    ReviewQueue,
    SplitIn,
    SplitOut,
    StimulusCreate,
    StimulusPatch,
)
from qbank.services import figures, proposals, stimuli
from qbank.services import review as service

router = APIRouter(prefix="/api/v1", tags=["review"])
Client = Annotated[LLMClient, Depends(proposals.get_client)]
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"description": "version_conflict (body carries `current`) or invalid state"}
}


# --- questions --------------------------------------------------------------------------------


@router.post("/questions", response_model=QuestionOut, status_code=201)
def create_question(data: QuestionCreate, db: DB, user: Writer) -> Question:
    return service.create(db, user, data)


@router.post("/questions/bulk", response_model=BulkOut)
def bulk(data: BulkIn, db: DB, user: Writer) -> BulkOut:
    return service.bulk(db, user, data)


@router.post("/questions/merge", response_model=QuestionOut)
def merge(data: MergeIn, db: DB, user: Writer) -> Question:
    return service.merge(db, user, data.ids)


@router.patch("/questions/{id}", response_model=QuestionOut, responses=CONFLICT)
def patch_question(id: UUID, data: QuestionPatch, db: DB, user: Writer) -> Question:
    return service.patch(db, user, id, data)


@router.delete("/questions/{id}", status_code=204)
def delete_question(id: UUID, db: DB, user: Writer) -> None:
    service.delete_question(db, user, id)


@router.post("/questions/{id}/approve", response_model=QuestionOut, responses=CONFLICT)
def approve(id: UUID, db: DB, user: Writer, data: ApproveIn | None = None) -> Question:
    return service.change_status(db, user, id, "approve", data or ApproveIn())


@router.post("/questions/{id}/reject", response_model=QuestionOut, responses=CONFLICT)
def reject(id: UUID, db: DB, user: Writer, data: RejectIn | None = None) -> Question:
    return service.change_status(db, user, id, "reject", data or RejectIn())


@router.post("/questions/{id}/reopen", response_model=QuestionOut, responses=CONFLICT)
def reopen(id: UUID, db: DB, user: Writer, data: ReopenIn | None = None) -> Question:
    return service.change_status(db, user, id, "reopen", data or ReopenIn())


@router.post("/questions/{id}/split", response_model=SplitOut)
def split(id: UUID, data: SplitIn, db: DB, user: Writer) -> SplitOut:
    first, second = service.split(db, user, id, data)
    return SplitOut(
        first=QuestionOut.model_validate(first), second=QuestionOut.model_validate(second)
    )


@router.get("/questions/{id}/history", response_model=list[QuestionEventOut])
def history(id: UUID, db: DB, user: Current) -> list[QuestionEventOut]:
    return [QuestionEventOut.model_validate(e) for e in service.history(db, user, id)]


@router.post("/issues/{id}/resolve", response_model=ValidationIssueOut)
def resolve_issue(id: UUID, db: DB, user: Writer) -> ValidationIssue:
    return service.set_issue_resolved(db, user, id, resolved=True)


@router.post("/issues/{id}/unresolve", response_model=ValidationIssueOut)
def unresolve_issue(id: UUID, db: DB, user: Writer) -> ValidationIssue:
    return service.set_issue_resolved(db, user, id, resolved=False)


# --- figures and regions ----------------------------------------------------------------------


@router.post("/questions/{id}/figures", response_model=AssetOut, status_code=201)
def add_figure(id: UUID, data: FigureIn, db: DB, user: Writer) -> AssetOut:
    return AssetOut.model_validate(figures.add_figure(db, user, id, data))


@router.delete("/questions/{id}/figures/{asset_id}", status_code=204)
def delete_figure(id: UUID, asset_id: UUID, db: DB, user: Writer) -> None:
    figures.delete_figure(db, user, id, asset_id)


@router.get("/assets/{id}", response_model=AssetOut)
def get_asset(id: UUID, db: DB, user: Current) -> AssetOut:
    return AssetOut.model_validate(figures.get_asset(db, user.org_id, id))


@router.put("/assets/{id}/region", response_model=AssetOut)
def recrop(id: UUID, data: Region, db: DB, user: Writer) -> AssetOut:
    return AssetOut.model_validate(figures.recrop(db, user, id, data.box))


# --- stimuli ----------------------------------------------------------------------------------


@router.post("/stimuli", response_model=StimulusOut, status_code=201)
def create_stimulus(data: StimulusCreate, db: DB, user: Writer) -> Stimulus:
    return stimuli.create(db, user, data)


@router.patch("/stimuli/{id}", response_model=StimulusOut)
def patch_stimulus(id: UUID, data: StimulusPatch, db: DB, user: Writer) -> Stimulus:
    return stimuli.patch(db, user, id, data)


@router.delete("/stimuli/{id}", status_code=204)
def delete_stimulus(id: UUID, db: DB, user: Writer) -> None:
    stimuli.delete(db, user, id)


@router.post("/stimuli/{id}/approve", response_model=StimulusOut)
def approve_stimulus(id: UUID, db: DB, user: Writer) -> Stimulus:
    return stimuli.set_status(db, user, id, "approved")


@router.post("/stimuli/{id}/reject", response_model=StimulusOut)
def reject_stimulus(id: UUID, db: DB, user: Writer) -> Stimulus:
    return stimuli.set_status(db, user, id, "rejected")


# --- re-extraction ----------------------------------------------------------------------------


@router.post("/sources/{id}/pages/{number}/reextract", response_model=ReextractOut, status_code=202)
def reextract(
    id: UUID, number: int, db: DB, user: Writer, data: ReextractIn | None = None
) -> ReextractOut:
    model = data.model if data else None
    return ReextractOut(job_id=proposals.start_reextract(db, user, id, number, model))


@router.post("/sources/{id}/pages/{number}/extract-region", response_model=DraftQuestion)
def extract_region(  # noqa: PLR0913, PLR0917 -- path, body and injected dependencies
    id: UUID, number: int, data: ExtractRegionIn, db: DB, user: Writer, client: Client
) -> DraftQuestion:
    return proposals.extract_region(db, client, user, id, number, data)


@router.get("/page-proposals/{id}", response_model=ProposalDetail)
def proposal_detail(id: UUID, db: DB, user: Writer) -> ProposalDetail:
    return proposals.detail(db, user, id)


@router.post("/page-proposals/{id}/accept", response_model=AcceptOut)
def accept_proposal(id: UUID, db: DB, user: Writer, data: AcceptIn | None = None) -> AcceptOut:
    return proposals.accept(db, user, id, data or AcceptIn())


@router.post("/page-proposals/{id}/discard", response_model=PageProposalOut)
def discard_proposal(id: UUID, db: DB, user: Writer) -> PageProposalOut:
    return proposals.discard(db, user, id)


# --- review queue -----------------------------------------------------------------------------


@router.get("/sources/{id}/review-queue", response_model=ReviewQueue)
def review_queue(  # noqa: PLR0913, PLR0917 -- independent query filters
    id: UUID,
    db: DB,
    user: Current,
    status: str | None = None,
    severity: Literal["error", "warning"] | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    sort: Literal["page", "severity", "confidence"] = "page",
) -> ReviewQueue:
    return service.review_queue(db, user, id, status, severity, page, sort)
