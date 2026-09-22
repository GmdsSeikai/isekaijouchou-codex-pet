from __future__ import annotations

import json
import statistics
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from .builder import (
    CELL_HEIGHT,
    CELL_WIDTH,
    COLUMNS,
    LOOK_DIRECTIONS,
    STANDARD_ORDER,
    decoded_pixel_hash,
)

HORIZONTAL_PAIRS = (
    ("022.5", "337.5"),
    ("045", "315"),
    ("067.5", "292.5"),
    ("090", "270"),
    ("112.5", "247.5"),
    ("135", "225"),
    ("157.5", "202.5"),
)
VERTICAL_PAIRS = (
    ("000", "180"),
    ("022.5", "157.5"),
    ("045", "135"),
    ("067.5", "112.5"),
    ("202.5", "337.5"),
    ("225", "315"),
    ("247.5", "292.5"),
)


def _cell(atlas: Image.Image, direction: str) -> Image.Image:
    index = LOOK_DIRECTIONS.index(direction)
    row = 9 + index // COLUMNS
    column = index % COLUMNS
    return atlas.crop(
        (
            column * CELL_WIDTH,
            row * CELL_HEIGHT,
            (column + 1) * CELL_WIDTH,
            (row + 1) * CELL_HEIGHT,
        )
    )


