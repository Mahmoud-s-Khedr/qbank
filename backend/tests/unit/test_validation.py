"""Unit tests for all 12 validation rules, confidence/status math, verifier, and classifier."""

from io import BytesIO
from uuid import uuid4

from PIL import Image

from qbank.config import Settings
from qbank.llm import FakeLLMClient
from qbank.models import (
    Language,
    Organization,
    PageKind,
    PageStatus,
    Question,
    Source,
    SourcePage,
    Stimulus,
)
from qbank.pipeline.classify import (
    BATCH_SIZE,
    apply_classifications,
    classify_batch,
    pending_classification_questions,
)
from qbank.pipeline.schema import MAX_CLASSIFY_TAGS, Discrepancy, QuestionClassification
from qbank.pipeline.validate import (
    RULES,
    Issue,
    ValidationContext,
    compute_confidence,
    compute_status,
    duplicate_of,
    empty_stem,
    evaluate_question,
    figure_referenced_not_attached,
    latex_invalid,
    low_confidence,
    mcq_duplicate_labels,
    mcq_label_sequence,
    mcq_too_few_choices,
    missing_answer,
    numbering_gap,
    stimulus_orphan,
    truncated_stem,
)
from qbank.pipeline.verify import (
    apply_discrepancies,
    get_verify_policy,
    select_pages_to_verify,
    verify_page,
)

EXPECTED_BATCH_SIZE = 20
HUMAN_DIFFICULTY = 5
AI_DIFFICULTY_MED = 3
AI_DIFFICULTY_EASY = 2
BASE_MODEL_CONFIDENCE = 0.9


def make_question(**overrides: object) -> Question:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "org_id": uuid4(),
        "subject_id": uuid4(),
        "source_id": uuid4(),
        "position": 0,
        "number_label": "1",
        "type": "mcq_single",
        "stem": "ما هي عاصمة جمهورية مصر العربية؟",
        "choices": [
            {"label": "أ", "content": "القاهرة", "is_correct": True, "pinned": False},
            {"label": "ب", "content": "الإسكندرية", "is_correct": False, "pinned": False},
            {"label": "ج", "content": "أسوان", "is_correct": False, "pinned": False},
            {"label": "د", "content": "الأقصر", "is_correct": False, "pinned": False},
        ],
        "answer": None,
        "language": Language.ar,
        "regions": [{"page": "page-1", "box": [0.1, 0.1, 0.9, 0.3]}],
        "status": "draft",
        "confidence": BASE_MODEL_CONFIDENCE,
        "tags": [],
        "metadata_json": {"model_confidence": BASE_MODEL_CONFIDENCE},
    }
    defaults.update(overrides)
    return Question(**defaults)


def test_rule_registry_contains_all_twelve_rules() -> None:
    expected = {
        "mcq_too_few_choices",
        "mcq_duplicate_labels",
        "mcq_label_sequence",
        "missing_answer",
        "figure_referenced_not_attached",
        "empty_stem",
        "truncated_stem",
        "latex_invalid",
        "numbering_gap",
        "low_confidence",
        "duplicate_of",
        "stimulus_orphan",
    }
    assert set(RULES.keys()) == expected


def test_rule_mcq_too_few_choices() -> None:
    ctx = ValidationContext()
    bad = make_question(choices=[{"label": "أ", "content": "خيار واحد", "is_correct": True}])
    issues = mcq_too_few_choices(bad, ctx)
    assert len(issues) == 1
    assert issues[0].code == "mcq_too_few_choices"
    assert issues[0].severity == "error"

    good = make_question()
    assert mcq_too_few_choices(good, ctx) == []

    essay = make_question(type="essay", choices=[])
    assert mcq_too_few_choices(essay, ctx) == []


