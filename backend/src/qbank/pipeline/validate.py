"""Validation rules engine, confidence scoring, and status assignment."""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.config import get_settings
from qbank.models import Question, Source, Stimulus, ValidationIssue
from qbank.pipeline.dedup import dedup_source, ensure_normalized
from qbank.text.normalize import normalize_ar

IssueSeverity = Literal["error", "warning"]

ERROR_PENALTY = 0.5
WARNING_PENALTY = 0.85
LOW_CONFIDENCE_THRESHOLD = 0.6
MIN_STEM_NORMALIZED_CHARS = 8
MIN_MCQ_CHOICES = 2

_MCQ_TYPES = frozenset({"mcq_single", "mcq_multi"})

# Valid contiguous label alphabets for MCQ choices (normalized).
_LABEL_ALPHABETS: tuple[tuple[str, ...], ...] = (
    ("\u0627", "ب", "ج", "د", "\u0647", "و", "ز", "ح"),  # Arabic Abjad
    ("\u0627", "ب", "ت", "ث", "ج", "ح", "خ", "د"),  # Arabic Hijai
    ("a", "b", "c", "d", "e", "f", "g", "h"),  # Latin
    ("1", "2", "3", "4", "5", "6", "7", "8"),  # Numeric
    ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii"),  # Roman
)

_LABEL_STRIP_RE = re.compile(r"[\s().\-،:;\[\]\u0640]+")
_LABEL_MAP = str.maketrans(
    {
        "\u0623": "\u0627",
        "\u0625": "\u0627",
        "\u0622": "\u0627",
        "\u0671": "\u0627",
        "\u0629": "\u0647",
        "\u0660": "0",
        "\u0661": "1",
        "\u0662": "2",
        "\u0663": "3",
        "\u0664": "4",
        "\u0665": "5",
        "\u0666": "6",
        "\u0667": "7",
        "\u0668": "8",
        "\u0669": "9",
        "\u06f0": "0",
        "\u06f1": "1",
        "\u06f2": "2",
        "\u06f3": "3",
        "\u06f4": "4",
        "\u06f5": "5",
        "\u06f6": "6",
        "\u06f7": "7",
        "\u06f8": "8",
        "\u06f9": "9",
    }
)

_ASSET_LINK_RE = re.compile(r"asset:[^\s)]+", re.IGNORECASE)
_ASSET_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\(asset:[^)]*\)", re.IGNORECASE)

# Arabic normalized keywords (الشكل, الصورة->الصوره, الرسم, المقابل) and English figure keywords.
_AR_FIGURE_KEYWORDS_RE = re.compile(
    r"(?:^|\s|[،,.؛:(])(?:و|ف|ب|ك|ل|لل|بال|كال|في\s+)?"
    r"(?:الشكل|الصور\u0647|الرسم|المقابل)(?:ان|ين|\u0647|ات)?(?=$|\s|[،,.؛:؟?)])"
)
_EN_FIGURE_KEYWORDS_RE = re.compile(
    r"\b(?:figure|diagram|graph|chart|table)s?\b",
    re.IGNORECASE,
)

