"""CLI and runner for benchmarking extraction models against the golden set."""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import sys
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any, TypeVar
from uuid import UUID

from jinja2 import StrictUndefined, Template
from pydantic import BaseModel

from qbank.config import Settings, get_settings
from qbank.eval.metrics import (
    COMPOSITE_WEIGHTS,
    ModelMetrics,
    PageMetrics,
    QuestionDiff,
    aggregate_model_metrics,
    score_page,
)
from qbank.llm import (
    BudgetExceeded,
    LLMClient,
    LLMOutputInvalid,
    LLMResult,
    OrgBudgetExceeded,
    get_llm_client,
)
from qbank.llm.client import guard_model
from qbank.llm.pricing import estimate_cost
from qbank.pipeline.extract import PROMPT_PATH, extract_page

T = TypeVar("T", bound=BaseModel)

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
REPORTS_ROOT = REPO_ROOT / "eval-reports"

IMAGE_INPUT_TOKENS = 1300
EXPECTED_OUTPUT_TOKENS = 2500
CHARS_PER_TOKEN = 4
DEFAULT_CONCURRENCY = 4
DEFAULT_GOLDEN_PAGE_COUNT = 14


@dataclass(frozen=True)
class ModelCostEstimate:
    model: str
    pages: int
    repeat: int
    calls: int
    input_tokens_per_call: int
    expected_output_tokens_per_call: int
    worst_output_tokens_per_call: int
    expected_cost_usd: Decimal
    worst_case_cost_usd: Decimal
    per_call_expected_usd: Decimal
    per_call_worst_usd: Decimal


@dataclass(frozen=True)
class EvalEstimate:
    models: list[ModelCostEstimate]
    total_expected_usd: Decimal
    total_worst_case_usd: Decimal
    max_cost_usd: Decimal

    @property
    def exceeds_max_cost(self) -> bool:
        return self.total_worst_case_usd > self.max_cost_usd


def estimate_prompt_tokens() -> int:
    """Estimate token count for the rendered extraction prompt."""
    rendered = Template(PROMPT_PATH.read_text(encoding="utf-8"), undefined=StrictUndefined).render(
        subject="اللغة العربية", language="ar", grade="3 ثانوي"
    )
    return math.ceil(len(rendered) / CHARS_PER_TOKEN)


def estimate_eval_cost(
    models: Sequence[str],
    *,
    num_pages: int,
    repeat: int,
    max_cost_usd: Decimal,
    settings: Settings | None = None,
) -> EvalEstimate:
    """Compute expected and worst-case cost estimates per model before calling the LLM."""
    cfg = settings or get_settings()
    stage_cfg = cfg.llm_stage_models.get("eval") or cfg.llm_stage_models["extract"]
    input_tokens = IMAGE_INPUT_TOKENS + estimate_prompt_tokens()
    expected_out = EXPECTED_OUTPUT_TOKENS
    worst_out = stage_cfg.max_tokens
    calls = num_pages * repeat

    estimates: list[ModelCostEstimate] = []
    for model in models:
        guard_model(cfg, model)
        per_call_exp = estimate_cost(model, input_tokens, expected_out)
        per_call_worst = estimate_cost(model, input_tokens, worst_out)
        exp_cost = estimate_cost(model, calls * input_tokens, calls * expected_out)
        worst_cost = estimate_cost(model, calls * input_tokens, calls * worst_out)
        estimates.append(
            ModelCostEstimate(
                model=model,
                pages=num_pages,
                repeat=repeat,
                calls=calls,
                input_tokens_per_call=input_tokens,
                expected_output_tokens_per_call=expected_out,
                worst_output_tokens_per_call=worst_out,
                expected_cost_usd=exp_cost,
                worst_case_cost_usd=worst_cost,
                per_call_expected_usd=per_call_exp,
                per_call_worst_usd=per_call_worst,
            )
        )

    total_exp = sum((e.expected_cost_usd for e in estimates), Decimal(0))
    total_worst = sum((e.worst_case_cost_usd for e in estimates), Decimal(0))
    return EvalEstimate(
        models=estimates,
        total_expected_usd=total_exp,
        total_worst_case_usd=total_worst,
        max_cost_usd=max_cost_usd,
    )