def test_rule_mcq_duplicate_labels() -> None:
    ctx = ValidationContext()
    bad = make_question(
        choices=[
            {"label": "أ", "content": "الأول", "is_correct": True},
            {"label": "\u0627", "content": "الثاني", "is_correct": False},
            {"label": "ج", "content": "الثالث", "is_correct": False},
        ]
    )
    issues = mcq_duplicate_labels(bad, ctx)
    assert len(issues) == 1
    assert issues[0].code == "mcq_duplicate_labels"
    assert issues[0].severity == "error"

    good = make_question()
    assert mcq_duplicate_labels(good, ctx) == []


def test_rule_mcq_label_sequence() -> None:
    ctx = ValidationContext()
    bad = make_question(
        choices=[
            {"label": "أ", "content": "الأول", "is_correct": True},
            {"label": "ب", "content": "الثاني", "is_correct": False},
            {"label": "د", "content": "الرابع", "is_correct": False},
        ]
    )
    issues = mcq_label_sequence(bad, ctx)
    assert len(issues) == 1
    assert issues[0].code == "mcq_label_sequence"
    assert issues[0].severity == "warning"

    good_ar = make_question()
    assert mcq_label_sequence(good_ar, ctx) == []

    good_en = make_question(
        choices=[
            {"label": "A", "content": "One", "is_correct": True},
            {"label": "B", "content": "Two", "is_correct": False},
            {"label": "C", "content": "Three", "is_correct": False},
        ]
    )
    assert mcq_label_sequence(good_en, ctx) == []

    good_num = make_question(
        choices=[
            {"label": "\u0661", "content": "واحد", "is_correct": True},
            {"label": "\u0662", "content": "اثنان", "is_correct": False},
        ]
    )
    assert mcq_label_sequence(good_num, ctx) == []


def test_rule_missing_answer() -> None:
    no_ans = make_question(
        choices=[
            {"label": "أ", "content": "الأول", "is_correct": False},
            {"label": "ب", "content": "الثاني", "is_correct": False},
        ],
        answer=None,
    )
    warn_issues = missing_answer(no_ans, ValidationContext(answer_key_matched=False))
    assert len(warn_issues) == 1
    assert warn_issues[0].code == "missing_answer"
    assert warn_issues[0].severity == "warning"

    err_issues = missing_answer(no_ans, ValidationContext(answer_key_matched=True))
    assert len(err_issues) == 1
    assert err_issues[0].code == "missing_answer"
    assert err_issues[0].severity == "error"

    with_choice_ans = make_question()
    assert missing_answer(with_choice_ans, ValidationContext(answer_key_matched=True)) == []

    with_text_ans = make_question(type="short_answer", choices=[], answer="القاهرة")
    assert missing_answer(with_text_ans, ValidationContext(answer_key_matched=True)) == []


def test_rule_figure_referenced_not_attached() -> None:
    ctx = ValidationContext()
    bad_ar = make_question(stem="من الشكل المقابل احسب قيمة التيار الكهربي.")
    issues_ar = figure_referenced_not_attached(bad_ar, ctx)
    assert len(issues_ar) == 1
    assert issues_ar[0].code == "figure_referenced_not_attached"
    assert issues_ar[0].severity == "error"

    bad_en = make_question(stem="Refer to the diagram below to find the angle.")
    issues_en = figure_referenced_not_attached(bad_en, ctx)
    assert len(issues_en) == 1
    assert issues_en[0].code == "figure_referenced_not_attached"

    good_in_stem = make_question(
        stem="من الشكل المقابل احسب التيار\n![](asset:123e4567-e89b-12d3-a456-426614174000)"
    )
    assert figure_referenced_not_attached(good_in_stem, ctx) == []

    stim_id = uuid4()
    stim = Stimulus(
        id=stim_id,
        org_id=uuid4(),
        source_id=uuid4(),
        kind="figure",
        content="![](asset:123e4567-e89b-12d3-a456-426614174000)",
        regions=[],
    )
    good_in_stim = make_question(
        stem="في الصورة المقابلة ما نوع التفاعل؟",
        stimulus_id=stim_id,
    )
    assert figure_referenced_not_attached(good_in_stim, ValidationContext(stimuli=[stim])) == []


