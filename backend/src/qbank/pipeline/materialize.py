"""Stitch extracted pages and persist draft items and figure crops."""

import re
from dataclasses import dataclass, field
from io import BytesIO
from uuid import UUID

import cv2
import numpy as np
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from qbank.db import new_uuid
from qbank.models import Asset, Question, Source, SourcePage, Stimulus, Subject
from qbank.pipeline.schema import PageExtraction, to_region_box
from qbank.pipeline.schema import Question as ExtractedQuestion
from qbank.pipeline.schema import Stimulus as ExtractedStimulus
from qbank.storage import get_store, keys
from qbank.text.normalize import content_hash, question_normalized_text

WHITE_THRESHOLD = 245
PINNED = ("جميع ما سبق", "كل ما سبق", "لا شيء مما سبق", "all of the above", "none of the above")


# Fill-in placeholders printed as runs of dots/ellipses/underscores become the QMD blank `____`.
# Done deterministically here because models often copy the dots verbatim (seen in live runs).
BLANK_RUN = re.compile(r"\.(?:\s?\.){3,}|…(?:\s?…)+|_{4,}")


def normalize_blanks(text: str) -> str:
    return BLANK_RUN.sub("____", text)


def pinned(content: str) -> bool:
    return any(pattern in content.casefold() for pattern in PINNED)


