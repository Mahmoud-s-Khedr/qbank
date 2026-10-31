#!/usr/bin/env python3
"""Validate all golden-set JSON annotations in fixtures/golden/."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
SCHEMA_PATH = GOLDEN_DIR / "schema.json"
PAGES_DIR = GOLDEN_DIR / "pages"

BOX_LEN = 4
MIN_MCQ_CHOICES = 2
COORD_DECIMALS = 3
COORD_TOL = 1e-9


def check_box(box: list[float], label: str, errors: list[str]) -> None:
    if len(box) != BOX_LEN:
        errors.append(f"{label}: box must have {BOX_LEN} elements, got {len(box)}")
        return
    x0, y0, x1, y1 = box
    if not (0.0 <= x0 < x1 <= 1.0):
        errors.append(
            f"{label}: invalid x range in box {box} (expected 0 <= x0 < x1 <= 1)"
        )
    if not (0.0 <= y0 < y1 <= 1.0):
        errors.append(
            f"{label}: invalid y range in box {box} (expected 0 <= y0 < y1 <= 1)"
        )
    for coord in box:
        rounded = round(coord, COORD_DECIMALS)
        if abs(coord - rounded) > COORD_TOL:
            errors.append(f"{label}: coordinate {coord} has more than 3 decimal places")


def _validate_questions(
    json_name: str,
    questions: list[dict[str, Any]],
    stimulus_refs: set[str],
    errors: list[str],
) -> None:
    seen_numbers: set[str] = set()
    for idx, q in enumerate(questions):
        num = q["number_label"]
        q_label = f"{json_name}:questions[{idx}](#{num})"
        if num in seen_numbers:
            errors.append(f"{q_label}: duplicate question number_label '{num}' on page")
        seen_numbers.add(num)

        check_box(q["box"], q_label, errors)

        stim_ref = q["stimulus_ref"]
        if stim_ref is not None and stim_ref not in stimulus_refs:
            errors.append(f"{q_label}: unresolved stimulus_ref '{stim_ref}'")

        q_type = q["type"]
        choices = q["choices"]
        if q_type in ("mcq_single", "mcq_multi"):
            if len(choices) < MIN_MCQ_CHOICES:
                errors.append(
                    f"{q_label}: MCQ must have >= {MIN_MCQ_CHOICES} choices, got {len(choices)}"
                )
            choice_labels = [c["label"] for c in choices]
            if len(choice_labels) != len(set(choice_labels)):
                errors.append(f"{q_label}: duplicate choice labels {choice_labels}")
        elif len(choices) != 0:
            errors.append(f"{q_label}: non-MCQ ({q_type}) must have empty choices list")

        for f_idx, fig in enumerate(q["figures"]):
            check_box(fig["box"], f"{q_label}.figures[{f_idx}]", errors)


def validate_file(
    json_path: Path,
    validator: Draft202012Validator,
) -> list[str]:
    errors: list[str] = []
    try:
        data: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{json_path.name}: failed to parse JSON: {exc}"]

    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = ".".join(str(p) for p in err.path) or "<root>"
        errors.append(f"{json_path.name} [{loc}]: {err.message}")

    if errors:
        return errors

    image_rel = data["image"]
    if not (GOLDEN_DIR / image_rel).is_file():
        errors.append(f"{json_path.name}: image file not found at {image_rel}")
    expected_image_rel = f"pages/{json_path.stem}.png"
    if image_rel != expected_image_rel:
        errors.append(
            f"{json_path.name}: image field '{image_rel}' does not match '{expected_image_rel}'"
        )

    for idx, heading in enumerate(data["headings"]):
        check_box(heading["box"], f"{json_path.name}:headings[{idx}]", errors)

    stimulus_refs: set[str] = set()
    for stim in data["stimuli"]:
        ref = stim["ref"]
        if ref in stimulus_refs:
            errors.append(f"{json_path.name}: duplicate stimulus ref '{ref}'")
        stimulus_refs.add(ref)
        check_box(stim["box"], f"{json_path.name}:stimuli[{ref}]", errors)

    _validate_questions(json_path.name, data["questions"], stimulus_refs, errors)

    if data["page_kind"] not in ("questions", "answer_key") and (
        data["questions"] or data["stimuli"]
    ):
        errors.append(
            f"{json_path.name}: non-question page_kind '{data['page_kind']}' "
            "must have empty questions and stimuli"
        )

    return errors


def main() -> int:
    if not SCHEMA_PATH.is_file():
        sys.stderr.write(f"ERROR: Schema not found at {SCHEMA_PATH}\n")
        return 1

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    page_pngs = sorted(PAGES_DIR.glob("*.png"))
    golden_jsons = sorted(
        p for p in GOLDEN_DIR.glob("*.json") if p.name != "schema.json"
    )

    all_errors: list[str] = []

    expected_stems = {p.stem for p in page_pngs}
    actual_stems = {p.stem for p in golden_jsons}
    missing = sorted(expected_stems - actual_stems)
    extra = sorted(actual_stems - expected_stems)
    if missing:
        all_errors.append(f"Missing golden JSON files for page images: {missing}")
    if extra:
        all_errors.append(f"Golden JSON files without matching page image: {extra}")

    for json_path in golden_jsons:
        all_errors.extend(validate_file(json_path, validator))

    if all_errors:
        for err in all_errors:
            sys.stderr.write(f"FAIL: {err}\n")
        sys.stderr.write(
            f"\nValidation failed with {len(all_errors)} error(s) "
            f"across {len(golden_jsons)} file(s).\n"
        )
        return 1

    total_q = 0
    total_s = 0
    total_f = 0
    total_h = 0
    for json_path in golden_jsons:
        d = json.loads(json_path.read_text(encoding="utf-8"))
        total_q += len(d["questions"])
        total_s += len(d["stimuli"])
        total_h += len(d["headings"])
        total_f += sum(len(q["figures"]) for q in d["questions"])

    sys.stdout.write(
        f"OK: validated {len(golden_jsons)} golden files "
        f"({total_q} questions, {total_s} stimuli, {total_f} figures, {total_h} headings).\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
