"""Plain data handed to the templates, plus the small formatting rules they rely on."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from qbank.exams.versions import CHOICE_TYPES
from qbank.schemas.exams import AnswerKey, ExamLayout

ARABIC_DECIMAL = "\u066b"
ARABIC_INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
SHORT_CHOICE = 18
MEDIUM_CHOICE = 40
LINE_TYPES = frozenset({"essay", "short_answer"})


def arabic_digits(text: str) -> str:
    """Western digits to Arabic-Indic, and the decimal point to the Arabic decimal separator."""
    out = text.translate(ARABIC_INDIC)
    return "".join(
        ARABIC_DECIMAL
        if c == "." and 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit()
        else c
        for i, c in enumerate(out)
    )


def format_number(value: float) -> str:
    """``2.0`` -> ``2``, ``0.5`` -> ``0.5``."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def auto_choices_per_row(contents: Sequence[str]) -> int:
    """4 per row if every choice is at most 18 characters, 2 if at most 40, otherwise 1."""
    longest = max((len(c.strip()) for c in contents), default=0)
    if longest <= SHORT_CHOICE:
        return 4
    return 2 if longest <= MEDIUM_CHOICE else 1


def choices_per_row(setting: str | int, contents: Sequence[str]) -> int:
    return auto_choices_per_row(contents) if setting == "auto" else int(setting)


def digits_formatter(language: str, digits: str) -> Callable[[object], str]:
    """Formats numbers for display: Arabic-Indic only for Arabic exams that ask for them."""
    use_arabic = digits == "arabic" and language == "ar"

    def fmt(value: object) -> str:
        text = format_number(value) if isinstance(value, float) else str(value)
        return arabic_digits(text) if use_arabic else text

    return fmt


@dataclass(frozen=True)
class ChoiceView:
    label: str
    content: str


@dataclass(frozen=True)
class QuestionView:
    number: int
    type: str
    stem: str
    points: float
    choices: Sequence[ChoiceView] = ()

    @property
    def has_lines(self) -> bool:
        return self.type in LINE_TYPES


@dataclass(frozen=True)
class StimulusView:
    kind: str
    content: str
    intro: str | None = None


@dataclass(frozen=True)
class GroupView:
    questions: Sequence[QuestionView]
    stimulus: StimulusView | None = None


@dataclass(frozen=True)
class SectionView:
    title: str
    instructions: str | None
    groups: Sequence[GroupView]


@dataclass(frozen=True)
class HeaderView:
    school_name: str = ""
    exam_title: str = ""
    subject: str = ""
    grade: str = ""
    date: str = ""
    duration_minutes: int | None = None
    instructions: str = ""
    logo_uri: str | None = None


@dataclass(frozen=True)
class ExamView:
    language: str
    version_label: str
    header: HeaderView
    layout: ExamLayout
    sections: Sequence[SectionView] = field(default_factory=tuple)
    key: AnswerKey | None = None

    @property
    def questions(self) -> list[QuestionView]:
        return [q for s in self.sections for g in s.groups for q in g.questions]

    @property
    def total_points(self) -> float:
        return sum(q.points for q in self.questions)

    @property
    def all_mcq(self) -> bool:
        questions = self.questions
        return bool(questions) and all(q.type in CHOICE_TYPES for q in questions)

    def with_key(self, key: AnswerKey) -> "ExamView":
        return replace(self, key=key)