def write_blind_challenge(atlas: Image.Image, spritesheet: Path, qa_dir: Path) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    pairs = [("horizontal", *pair) for pair in HORIZONTAL_PAIRS] + [
        ("vertical", *pair) for pair in VERTICAL_PAIRS
    ]
    card_width = CELL_WIDTH * 2 + 28
    card_height = CELL_HEIGHT + 54
    sheet = Image.new("RGBA", (card_width * 2, card_height * 7), "white")
    draw = ImageDraw.Draw(sheet)
    answer_key = []
    for index, (axis, first, second) in enumerate(pairs):
        swap = index % 2 == 1
        a_direction, b_direction = (second, first) if swap else (first, second)
        left = index % 2 * card_width
        top = index // 2 * card_height
        pair_id = f"{axis[0].upper()}{index % 7 + 1}"
        draw.rectangle((left, top, left + card_width - 1, top + card_height - 1), outline="#BBBBBB")
        draw.text((left + 8, top + 6), f"{pair_id}  classify {axis} axis", fill="black")
        draw.text((left + 8, top + 26), "A", fill="black")
        draw.text((left + CELL_WIDTH + 20, top + 26), "B", fill="black")
        sheet.alpha_composite(_cell(atlas, a_direction), (left + 4, top + 46))
        sheet.alpha_composite(_cell(atlas, b_direction), (left + CELL_WIDTH + 16, top + 46))
        answer_key.append(
            {
                "id": pair_id,
                "axis": axis,
                "A": _expected_label(a_direction, axis),
                "B": _expected_label(b_direction, axis),
            }
        )
    sheet.convert("RGB").save(qa_dir / "direction-blind-pairs.png")
    payload = {
        "schemaVersion": 1,
        "spritesheetSha256": decoded_pixel_hash(spritesheet),
        "pairs": answer_key,
    }
    (qa_dir / "direction-blind-answer-key.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _expected_label(direction: str, axis: str) -> str:
    degrees = float(direction)
    if axis == "horizontal":
        return "screen-right" if 0 < degrees < 180 else "screen-left"
    return "up" if degrees < 90 or degrees > 270 else "down"


def _visible_pixels(cell: Image.Image) -> int:
    return sum(value > 16 for value in cell.getchannel("A").get_flattened_data())


def _changed_pixels(first: Image.Image, second: Image.Image) -> int:
    difference = ImageChops.difference(first, second)
    return sum(any(pixel) for pixel in difference.get_flattened_data())


def _bbox_metrics(cell: Image.Image) -> tuple[float, float, int, int]:
    alpha = cell.getchannel("A")
    box = alpha.getbbox()
    if box is None:
        return 0.0, 0.0, 0, 0
    left, top, right, bottom = box
    return (left + right) / 2, (top + bottom) / 2, bottom, _visible_pixels(cell)


def write_motion_reports(root: Path, atlas: Image.Image, spritesheet: Path, qa_dir: Path) -> None:
    manifest = json.loads((root / "source" / "generation-manifest.json").read_text(encoding="utf-8"))
    animation_rows = []
    animation_errors: list[str] = []
    for row_index, row_id in enumerate(STANDARD_ORDER):
        count = manifest["frameCounts"][row_id]
        cells = [
            atlas.crop((column * CELL_WIDTH, row_index * CELL_HEIGHT, (column + 1) * CELL_WIDTH, (row_index + 1) * CELL_HEIGHT))
            for column in range(count)
        ]
        changes = [_changed_pixels(cells[index], cells[(index + 1) % count]) for index in range(count)]
        non_closure = changes[:-1] or changes
        median_change = statistics.median(non_closure)
        closure_ratio = changes[-1] / median_change if median_change else 0
        areas = [_visible_pixels(cell) for cell in cells]
        bottoms = [_bbox_metrics(cell)[2] for cell in cells]
        area_ratio = max(areas) / min(areas)
        row_errors = []
        if min(changes) == 0:
            row_errors.append("contains identical adjacent frames")
        if closure_ratio > 2.5:
            row_errors.append(f"loop closure ratio {closure_ratio:.2f} exceeds 2.50")
        if row_id not in {"jumping", "failed"} and max(bottoms) - min(bottoms) > 12:
            row_errors.append(f"baseline range {max(bottoms) - min(bottoms)}px exceeds 12px")
        area_limit = 2.0 if row_id == "failed" else 1.45
        if area_ratio > area_limit:
            row_errors.append(f"area ratio {area_ratio:.2f} exceeds {area_limit:.2f}")
        animation_errors.extend(f"{row_id}: {message}" for message in row_errors)
        animation_rows.append(
            {
                "row": row_id,
                "changedPixels": changes,
                "loopClosureRatio": round(closure_ratio, 4),
                "baselineRange": max(bottoms) - min(bottoms),
                "areaRatio": round(area_ratio, 4),
                "errors": row_errors,
            }
        )

    look_cells = [_cell(atlas, direction) for direction in LOOK_DIRECTIONS]
    look_pairs = []
    look_errors: list[str] = []
    for index, direction in enumerate(LOOK_DIRECTIONS):
        next_direction = LOOK_DIRECTIONS[(index + 1) % len(LOOK_DIRECTIONS)]
        first = _bbox_metrics(look_cells[index])
        second = _bbox_metrics(look_cells[(index + 1) % len(look_cells)])
        center_delta = ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2) ** 0.5
        area_ratio = max(first[3], second[3]) / min(first[3], second[3])
        baseline_delta = abs(first[2] - second[2])
        if center_delta > 12:
            look_errors.append(f"{direction}->{next_direction}: center delta {center_delta:.2f}px exceeds 12px")
        if area_ratio > 1.25:
            look_errors.append(f"{direction}->{next_direction}: area ratio {area_ratio:.2f} exceeds 1.25")
        if baseline_delta > 5:
            look_errors.append(f"{direction}->{next_direction}: baseline delta {baseline_delta}px exceeds 5px")
        look_pairs.append(
            {
                "from": direction,
                "to": next_direction,
                "centerDelta": round(center_delta, 4),
                "areaRatio": round(area_ratio, 4),
                "baselineDelta": baseline_delta,
            }
        )

    digest = decoded_pixel_hash(spritesheet)
    animation_payload = {
        "ok": not animation_errors,
        "spritesheetSha256": digest,
        "warnings": [],
        "errors": animation_errors,
        "rows": animation_rows,
    }
    continuity_payload = {
        "ok": not look_errors,
        "reviewRequired": False,
        "spritesheetSha256": digest,
        "warnings": [],
        "errors": look_errors,
        "pairs": look_pairs,
    }
    (qa_dir / "animation-metrics.json").write_text(
        json.dumps(animation_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (qa_dir / "look-continuity.json").write_text(
        json.dumps(continuity_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def combine_direction_verdicts(qa_dir: Path, *, write: bool = True) -> dict[str, object]:
    key = json.loads((qa_dir / "direction-blind-answer-key.json").read_text(encoding="utf-8"))
    verdicts = [
        json.loads((qa_dir / f"direction-blind-verdicts-{index}.json").read_text(encoding="utf-8"))
        for index in range(1, 4)
    ]
    warnings: list[str] = []
    unconfirmed: list[str] = []
    results = []
    for pair in key["pairs"]:
        result = {"id": pair["id"], "axis": pair["axis"]}
        for label in ("A", "B"):
            votes = [review["answers"][pair["id"]][label] for review in verdicts]
            counts = {vote: votes.count(vote) for vote in sorted(set(votes))}
            consensus = max(counts, key=counts.get)
            if counts[consensus] < 2:
                unconfirmed.append(f"{pair['id']} {label}: no majority")
            elif consensus != pair[label]:
                warnings.append(f"{pair['id']} {label}: expected {pair[label]}, got {consensus}")
            result[label] = {"expected": pair[label], "consensus": consensus, "votes": votes}
        results.append(result)
    payload = {
        "ok": not warnings and not unconfirmed,
        "reviewRequired": bool(warnings or unconfirmed),
        "spritesheetSha256": key["spritesheetSha256"],
        "reviewerCount": 3,
        "warnings": warnings,
        "unconfirmed": unconfirmed,
        "results": results,
    }
    if write:
        (qa_dir / "direction-blind-validation.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return payload


def write_qa_assets(root: Path, atlas: Image.Image, spritesheet: Path, qa_dir: Path) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    write_blind_challenge(atlas, spritesheet, qa_dir)
    write_motion_reports(root, atlas, spritesheet, qa_dir)
