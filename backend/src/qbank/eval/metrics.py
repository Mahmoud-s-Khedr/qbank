"""Pure evaluation metrics for benchmarking page extraction against the golden set."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from qbank.pipeline.schema import PageExtraction, Question, Stimulus, to_region_box

# Arabic normalization patterns: strip tashkeel (U+064B..U+065F, U+0670, U+06D6..U+06ED)
# and tatweel (U+0640).
_TASHKEEL_AND_TATWEEL_RE = re.compile(r"[\u0640\u064B-\u065F\u0670\u06D6-\u06ED]")
_WHITESPACE_RE = re.compile(r"\s+")
_ARABIC_CHAR_MAP = str.maketrans(
    {
        "\u0623": "\u0627",  # alef with hamza above -> bare alef
        "\u0625": "\u0627",  # alef with hamza below -> bare alef
        "\u0622": "\u0627",  # alef with madda -> bare alef
        "\u0671": "\u0627",  # alef wasla -> bare alef
        "\u0649": "\u064a",  # alef maqsura -> yeh
        "\u0629": "\u0647",  # teh marbuta -> heh
    }
)

BOX_COORD_LEN = 4
DEFAULT_FIGURE_IOU_THRESHOLD = 0.5
P95_QUANTILE = 0.95
TOP_WORST_QUESTIONS = 10

COMPOSITE_WEIGHTS: dict[str, float] = {
    "stem_cer_normalized": 0.35,
    "choice_cer": 0.15,
    "question_count_match": 0.15,
    "type_accuracy": 0.10,
    "figure_recall": 0.10,
    "question_box_iou": 0.10,
    "page_kind_accuracy": 0.05,
}


def normalize_arabic(text: str) -> str:
    """Strip tashkeel/tatweel, unify alef forms, map alef maqsura/teh marbuta, collapse spaces."""
    stripped = _TASHKEEL_AND_TATWEEL_RE.sub("", text)
    mapped = stripped.translate(_ARABIC_CHAR_MAP)
    return _WHITESPACE_RE.sub(" ", mapped).strip()


def levenshtein_distance(reference: str, hypothesis: str) -> int:
    """Compute character-level Levenshtein edit distance between two strings."""
    if reference == hypothesis:
        return 0
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    prev_row = list(range(len(hypothesis) + 1))
    for i, ref_char in enumerate(reference, start=1):
        curr_row = [i]
        for j, hyp_char in enumerate(hypothesis, start=1):
            insert_cost = curr_row[j - 1] + 1
            delete_cost = prev_row[j] + 1
            replace_cost = prev_row[j - 1] + (0 if ref_char == hyp_char else 1)
            curr_row.append(min(insert_cost, delete_cost, replace_cost))
        prev_row = curr_row
    return prev_row[-1]


def cer(reference: str, hypothesis: str, *, normalized: bool = False) -> float:
    """Compute character error rate (CER) clamped to [0.0, 1.0]."""
    ref = normalize_arabic(reference) if normalized else reference
    hyp = normalize_arabic(hypothesis) if normalized else hypothesis
    if not ref and not hyp:
        return 0.0
    if not ref:
        return 1.0
    distance = levenshtein_distance(ref, hyp)
    return min(1.0, distance / len(ref))


def cer_exact(reference: str, hypothesis: str) -> float:
    """Compute exact character error rate (preserving tashkeel)."""
    return cer(reference, hypothesis, normalized=False)


def cer_normalized(reference: str, hypothesis: str) -> float:
    """Compute normalized Arabic character error rate."""
    return cer(reference, hypothesis, normalized=True)


def box_iou(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    """Compute Intersection-over-Union (IoU) for two [x0, y0, x1, y1] boxes."""
    if len(box_a) != BOX_COORD_LEN or len(box_b) != BOX_COORD_LEN:
        return 0.0
    ax0, ay0, ax1, ay1 = (float(v) for v in box_a)
    bx0, by0, bx1, by1 = (float(v) for v in box_b)
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    if area_a <= 0.0 and area_b <= 0.0:
        return 0.0
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter <= 0.0:
        return 0.0
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


@dataclass(frozen=True)
class BoxMatchResult:
    matches: list[tuple[int, int, float]]
    unmatched_golden: list[int]
    unmatched_pred: list[int]
    precision: float
    recall: float
    mean_iou: float


def greedy_match_boxes(
    golden_boxes: Sequence[Sequence[float]],
    pred_boxes: Sequence[Sequence[float]],
    *,
    iou_threshold: float = DEFAULT_FIGURE_IOU_THRESHOLD,
) -> BoxMatchResult:
    """Greedily match golden and predicted boxes by descending IoU >= iou_threshold."""
    candidates: list[tuple[float, int, int]] = []
    for g_idx, g_box in enumerate(golden_boxes):
        for p_idx, p_box in enumerate(pred_boxes):
            score = box_iou(g_box, p_box)
            if score >= iou_threshold:
                candidates.append((score, g_idx, p_idx))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_g: set[int] = set()
    used_p: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for score, g_idx, p_idx in candidates:
        if g_idx not in used_g and p_idx not in used_p:
            used_g.add(g_idx)
            used_p.add(p_idx)
            matches.append((g_idx, p_idx, score))
    unmatched_g = [i for i in range(len(golden_boxes)) if i not in used_g]
    unmatched_p = [i for i in range(len(pred_boxes)) if i not in used_p]
    tp = len(matches)
    num_g = len(golden_boxes)
    num_p = len(pred_boxes)
    if num_g == 0 and num_p == 0:
        precision = 1.0
        recall = 1.0
    elif num_g == 0:
        precision = 0.0
        recall = 1.0
    elif num_p == 0:
        precision = 0.0
        recall = 0.0
    else:
        precision = tp / num_p
        recall = tp / num_g
    mean_iou = sum(m[2] for m in matches) / tp if tp > 0 else 0.0
    return BoxMatchResult(
        matches=matches,
        unmatched_golden=unmatched_g,
        unmatched_pred=unmatched_p,
        precision=precision,
        recall=recall,
        mean_iou=mean_iou,
    )


@dataclass(frozen=True)
class QuestionMatchResult:
    matched: list[tuple[dict[str, Any], Question]]
    unmatched_golden: list[dict[str, Any]]
    extra_pred: list[Question]
    exact_count_match: bool


def match_questions_by_label(
    golden_questions: Sequence[dict[str, Any]],
    pred_questions: Sequence[Question],
) -> QuestionMatchResult:
    """Match questions by number_label, reporting unmatched golden and extra predicted items."""
    remaining_pred: list[tuple[int, Question]] = list(enumerate(pred_questions))
    used_pred_indices: set[int] = set()
    matched: list[tuple[dict[str, Any], Question]] = []
    unmatched_golden: list[dict[str, Any]] = []

    for g_q in golden_questions:
        g_label = str(g_q["number_label"]).strip()
        found_idx: int | None = None
        found_pred: Question | None = None
        for p_idx, p_q in remaining_pred:
            if p_idx not in used_pred_indices and p_q.number_label.strip() == g_label:
                found_idx = p_idx
                found_pred = p_q
                break
        if found_idx is not None and found_pred is not None:
            used_pred_indices.add(found_idx)
            matched.append((g_q, found_pred))
        else:
            unmatched_golden.append(g_q)

    extra_pred = [p_q for p_idx, p_q in remaining_pred if p_idx not in used_pred_indices]
    exact_count_match = len(golden_questions) == len(pred_questions)
    return QuestionMatchResult(
        matched=matched,
        unmatched_golden=unmatched_golden,
        extra_pred=extra_pred,
        exact_count_match=exact_count_match,
    )


@dataclass(frozen=True)
class StimulusMatchResult:
    matched: list[tuple[dict[str, Any], Stimulus]]
    ref_map: dict[str, str]
    count_match: bool
    content_cer_normalized: float
    kind_accuracy: float


def match_stimuli(
    golden_stimuli: Sequence[dict[str, Any]],
    pred_stimuli: Sequence[Stimulus],
) -> StimulusMatchResult:
    """Match golden and predicted stimuli and build a golden_ref -> pred_ref mapping."""
    count_match = len(golden_stimuli) == len(pred_stimuli)
    if not golden_stimuli or not pred_stimuli:
        cer_val = 0.0 if not golden_stimuli and not pred_stimuli else 1.0
        kind_acc = 1.0 if not golden_stimuli and not pred_stimuli else 0.0
        return StimulusMatchResult(
            matched=[],
            ref_map={},
            count_match=count_match,
            content_cer_normalized=cer_val,
            kind_accuracy=kind_acc,
        )

    candidates: list[tuple[float, float, int, int, int]] = []
    for g_idx, g_stim in enumerate(golden_stimuli):
        g_box = g_stim["box"]
        g_content = str(g_stim["content"])
        g_ref = str(g_stim["ref"]).strip()
        for p_idx, p_stim in enumerate(pred_stimuli):
            p_box = to_region_box(p_stim.box_2d)
            iou = box_iou(g_box, p_box)
            text_sim = 1.0 - cer_normalized(g_content, p_stim.content)
            ref_eq = 1 if g_ref == p_stim.ref.strip() else 0
            combined = 0.5 * iou + 0.4 * text_sim + 0.1 * ref_eq
            candidates.append((combined, iou, ref_eq, g_idx, p_idx))

    candidates.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3], item[4]))
    used_g: set[int] = set()
    used_p: set[int] = set()
    matched: list[tuple[dict[str, Any], Stimulus]] = []
    ref_map: dict[str, str] = {}
    for _, _, _, g_idx, p_idx in candidates:
        if g_idx not in used_g and p_idx not in used_p:
            used_g.add(g_idx)
            used_p.add(p_idx)
            g_stim = golden_stimuli[g_idx]
            p_stim = pred_stimuli[p_idx]
            matched.append((g_stim, p_stim))
            ref_map[str(g_stim["ref"]).strip()] = p_stim.ref.strip()

    content_cers = [cer_normalized(str(g["content"]), p.content) for g, p in matched]
    kind_matches = [1.0 if p.kind == g["kind"] else 0.0 for g, p in matched]
    return StimulusMatchResult(
        matched=matched,
        ref_map=ref_map,
        count_match=count_match,
        content_cer_normalized=sum(content_cers) / len(content_cers) if content_cers else 1.0,
        kind_accuracy=sum(kind_matches) / len(kind_matches) if kind_matches else 0.0,
    )


def score_choices(
    golden_choices: Sequence[dict[str, Any]],
    pred_choices: Sequence[Any],
) -> tuple[float, bool, bool]:
    """Return (choice_cer_normalized, choice_count_match, has_choices)."""
    count_match = len(golden_choices) == len(pred_choices)
    if not golden_choices and not pred_choices:
        return 0.0, True, False
    if not golden_choices or not pred_choices:
        return 1.0, False, True
    pred_by_label: dict[str, str] = {}
    for choice in pred_choices:
        label = choice.label.strip() if hasattr(choice, "label") else str(choice["label"]).strip()
        content = choice.content if hasattr(choice, "content") else str(choice["content"])
        if label not in pred_by_label:
            pred_by_label[label] = content
    cers: list[float] = []
    for g_choice in golden_choices:
        g_label = str(g_choice["label"]).strip()
        g_content = str(g_choice["content"])
        if g_label in pred_by_label:
            cers.append(cer_normalized(g_content, pred_by_label[g_label]))
        else:
            cers.append(1.0)
    return sum(cers) / len(cers), count_match, True


def score_answer(golden_answer: dict[str, Any] | None, pred_question: Question) -> bool | None:
    """Return True/False when golden has an answer, or None if golden answer is null."""
    if golden_answer is None:
        return None
    if pred_question.answer is None:
        return False
    if golden_answer.get("labels"):
        g_labels = [str(lbl).strip() for lbl in golden_answer["labels"]]
        p_labels = [lbl.strip() for lbl in pred_question.answer.labels]
        return g_labels == p_labels
    if golden_answer.get("text") is not None:
        g_text = normalize_arabic(str(golden_answer["text"]))
        p_text = normalize_arabic(pred_question.answer.text or "")
        return bool(g_text) and g_text == p_text
    return False


def compute_composite_score(  # noqa: PLR0913 -- explicit composite components per spec
    *,
    stem_cer_normalized: float,
    choice_cer: float,
    question_count_match: float,
    type_accuracy: float,
    figure_recall: float,
    question_box_iou: float,
    page_kind_accuracy: float,
) -> float:
    """Compute the weighted composite extraction score in [0.0, 1.0]."""
    stem_score = 1.0 - min(1.0, max(0.0, stem_cer_normalized))
    choice_score = 1.0 - min(1.0, max(0.0, choice_cer))
    return (
        COMPOSITE_WEIGHTS["stem_cer_normalized"] * stem_score
        + COMPOSITE_WEIGHTS["choice_cer"] * choice_score
        + COMPOSITE_WEIGHTS["question_count_match"] * question_count_match
        + COMPOSITE_WEIGHTS["type_accuracy"] * type_accuracy
        + COMPOSITE_WEIGHTS["figure_recall"] * figure_recall
        + COMPOSITE_WEIGHTS["question_box_iou"] * question_box_iou
        + COMPOSITE_WEIGHTS["page_kind_accuracy"] * page_kind_accuracy
    )


@dataclass(frozen=True)
class QuestionDiff:
    page_name: str
    number_label: str
    stem_cer_exact: float
    stem_cer_normalized: float
    choice_cer: float
    choice_count_match: bool
    type_match: bool
    stimulus_ref_match: bool
    box_iou: float
    answer_match: bool | None
    golden_stem: str
    pred_stem: str
    golden_choices: list[dict[str, str]]
    pred_choices: list[dict[str, str]]


@dataclass(frozen=True)
class PageMetrics:
    page_name: str
    golden_page_kind: str
    pred_page_kind: str | None
    page_kind_match: bool
    golden_question_count: int
    pred_question_count: int
    question_count_match: bool
    matched_question_count: int
    unmatched_golden_labels: list[str]
    extra_pred_labels: list[str]
    stem_cer_exact: float
    stem_cer_normalized: float
    choice_cer: float
    choice_count_match_rate: float
    type_accuracy: float
    stimulus_ref_accuracy: float
    stimulus_count_match: bool
    stimulus_content_cer_normalized: float
    stimulus_kind_accuracy: float
    question_box_iou: float
    golden_figure_count: int
    pred_figure_count: int
    matched_figure_count: int
    figure_precision: float
    figure_recall: float
    figure_mean_iou: float
    answer_accuracy: float | None
    golden_answer_count: int
    correct_answer_count: int
    valid_output: bool
    used_fallback: bool
    latency_ms: int
    cost_usd: Decimal
    error: str | None
    composite_score: float
    question_diffs: list[QuestionDiff] = field(default_factory=list)
    choice_question_count: int = 0
    golden_stimulus_count: int = 0
    matched_stimulus_count: int = 0


def score_page(  # noqa: PLR0913, PLR0915 -- collects all per-page metrics in one pass
    golden: dict[str, Any],
    pred: PageExtraction | None,
    *,
    page_name: str = "",
    latency_ms: int = 0,
    cost_usd: Decimal = Decimal(0),
    used_fallback: bool = False,
    error: str | None = None,
) -> PageMetrics:
    """Evaluate a single page's PageExtraction against its golden ground truth dict."""
    g_page_kind = str(golden["page_kind"])
    g_questions: list[dict[str, Any]] = list(golden.get("questions", []))
    g_stimuli: list[dict[str, Any]] = list(golden.get("stimuli", []))
    g_fig_boxes: list[list[float]] = [
        list(fig["box"]) for q in g_questions for fig in q.get("figures", [])
    ]
    g_ans_count = sum(1 for q in g_questions if q.get("answer") is not None)

    if pred is None:
        return PageMetrics(
            page_name=page_name,
            golden_page_kind=g_page_kind,
            pred_page_kind=None,
            page_kind_match=False,
            golden_question_count=len(g_questions),
            pred_question_count=0,
            question_count_match=False,
            matched_question_count=0,
            unmatched_golden_labels=[str(q["number_label"]) for q in g_questions],
            extra_pred_labels=[],
            stem_cer_exact=1.0 if g_questions else 0.0,
            stem_cer_normalized=1.0 if g_questions else 0.0,
            choice_cer=1.0 if g_questions else 0.0,
            choice_count_match_rate=0.0 if g_questions else 1.0,
            type_accuracy=0.0 if g_questions else 1.0,
            stimulus_ref_accuracy=0.0 if g_questions else 1.0,
            stimulus_count_match=False,
            stimulus_content_cer_normalized=1.0 if g_stimuli else 0.0,
            stimulus_kind_accuracy=0.0 if g_stimuli else 1.0,
            question_box_iou=0.0 if g_questions else 1.0,
            golden_figure_count=len(g_fig_boxes),
            pred_figure_count=0,
            matched_figure_count=0,
            figure_precision=0.0 if g_fig_boxes else 1.0,
            figure_recall=0.0 if g_fig_boxes else 1.0,
            figure_mean_iou=0.0,
            answer_accuracy=0.0 if g_ans_count > 0 else None,
            golden_answer_count=g_ans_count,
            correct_answer_count=0,
            valid_output=False,
            used_fallback=used_fallback,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            error=error or "No valid output",
            composite_score=0.0,
            question_diffs=[],
            choice_question_count=0,
            golden_stimulus_count=len(g_stimuli),
            matched_stimulus_count=0,
        )

    page_kind_match = pred.page_kind == g_page_kind
    stim_res = match_stimuli(g_stimuli, pred.stimuli)
    q_res = match_questions_by_label(g_questions, pred.questions)

    p_fig_boxes = [to_region_box(fig.box_2d) for q in pred.questions for fig in q.figures]
    fig_res = greedy_match_boxes(g_fig_boxes, p_fig_boxes)

    stem_exact_list: list[float] = []
    stem_norm_list: list[float] = []
    choice_cer_list: list[float] = []
    choice_count_matches: list[float] = []
    type_matches: list[float] = []
    stim_ref_matches: list[float] = []
    q_ious: list[float] = []
    ans_matches: list[bool] = []
    q_diffs: list[QuestionDiff] = []

    for g_q, p_q in q_res.matched:
        s_exact = cer_exact(str(g_q["stem"]), p_q.stem)
        s_norm = cer_normalized(str(g_q["stem"]), p_q.stem)
        c_cer, c_count_ok, has_choices = score_choices(g_q.get("choices", []), p_q.choices)
        t_ok = p_q.type == g_q["type"]
        g_sref = g_q.get("stimulus_ref")
        if g_sref is None:
            sref_ok = p_q.stimulus_ref is None
        else:
            mapped_ref = stim_res.ref_map.get(str(g_sref).strip())
            sref_ok = mapped_ref is not None and (p_q.stimulus_ref or "").strip() == mapped_ref
        q_iou = box_iou(g_q["box"], to_region_box(p_q.box_2d))
        ans_ok = score_answer(g_q.get("answer"), p_q)

        stem_exact_list.append(s_exact)
        stem_norm_list.append(s_norm)
        if has_choices:
            choice_cer_list.append(c_cer)
        choice_count_matches.append(1.0 if c_count_ok else 0.0)
        type_matches.append(1.0 if t_ok else 0.0)
        stim_ref_matches.append(1.0 if sref_ok else 0.0)
        q_ious.append(q_iou)
        if ans_ok is not None:
            ans_matches.append(ans_ok)

        q_diffs.append(
            QuestionDiff(
                page_name=page_name,
                number_label=str(g_q["number_label"]),
                stem_cer_exact=s_exact,
                stem_cer_normalized=s_norm,
                choice_cer=c_cer,
                choice_count_match=c_count_ok,
                type_match=t_ok,
                stimulus_ref_match=sref_ok,
                box_iou=q_iou,
                answer_match=ans_ok,
                golden_stem=str(g_q["stem"]),
                pred_stem=p_q.stem,
                golden_choices=[
                    {"label": str(c["label"]), "content": str(c["content"])}
                    for c in g_q.get("choices", [])
                ],
                pred_choices=[{"label": c.label, "content": c.content} for c in p_q.choices],
            )
        )

    has_g_q = len(g_questions) > 0
    matched_n = len(q_res.matched)
    if matched_n > 0:
        stem_cer_ex = sum(stem_exact_list) / matched_n
        stem_cer_nm = sum(stem_norm_list) / matched_n
        choice_cer_val = sum(choice_cer_list) / len(choice_cer_list) if choice_cer_list else 0.0
        choice_cnt_rate = sum(choice_count_matches) / matched_n
        type_acc = sum(type_matches) / matched_n
        sref_acc = sum(stim_ref_matches) / matched_n
        q_box_iou = sum(q_ious) / matched_n
    else:
        stem_cer_ex = 1.0 if has_g_q else 0.0
        stem_cer_nm = 1.0 if has_g_q else 0.0
        choice_cer_val = 1.0 if has_g_q else 0.0
        choice_cnt_rate = 0.0 if has_g_q else 1.0
        type_acc = 0.0 if has_g_q else 1.0
        sref_acc = 0.0 if has_g_q else 1.0
        q_box_iou = 0.0 if has_g_q else 1.0

    correct_ans = sum(1 for a in ans_matches if a)
    if g_ans_count > 0:
        ans_acc: float | None = correct_ans / g_ans_count
    else:
        ans_acc = None

    comp = compute_composite_score(
        stem_cer_normalized=stem_cer_nm,
        choice_cer=choice_cer_val,
        question_count_match=1.0 if q_res.exact_count_match else 0.0,
        type_accuracy=type_acc,
        figure_recall=fig_res.recall,
        question_box_iou=q_box_iou,
        page_kind_accuracy=1.0 if page_kind_match else 0.0,
    )

    return PageMetrics(
        page_name=page_name,
        golden_page_kind=g_page_kind,
        pred_page_kind=pred.page_kind,
        page_kind_match=page_kind_match,
        golden_question_count=len(g_questions),
        pred_question_count=len(pred.questions),
        question_count_match=q_res.exact_count_match,
        matched_question_count=matched_n,
        unmatched_golden_labels=[str(q["number_label"]) for q in q_res.unmatched_golden],
        extra_pred_labels=[q.number_label for q in q_res.extra_pred],
        stem_cer_exact=stem_cer_ex,
        stem_cer_normalized=stem_cer_nm,
        choice_cer=choice_cer_val,
        choice_count_match_rate=choice_cnt_rate,
        type_accuracy=type_acc,
        stimulus_ref_accuracy=sref_acc,
        stimulus_count_match=stim_res.count_match,
        stimulus_content_cer_normalized=stim_res.content_cer_normalized,
        stimulus_kind_accuracy=stim_res.kind_accuracy,
        question_box_iou=q_box_iou,
        golden_figure_count=len(g_fig_boxes),
        pred_figure_count=len(p_fig_boxes),
        matched_figure_count=len(fig_res.matches),
        figure_precision=fig_res.precision,
        figure_recall=fig_res.recall,
        figure_mean_iou=fig_res.mean_iou,
        answer_accuracy=ans_acc,
        golden_answer_count=g_ans_count,
        correct_answer_count=correct_ans,
        valid_output=True,
        used_fallback=used_fallback,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        error=error,
        composite_score=comp,
        question_diffs=q_diffs,
        choice_question_count=len(choice_cer_list),
        golden_stimulus_count=len(g_stimuli),
        matched_stimulus_count=len(stim_res.matched),
    )