def test_rule_empty_stem() -> None:
    ctx = ValidationContext()
    bad = make_question(stem="   \n  ")
    issues = empty_stem(bad, ctx)
    assert len(issues) == 1
    assert issues[0].code == "empty_stem"
    assert issues[0].severity == "error"

    good = make_question()
    assert empty_stem(good, ctx) == []


def test_rule_truncated_stem() -> None:
    ctx = ValidationContext()
    short_q = make_question(stem="ما هو")
    issues_short = truncated_stem(short_q, ctx)
    assert len(issues_short) == 1
    assert issues_short[0].code == "truncated_stem"
    assert issues_short[0].severity == "warning"

    comma_q = make_question(stem="إذا كانت سرعة الجسم تساوي عشرة أمتار في الثانية،")
    assert len(truncated_stem(comma_q, ctx)) == 1

    waw_q = make_question(stem="احسب القوة المؤثرة على الجسم الأول و")
    assert len(truncated_stem(waw_q, ctx)) == 1

    midword_q = make_question(stem="Compute the gravitational accel-")
    assert len(truncated_stem(midword_q, ctx)) == 1

    fill_blank_short = make_question(type="fill_blank", stem="س = ____")
    assert truncated_stem(fill_blank_short, ctx) == []

    good = make_question()
    assert truncated_stem(good, ctx) == []


def test_rule_latex_invalid() -> None:
    ctx = ValidationContext()
    unclosed_dollar = make_question(stem="احسب قيمة $x^2 + 5 في المعادلة التالية.")
    issues1 = latex_invalid(unclosed_dollar, ctx)
    assert len(issues1) == 1
    assert issues1[0].code == "latex_invalid"
    assert issues1[0].severity == "error"

    unbalanced_braces = make_question(stem="احسب قيمة $\\frac{x + 1}{2$ في المعادلة.")
    issues2 = latex_invalid(unbalanced_braces, ctx)
    assert len(issues2) == 1
    assert issues2[0].code == "latex_invalid"

    valid_math = make_question(stem="احسب قيمة $\\frac{x^2 + 1}{2}$ و $$\\ce{H2O -> H+ + OH-}$$")
    assert latex_invalid(valid_math, ctx) == []


def test_rule_numbering_gap() -> None:
    q1 = make_question(number_label="3")
    q2 = make_question(number_label="5")
    ctx = ValidationContext(questions=[q1, q2])

    assert numbering_gap(q1, ctx) == []
    issues = numbering_gap(q2, ctx)
    assert len(issues) == 1
    assert issues[0].code == "numbering_gap"
    assert issues[0].severity == "warning"

    q_seq = make_question(number_label="4")
    ctx_ok = ValidationContext(questions=[q1, q_seq, q2])
    assert numbering_gap(q2, ctx_ok) == []


def test_rule_low_confidence() -> None:
    ctx = ValidationContext()
    low = make_question(confidence=0.55, metadata_json={"model_confidence": 0.55})
    issues = low_confidence(low, ctx)
    assert len(issues) == 1
    assert issues[0].code == "low_confidence"
    assert issues[0].severity == "warning"

    high = make_question(confidence=0.6, metadata_json={"model_confidence": 0.6})
    assert low_confidence(high, ctx) == []


def test_rule_duplicate_of() -> None:
    ctx = ValidationContext()
    orig_id = uuid4()
    dup = make_question(duplicate_of_id=orig_id, metadata_json={"duplicate_similarity": 0.95})
    issues = duplicate_of(dup, ctx)
    assert len(issues) == 1
    assert issues[0].code == "duplicate_of"
    assert issues[0].severity == "warning"
    assert issues[0].details["duplicate_of_id"] == str(orig_id)

    unique = make_question(duplicate_of_id=None)
    assert duplicate_of(unique, ctx) == []


