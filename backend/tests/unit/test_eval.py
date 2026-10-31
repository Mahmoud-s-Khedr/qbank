"""Unit tests for qbank.eval metrics, cost estimation, budget guards, and CLI reporting."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import qbank.eval.cli as eval_cli
from qbank.eval import (
    aggregate_model_metrics,
    box_iou,
    cer,
    cer_exact,
    cer_normalized,
    compute_composite_score,
    estimate_eval_cost,
    greedy_match_boxes,
    levenshtein_distance,
    main,
    match_questions_by_label,
    match_stimuli,
    normalize_arabic,
    run_eval,
    score_page,
)
from qbank.llm import BudgetExceeded, FakeLLMClient, LLMOutputInvalid, LLMResult, ModelNotAllowed
from qbank.pipeline.schema import PageExtraction, Question, Stimulus


def _make_pred_question(**overrides: Any) -> Question:
    base: dict[str, Any] = {
        "number_label": "1",
        "type": "mcq_single",
        "stem": "ما عاصمة مصر؟",
        "choices": [
            {"label": "أ", "content": "القاهرة"},
            {"label": "ب", "content": "الإسكندرية"},
        ],
        "answer": {"labels": ["أ"], "text": None},
        "stimulus_ref": None,
        "figures": [],
        "box_2d": (100, 100, 500, 800),
        "continues_from_previous": False,
        "continues_on_next": False,
        "confidence": 0.95,
    }
    base.update(overrides)
    return Question.model_validate(base)


def _make_golden_page(page_num: int = 1, *, with_figure: bool = True) -> dict[str, Any]:
    return {
        "image": f"pages/p{page_num:03d}.png",
        "source_pdf": "test-exams.pdf",
        "page_number": page_num,
        "page_kind": "questions",
        "headings": [{"level": "exam", "text": "الاختبار الأول", "box": [0.1, 0.02, 0.9, 0.08]}],
        "stimuli": [
            {
                "ref": "s1",
                "kind": "poem",
                "intro": "قال الشاعر:",
                "content": "أَلا لَيتَ الشَبابَ يَعُودُ يَوماً ... فَأُخبِرَهُ بِما فَعَلَ المَشيبُ",
                "box": [0.1, 0.1, 0.9, 0.25],
                "continues_from_previous": False,
                "continues_on_next": False,
            }
        ],
        "questions": [
            {
                "number_label": "1",
                "type": "mcq_single",
                "stem": "مَا الغَرَضُ البَلَاغِيُّ فِي البَيْتِ؟",
                "choices": [
                    {"label": "أ", "content": "التَّمَنِّي"},
                    {"label": "ب", "content": "التَّرَجِّي"},
                ],
                "answer": {"labels": ["أ"]},
                "stimulus_ref": "s1",
                "figures": (
                    [{"box": [0.2, 0.3, 0.6, 0.5], "kind": "diagram"}] if with_figure else []
                ),
                "box": [0.1, 0.3, 0.8, 0.6],
                "continues_from_previous": False,
                "continues_on_next": False,
            },
            {
                "number_label": "2",
                "type": "essay",
                "stem": "اشْرَحِ الصُّورَةَ البَيَانِيَّةَ.",
                "choices": [],
                "answer": {"text": "استعارة مكنية"},
                "stimulus_ref": None,
                "figures": [],
                "box": [0.1, 0.65, 0.8, 0.85],
                "continues_from_previous": False,
                "continues_on_next": False,
            },
        ],
        "notes": None,
    }


def _make_pred_page(*, confidence: float = 0.95, stem_q1: str | None = None) -> dict[str, Any]:
    return {
        "page_kind": "questions",
        "headings": [{"level": "exam", "text": "الاختبار الأول", "box_2d": [20, 100, 80, 900]}],
        "stimuli": [
            {
                "ref": "poem_1",
                "kind": "poem",
                "intro": "قال الشاعر:",
                "content": "الا ليت الشباب يعود يوما ... فاخبره بما فعل المشيب",
                "box_2d": [100, 100, 250, 900],
                "continues_from_previous": False,
                "continues_on_next": False,
            }
        ],
        "questions": [
            {
                "number_label": "1",
                "type": "mcq_single",
                "stem": stem_q1 or "ما الغرض البلاغي في البيت؟",
                "choices": [
                    {"label": "أ", "content": "التمني"},
                    {"label": "ب", "content": "الترجي"},
                ],
                "answer": {"labels": ["أ"], "text": None},
                "stimulus_ref": "poem_1",
                "figures": [{"box_2d": [300, 200, 500, 600], "kind": "diagram"}],
                "box_2d": [300, 100, 600, 800],
                "continues_from_previous": False,
                "continues_on_next": False,
                "confidence": confidence,
            },
            {
                "number_label": "2",
                "type": "essay",
                "stem": "اشرح الصوره البيانيه.",
                "choices": [],
                "answer": {"labels": [], "text": "إستعارة مكنية"},
                "stimulus_ref": None,
                "figures": [],
                "box_2d": [650, 100, 850, 800],
                "continues_from_previous": False,
                "continues_on_next": False,
                "confidence": confidence,
            },
        ],
        "answer_key_entries": [],
        "page_confidence": confidence,
        "notes": "",
    }


def _write_synthetic_golden_set(golden_dir: Path) -> None:
    pages_dir = golden_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for idx in (1, 2):
        img_path = pages_dir / f"p{idx:03d}.png"
        Image.new("RGB", (200, 300), color="white").save(img_path, format="PNG")
        golden_json = _make_golden_page(idx, with_figure=(idx == 1))
        (golden_dir / f"p{idx:03d}.json").write_text(
            json.dumps(golden_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def test_cer_and_arabic_normalization() -> None:
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("abc", "") == 3  # noqa: PLR2004
    assert levenshtein_distance("", "xyz") == 3  # noqa: PLR2004
    assert cer("", "") == 0.0
    assert cer("", "غير فارغ") == 1.0
    assert cer("النص", "") == 1.0
    assert cer("النص", "النص") == 0.0

    with_tashkeel = "مَا الغَرَضُ البَلَاغِيُّ فِي القَصِيدَةِ وَالإِيمَانِ؟"
    without_tashkeel = "ما   الغرض البلاغي   فى القصيده والايمان؟"

    assert cer_exact(with_tashkeel, without_tashkeel) > 0.2  # noqa: PLR2004
    assert normalize_arabic("الـكـتـابُ الأَوَّلُ فِي المَدْرَسَةِ الكُبْرَى") == "الكتاب الاول في المدرسه الكبري"
    assert cer_normalized(with_tashkeel, without_tashkeel) == 0.0


def test_box_iou_edge_cases_and_greedy_matching() -> None:
    assert box_iou([0.1, 0.1, 0.5, 0.5], [0.1, 0.1, 0.5, 0.5]) == pytest.approx(1.0)
    assert box_iou([0.0, 0.0, 0.2, 0.2], [0.3, 0.3, 0.5, 0.5]) == 0.0
    # Touching edge only -> 0 intersection area
    assert box_iou([0.0, 0.0, 0.5, 0.5], [0.5, 0.0, 1.0, 0.5]) == 0.0
    # Degenerate zero-area boxes
    assert box_iou([0.5, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5]) == 0.0
    assert box_iou([0.1, 0.2], [0.1, 0.2, 0.3, 0.4]) == 0.0
    # Partial overlap: two 0.5x0.5 boxes overlapping in 0.25x0.25 -> 0.0625 / 0.4375 = 1/7
    assert box_iou([0.0, 0.0, 0.5, 0.5], [0.25, 0.25, 0.75, 0.75]) == pytest.approx(1.0 / 7.0)

    # Greedy matching
    g_boxes = [[0.0, 0.0, 0.4, 0.4], [0.5, 0.5, 0.9, 0.9]]
    p_boxes = [
        [0.02, 0.02, 0.4, 0.4],  # high IoU with g_boxes[0]
        [0.0, 0.0, 0.3, 0.3],  # lower IoU with g_boxes[0], shouldn't steal match
        [0.8, 0.8, 0.95, 0.95],  # IoU < 0.5 with g_boxes[1]
    ]
    res = greedy_match_boxes(g_boxes, p_boxes, iou_threshold=0.5)
    assert len(res.matches) == 1
    assert res.matches[0][0] == 0
    assert res.matches[0][1] == 0
    assert res.unmatched_golden == [1]
    assert res.unmatched_pred == [1, 2]
    assert res.precision == pytest.approx(1.0 / 3.0)
    assert res.recall == pytest.approx(0.5)
    assert res.mean_iou == pytest.approx(res.matches[0][2])

    empty_res = greedy_match_boxes([], [])
    assert empty_res.precision == 1.0
    assert empty_res.recall == 1.0
    assert empty_res.mean_iou == 0.0


def test_question_matching_and_composite_score() -> None:
    golden_qs = [
        {"number_label": "1", "stem": "س1"},
        {"number_label": "2", "stem": "س2"},
        {"number_label": "3", "stem": "س3"},
    ]
    pred_qs = [
        _make_pred_question(number_label="1", stem="س1"),
        _make_pred_question(number_label="3", stem="س3"),
        _make_pred_question(number_label="4", stem="س4"),
        _make_pred_question(number_label="1", stem="مكرر"),
    ]
    q_match = match_questions_by_label(golden_qs, pred_qs)
    assert [g["number_label"] for g, _ in q_match.matched] == ["1", "3"]
    assert [g["number_label"] for g in q_match.unmatched_golden] == ["2"]
    assert [p.number_label for p in q_match.extra_pred] == ["4", "1"]
    assert q_match.exact_count_match is False

    perfect = compute_composite_score(
        stem_cer_normalized=0.0,
        choice_cer=0.0,
        question_count_match=1.0,
        type_accuracy=1.0,
        figure_recall=1.0,
        question_box_iou=1.0,
        page_kind_accuracy=1.0,
    )
    assert perfect == pytest.approx(1.0)

    worst = compute_composite_score(
        stem_cer_normalized=1.0,
        choice_cer=1.0,
        question_count_match=0.0,
        type_accuracy=0.0,
        figure_recall=0.0,
        question_box_iou=0.0,
        page_kind_accuracy=0.0,
    )
    assert worst == pytest.approx(0.0)

    partial = compute_composite_score(
        stem_cer_normalized=0.2,
        choice_cer=0.1,
        question_count_match=1.0,
        type_accuracy=0.5,
        figure_recall=0.8,
        question_box_iou=0.7,
        page_kind_accuracy=1.0,
    )
    expected = 0.35 * 0.8 + 0.15 * 0.9 + 0.15 * 1.0 + 0.1 * 0.5 + 0.1 * 0.8 + 0.1 * 0.7 + 0.05 * 1.0
    assert partial == pytest.approx(expected)


def test_score_page_and_aggregate_metrics() -> None:
    golden = _make_golden_page(1)
    pred = PageExtraction.model_validate(_make_pred_page())
    pm = score_page(golden, pred, page_name="p001", latency_ms=250, cost_usd=Decimal("0.01"))
    assert pm.page_kind_match is True
    assert pm.question_count_match is True
    assert pm.stem_cer_normalized == 0.0
    assert pm.stem_cer_exact > 0.0
    assert pm.choice_cer == 0.0
    assert pm.type_accuracy == 1.0
    assert pm.stimulus_ref_accuracy == 1.0
    assert pm.stimulus_count_match is True
    assert pm.stimulus_content_cer_normalized == 0.0
    assert pm.stimulus_kind_accuracy == 1.0
    assert pm.question_box_iou == pytest.approx(1.0)
    assert pm.figure_precision == pytest.approx(1.0)
    assert pm.figure_recall == pytest.approx(1.0)
    assert pm.answer_accuracy == pytest.approx(1.0)
    assert pm.composite_score == pytest.approx(1.0)

    failed_pm = score_page(
        golden,
        None,
        page_name="p002",
        latency_ms=100,
        cost_usd=Decimal("0.005"),
        used_fallback=True,
        error="LLMOutputInvalid",
    )
    assert failed_pm.valid_output is False
    assert failed_pm.composite_score == 0.0

    agg = aggregate_model_metrics("google/gemini-3.8-flash", [pm, failed_pm])
    assert agg.page_count == 2  # noqa: PLR2004
    assert agg.valid_output_rate == pytest.approx(0.5)
    assert agg.fallback_rate == pytest.approx(0.5)
    assert agg.total_cost_usd == Decimal("0.015")
    assert agg.per_page_cost_usd == Decimal("0.0075")
    assert agg.p95_latency_ms == 250.0  # noqa: PLR2004
    assert len(agg.worst_questions) == 2  # noqa: PLR2004

    # Also test match_stimuli when empty
    empty_stim = match_stimuli([], [Stimulus.model_validate(_make_pred_page()["stimuli"][0])])
    assert empty_stim.count_match is False
    assert empty_stim.content_cer_normalized == 1.0


def test_cli_dry_run_and_refuse_over_max_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    golden_dir = tmp_path / "golden"
    _write_synthetic_golden_set(golden_dir)

    fake = FakeLLMClient()
    monkeypatch.setattr(eval_cli, "get_llm_client", lambda: fake)

    # 1. Dry-run prints estimate and makes 0 calls even with small max-cost
    code = main(
        [
            "--models",
            "google/gemini-3.8-flash",
            "--max-cost",
            "0.001",
            "--golden-dir",
            str(golden_dir),
            "--dry-run",
        ]
    )
    out = capsys.readouterr()
    assert code == 0
    assert "Cost Estimate" in out.out
    assert "google/gemini-3.8-flash" in out.out
    assert len(fake.calls) == 0

    # 2. Without --dry-run, refuses when worst-case estimate > max-cost and makes 0 calls
    code_refused = main(
        [
            "--models",
            "google/gemini-3.8-flash",
            "--max-cost",
            "0.001",
            "--golden-dir",
            str(golden_dir),
        ]
    )
    out_refused = capsys.readouterr()
    assert code_refused != 0
    assert "Cost Estimate" in out_refused.out
    assert "exceeds --max-cost" in out_refused.err
    assert len(fake.calls) == 0

    # 3. Disallowed model raises ModelNotAllowed
    with pytest.raises(ModelNotAllowed):
        estimate_eval_cost(["unknown/model"], num_pages=2, repeat=1, max_cost_usd=Decimal("1.0"))


def test_cli_full_run_and_writes_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    golden_dir = tmp_path / "golden"
    out_dir = tmp_path / "out"
    _write_synthetic_golden_set(golden_dir)

    fake = FakeLLMClient()
    # Page 1 succeeds directly; Page 2 triggers low-confidence fallback to extract_strong
    fake.queue("eval", (_make_pred_page(confidence=0.95), Decimal("0.002"), 120))
    fake.queue(
        "eval",
        (_make_pred_page(confidence=0.2, stem_q1="خطأ أولي"), Decimal("0.002"), 110),
    )
    fake.queue("extract_strong", (_make_pred_page(confidence=0.9), Decimal("0.003"), 180))
    monkeypatch.setattr(eval_cli, "get_llm_client", lambda: fake)

    code = main(
        [
            "--models",
            "openai/gpt-6-luna",
            "--max-cost",
            "0.10",
            "--golden-dir",
            str(golden_dir),
            "--out",
            str(out_dir),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Cost Estimate" in captured.out
    assert "Evaluation Summary" in captured.out
    assert "openai/gpt-6-luna" in captured.out

    report_md = out_dir / "report.md"
    results_json = out_dir / "results.json"
    assert report_md.is_file()
    assert results_json.is_file()

    md_text = report_md.read_text(encoding="utf-8")
    assert "## Composite Score Weights" in md_text
    assert "### Per-Page Breakdown" in md_text
    assert "10 Worst Question Diffs" in md_text

    data = json.loads(results_json.read_text(encoding="utf-8"))
    assert data["stopped_early"] is False
    assert data["actual_spend_usd"] == pytest.approx(0.007)
    assert len(data["models"]) == 1
    assert data["models"][0]["page_count"] == 2  # noqa: PLR2004
    assert data["models"][0]["fallback_rate"] == pytest.approx(0.5)
    assert [c["stage"] for c in fake.calls] == ["eval", "eval", "extract_strong"]


def test_cli_stops_mid_run_when_actual_spend_would_exceed_max_cost(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    golden_dir = tmp_path / "golden"
    out_dir = tmp_path / "out_partial"
    _write_synthetic_golden_set(golden_dir)

    # Estimate for 2 pages of openai/gpt-6-luna:
    # per-call worst-case cost is ~(1644 * 0.10 + 4096 * 0.50) / 1e6 = ~$0.0022124
    # 2 pages worst-case total is ~$0.0044248.
    # Set max_cost to $0.005 so the pre-run estimate check passes,
    # and make page 1 actually spend $0.004 so page 1 + page 2 worst-case > $0.005!
    fake = FakeLLMClient()
    fake.queue(
        "eval",
        LLMResult(
            parsed=PageExtraction.model_validate(_make_pred_page()),
            raw_text="{}",
            model="openai/gpt-6-luna",
            input_tokens=1600,
            output_tokens=3000,
            reasoning_tokens=0,
            cost_usd=Decimal("0.0040"),
            latency_ms=150,
            request_hash="h1",
        ),
    )
    fake.queue("eval", (_make_pred_page(), Decimal("0.0020"), 150))

    code = run_eval(
        models=["openai/gpt-6-luna"],
        max_cost_usd=Decimal("0.0050"),
        out_dir=out_dir,
        golden_dir=golden_dir,
        client=fake,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert len(fake.calls) == 1  # Stopped after page 1 before calling page 2!
    assert "Evaluation Summary" in captured.out

    report_md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "WARNING" in report_md
    assert "partial report" in report_md

    data = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    assert data["stopped_early"] is True
    assert data["actual_spend_usd"] == pytest.approx(0.004)
    assert data["models"][0]["page_count"] == 1


def test_cli_page_errors_and_budget_exception_handling(tmp_path: Path) -> None:
    golden_dir = tmp_path / "golden"
    out_dir = tmp_path / "out_err"
    _write_synthetic_golden_set(golden_dir)

    fake = FakeLLMClient()
    # Page 1 fails both extract and extract_strong with LLMOutputInvalid
    fake.queue("eval", LLMOutputInvalid("bad json", cost_usd=Decimal("0.001")))
    fake.queue("extract_strong", LLMOutputInvalid("still bad", cost_usd=Decimal("0.001")))
    # Page 2 raises BudgetExceeded
    budget_err = BudgetExceeded("cap hit")
    budget_err.cost_usd = Decimal("0.001")
    fake.queue("eval", budget_err)

    code = run_eval(
        models=["openai/gpt-6-luna", "anthropic/claude-haiku-5.5"],
        max_cost_usd=Decimal("0.50"),
        out_dir=out_dir,
        golden_dir=golden_dir,
        client=fake,
        concurrency=1,
    )
    assert code == 0
    data = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    # Stopped before running the second model due to BudgetExceeded on page 2
    assert data["stopped_early"] is True
    assert len(data["models"]) == 1
    assert data["models"][0]["valid_output_rate"] == 0.0