def percentile_95(values: Sequence[int | float]) -> float:
    """Compute nearest-rank 95th percentile."""
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    idx = min(len(ordered) - 1, max(0, math.ceil(P95_QUANTILE * len(ordered)) - 1))
    return ordered[idx]


@dataclass(frozen=True)
class ModelMetrics:
    model: str
    page_count: int
    page_kind_accuracy: float
    question_count_match_rate: float
    total_golden_questions: int
    total_pred_questions: int
    total_matched_questions: int
    total_unmatched_golden: int
    total_extra_pred: int
    stem_cer_exact: float
    stem_cer_normalized: float
    choice_cer: float
    choice_count_match_rate: float
    type_accuracy: float
    stimulus_ref_accuracy: float
    stimulus_count_match_rate: float
    stimulus_content_cer_normalized: float
    stimulus_kind_accuracy: float
    question_box_iou: float
    figure_precision: float
    figure_recall: float
    figure_mean_iou: float
    answer_accuracy: float | None
    valid_output_rate: float
    fallback_rate: float
    mean_latency_ms: float
    p95_latency_ms: float
    total_cost_usd: Decimal
    per_page_cost_usd: Decimal
    composite_score: float
    pages: list[PageMetrics]
    worst_questions: list[QuestionDiff]


def aggregate_model_metrics(  # noqa: PLR0915 -- computes all model-level aggregate metrics
    model: str, pages: Sequence[PageMetrics]
) -> ModelMetrics:
    """Aggregate per-page metrics into model-level accuracy, ops, and composite scores."""
    n_pages = len(pages)
    if n_pages == 0:
        return ModelMetrics(
            model=model,
            page_count=0,
            page_kind_accuracy=0.0,
            question_count_match_rate=0.0,
            total_golden_questions=0,
            total_pred_questions=0,
            total_matched_questions=0,
            total_unmatched_golden=0,
            total_extra_pred=0,
            stem_cer_exact=1.0,
            stem_cer_normalized=1.0,
            choice_cer=1.0,
            choice_count_match_rate=0.0,
            type_accuracy=0.0,
            stimulus_ref_accuracy=0.0,
            stimulus_count_match_rate=0.0,
            stimulus_content_cer_normalized=1.0,
            stimulus_kind_accuracy=0.0,
            question_box_iou=0.0,
            figure_precision=0.0,
            figure_recall=0.0,
            figure_mean_iou=0.0,
            answer_accuracy=None,
            valid_output_rate=0.0,
            fallback_rate=0.0,
            mean_latency_ms=0.0,
            p95_latency_ms=0.0,
            total_cost_usd=Decimal(0),
            per_page_cost_usd=Decimal(0),
            composite_score=0.0,
            pages=[],
            worst_questions=[],
        )

    page_kind_acc = sum(1.0 for p in pages if p.page_kind_match) / n_pages
    q_count_match = sum(1.0 for p in pages if p.question_count_match) / n_pages
    stim_count_match = sum(1.0 for p in pages if p.stimulus_count_match) / n_pages

    total_g_q = sum(p.golden_question_count for p in pages)
    total_p_q = sum(p.pred_question_count for p in pages)
    total_m_q = sum(p.matched_question_count for p in pages)
    total_unmatched = sum(len(p.unmatched_golden_labels) for p in pages)
    total_extra = sum(len(p.extra_pred_labels) for p in pages)

    all_diffs = [diff for p in pages for diff in p.question_diffs]
    if total_m_q > 0:
        stem_cer_ex = sum(d.stem_cer_exact for d in all_diffs) / total_m_q
        stem_cer_nm = sum(d.stem_cer_normalized for d in all_diffs) / total_m_q
        choice_cnt_rate = sum(1.0 if d.choice_count_match else 0.0 for d in all_diffs) / total_m_q
        type_acc = sum(1.0 if d.type_match else 0.0 for d in all_diffs) / total_m_q
        sref_acc = sum(1.0 if d.stimulus_ref_match else 0.0 for d in all_diffs) / total_m_q
        q_box_iou = sum(d.box_iou for d in all_diffs) / total_m_q
        total_choice_qs = sum(p.choice_question_count for p in pages)
        choice_cer_val = (
            sum(p.choice_cer * p.choice_question_count for p in pages) / total_choice_qs
            if total_choice_qs > 0
            else 0.0
        )
    else:
        has_g_q = total_g_q > 0
        stem_cer_ex = 1.0 if has_g_q else 0.0
        stem_cer_nm = 1.0 if has_g_q else 0.0
        choice_cer_val = 1.0 if has_g_q else 0.0
        choice_cnt_rate = 0.0 if has_g_q else 1.0
        type_acc = 0.0 if has_g_q else 1.0
        sref_acc = 0.0 if has_g_q else 1.0
        q_box_iou = 0.0 if has_g_q else 1.0

    total_m_stim = sum(p.matched_stimulus_count for p in pages)
    total_g_stim = sum(p.golden_stimulus_count for p in pages)
    if total_m_stim > 0:
        stim_cer = (
            sum(p.stimulus_content_cer_normalized * p.matched_stimulus_count for p in pages)
            / total_m_stim
        )
        stim_kind_acc = (
            sum(p.stimulus_kind_accuracy * p.matched_stimulus_count for p in pages) / total_m_stim
        )
    else:
        stim_cer = 1.0 if total_g_stim > 0 else 0.0
        stim_kind_acc = 0.0 if total_g_stim > 0 else 1.0

    total_g_fig = sum(p.golden_figure_count for p in pages)
    total_p_fig = sum(p.pred_figure_count for p in pages)
    total_m_fig = sum(p.matched_figure_count for p in pages)
    if total_g_fig == 0 and total_p_fig == 0:
        fig_prec = 1.0
        fig_rec = 1.0
    elif total_g_fig == 0:
        fig_prec = 0.0
        fig_rec = 1.0
    elif total_p_fig == 0:
        fig_prec = 0.0
        fig_rec = 0.0
    else:
        fig_prec = total_m_fig / total_p_fig
        fig_rec = total_m_fig / total_g_fig
    fig_mean_iou = (
        sum(p.figure_mean_iou * p.matched_figure_count for p in pages) / total_m_fig
        if total_m_fig > 0
        else 0.0
    )

    total_g_ans = sum(p.golden_answer_count for p in pages)
    total_c_ans = sum(p.correct_answer_count for p in pages)
    ans_acc: float | None = total_c_ans / total_g_ans if total_g_ans > 0 else None

    valid_rate = sum(1.0 for p in pages if p.valid_output) / n_pages
    fallback_rate = sum(1.0 for p in pages if p.used_fallback) / n_pages
    latencies = [p.latency_ms for p in pages]
    mean_lat = sum(latencies) / n_pages
    p95_lat = percentile_95(latencies)
    total_cost = sum((p.cost_usd for p in pages), Decimal(0))
    per_page_cost = total_cost / Decimal(n_pages)

    comp = compute_composite_score(
        stem_cer_normalized=stem_cer_nm,
        choice_cer=choice_cer_val,
        question_count_match=q_count_match,
        type_accuracy=type_acc,
        figure_recall=fig_rec,
        question_box_iou=q_box_iou,
        page_kind_accuracy=page_kind_acc,
    )

    worst_questions = sorted(
        all_diffs,
        key=lambda d: (-(d.stem_cer_normalized + d.choice_cer), -d.stem_cer_exact, d.page_name),
    )[:TOP_WORST_QUESTIONS]

    return ModelMetrics(
        model=model,
        page_count=n_pages,
        page_kind_accuracy=page_kind_acc,
        question_count_match_rate=q_count_match,
        total_golden_questions=total_g_q,
        total_pred_questions=total_p_q,
        total_matched_questions=total_m_q,
        total_unmatched_golden=total_unmatched,
        total_extra_pred=total_extra,
        stem_cer_exact=stem_cer_ex,
        stem_cer_normalized=stem_cer_nm,
        choice_cer=choice_cer_val,
        choice_count_match_rate=choice_cnt_rate,
        type_accuracy=type_acc,
        stimulus_ref_accuracy=sref_acc,
        stimulus_count_match_rate=stim_count_match,
        stimulus_content_cer_normalized=stim_cer,
        stimulus_kind_accuracy=stim_kind_acc,
        question_box_iou=q_box_iou,
        figure_precision=fig_prec,
        figure_recall=fig_rec,
        figure_mean_iou=fig_mean_iou,
        answer_accuracy=ans_acc,
        valid_output_rate=valid_rate,
        fallback_rate=fallback_rate,
        mean_latency_ms=mean_lat,
        p95_latency_ms=p95_lat,
        total_cost_usd=total_cost,
        per_page_cost_usd=per_page_cost,
        composite_score=comp,
        pages=list(pages),
        worst_questions=worst_questions,
    )