def format_estimate_table(estimate: EvalEstimate) -> str:
    """Format the pre-run cost estimate as a Markdown table."""
    header = (
        "| Model | Pages | Repeat | Calls | In Tokens/Call | "
        "Out Tokens (Exp / Max) | Expected ($) | Worst-Case ($) |"
    )
    lines = [
        "### Cost Estimate",
        "",
        header,
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *(
            f"| `{item.model}` | {item.pages} | {item.repeat} | {item.calls} | "
            f"{item.input_tokens_per_call} | {item.expected_output_tokens_per_call} / "
            f"{item.worst_output_tokens_per_call} | ${item.expected_cost_usd:.4f} | "
            f"${item.worst_case_cost_usd:.4f} |"
            for item in estimate.models
        ),
        (
            f"| **Total** | | | **{sum(m.calls for m in estimate.models)}** | | | "
            f"**${estimate.total_expected_usd:.4f}** | **${estimate.total_worst_case_usd:.4f}** |"
        ),
        f"\nMax cost budget: **${estimate.max_cost_usd:.4f}**",
    ]
    return "\n".join(lines)


def discover_golden_files(golden_dir: Path, pages_glob: str = "*") -> list[Path]:
    """Find golden JSON files matching pages_glob (excluding schema.json)."""
    if not golden_dir.is_dir():
        return []
    candidates = sorted(p for p in golden_dir.glob("*.json") if p.name != "schema.json")
    if pages_glob in ("*", "*.json"):
        return candidates
    return [
        p
        for p in candidates
        if fnmatch.fnmatch(p.name, pages_glob) or fnmatch.fnmatch(p.stem, pages_glob)
    ]


def infer_page_context(golden_data: dict[str, Any]) -> tuple[str, str, str]:
    """Infer (subject, language, grade) from the golden page metadata."""
    source_pdf = str(golden_data.get("source_pdf", "")).lower()
    if "2027" in source_pdf:
        return ("الأحياء", "ar", "3 ثانوي")
    return ("اللغة العربية", "ar", "3 ثانوي")