_MID_WORD_HYPHEN_RE = re.compile(r"\w-$")
_TRAILING_WAW_RE = re.compile(r"(?:^|\s)و$")
_FIRST_INT_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class Issue:
    code: str
    severity: IssueSeverity
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class ValidationContext:
    answer_key_matched: bool = False
    questions: Sequence[Question] = ()
    stimuli: Sequence[Stimulus] = ()
    stimuli_by_id: dict[UUID, Stimulus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stimuli and not self.stimuli_by_id:
            self.stimuli_by_id = {s.id: s for s in self.stimuli if s.id is not None}


RuleFn = Callable[[Question, ValidationContext], list[Issue]]


def _normalize_choice_label(label: str) -> str:
    cleaned = _LABEL_STRIP_RE.sub("", label)
    return cleaned.translate(_LABEL_MAP).lower()


def get_model_confidence(question: Question) -> float:
    """Return the original LLM-reported confidence before rule penalties."""
    if question.metadata_json and "model_confidence" in question.metadata_json:
        raw = question.metadata_json["model_confidence"]
        if isinstance(raw, int | float):
            return float(raw)
    return float(question.confidence)


def mcq_too_few_choices(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag MCQ questions with fewer than 2 choices."""
    if question.type not in _MCQ_TYPES:
        return []
    count = len(question.choices)
    if count < MIN_MCQ_CHOICES:
        return [
            Issue(
                code="mcq_too_few_choices",
                severity="error",
                message=f"MCQ question has {count} choice(s); at least 2 are required.",
                details={"choice_count": count},
            )
        ]
    return []


def mcq_duplicate_labels(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag questions whose choices contain duplicate labels."""
    if len(question.choices) < MIN_MCQ_CHOICES:
        return []
    labels = [_normalize_choice_label(str(c.get("label", ""))) for c in question.choices]
    seen: set[str] = set()
    duplicates: list[str] = []
    for lbl in labels:
        if lbl in seen and lbl not in duplicates:
            duplicates.append(lbl)
        seen.add(lbl)
    if duplicates:
        return [
            Issue(
                code="mcq_duplicate_labels",
                severity="error",
                message=f"Duplicate choice labels: {', '.join(duplicates)}",
                details={"labels": labels, "duplicates": duplicates},
            )
        ]
    return []


def mcq_label_sequence(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag MCQ choices whose labels are not contiguous in their alphabet."""
    if question.type not in _MCQ_TYPES or len(question.choices) < MIN_MCQ_CHOICES:
        return []
    labels = tuple(_normalize_choice_label(str(c.get("label", ""))) for c in question.choices)
    if len(set(labels)) < len(labels):
        # Covered by mcq_duplicate_labels.
        return []
    n = len(labels)
    for alphabet in _LABEL_ALPHABETS:
        if n <= len(alphabet) and alphabet[:n] == labels:
            return []
    return [
        Issue(
            code="mcq_label_sequence",
            severity="warning",
            message=f"Choice labels are not contiguous: {', '.join(labels)}",
            details={"labels": list(labels)},
        )
    ]


def missing_answer(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag questions missing a correct answer (error if source answer key was matched)."""
    has_text_answer = question.answer is not None and bool(question.answer.strip())
    has_correct_choice = any(bool(c.get("is_correct")) for c in question.choices)
    if has_text_answer or has_correct_choice:
        return []
    key_matched = bool(
        context.answer_key_matched
        or (question.metadata_json and question.metadata_json.get("answer_key_matched"))
    )
    severity: IssueSeverity = "error" if key_matched else "warning"
    return [
        Issue(
            code="missing_answer",
            severity=severity,
            message="Question is missing a correct answer.",
            details={"answer_key_matched": key_matched},
        )
    ]


def figure_referenced_not_attached(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag questions whose stem mentions a figure/diagram/table without an attached asset."""
    stem_without_assets = _ASSET_MARKDOWN_RE.sub(" ", question.stem)
    norm_stem = normalize_ar(stem_without_assets)
    mentions_ar = bool(_AR_FIGURE_KEYWORDS_RE.search(norm_stem))
    mentions_en = bool(_EN_FIGURE_KEYWORDS_RE.search(stem_without_assets))
    if not (mentions_ar or mentions_en):
        return []

    texts_to_check = [question.stem]
    for choice in question.choices:
        content = choice.get("content")
        if isinstance(content, str):
            texts_to_check.append(content)
    stimulus = context.stimuli_by_id.get(question.stimulus_id) if question.stimulus_id else None
    if stimulus is not None:
        texts_to_check.append(stimulus.content)

    if any(_ASSET_LINK_RE.search(t) for t in texts_to_check):
        return []

    return [
        Issue(
            code="figure_referenced_not_attached",
            severity="error",
            message="Stem references a figure/diagram/table, but no asset is attached.",
            details={},
        )
    ]


def empty_stem(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag questions with an empty stem."""
    norm_stem = normalize_ar(question.stem)
    if not question.stem.strip() or not norm_stem:
        return [
            Issue(
                code="empty_stem",
                severity="error",
                message="Question stem is empty.",
                details={},
            )
        ]
    return []


def truncated_stem(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag stems that appear truncated (ends mid-word, with ،/و, or < 8 normalized chars)."""
    norm_stem = normalize_ar(question.stem)
    if not question.stem.strip() or not norm_stem:
        return []

    clean_stem = _ASSET_MARKDOWN_RE.sub("", question.stem).strip()
    notes = (
        question.metadata_json.get("notes", []) if isinstance(question.metadata_json, dict) else []
    )
    unmatched_continuation = isinstance(notes, list) and any(
        "Unmatched continuation on next page" in str(n) for n in notes
    )
    ends_with_comma_or_waw = clean_stem.endswith(("،", ",", "؛")) or bool(
        _TRAILING_WAW_RE.search(clean_stem)
    )
    ends_mid_word = (
        clean_stem.endswith(("\u0640", "(", "[", "{", "\\"))
        or bool(_MID_WORD_HYPHEN_RE.search(clean_stem))
        or unmatched_continuation
    )
    too_short = len(norm_stem) < MIN_STEM_NORMALIZED_CHARS and question.type != "fill_blank"

    if ends_with_comma_or_waw or ends_mid_word or too_short:
        reason = (
            "too_short"
            if too_short
            else ("ends_with_conjunction_or_comma" if ends_with_comma_or_waw else "ends_mid_word")
        )
        return [
            Issue(
                code="truncated_stem",
                severity="warning",
                message="Question stem appears truncated.",
                details={"reason": reason, "normalized_length": len(norm_stem)},
            )
        ]
    return []


def _scan_math_span(text: str, start: int, *, is_display: bool) -> tuple[int, str | None]:
    """Scan inside a $...$ or $$...$$ block and return (next_index, error_reason)."""
    delim = "$$" if is_display else "$"
    i = start
    n = len(text)
    brace_depth = 0
    while i < n:
        ch = text[i]
        if ch == "\\":
            if i + 1 >= n:
                return n, "dangling_backslash_in_math"
            i += 2
            continue
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth < 0:
                return i + 1, "unbalanced_braces_in_math"
        elif ch == "$":
            has_second_dollar = i + 1 < n and text[i + 1] == "$"
            if is_display != has_second_dollar:
                return i + 1, "mismatched_dollar_delimiter"
            next_i = i + (2 if is_display else 1)
            err = (
                "unbalanced_braces_in_math"
                if brace_depth != 0
                else ("empty_math_expression" if not text[start:i].strip() else None)
            )
            return next_i, err
        i += 1
    return n, f"unclosed_{delim}"


def _check_latex_text(text: str) -> str | None:
    """Return an error reason if math delimiters ($) or braces inside math are unbalanced."""
    i = 0
    n = len(text)
    in_code = False
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
            i += 1
            continue
        if not in_code and ch == "$":
            is_display = i + 1 < n and text[i + 1] == "$"
            i, err = _scan_math_span(text, i + (2 if is_display else 1), is_display=is_display)
            if err is not None:
                return err
            continue
        i += 1
    return None


def latex_invalid(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag unbalanced $ delimiters or unbalanced braces inside math expressions."""
    fields: list[tuple[str, str]] = [("stem", question.stem)]
    for idx, choice in enumerate(question.choices):
        content = choice.get("content")
        if isinstance(content, str):
            fields.append((f"choice_{idx}", content))
    if question.answer:
        fields.append(("answer", question.answer))
    if question.explanation:
        fields.append(("explanation", question.explanation))

    for field_name, value in fields:
        problem = _check_latex_text(value)
        if problem is not None:
            return [
                Issue(
                    code="latex_invalid",
                    severity="error",
                    message=f"Invalid LaTeX in {field_name}: {problem}",
                    details={"field": field_name, "problem": problem},
                )
            ]
    return []


def _parse_question_number(label: str) -> int | None:
    mapped = label.translate(_LABEL_MAP)
    match = _FIRST_INT_RE.search(mapped)
    return int(match.group(0)) if match else None


def _first_page_key(regions: list[dict[str, object]]) -> str | None:
    if not regions:
        return None
    page = regions[0].get("page")
    return str(page) if page is not None else None


def numbering_gap(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag a gap in sequential question numbering on the same page (e.g. 3 -> 5)."""
    if not context.questions:
        return []
    target_page = _first_page_key(question.regions)
    page_questions = [q for q in context.questions if _first_page_key(q.regions) == target_page]
    for idx, q in enumerate(page_questions):
        is_target = q is question or (q.id is not None and q.id == question.id)
        if not is_target:
            continue
        if idx == 0:
            return []
        prev_q = page_questions[idx - 1]
        prev_num = _parse_question_number(prev_q.number_label)
        curr_num = _parse_question_number(question.number_label)
        if prev_num is not None and curr_num is not None and curr_num > prev_num + 1:
            return [
                Issue(
                    code="numbering_gap",
                    severity="warning",
                    message=f"Question number jumps from {prev_num} to {curr_num}.",
                    details={
                        "previous_number": prev_num,
                        "current_number": curr_num,
                        "missing_numbers": list(range(prev_num + 1, curr_num)),
                    },
                )
            ]
        return []
    return []


def low_confidence(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag questions whose model confidence is below 0.6."""
    conf = get_model_confidence(question)
    if conf < LOW_CONFIDENCE_THRESHOLD:
        return [
            Issue(
                code="low_confidence",
                severity="warning",
                message=f"Low extraction confidence ({conf:.2f} < {LOW_CONFIDENCE_THRESHOLD}).",
                details={"model_confidence": conf},
            )
        ]
    return []


def duplicate_of(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag questions linked as near-duplicates of an older question."""
    if question.duplicate_of_id is None:
        return []
    sim = (
        question.metadata_json.get("duplicate_similarity")
        if isinstance(question.metadata_json, dict)
        else None
    )
    details: dict[str, object] = {"duplicate_of_id": str(question.duplicate_of_id)}
    if isinstance(sim, int | float):
        details["similarity"] = float(sim)
    return [
        Issue(
            code="duplicate_of",
            severity="warning",
            message=f"Question is a near-duplicate of {question.duplicate_of_id}",
            details=details,
        )
    ]


def stimulus_orphan(question: Question, context: ValidationContext) -> list[Issue]:
    """Flag a stimulus that has no questions referencing it."""
    if not context.stimuli:
        return []
    all_questions = list(context.questions) if context.questions else [question]
    referenced_ids = {q.stimulus_id for q in all_questions if q.stimulus_id is not None}
    orphans = [s for s in context.stimuli if s.id not in referenced_ids]
    if not orphans:
        return []

    issues: list[Issue] = []
    for orphan in orphans:
        orphan_page = _first_page_key(orphan.regions)
        carrier: Question | None = None
        if orphan_page is not None:
            carrier = next(
                (q for q in all_questions if _first_page_key(q.regions) == orphan_page),
                None,
            )
        if carrier is None:
            carrier = all_questions[0]
        if carrier is question or (carrier.id is not None and carrier.id == question.id):
            issues.append(
                Issue(
                    code="stimulus_orphan",
                    severity="warning",
                    message=f"Stimulus {orphan.id} has no linked questions.",
                    details={"stimulus_id": str(orphan.id) if orphan.id else None},
                )
            )
    return issues


RULES: dict[str, RuleFn] = {
    "mcq_too_few_choices": mcq_too_few_choices,
    "mcq_duplicate_labels": mcq_duplicate_labels,
    "mcq_label_sequence": mcq_label_sequence,
    "missing_answer": missing_answer,
    "figure_referenced_not_attached": figure_referenced_not_attached,
    "empty_stem": empty_stem,
    "truncated_stem": truncated_stem,
    "latex_invalid": latex_invalid,
    "numbering_gap": numbering_gap,
    "low_confidence": low_confidence,
    "duplicate_of": duplicate_of,
    "stimulus_orphan": stimulus_orphan,
}


def _verifier_issues_from_metadata(question: Question) -> list[Issue]:
    """Extract persisted verifier_* issues from question metadata so re-validation keeps them."""
    if not isinstance(question.metadata_json, dict):
        return []
    raw_list = question.metadata_json.get("verifier_issues")
    if not isinstance(raw_list, list):
        return []
    result: list[Issue] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "verifier_stem"))
        sev_raw = str(item.get("severity", "warning"))
        severity: IssueSeverity = "error" if sev_raw == "error" else "warning"
        message = str(item.get("message", "Verifier reported a discrepancy."))
        details = item.get("details")
        result.append(
            Issue(
                code=code,
                severity=severity,
                message=message,
                details=dict(details) if isinstance(details, dict) else {},
            )
        )
    return result


def evaluate_question(question: Question, context: ValidationContext | None = None) -> list[Issue]:
    """Run all registered validation rules plus any verifier issues on a question."""
    ctx = context or ValidationContext()
    issues: list[Issue] = []
    for rule in RULES.values():
        issues.extend(rule(question, ctx))
    issues.extend(_verifier_issues_from_metadata(question))
    return issues


def compute_confidence(model_confidence: float, issues: Sequence[Issue | ValidationIssue]) -> float:
    """Compute final question confidence.

    Formula:
        confidence = model_confidence * prod(penalty per issue)
    where:
        - error penalty = 0.5
        - warning penalty = 0.85
    The result is clamped to [0.0, 1.0].
    """
    score = float(model_confidence)
    for issue in issues:
        penalty = ERROR_PENALTY if issue.severity == "error" else WARNING_PENALTY
        score *= penalty
    return min(1.0, max(0.0, score))


def compute_status(
    confidence: float,
    issues: Sequence[Issue | ValidationIssue],
    *,
    review_threshold: float | None = None,
) -> Literal["draft", "needs_review"]:
    """Determine question status from confidence and issues.

    Any error issue or confidence < settings.review_threshold (default 0.75)
    transitions the question to 'needs_review'; otherwise it remains 'draft'.
    """
    threshold = (
        review_threshold if review_threshold is not None else get_settings().review_threshold
    )
    has_error = any(issue.severity == "error" for issue in issues)
    if has_error or confidence < threshold:
        return "needs_review"
    return "draft"


def validate_question(
    db: Session,
    question: Question,
    context: ValidationContext | None = None,
    *,
    review_threshold: float | None = None,
) -> list[ValidationIssue]:
    """Validate a question, replace unresolved issues, and keep resolved issues if applicable."""
    ctx = context or ValidationContext()
    model_conf = get_model_confidence(question)
    question.metadata_json = {
        **(question.metadata_json or {}),
        "model_confidence": model_conf,
    }
    stim = ctx.stimuli_by_id.get(question.stimulus_id) if question.stimulus_id else None
    intro = (
        str(stim.metadata_json["intro"])
        if stim and stim.metadata_json and stim.metadata_json.get("intro") is not None
        else None
    )
    ensure_normalized(question, intro)

    computed_issues = evaluate_question(question, ctx)
    existing_rows = list(
        db.scalars(select(ValidationIssue).where(ValidationIssue.question_id == question.id))
    )

    resolved_by_code: dict[str, ValidationIssue] = {}
    for row in existing_rows:
        if row.resolved_at is not None and row.code not in resolved_by_code:
            resolved_by_code[row.code] = row
        else:
            db.delete(row)

    new_codes = {issue.code for issue in computed_issues}
    for code, resolved_row in list(resolved_by_code.items()):
        if code not in new_codes:
            db.delete(resolved_row)
            del resolved_by_code[code]

    persisted: list[ValidationIssue] = []
    consumed_resolved_codes: set[str] = set()
    for issue in computed_issues:
        if issue.code in resolved_by_code and issue.code not in consumed_resolved_codes:
            kept = resolved_by_code[issue.code]
            kept.severity = issue.severity
            kept.message = issue.message
            kept.details = issue.details
            consumed_resolved_codes.add(issue.code)
            persisted.append(kept)
        else:
            new_row = ValidationIssue(
                question_id=question.id,
                code=issue.code,
                severity=issue.severity,
                message=issue.message,
                details=issue.details,
            )
            db.add(new_row)
            persisted.append(new_row)

    question.confidence = compute_confidence(model_conf, computed_issues)
    if question.status not in ("approved", "rejected"):
        question.status = compute_status(
            question.confidence,
            computed_issues,
            review_threshold=review_threshold,
        )
    db.flush()
    return persisted


def validate_source(
    db: Session,
    source: Source,
    *,
    question_ids: set[UUID] | None = None,
    run_dedup: bool = True,
) -> None:
    """Run deduplication and validation across a source's questions."""
    questions = list(
        db.scalars(
            select(Question)
            .where(Question.source_id == source.id)
            .order_by(Question.position.asc(), Question.id.asc())
        )
    )
    stimuli = list(
        db.scalars(
            select(Stimulus)
            .where(Stimulus.source_id == source.id)
            .order_by(Stimulus.created_at.asc(), Stimulus.id.asc())
        )
    )
    stimuli_by_id = {s.id: s for s in stimuli}
    if run_dedup:
        dedup_source(
            db,
            source.id,
            questions=questions,
            stimuli_by_id=stimuli_by_id,
            sync_issue=False,
        )
    answer_key_matched = bool(
        isinstance(source.pipeline_config, dict)
        and source.pipeline_config.get("answer_key_matched", False)
    )
    context = ValidationContext(
        answer_key_matched=answer_key_matched,
        questions=questions,
        stimuli=stimuli,
        stimuli_by_id=stimuli_by_id,
    )
    threshold = get_settings().review_threshold
    for q in questions:
        if question_ids is not None and q.id not in question_ids:
            continue
        validate_question(db, q, context, review_threshold=threshold)