@dataclass
class Item:
    value: ExtractedQuestion | ExtractedStimulus
    pages: list[SourcePage]
    regions: list[dict[str, object]]
    refs: list[tuple[int, str]] = field(default_factory=list)
    figures: list[tuple[SourcePage, tuple[int, int, int, int]]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def stitch(  # noqa: PLR0912 -- both item types share continuation handling.
    pages: list[SourcePage],
) -> tuple[list[Item], list[Item]]:
    stimuli: list[Item] = []
    questions: list[Item] = []
    previous_stimulus: Item | None = None
    previous_question: Item | None = None
    for page in pages:
        if page.extraction is None:
            continue
        extraction = PageExtraction.model_validate(page.extraction)
        if extraction.page_kind not in ("questions", "answer_key"):
            continue
        for kind, values, output in (
            ("stimulus", extraction.stimuli, stimuli),
            ("question", extraction.questions, questions),
        ):
            previous = previous_stimulus if kind == "stimulus" else previous_question
            matched = False
            first_continuation = next(
                (
                    index
                    for index, value in enumerate(values)
                    if isinstance(value, ExtractedQuestion | ExtractedStimulus)
                    and value.continues_from_previous
                ),
                None,
            )
            for index, value in enumerate(values):
                if not isinstance(value, ExtractedQuestion | ExtractedStimulus):
                    raise TypeError("Unexpected extracted item")
                region: dict[str, object] = {
                    "page": str(page.id),
                    "box": to_region_box(value.box_2d),
                }
                can_merge = (
                    index == first_continuation
                    and previous is not None
                    and previous.pages[-1].page_number + 1 == page.page_number
                    and previous.value.continues_on_next
                    and value.continues_from_previous
                )
                if can_merge and previous is not None:
                    item = previous
                    matched = True
                    if isinstance(item.value, ExtractedQuestion) and isinstance(
                        value, ExtractedQuestion
                    ):
                        item.value.stem += "\n" + value.stem
                        item.value.choices.extend(value.choices)
                        if item.value.answer is None:
                            item.value.answer = value.answer
                        item.value.continues_on_next = value.continues_on_next
                    elif isinstance(item.value, ExtractedStimulus) and isinstance(
                        value, ExtractedStimulus
                    ):
                        item.value.content += "\n" + value.content
                        item.value.continues_on_next = value.continues_on_next
                    item.pages.append(page)
                    item.regions.append(region)
                else:
                    item = Item(value=value.model_copy(deep=True), pages=[page], regions=[region])
                    if value.continues_from_previous:
                        item.notes.append("Unmatched continuation from previous page")
                    output.append(item)
                if isinstance(value, ExtractedStimulus):
                    item.refs.append((page.page_number, value.ref))
                    if value.kind == "figure":
                        item.figures.append((page, value.box_2d))
                elif isinstance(value, ExtractedQuestion):
                    item.figures.extend((page, figure.box_2d) for figure in value.figures)
            if previous is not None and previous.value.continues_on_next and not matched:
                previous.notes.append("Unmatched continuation on next page")
            if kind == "stimulus":
                previous_stimulus = stimuli[-1] if values else None
            else:
                previous_question = questions[-1] if values else None
    for item in [*stimuli, *questions]:
        if item.value.continues_on_next:
            item.notes.append("Unmatched continuation on next page")
    return stimuli, questions


def render_crop(
    source: Source,
    page: SourcePage,
    region: list[float],
    *,
    trim: bool = True,
    image_format: str = "WEBP",
) -> tuple[bytes, int, int]:
    """Crop a normalized x0,y0,x1,y1 region from the hires page; returns bytes, width, height."""
    data = get_store().get_bytes(keys.page(source.org_id, source.id, page.page_number, hires=True))
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
        x0, y0, x1, y1 = region
        left, top = max(0, int((x0 - 0.01) * width)), max(0, int((y0 - 0.01) * height))
        right, bottom = min(width, int((x1 + 0.01) * width)), min(height, int((y1 + 0.01) * height))
        if right <= left or bottom <= top:
            raise ValueError("Empty figure region")
        pixels = np.array(image.convert("RGB").crop((left, top, right, bottom)))
    if trim:
        gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
        points = cv2.findNonZero((gray < WHITE_THRESHOLD).astype("uint8"))
        if points is not None:
            x, y, w, h = cv2.boundingRect(points)
            pad = max(1, round(min(pixels.shape[:2]) * 0.01))
            pixels = pixels[max(0, y - pad) : y + h + pad, max(0, x - pad) : x + w + pad]
    output = BytesIO()
    Image.fromarray(pixels).save(output, format=image_format)
    return output.getvalue(), pixels.shape[1], pixels.shape[0]


def crop_region(
    db: Session,
    source: Source,
    page: SourcePage,
    region: list[float],
    *,
    pipeline_generated: bool = True,
) -> Asset:
    """Crop a region into a new figure asset (added to the session)."""
    data, width, height = render_crop(source, page, region)
    asset_id = new_uuid()
    key = keys.prefix(source.org_id, source.id) + f"assets/{asset_id}.webp"
    get_store().put_bytes(key, data, "image/webp")
    asset = Asset(
        id=asset_id,
        org_id=source.org_id,
        source_page_id=page.id,
        kind="figure",
        image_key=key,
        pipeline_generated=pipeline_generated,
        region=region,
        width=width,
        height=height,
    )
    db.add(asset)
    return asset


def crop(db: Session, source: Source, page: SourcePage, box: tuple[int, int, int, int]) -> str:
    asset = crop_region(db, source, page, to_region_box(box))
    return f"![](asset:{asset.id})"


def _purge_drafts(
    db: Session, source: Source, pages: list[SourcePage]
) -> tuple[list[str], dict[UUID, str | None]]:
    reviewed = list(
        db.scalars(
            select(Question).where(
                Question.source_id == source.id, Question.status.in_(["approved", "rejected"])
            )
        )
    )
    protected = {question.stimulus_id for question in reviewed if question.stimulus_id}
    reviewed_stimuli = list(
        db.scalars(
            select(Stimulus).where(
                Stimulus.source_id == source.id,
                (Stimulus.status.in_(["approved", "rejected"]) | Stimulus.id.in_(protected)),
            )
        )
    )
    protected.update(item.id for item in reviewed_stimuli)
    text = " ".join(
        [q.stem + str(q.choices) for q in reviewed] + [s.content for s in reviewed_stimuli]
    )
    protected_assets = set(re.findall(r"asset:([0-9a-f-]{36})", text))
    assets = list(
        db.scalars(
            select(Asset).where(
                Asset.source_page_id.in_([p.id for p in pages]), Asset.pipeline_generated.is_(True)
            )
        )
    )
    old_keys: list[str] = []
    for asset in assets:
        if str(asset.id) not in protected_assets:
            old_keys.append(asset.image_key)
            db.delete(asset)
    db.execute(
        delete(Question).where(
            Question.source_id == source.id, Question.status.in_(["draft", "needs_review"])
        )
    )
    stmt = delete(Stimulus).where(
        Stimulus.source_id == source.id, Stimulus.status.in_(["draft", "needs_review"])
    )
    if protected:
        stmt = stmt.where(Stimulus.id.not_in(protected))
    db.execute(stmt)
    db.flush()
    intros: dict[UUID, str | None] = {
        s.id: str(s.metadata_json.get("intro")) if s.metadata_json.get("intro") else None
        for s in reviewed_stimuli
    }
    return old_keys, intros


def materialize(db: Session, source: Source) -> list[str]:
    pages = list(
        db.scalars(
            select(SourcePage)
            .where(SourcePage.source_id == source.id)
            .order_by(SourcePage.page_number)
        )
    )
    stimuli, questions = stitch(pages)
    old_keys, intros = _purge_drafts(db, source, pages)
    subject = db.get(Subject, source.subject_id)
    if subject is None:
        raise ValueError("Missing subject")
    refs: dict[tuple[int, str], UUID] = {}
    positions: dict[UUID, int] = {}
    for item in stimuli:
        if not isinstance(item.value, ExtractedStimulus):
            raise TypeError("Expected stimulus")
        content = item.value.content
        for page, box in item.figures:
            content += "\n" + crop(db, source, page, box)
        sid = new_uuid()
        for ref in item.refs:
            refs[ref] = sid
        intros[sid] = item.value.intro
        db.add(
            Stimulus(
                id=sid,
                org_id=source.org_id,
                source_id=source.id,
                kind=item.value.kind,
                content=normalize_blanks(content),
                regions=item.regions,
                status="draft",
                metadata_json={"notes": item.notes, "intro": item.value.intro},
            )
        )
    db.flush()
    for position, item in enumerate(questions):
        q = item.value
        if not isinstance(q, ExtractedQuestion):
            raise TypeError("Expected question")
        stem = normalize_blanks(q.stem)
        for page, box in item.figures:
            stem += "\n" + crop(db, source, page, box)
        stimulus_id = None
        if q.stimulus_ref:
            candidates = [
                (number, ref_id)
                for (number, ref), ref_id in refs.items()
                if ref == q.stimulus_ref and number <= item.pages[0].page_number
            ]
            if candidates:
                stimulus_id = max(candidates, key=lambda candidate: candidate[0])[1]
        stimulus_position = None
        if stimulus_id:
            positions[stimulus_id] = positions.get(stimulus_id, 0) + 1
            stimulus_position = positions[stimulus_id]
        labels = q.answer.labels if q.answer else []
        choices = [
            {
                "label": c.label,
                "content": normalize_blanks(c.content),
                "is_correct": c.label in labels if q.answer else None,
                "pinned": pinned(c.content),
            }
            for c in q.choices
        ]
        db.add(
            Question(
                org_id=source.org_id,
                subject_id=source.subject_id,
                source_id=source.id,
                stimulus_id=stimulus_id,
                stimulus_position=stimulus_position,
                position=position,
                number_label=q.number_label,
                type=q.type,
                stem=stem,
                choices=choices,
                answer=q.answer.text if q.answer else None,
                language=subject.language,
                regions=item.regions,
                status="draft",
                confidence=q.confidence,
                normalized_text=(
                    norm := question_normalized_text(
                        stem, choices, intros.get(stimulus_id) if stimulus_id else None
                    )
                ),
                content_hash=content_hash(norm),
                metadata_json={"notes": item.notes, "model_confidence": q.confidence},
            )
        )
    return old_keys