def test_rule_stimulus_orphan() -> None:
    orphan = Stimulus(
        id=uuid4(),
        org_id=uuid4(),
        source_id=uuid4(),
        kind="passage",
        content="نص القراءة",
        regions=[{"page": "page-1", "box": [0.1, 0.1, 0.9, 0.2]}],
    )
    q = make_question(stimulus_id=None)
    ctx_orphan = ValidationContext(questions=[q], stimuli=[orphan])
    issues = stimulus_orphan(q, ctx_orphan)
    assert len(issues) == 1
    assert issues[0].code == "stimulus_orphan"
    assert issues[0].severity == "warning"

    q_linked = make_question(stimulus_id=orphan.id)
    ctx_linked = ValidationContext(questions=[q_linked], stimuli=[orphan])
    assert stimulus_orphan(q_linked, ctx_linked) == []


def test_confidence_and_status_calculation() -> None:
    err = Issue(code="empty_stem", severity="error", message="err")
    warn = Issue(code="truncated_stem", severity="warning", message="warn")

    assert compute_confidence(BASE_MODEL_CONFIDENCE, []) == BASE_MODEL_CONFIDENCE
    assert round(compute_confidence(BASE_MODEL_CONFIDENCE, [warn]), 4) == round(
        BASE_MODEL_CONFIDENCE * 0.85, 4
    )
    assert round(compute_confidence(BASE_MODEL_CONFIDENCE, [err, warn]), 4) == round(
        BASE_MODEL_CONFIDENCE * 0.5 * 0.85, 4
    )
    assert compute_confidence(1.5, []) == 1.0

    # No issues and confidence >= 0.75 -> stays 'draft'
    assert compute_status(0.8, [], review_threshold=0.75) == "draft"
    # Any error -> 'needs_review' even if confidence >= 0.75
    assert compute_status(0.8, [err], review_threshold=0.75) == "needs_review"
    # Warning only, confidence < 0.75 -> 'needs_review'
    assert compute_status(0.74, [warn], review_threshold=0.75) == "needs_review"
    # Warning only, confidence >= 0.75 -> stays 'draft'
    assert compute_status(0.85, [warn], review_threshold=0.75) == "draft"


def test_verifier_policy_routing_and_discrepancies() -> None:
    p1_id, p2_id = uuid4(), uuid4()
    p1 = SourcePage(
        id=p1_id,
        source_id=uuid4(),
        page_number=1,
        page_kind=PageKind.questions,
        status=PageStatus.extracted,
    )
    p2 = SourcePage(
        id=p2_id,
        source_id=uuid4(),
        page_number=2,
        page_kind=PageKind.questions,
        status=PageStatus.extracted,
    )
    q_high = make_question(
        number_label="1",
        confidence=BASE_MODEL_CONFIDENCE,
        regions=[{"page": str(p1_id), "box": [0.1, 0.1, 0.5, 0.5]}],
    )
    q_low = make_question(
        number_label="2",
        confidence=0.65,
        regions=[{"page": str(p2_id), "box": [0.1, 0.1, 0.5, 0.5]}],
    )

    src_default = Source(pipeline_config={})
    assert get_verify_policy(src_default) == "low_confidence"
    assert get_verify_policy(Source(pipeline_config={"verify": "off"})) == "off"
    assert get_verify_policy(Source(pipeline_config={"verify": "all"})) == "all"

    assert select_pages_to_verify([p1, p2], [q_high, q_low], policy="off") == []
    assert select_pages_to_verify(
        [p1, p2], [q_high, q_low], policy="low_confidence", review_threshold=0.75
    ) == [p2]
    assert select_pages_to_verify(
        [p1, p2], [q_high, q_low], policy="all", review_threshold=0.75
    ) == [p1, p2]

    fake = FakeLLMClient(Settings())
    fake.queue(
        "verify",
        [
            {
                "number_label": "2",
                "field": "stem",
                "problem": "Missing word at end of stem",
                "suggested_fix": "ما هي عاصمة مصر؟",
                "severity": "error",
            }
        ],
    )
    buf = BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    res, _ = verify_page(fake, buf.getvalue(), [q_low])
    assert len(res.parsed.discrepancies) == 1
    assert fake.calls[0]["model"] == "openai/gpt-6-luna"

    original_stem = q_low.stem
    affected = apply_discrepancies(
        [q_low],
        [
            Discrepancy(
                number_label="2",
                field="stem",
                problem="Missing word at end of stem",
                suggested_fix="ما هي عاصمة مصر؟",
                severity="error",
            )
        ],
    )
    assert q_low.id in affected
    assert q_low.stem == original_stem
    issues = evaluate_question(q_low, ValidationContext(questions=[q_low]))
    verifier_issues = [i for i in issues if i.code == "verifier_stem"]
    assert len(verifier_issues) == 1
    assert verifier_issues[0].severity == "error"
    assert verifier_issues[0].details["suggested_fix"] == "ما هي عاصمة مصر؟"


