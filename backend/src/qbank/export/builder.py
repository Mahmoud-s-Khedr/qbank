"""Database rows to an ``ExamView`` and finally to PDF bytes."""

import base64
from io import BytesIO
from uuid import UUID

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.exams.versions import CHOICE_TYPES, display_label
from qbank.export.pdf import render_pdf
from qbank.export.render import render_answer_key, render_bubble_sheet, render_exam
from qbank.export.view import (
    ChoiceView,
    ExamView,
    GroupView,
    HeaderView,
    QuestionView,
    SectionView,
    StimulusView,
)
from qbank.models import (
    Asset,
    Exam,
    ExamSection,
    ExamTemplate,
    ExamVersion,
    Question,
    Stimulus,
    Subject,
)
from qbank.schemas.exams import ExamHeader, ExamSettings
from qbank.services import exam_generation
from qbank.services.errors import Invalid
from qbank.storage import ObjectStore


class StoreAssets:
    """Resolves ``asset:<id>`` to a ``data:`` URI from object storage (org-scoped, cached)."""

    def __init__(self, db: Session, org_id: UUID, store: ObjectStore) -> None:
        self.db, self.org_id, self.store = db, org_id, store
        self.cache: dict[str, str | None] = {}

    def __call__(self, asset_id: str) -> str | None:
        if asset_id not in self.cache:
            self.cache[asset_id] = self._load(asset_id)
        return self.cache[asset_id]

    def _load(self, asset_id: str) -> str | None:
        try:
            key = UUID(asset_id)
        except ValueError:
            return None
        asset = self.db.scalar(select(Asset).where(Asset.id == key, Asset.org_id == self.org_id))
        if asset is None or not self.store.exists(asset.image_key):
            return None
        data = self.store.get_bytes(asset.image_key)
        with Image.open(BytesIO(data)) as image:
            mime = Image.MIME.get(image.format or "", "image/png")
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def merge_header(own: ExamHeader, template: dict[str, object]) -> ExamHeader:
    """The exam's own non-empty header values win over the template's defaults."""
    base = ExamHeader.model_validate(template)
    return ExamHeader(
        **{name: getattr(own, name) or getattr(base, name) for name in ExamHeader.model_fields}
    )


def build_view(db: Session, exam: Exam, version: ExamVersion, assets: StoreAssets) -> ExamView:
    settings = ExamSettings.model_validate(exam.settings)
    language = settings.language
    template = (
        db.scalar(
            select(ExamTemplate).where(
                ExamTemplate.id == settings.template_id, ExamTemplate.org_id == exam.org_id
            )
        )
        if settings.template_id
        else None
    )
    header = merge_header(settings.header, template.header if template else {})
    subject = db.get(Subject, exam.subject_id)
    logo = assets(str(template.logo_asset_id)) if template and template.logo_asset_id else None
    section_rows = version.layout["sections"]
    layout_items = [i for s in section_rows for i in s["items"]]  # type: ignore[attr-defined]  # JSONB is untyped
    questions = {
        q.id: q
        for q in db.scalars(
            select(Question).where(
                Question.id.in_([UUID(str(i["question_id"])) for i in layout_items])
            )
        )
    }
    stimuli = {
        s.id: s
        for s in db.scalars(
            select(Stimulus).where(
                Stimulus.id.in_({q.stimulus_id for q in questions.values() if q.stimulus_id})
            )
        )
    }
    titles = {
        s.id: s for s in db.scalars(select(ExamSection).where(ExamSection.exam_id == exam.id))
    }
    sections: list[SectionView] = []
    for section in section_rows:  # type: ignore[attr-defined]  # JSONB is untyped
        meta = titles.get(UUID(str(section["section_id"])))
        groups: list[GroupView] = []
        current: list[QuestionView] = []
        current_stimulus: UUID | None = None
        for layout_item in section["items"]:
            question = questions.get(UUID(str(layout_item["question_id"])))
            if question is None:
                continue
            if current and (
                question.stimulus_id is None or question.stimulus_id != current_stimulus
            ):
                groups.append(_group(current, current_stimulus, stimuli))
                current = []
            current_stimulus = question.stimulus_id
            current.append(_question(layout_item, question, language))
        if current:
            groups.append(_group(current, current_stimulus, stimuli))
        if groups:
            sections.append(
                SectionView(
                    title=meta.title if meta else "",
                    instructions=meta.instructions if meta else None,
                    groups=groups,
                )
            )
    return ExamView(
        language=language,
        version_label=version.label,
        header=HeaderView(
            school_name=header.school_name,
            exam_title=header.exam_title or exam.title,
            subject=header.subject_label or (subject.name if subject else ""),
            grade=header.grade or ((subject.grade or "") if subject else ""),
            date=header.date,
            duration_minutes=header.duration_minutes,
            instructions=header.instructions,
            logo_uri=logo,
        ),
        layout=settings.layout,
        sections=sections,
    )


def _question(layout_item: dict[str, object], question: Question, language: str) -> QuestionView:
    choices: list[ChoiceView] = []
    order = layout_item.get("choice_order")
    if question.type in CHOICE_TYPES and isinstance(order, list):
        choices = [
            ChoiceView(
                label=display_label(language, position),
                content=str(question.choices[source].get("content", "")),
            )
            for position, source in enumerate(order)
        ]
    return QuestionView(
        number=int(str(layout_item["number"])),
        type=question.type,
        stem=question.stem,
        points=float(str(layout_item["points"])),
        choices=choices,
    )


def _group(
    questions: list[QuestionView], stimulus_id: UUID | None, stimuli: dict[UUID, Stimulus]
) -> GroupView:
    stimulus = stimuli.get(stimulus_id) if stimulus_id else None
    if stimulus is None:
        return GroupView(questions=questions)
    intro = stimulus.metadata_json.get("intro")
    return GroupView(
        questions=questions,
        stimulus=StimulusView(
            kind=stimulus.kind,
            content=stimulus.content,
            intro=intro if isinstance(intro, str) and intro else None,
        ),
    )


def render_export(
    db: Session, exam: Exam, version: ExamVersion, kind: str, store: ObjectStore
) -> bytes:
    """PDF bytes of one export ``kind`` for one exam version."""
    assets = StoreAssets(db, exam.org_id, store)
    view = build_view(db, exam, version, assets)
    if kind == "pdf":
        html = render_exam(view, assets)
    elif kind == "answer_key_pdf":
        key = exam_generation.key_for(db, exam, version)
        html = render_answer_key(view.with_key(key), assets)
    elif kind == "bubble_sheet_pdf":
        if not view.all_mcq:
            raise Invalid("bubble_sheet_requires_mcq")
        html = render_bubble_sheet(view)
    else:
        raise Invalid("unsupported_export_kind")
    return render_pdf(
        html,
        title=view.header.exam_title,
        version_label=view.version_label,
        language=view.language,
    )
