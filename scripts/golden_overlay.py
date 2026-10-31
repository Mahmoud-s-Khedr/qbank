#!/usr/bin/env python3
"""Render bounding-box overlays for all golden-set pages into .data/golden-overlays/."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
OUT_DIR = REPO_ROOT / ".data" / "golden-overlays"

COLORS: dict[str, tuple[int, int, int]] = {
    "question": (220, 38, 38),  # red
    "stimulus": (37, 99, 235),  # blue
    "figure": (22, 163, 74),  # green
    "heading": (234, 88, 12),  # orange
}


@dataclass(frozen=True)
class BoxSpec:
    box: list[float]
    color: tuple[int, int, int]
    label: str
    line_width: int = 3
    label_pos: str = "top-left"


def load_font(size: int = 20) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_labeled_box(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    spec: BoxSpec,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    width, height = size
    x0 = round(spec.box[0] * width)
    y0 = round(spec.box[1] * height)
    x1 = round(spec.box[2] * width)
    y1 = round(spec.box[3] * height)

    draw.rectangle([x0, y0, x1, y1], outline=spec.color, width=spec.line_width)

    bbox = draw.textbbox((0, 0), spec.label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 4

    if spec.label_pos == "top-right":
        lx0 = max(0, x1 - tw - 2 * pad)
        ly0 = max(0, y0 - th - 2 * pad) if y0 >= th + 2 * pad else y0
    elif spec.label_pos == "bottom-left":
        lx0 = max(0, x0)
        ly0 = min(height - th - 2 * pad, y1)
    else:
        lx0 = max(0, x0)
        ly0 = max(0, y0 - th - 2 * pad) if y0 >= th + 2 * pad else y0

    draw.rectangle([lx0, ly0, lx0 + tw + 2 * pad, ly0 + th + 2 * pad], fill=spec.color)
    draw.text(
        (lx0 + pad, ly0 + pad - bbox[1]), spec.label, fill=(255, 255, 255), font=font
    )


def render_overlay(
    json_path: Path, font: ImageFont.FreeTypeFont | ImageFont.ImageFont
) -> Path:
    data: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
    image_path = GOLDEN_DIR / data["image"]
    with Image.open(image_path) as im:
        canvas = im.convert("RGB")

    size = canvas.size
    draw = ImageDraw.Draw(canvas)

    for idx, heading in enumerate(data["headings"]):
        draw_labeled_box(
            draw,
            size,
            BoxSpec(
                box=heading["box"],
                color=COLORS["heading"],
                label=f"H{idx + 1}:{heading['level']}",
                line_width=3,
                label_pos="top-left",
            ),
            font,
        )

    for stim in data["stimuli"]:
        draw_labeled_box(
            draw,
            size,
            BoxSpec(
                box=stim["box"],
                color=COLORS["stimulus"],
                label=f"{stim['ref']} ({stim['kind']})",
                line_width=4,
                label_pos="top-left",
            ),
            font,
        )

    for q in data["questions"]:
        q_label = f"Q{q['number_label']}"
        if q["stimulus_ref"]:
            q_label += f"->{q['stimulus_ref']}"
        draw_labeled_box(
            draw,
            size,
            BoxSpec(
                box=q["box"],
                color=COLORS["question"],
                label=q_label,
                line_width=3,
                label_pos="top-right",
            ),
            font,
        )
        for f_idx, fig in enumerate(q["figures"]):
            draw_labeled_box(
                draw,
                size,
                BoxSpec(
                    box=fig["box"],
                    color=COLORS["figure"],
                    label=f"Q{q['number_label']}.F{f_idx + 1}:{fig['kind']}",
                    line_width=3,
                    label_pos="bottom-left",
                ),
                font,
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{json_path.stem}.png"
    canvas.save(out_path)
    return out_path


def main() -> int:
    golden_jsons = sorted(
        p for p in GOLDEN_DIR.glob("*.json") if p.name != "schema.json"
    )
    if not golden_jsons:
        sys.stderr.write("No golden JSON files found in fixtures/golden/\n")
        return 1

    font = load_font(size=18)
    for json_path in golden_jsons:
        out_path = render_overlay(json_path, font)
        sys.stdout.write(f"Wrote {out_path.relative_to(REPO_ROOT)}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