def test_classification_batching_and_human_difficulty_preserved() -> None:
    assert BATCH_SIZE == EXPECTED_BATCH_SIZE
    q_human = make_question(
        difficulty=HUMAN_DIFFICULTY,
        difficulty_reason="تقدير المعلم",
        difficulty_source="human",
        tags=["بلاغة"],
    )
    q_ai = make_question(difficulty=None, difficulty_source=None)

    pending = pending_classification_questions([q_human, q_ai])
    assert pending == [q_ai]

    # Even if apply_classifications receives an entry for a human-difficulty question,
    # human values are preserved.
    items = [
        QuestionClassification(
            id=str(q_human.id),
            difficulty=1,
            difficulty_reason="سهل جدا",
            tags=["نحو"],
        ),
        QuestionClassification(
            id=str(q_ai.id),
            difficulty=AI_DIFFICULTY_MED,
            difficulty_reason="يتطلب خطوتين للحل في المعادلة",
            tags=["جبر", "معادلات", "ثانوي", "رابع_يحذف"],
        ),
    ]
    updated = apply_classifications([q_human, q_ai], items)
    assert updated == 1
    assert q_human.difficulty == HUMAN_DIFFICULTY
    assert q_human.difficulty_reason == "تقدير المعلم"
    assert q_human.difficulty_source == "human"
    assert q_human.tags == ["بلاغة"]

    assert q_ai.difficulty == AI_DIFFICULTY_MED
    assert q_ai.difficulty_source == "ai"
    assert len(q_ai.tags) == MAX_CLASSIFY_TAGS

    fake = FakeLLMClient(Settings())
    fake.queue(
        "classify",
        [
            {
                "id": str(q_ai.id),
                "difficulty": AI_DIFFICULTY_EASY,
                "difficulty_reason": "سؤال مباشر",
                "tags": ["تاريخ"],
            }
        ],
    )
    res, _ = classify_batch(fake, [q_ai])
    assert len(res.parsed.items) == 1
    assert res.parsed.items[0].difficulty == AI_DIFFICULTY_EASY


def test_verify_policy_organization_default_and_source_override() -> None:
    org = Organization(name="Test", settings={"verify_policy": "all"})
    assert get_verify_policy(Source(pipeline_config={}), org) == "all"
    assert get_verify_policy(Source(pipeline_config={"verify": "off"}), org) == "off"


def test_rule_figure_ignores_rhetorical_image_phrases() -> None:
    """«الصورة البيانية» is a figure of speech in Arabic rhetoric, not a picture (seen live)."""
    ctx = ValidationContext()
    for stem in (
        "ميّز الصورة البيانية في قول الشاعر: «رفعته في الوَرَى شيم» في البيت الثاني.",
        "ميز نوع الصورة البيانية في قول الشاعر: (نَجِدَ الأَمَانَ مَعَ المُنَى)",
        "دلل على استخدام الشاعر للصورة الكلية في الأبيات.",
        "اشرح الصور البيانية في النص.",
    ):
        assert figure_referenced_not_attached(make_question(stem=stem), ctx) == [], stem
    # A real picture reference in the same question is still caught.
    mixed = make_question(stem="ميز الصورة البيانية ثم انظر إلى الشكل المقابل.")
    assert len(figure_referenced_not_attached(mixed, ctx)) == 1