class _PageClientProxy:
    """Per-page LLMClient wrapper that tracks fallback usage, latency, and cost."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.used_fallback = False
        self.latency_ms = 0
        self.cost_usd = Decimal(0)

    def complete_json(  # noqa: PLR0913 -- matches LLMClient protocol
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        org_id: UUID | None,
        source_id: UUID | None = None,
        model_override: str | None = None,
    ) -> LLMResult[T]:
        if stage == "extract_strong":
            self.used_fallback = True
        result = self.inner.complete_json(
            stage=stage,
            messages=messages,
            schema=schema,
            org_id=org_id,
            source_id=source_id,
            model_override=model_override,
        )
        self.latency_ms += result.latency_ms
        self.cost_usd += result.cost_usd
        return result

    def complete_text(
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        org_id: UUID | None,
        source_id: UUID | None = None,
        model_override: str | None = None,
    ) -> LLMResult[str]:
        result = self.inner.complete_text(
            stage=stage,
            messages=messages,
            org_id=org_id,
            source_id=source_id,
            model_override=model_override,
        )
        self.latency_ms += result.latency_ms
        self.cost_usd += result.cost_usd
        return result


def _evaluate_one_page(  # noqa: PLR0913, PLR0917 -- worker task parameters
    client: LLMClient,
    golden_path: Path,
    golden_dir: Path,
    model: str,
    repeat_idx: int,
    repeat_total: int,
    settings: Settings,
) -> tuple[PageMetrics, Decimal, bool]:
    """Run extraction on one golden page and return (PageMetrics, cost, budget_exceeded)."""
    golden_data: dict[str, Any] = json.loads(golden_path.read_text(encoding="utf-8"))
    image_path = golden_dir / str(golden_data["image"])
    image_bytes = image_path.read_bytes()
    subject, language, grade = infer_page_context(golden_data)
    page_name = f"{golden_path.stem}#r{repeat_idx + 1}" if repeat_total > 1 else golden_path.stem
    proxy = _PageClientProxy(client)
    started = time.monotonic()
    try:
        result, total_cost = extract_page(
            proxy,
            image_bytes,
            subject=subject,
            language=language,
            grade=grade,
            org_id=None,
            source_id=None,
            max_side=settings.extract_image_max_side,
            fallback_threshold=settings.extract_fallback_threshold,
            model_override=model,
            stage="eval",
        )
    except (BudgetExceeded, OrgBudgetExceeded) as exc:
        incurred = max(exc.cost_usd, proxy.cost_usd)
        elapsed_ms = proxy.latency_ms or int((time.monotonic() - started) * 1000)
        metrics = score_page(
            golden_data,
            None,
            page_name=page_name,
            latency_ms=elapsed_ms,
            cost_usd=incurred,
            used_fallback=proxy.used_fallback,
            error=type(exc).__name__,
        )
        return metrics, incurred, True
    except Exception as exc:
        incurred = exc.cost_usd if isinstance(exc, LLMOutputInvalid) else proxy.cost_usd
        elapsed_ms = proxy.latency_ms or int((time.monotonic() - started) * 1000)
        metrics = score_page(
            golden_data,
            None,
            page_name=page_name,
            latency_ms=elapsed_ms,
            cost_usd=incurred,
            used_fallback=proxy.used_fallback,
            error=f"{type(exc).__name__}: {exc}",
        )
        return metrics, incurred, False

    elapsed_ms = proxy.latency_ms or int((time.monotonic() - started) * 1000)
    metrics = score_page(
        golden_data,
        result.parsed,
        page_name=page_name,
        latency_ms=elapsed_ms,
        cost_usd=total_cost,
        used_fallback=proxy.used_fallback,
        error=None,
    )
    return metrics, total_cost, False


def _format_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _format_float(value: float | None, decimals: int = 3) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def _escape_md_cell(text: str, max_len: int = 120) -> str:
    cleaned = text.replace("\n", " ⏎ ").replace("|", "\\|").strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def format_summary_table(models: Sequence[ModelMetrics]) -> str:
    """Format the model comparison summary table (printed to stdout and report.md)."""
    header = (
        "| Model | Composite | PageKind Acc | Q Count Match | Stem CER (Norm) | "
        "Stem CER (Exact) | Choice CER | Type Acc | Fig Recall | Q Box IoU | "
        "Ans Acc | Valid Rate | Fallback | Mean / P95 (ms) | Cost ($ Total / Page) |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    rows = [
        (
            f"| `{m.model}` | **{_format_float(m.composite_score)}** | "
            f"{_format_pct(m.page_kind_accuracy)} | {_format_pct(m.question_count_match_rate)} | "
            f"{_format_float(m.stem_cer_normalized)} | {_format_float(m.stem_cer_exact)} | "
            f"{_format_float(m.choice_cer)} | {_format_pct(m.type_accuracy)} | "
            f"{_format_pct(m.figure_recall)} | {_format_float(m.question_box_iou)} | "
            f"{_format_pct(m.answer_accuracy)} | {_format_pct(m.valid_output_rate)} | "
            f"{_format_pct(m.fallback_rate)} | {m.mean_latency_ms:.0f} / {m.p95_latency_ms:.0f} | "
            f"${m.total_cost_usd:.4f} / ${m.per_page_cost_usd:.4f} |"
        )
        for m in models
    ]
    return "\n".join([header, sep, *rows])


def _format_choices_inline(choices: list[dict[str, str]]) -> str:
    if not choices:
        return "(none)"
    return " ; ".join(f"{c['label']}) {c['content']}" for c in choices)


def _format_worst_questions(diffs: Sequence[QuestionDiff]) -> list[str]:
    if not diffs:
        return ["_No matched questions to diff._"]
    header = (
        "| Page | Q# | Stem CER (Norm / Exact) | Choice CER | Box IoU | "
        "Golden (Stem & Choices) | Predicted (Stem & Choices) |"
    )
    lines = [header, "|---|---|---:|---:|---:|---|---|"]
    for d in diffs:
        g_summary = _escape_md_cell(
            f"{d.golden_stem} [{_format_choices_inline(d.golden_choices)}]", max_len=160
        )
        p_summary = _escape_md_cell(
            f"{d.pred_stem} [{_format_choices_inline(d.pred_choices)}]", max_len=160
        )
        lines.append(
            f"| `{d.page_name}` | `{d.number_label}` | "
            f"{d.stem_cer_normalized:.3f} / {d.stem_cer_exact:.3f} | {d.choice_cer:.3f} | "
            f"{d.box_iou:.3f} | {g_summary} | {p_summary} |"
        )
    return lines


def generate_markdown_report(
    *,
    timestamp: str,
    estimate: EvalEstimate,
    models: Sequence[ModelMetrics],
    actual_spend_usd: Decimal,
    stopped_early: bool,
) -> str:
    """Build the full Markdown report (`report.md`)."""
    sections: list[str] = [
        f"# Qbank Extraction Model Evaluation Report ({timestamp})",
        "",
    ]
    if stopped_early:
        sections.extend(
            [
                "> **WARNING:** Evaluation stopped early because continuing would exceed "
                f"`--max-cost ${estimate.max_cost_usd:.4f}` "
                f"(actual spend: `${actual_spend_usd:.4f}`). This is a partial report.",
                "",
            ]
        )

    cost_header = (
        "| Model | Pages Run | Mean Latency (ms) | P95 Latency (ms) | "
        "Total Cost ($) | Cost / Page ($) |"
    )
    sections.extend(
        [
            "## Summary Table",
            "",
            format_summary_table(models),
            "",
            "## Composite Score Weights",
            "",
            "The composite score is computed as:",
            "",
            "```text",
            "0.35 * (1 - normalized_stem_cer)",
            "+ 0.15 * (1 - choice_cer)",
            "+ 0.15 * question_count_match",
            "+ 0.10 * type_acc",
            "+ 0.10 * figure_recall",
            "+ 0.10 * question_box_iou",
            "+ 0.05 * page_kind_acc",
            "```",
            "",
            "| Component | Weight |",
            "|---|---:|",
            *(f"| `{k}` | {v:.2f} |" for k, v in COMPOSITE_WEIGHTS.items()),
            "",
            "## Cost & Latency Summary",
            "",
            f"- **Max Cost Budget:** `${estimate.max_cost_usd:.4f}`",
            f"- **Estimated Expected Cost:** `${estimate.total_expected_usd:.4f}`",
            f"- **Estimated Worst-Case Cost:** `${estimate.total_worst_case_usd:.4f}`",
            f"- **Actual Spend:** `${actual_spend_usd:.4f}`",
            f"- **Stopped Early:** `{stopped_early}`",
            "",
            cost_header,
            "|---|---:|---:|---:|---:|---:|",
            *(
                f"| `{m.model}` | {m.page_count} | {m.mean_latency_ms:.1f} | "
                f"{m.p95_latency_ms:.1f} | ${m.total_cost_usd:.4f} | ${m.per_page_cost_usd:.4f} |"
                for m in models
            ),
            "",
        ]
    )

    page_header = (
        "| Page | Kind (G/P) | Qs (G/P/M) | Missing / Extra | Stem CER (N) | "
        "Choice CER | Q Box IoU | Fig P/R | Composite | Latency (ms) | Cost ($) | Status |"
    )
    for m in models:
        q_counts = (
            f"{m.total_golden_questions} / {m.total_pred_questions} / {m.total_matched_questions}"
        )
        unmatched_counts = f"{m.total_unmatched_golden} / {m.total_extra_pred}"
        cost_pair = f"${m.total_cost_usd:.4f} / ${m.per_page_cost_usd:.4f}"
        sections.extend(
            [
                f"## Model: `{m.model}`",
                "",
                "### Aggregate Metrics",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Composite Score | **{m.composite_score:.4f}** |",
                f"| Pages Evaluated | {m.page_count} |",
                f"| Page Kind Accuracy | {_format_pct(m.page_kind_accuracy)} |",
                f"| Question Count Exact Match | {_format_pct(m.question_count_match_rate)} |",
                f"| Golden / Predicted / Matched Questions | {q_counts} |",
                f"| Unmatched Golden / Extra Predicted Questions | {unmatched_counts} |",
                f"| Stem CER (Normalized) | {m.stem_cer_normalized:.4f} |",
                f"| Stem CER (Exact) | {m.stem_cer_exact:.4f} |",
                f"| Choice CER (Normalized) | {m.choice_cer:.4f} |",
                f"| Choice Count Match Rate | {_format_pct(m.choice_count_match_rate)} |",
                f"| Question Type Accuracy | {_format_pct(m.type_accuracy)} |",
                f"| Stimulus Ref Linkage Accuracy | {_format_pct(m.stimulus_ref_accuracy)} |",
                f"| Stimulus Count Match Rate | {_format_pct(m.stimulus_count_match_rate)} |",
                f"| Stimulus Content CER (Normalized) | {m.stimulus_content_cer_normalized:.4f} |",
                f"| Stimulus Kind Accuracy | {_format_pct(m.stimulus_kind_accuracy)} |",
                f"| Question Box Mean IoU | {m.question_box_iou:.4f} |",
                f"| Figure Detection Precision (IoU >= 0.5) | {_format_pct(m.figure_precision)} |",
                f"| Figure Detection Recall (IoU >= 0.5) | {_format_pct(m.figure_recall)} |",
                f"| Figure Mean IoU (Matched) | {m.figure_mean_iou:.4f} |",
                f"| Answer Accuracy | {_format_pct(m.answer_accuracy)} |",
                f"| Valid Output Rate | {_format_pct(m.valid_output_rate)} |",
                f"| Fallback Rate | {_format_pct(m.fallback_rate)} |",
                f"| Mean / P95 Latency (ms) | {m.mean_latency_ms:.1f} / {m.p95_latency_ms:.1f} |",
                f"| Total / Per-Page Cost ($) | {cost_pair} |",
                "",
                "### Per-Page Breakdown",
                "",
                page_header,
                "|---|---|---:|---|---:|---:|---:|---|---:|---:|---:|---|",
            ]
        )
        for p in m.pages:
            status = (
                "fallback" if p.used_fallback else ("ok" if p.valid_output else f"error: {p.error}")
            )
            missing_str = ",".join(p.unmatched_golden_labels) or "-"
            extra_str = ",".join(p.extra_pred_labels) or "-"
            sections.append(
                f"| `{p.page_name}` | `{p.golden_page_kind}` / `{p.pred_page_kind or '-'}` | "
                f"{p.golden_question_count}/{p.pred_question_count}/{p.matched_question_count} | "
                f"{missing_str} / {extra_str} | {p.stem_cer_normalized:.3f} | "
                f"{p.choice_cer:.3f} | {p.question_box_iou:.3f} | "
                f"{_format_pct(p.figure_precision)}/{_format_pct(p.figure_recall)} | "
                f"{p.composite_score:.3f} | {p.latency_ms} | ${p.cost_usd:.4f} | {status} |"
            )
        sections.extend(
            [
                "",
                f"### 10 Worst Question Diffs (`{m.model}`)",
                "",
                *_format_worst_questions(m.worst_questions),
                "",
            ]
        )

    return "\n".join(sections)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def write_report_files(  # noqa: PLR0913 -- report serialization arguments
    out_dir: Path,
    *,
    timestamp: str,
    estimate: EvalEstimate,
    models: Sequence[ModelMetrics],
    actual_spend_usd: Decimal,
    stopped_early: bool,
    repeat: int,
    pages_glob: str,
) -> tuple[Path, Path]:
    """Write `report.md` and `results.json` to `out_dir`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report_md = generate_markdown_report(
        timestamp=timestamp,
        estimate=estimate,
        models=models,
        actual_spend_usd=actual_spend_usd,
        stopped_early=stopped_early,
    )
    report_path = out_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    results_payload = {
        "timestamp": timestamp,
        "pages_glob": pages_glob,
        "repeat": repeat,
        "max_cost_usd": float(estimate.max_cost_usd),
        "estimated_expected_cost_usd": float(estimate.total_expected_usd),
        "estimated_worst_case_cost_usd": float(estimate.total_worst_case_usd),
        "actual_spend_usd": float(actual_spend_usd),
        "stopped_early": stopped_early,
        "composite_weights": COMPOSITE_WEIGHTS,
        "estimates": [asdict(e) for e in estimate.models],
        "models": [asdict(m) for m in models],
    }
    results_path = out_dir / "results.json"
    results_path.write_text(
        json.dumps(results_payload, default=_json_default, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path, results_path


def run_eval(  # noqa: PLR0913, PLR0912, PLR0915 -- CLI orchestrates estimation, concurrency, budget guard, and reporting
    *,
    models: Sequence[str],
    max_cost_usd: Decimal,
    pages_glob: str = "*",
    repeat: int = 1,
    out_dir: Path | None = None,
    dry_run: bool = False,
    golden_dir: Path | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> int:
    """Execute `qbank-eval` and return the process exit code."""
    cfg = settings or get_settings()
    resolved_golden_dir = golden_dir if golden_dir is not None else GOLDEN_DIR
    golden_files = discover_golden_files(resolved_golden_dir, pages_glob)

    if not golden_files and not dry_run:
        sys.stderr.write(
            f"ERROR: No golden JSON files matching '{pages_glob}' found in {resolved_golden_dir}\n"
        )
        return 1

    num_pages = len(golden_files) if golden_files else DEFAULT_GOLDEN_PAGE_COUNT
    estimate = estimate_eval_cost(
        models,
        num_pages=num_pages,
        repeat=repeat,
        max_cost_usd=max_cost_usd,
        settings=cfg,
    )
    sys.stdout.write(format_estimate_table(estimate) + "\n")

    if dry_run:
        return 0

    if estimate.exceeds_max_cost:
        sys.stderr.write(
            f"ERROR: Worst-case estimated cost (${estimate.total_worst_case_usd:.4f}) "
            f"exceeds --max-cost (${max_cost_usd:.4f}). Refusing to call LLM.\n"
        )
        return 1

    llm_client = client or get_llm_client()
    spend_lock = Lock()
    actual_spend = Decimal(0)
    stopped_early = False
    model_results: list[ModelMetrics] = []

    for model_idx, model_est in enumerate(estimate.models):
        model = model_est.model
        has_more_models = model_idx + 1 < len(estimate.models)
        tasks: list[tuple[int, Path]] = [
            (r_idx, g_path) for r_idx in range(repeat) for g_path in golden_files
        ]
        page_metrics_by_idx: dict[int, PageMetrics] = {}
        task_cursor = 0
        total_tasks = len(tasks)

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            in_flight: dict[Future[tuple[PageMetrics, Decimal, bool]], int] = {}

            while task_cursor < total_tasks or in_flight:
                while task_cursor < total_tasks and len(in_flight) < concurrency:
                    with spend_lock:
                        current_spend = actual_spend
                    remaining_budget = max_cost_usd - current_spend
                    next_call_cost = model_est.per_call_worst_usd
                    if current_spend >= max_cost_usd or (
                        next_call_cost > Decimal(0)
                        and current_spend + next_call_cost > max_cost_usd
                    ):
                        stopped_early = True
                        break
                    # Limit concurrent in-flight tasks when remaining budget could be exceeded by
                    # parallel fallback calls.
                    needed_for_parallel = Decimal(len(in_flight) + 1) * Decimal(2) * next_call_cost
                    if in_flight and (
                        next_call_cost == Decimal(0) or remaining_budget < needed_for_parallel
                    ):
                        break

                    r_idx, g_path = tasks[task_cursor]
                    fut = pool.submit(
                        _evaluate_one_page,
                        llm_client,
                        g_path,
                        resolved_golden_dir,
                        model,
                        r_idx,
                        repeat,
                        cfg,
                    )
                    in_flight[fut] = task_cursor
                    task_cursor += 1

                if not in_flight:
                    break

                done_iter = as_completed(in_flight)
                completed_fut = next(done_iter)
                idx = in_flight.pop(completed_fut)
                p_metrics, incurred_cost, hit_budget_err = completed_fut.result()
                page_metrics_by_idx[idx] = p_metrics
                with spend_lock:
                    actual_spend += incurred_cost
                    has_more_work = bool(task_cursor < total_tasks or in_flight or has_more_models)
                    if hit_budget_err or (actual_spend >= max_cost_usd and has_more_work):
                        stopped_early = True

                if stopped_early:
                    for pending_fut in list(in_flight):
                        if not pending_fut.cancel():
                            p_idx = in_flight.pop(pending_fut)
                            pm, inc, _ = pending_fut.result()
                            page_metrics_by_idx[p_idx] = pm
                            with spend_lock:
                                actual_spend += inc
                        else:
                            in_flight.pop(pending_fut)
                    break

        ordered_pages = [page_metrics_by_idx[i] for i in sorted(page_metrics_by_idx)]
        if ordered_pages or not stopped_early:
            model_results.append(aggregate_model_metrics(model, ordered_pages))
        if stopped_early:
            break

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target_out_dir = out_dir if out_dir is not None else (REPORTS_ROOT / timestamp)
    report_path, results_path = write_report_files(
        target_out_dir,
        timestamp=timestamp,
        estimate=estimate,
        models=model_results,
        actual_spend_usd=actual_spend,
        stopped_early=stopped_early,
        repeat=repeat,
        pages_glob=pages_glob,
    )

    sys.stdout.write("\n### Evaluation Summary\n\n")
    sys.stdout.write(format_summary_table(model_results) + "\n")
    sys.stdout.write(f"\nWrote report to {report_path} and {results_path}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qbank-eval",
        description="Benchmark candidate extraction models against the golden set.",
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated list of candidate models (e.g. M1,M2).",
    )
    parser.add_argument(
        "--pages",
        default="*",
        help="Optional glob pattern to filter golden pages (default: '*').",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of repetitions per page per model (default: 1).",
    )
    parser.add_argument(
        "--max-cost",
        required=True,
        type=Decimal,
        help="Hard spend ceiling in USD.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory for report.md and results.json (default: eval-reports/<timestamp>).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the cost estimate only and exit without calling any model.",
    )
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=None,
        help="Override path to the golden directory (default: fixtures/golden).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    models = [m.strip() for m in str(args.models).split(",") if m.strip()]
    if not models:
        sys.stderr.write("ERROR: At least one model must be specified via --models\n")
        return 1
    if args.repeat < 1:
        sys.stderr.write("ERROR: --repeat must be >= 1\n")
        return 1
    return run_eval(
        models=models,
        max_cost_usd=args.max_cost,
        pages_glob=args.pages,
        repeat=args.repeat,
        out_dir=args.out,
        dry_run=args.dry_run,
        golden_dir=args.golden_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
