"""Build proposed taxonomy from extracted headings and assign question locations."""

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.llm import LLMClient, get_llm_client
from qbank.models import Chapter, Lesson, Question, Source, SourcePage
from qbank.pipeline.schema import PageExtraction
from qbank.text.normalize import normalize_ar

logger = logging.getLogger(__name__)
MATCH_THRESHOLD = 0.85
SMALL_HEADING_COUNT = 3
MIN_BOX_LENGTH = 2
PROMPT_VERSION = "structure_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"


class PlanItem(BaseModel):
    kind: Literal["chapter", "lesson"]
    title: str
    start_page: int
    existing_id: UUID | None = None


class StructurePlan(BaseModel):
    items: list[PlanItem] = Field(default_factory=list)


def headings(pages: list[SourcePage]) -> list[tuple[int, str, str, float]]:
    result: list[tuple[int, str, str, float]] = []
    for page in pages:
        if page.extraction is None:
            continue
        for h in sorted(
            PageExtraction.model_validate(page.extraction).headings, key=lambda h: h.box_2d[0]
        ):
            if (
                result
                and h.level == result[-1][1]
                and normalize_ar(h.text) == normalize_ar(result[-1][2])
            ):
                continue
            result.append((page.page_number, h.level, h.text, h.box_2d[0] / 1000))
    return result


Node = TypeVar("Node", Chapter, Lesson)


def match[Node: (Chapter, Lesson)](title: str, nodes: list[Node]) -> Node | None:
    ranked = [
        (SequenceMatcher(None, normalize_ar(title), normalize_ar(node.title)).ratio(), node)
        for node in nodes
    ]
    best = max(ranked, key=lambda pair: pair[0], default=None)
    return best[1] if best and best[0] >= MATCH_THRESHOLD else None


def structure_source(  # noqa: PLR0912, PLR0915 -- plan construction and assignment share state
    db: Session, source: Source, client: LLMClient | None = None
) -> None:
    pages = list(
        db.scalars(
            select(SourcePage)
            .where(SourcePage.source_id == source.id)
            .order_by(SourcePage.page_number)
        )
    )
    hs = headings(pages)
    chapters = list(
        db.scalars(
            select(Chapter)
            .where(Chapter.subject_id == source.subject_id)
            .order_by(Chapter.position)
        )
    )
    lessons = list(
        db.scalars(
            select(Lesson)
            .join(Chapter)
            .where(Chapter.subject_id == source.subject_id)
            .order_by(Lesson.position)
        )
    )
    relevant = [h for h in hs if h[1] in ("chapter", "lesson")]
    plan = [PlanItem(kind=h[1], title=h[2], start_page=h[0]) for h in relevant]
    if len(hs) > SMALL_HEADING_COUNT:
        prompt = PROMPT_PATH.read_text() + json.dumps(
            {
                "headings": hs,
                "chapters": [{"id": str(c.id), "title": c.title} for c in chapters],
                "lessons": [
                    {"id": str(node.id), "chapter_id": str(node.chapter_id), "title": node.title}
                    for node in lessons
                ],
            },
            ensure_ascii=False,
        )
        try:
            result = (client or get_llm_client()).complete_json(
                stage="structure",
                messages=[{"role": "user", "content": prompt}],
                schema=StructurePlan,
                org_id=source.org_id,
                source_id=source.id,
            )
            candidate = result.parsed.items
            if (
                all(
                    any(
                        h[0] == i.start_page
                        and h[1] == i.kind
                        and normalize_ar(h[2]) == normalize_ar(i.title)
                        for h in relevant
                    )
                    for i in candidate
                )
                and candidate
            ):
                plan = candidate
        except Exception:  # Budget and provider errors both use the fallback.
            logger.warning("Structure planning failed; using heading fallback")
    events: list[tuple[int, float, UUID, UUID | None]] = []
    chapter: Chapter | None = None
    for item in plan:
        h = next(
            (
                h
                for h in relevant
                if h[0] == item.start_page
                and h[1] == item.kind
                and normalize_ar(h[2]) == normalize_ar(item.title)
            ),
            None,
        )
        if h is None:
            continue
        if item.kind == "chapter":
            chapter = next((c for c in chapters if c.id == item.existing_id), None) or match(
                item.title, chapters
            )
            if not isinstance(chapter, Chapter):
                chapter = Chapter(
                    subject_id=source.subject_id,
                    title=item.title,
                    position=len(chapters) + 1,
                    metadata_json={"proposed": True},
                )
                db.add(chapter)
                db.flush()
                chapters.append(chapter)
            events.append((h[0], h[3], chapter.id, None))
        elif chapter is not None:
            available = [lesson for lesson in lessons if lesson.chapter_id == chapter.id]
            lesson = next(
                (node for node in available if node.id == item.existing_id), None
            ) or match(item.title, available)
            if not isinstance(lesson, Lesson):
                lesson = Lesson(
                    chapter_id=chapter.id,
                    title=item.title,
                    position=len(available) + 1,
                    metadata_json={"proposed": True},
                )
                db.add(lesson)
                db.flush()
                lessons.append(lesson)
            events.append((h[0], h[3], chapter.id, lesson.id))
    page_numbers = {str(p.id): p.page_number for p in pages}
    questions = db.scalars(select(Question).where(Question.source_id == source.id))
    for q in questions:
        if not q.regions:
            continue
        region = q.regions[0]
        page = page_numbers.get(str(region.get("page")))
        box = region.get("box")
        if page is None or not isinstance(box, list) or len(box) < MIN_BOX_LENGTH:
            continue
        pos = (page, float(box[1]))
        exam = [h for h in hs if h[1] == "exam" and (h[0], h[3]) <= pos]
        meta = dict(q.metadata_json or {})
        if exam:
            meta["exam_title"] = exam[-1][2]
        else:
            meta.pop("exam_title", None)
        sections = [h for h in hs if h[1] == "section" and (h[0], h[3]) <= pos]
        if sections:
            meta["section"] = sections[-1][2]
        else:
            meta.pop("section", None)
        q.metadata_json = meta
        applicable = [e for e in events if (e[0], e[1]) <= pos]
        if q.taxonomy_source != "human" and applicable:
            q.chapter_id, q.lesson_id = applicable[-1][2:]
            q.taxonomy_source = "ai"
