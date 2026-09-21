from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

CELL_WIDTH = 192
CELL_HEIGHT = 208
COLUMNS = 8
ROWS = 11
ATLAS_SIZE = (CELL_WIDTH * COLUMNS, CELL_HEIGHT * ROWS)
STANDARD_ORDER = (
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
)
LOOK_DIRECTIONS = (
    "000",
    "022.5",
    "045",
    "067.5",
    "090",
    "112.5",
    "135",
    "157.5",
    "180",
    "202.5",
    "225",
    "247.5",
    "270",
    "292.5",
    "315",
    "337.5",
)


@dataclass(frozen=True)
class RowSource:
    row_id: str
    path: Path
    frame_count: int
    sha256: str
    derived_from: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(root: Path) -> dict[str, object]:
    path = root / "source" / "generation-manifest.json"
    if not path.is_file():
        raise ValueError(f"missing source manifest: {path.relative_to(root)}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1:
        raise ValueError("source/generation-manifest.json: schemaVersion must be 1")
    return manifest


def _parse_key(value: str) -> tuple[int, int, int]:
    if len(value) != 7 or not value.startswith("#"):
        raise ValueError(f"invalid chroma key: {value}")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
    except ValueError as exc:
        raise ValueError(f"invalid chroma key: {value}") from exc


def _row_sources(root: Path, manifest: dict[str, object]) -> dict[str, RowSource]:
    rows = manifest.get("rows")
    if not isinstance(rows, list):
        raise ValueError("source/generation-manifest.json: rows must be an array")
    parsed: dict[str, RowSource] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("source/generation-manifest.json: each row must be an object")
        row_id = raw.get("id")
        relative = raw.get("path")
        frame_count = raw.get("frameCount")
        expected_hash = raw.get("sha256")
        derived_from = raw.get("derivedFrom")
        if not isinstance(row_id, str) or not isinstance(relative, str):
            raise ValueError("source/generation-manifest.json: row id and path must be strings")
        if not isinstance(frame_count, int) or frame_count < 1 or frame_count > COLUMNS:
            raise ValueError(f"source/generation-manifest.json: invalid frameCount for {row_id}")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise ValueError(f"source/generation-manifest.json: invalid sha256 for {row_id}")
        source_path = (root / relative).resolve()
        try:
            source_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"source path escapes repository: {relative}") from exc
        if not source_path.is_file():
            raise ValueError(f"missing source row: {relative}")
        actual_hash = sha256_file(source_path)
        if actual_hash != expected_hash:
            raise ValueError(f"source hash mismatch for {relative}: expected {expected_hash}, got {actual_hash}")
        parsed[row_id] = RowSource(row_id, source_path, frame_count, expected_hash, derived_from)
    required = set(STANDARD_ORDER) | {"look-row-9", "look-row-10"}
    missing = sorted(required - set(parsed))
    if missing:
        raise ValueError(f"source manifest is missing rows: {', '.join(missing)}")
    return parsed


def _color_distance(pixel: tuple[int, int, int, int], key: tuple[int, int, int]) -> float:
    return math.sqrt(sum((pixel[index] - key[index]) ** 2 for index in range(3)))


def _remove_chroma(image: Image.Image, key: tuple[int, int, int], threshold: float) -> Image.Image:
    rgba = image.convert("RGBA")
    output = []
    feather_end = threshold + 40
    for pixel in rgba.get_flattened_data():
        distance = _color_distance(pixel, key)
        if distance <= threshold:
            output.append((0, 0, 0, 0))
        elif distance < feather_end:
            alpha = round(pixel[3] * (distance - threshold) / (feather_end - threshold))
            output.append((pixel[0], pixel[1], pixel[2], alpha))
        else:
            output.append(pixel)
    rgba.putdata(output)
    return rgba


def _slot_crops(strip: Image.Image, frame_count: int) -> list[Image.Image]:
    slot_width = strip.width / frame_count
    return [
        strip.crop((round(index * slot_width), 0, round((index + 1) * slot_width), strip.height))
        for index in range(frame_count)
    ]


def _separated_crops(strip: Image.Image, frame_count: int) -> list[Image.Image]:
    alpha = strip.getchannel("A")
    occupied = [alpha.crop((x, 0, x + 1, strip.height)).getbbox() is not None for x in range(strip.width)]
    intervals: list[tuple[int, int]] = []
    start = None
    for index, visible in enumerate((*occupied, False)):
        if visible and start is None:
            start = index
        elif not visible and start is not None:
            if index - start >= 10:
                intervals.append((start, index))
            start = None
    if len(intervals) != frame_count:
        return _slot_crops(strip, frame_count)
    return [strip.crop((left, 0, right, strip.height)) for left, right in intervals]


def _normalize_frames(crops: list[Image.Image]) -> list[Image.Image]:
    bounds = [crop.getbbox() for crop in crops]
    if any(bound is None for bound in bounds):
        raise ValueError("source strip contains an empty frame")
    boxes = [bound for bound in bounds if bound is not None]
    viewport_width = max(right - left for left, _, right, _ in boxes) + 8
    viewport_height = max(bottom - top for _, top, _, bottom in boxes) + 8
    scale = min((CELL_WIDTH - 10) / viewport_width, (CELL_HEIGHT - 10) / viewport_height, 1.0)
    target_size = (max(1, round(viewport_width * scale)), max(1, round(viewport_height * scale)))
    frames: list[Image.Image] = []
    for crop, box in zip(crops, boxes):
        sprite = crop.crop(box)
        viewport = Image.new("RGBA", (viewport_width, viewport_height), (0, 0, 0, 0))
        viewport.alpha_composite(sprite, ((viewport_width - sprite.width) // 2, viewport_height - sprite.height - 4))
        resized = viewport.resize(target_size, Image.Resampling.LANCZOS)
        cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
        cell.alpha_composite(resized, ((CELL_WIDTH - resized.width) // 2, (CELL_HEIGHT - resized.height) // 2))
        frames.append(cell)
    return frames


def _extract_rows(
    sources: dict[str, RowSource], key: tuple[int, int, int], threshold: float
) -> dict[str, list[Image.Image]]:
    frames: dict[str, list[Image.Image]] = {}
    for row_id in STANDARD_ORDER:
        source = sources[row_id]
        if source.derived_from:
            if source.derived_from not in frames:
                raise ValueError(f"derived row {row_id} depends on unavailable {source.derived_from}")
            frames[row_id] = [frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for frame in frames[source.derived_from]]
            continue
        with Image.open(source.path) as opened:
            transparent = _remove_chroma(opened, key, threshold)
        frames[row_id] = _normalize_frames(_separated_crops(transparent, source.frame_count))

    look_crops: list[Image.Image] = []
    for row_id in ("look-row-9", "look-row-10"):
        source = sources[row_id]
        with Image.open(source.path) as opened:
            transparent = _remove_chroma(opened, key, threshold)
        look_crops.extend(_slot_crops(transparent, source.frame_count))
    normalized_look = _normalize_frames(look_crops)
    frames["look-row-9"] = normalized_look[:8]
    frames["look-row-10"] = normalized_look[8:]
    return frames


def _srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(value: float) -> float:
    return value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def _chroma_similarity(color: tuple[float, float, float], key: tuple[float, float, float]) -> float:
    color_mean = sum(color) / 3
    key_mean = sum(key) / 3
    centered_color = tuple(channel - color_mean for channel in color)
    centered_key = tuple(channel - key_mean for channel in key)
    denominator = sum(channel * channel for channel in centered_color) * sum(
        channel * channel for channel in centered_key
    )
    if denominator <= 1e-12:
        return -1
    return sum(a * b for a, b in zip(centered_color, centered_key)) / denominator**0.5


def _despill_atlas(atlas: Image.Image, key: tuple[int, int, int], radius: int = 5) -> Image.Image:
    output = Image.new("RGBA", atlas.size, (0, 0, 0, 0))
    key_linear = tuple(_srgb_to_linear(channel / 255) for channel in key)
    for row in range(ROWS):
        for column in range(COLUMNS):
            box = (
                column * CELL_WIDTH,
                row * CELL_HEIGHT,
                (column + 1) * CELL_WIDTH,
                (row + 1) * CELL_HEIGHT,
            )
            cell = atlas.crop(box).convert("RGBA")
            pixels = list(cell.get_flattened_data())
            colors = [tuple(_srgb_to_linear(channel / 255) for channel in pixel[:3]) for pixel in pixels]
            alpha = cell.getchannel("A")
            visible = [value > 0 for value in alpha.get_flattened_data()]
            transparent = Image.new("L", cell.size)
            transparent.putdata([0 if value else 255 for value in visible])
            near_transparency = list(
                transparent.filter(ImageFilter.MaxFilter(radius * 2 + 1)).get_flattened_data()
            )
            pending = [
                pixel[3] > 0
                and near_transparency[index] > 0
                and (
                    pixel[3] < 250
                    or (
                        max(color) > 0
                        and (max(color) - min(color)) / max(color) >= 0.1
                        and _chroma_similarity(color, key_linear) >= 0.85
                    )
                )
                for index, (pixel, color) in enumerate(zip(pixels, colors))
            ]
            filled = [pixel[3] > 0 and not flagged for pixel, flagged in zip(pixels, pending)]
            cleaned = pixels[:]
            for _ in range(radius * 2 + 1):
                updates: list[tuple[int, tuple[float, float, float]]] = []
                for index, flagged in enumerate(pending):
                    if not flagged:
                        continue
                    x, y = index % CELL_WIDTH, index // CELL_WIDTH
                    neighbors = []
                    for ny in range(max(0, y - 1), min(CELL_HEIGHT, y + 2)):
                        for nx in range(max(0, x - 1), min(CELL_WIDTH, x + 2)):
                            neighbor = ny * CELL_WIDTH + nx
                            if neighbor != index and filled[neighbor]:
                                neighbors.append(colors[neighbor])
                    if neighbors:
                        updates.append(
                            (
                                index,
                                tuple(
                                    sum(color[channel] for color in neighbors) / len(neighbors)
                                    for channel in range(3)
                                ),
                            )
                        )
                if not updates:
                    break
                for index, replacement in updates:
                    colors[index] = replacement
                    pending[index] = False
                    filled[index] = True
                    cleaned[index] = (
                        *(round(_linear_to_srgb(min(1, max(0, channel))) * 255) for channel in replacement),
                        pixels[index][3],
                    )
            for index, flagged in enumerate(pending):
                if flagged:
                    luminance = sum(colors[index]) / 3
                    value = round(_linear_to_srgb(luminance) * 255)
                    cleaned[index] = (value, value, value, pixels[index][3])
            cleaned = [(0, 0, 0, 0) if pixel[3] == 0 else pixel for pixel in cleaned]
            clean_cell = Image.new("RGBA", cell.size)
            clean_cell.putdata(cleaned)
            output.alpha_composite(clean_cell, box[:2])
    return output


def _compose_atlas(frames: dict[str, list[Image.Image]]) -> Image.Image:
    atlas = Image.new("RGBA", ATLAS_SIZE, (0, 0, 0, 0))
    for row_index, row_id in enumerate(STANDARD_ORDER):
        for column, frame in enumerate(frames[row_id]):
            atlas.alpha_composite(frame, (column * CELL_WIDTH, row_index * CELL_HEIGHT))
    for offset, row_id in enumerate(("look-row-9", "look-row-10"), start=9):
        for column, frame in enumerate(frames[row_id]):
            atlas.alpha_composite(frame, (column * CELL_WIDTH, offset * CELL_HEIGHT))
    return atlas


def _save_contact_sheet(atlas: Image.Image, path: Path) -> None:
    scale = 0.75
    cell_w, cell_h = round(CELL_WIDTH * scale), round(CELL_HEIGHT * scale)
    labels = (*STANDARD_ORDER, "look 000-157.5", "look 180-337.5")
    sheet = Image.new("RGBA", (cell_w * COLUMNS, (cell_h + 24) * ROWS), "white")
    draw = ImageDraw.Draw(sheet)
    for row, label in enumerate(labels):
        draw.text((4, row * (cell_h + 24) + 4), f"row {row}: {label}", fill="black")
        strip = atlas.crop((0, row * CELL_HEIGHT, ATLAS_SIZE[0], (row + 1) * CELL_HEIGHT))
        strip = strip.resize((cell_w * COLUMNS, cell_h), Image.Resampling.LANCZOS)
        sheet.alpha_composite(strip, (0, row * (cell_h + 24) + 24))
    sheet.convert("RGB").save(path)


def _save_direction_sheet(atlas: Image.Image, path: Path) -> None:
    neutral = atlas.crop((0, 0, CELL_WIDTH, CELL_HEIGHT))
    cells = [
        atlas.crop((column * CELL_WIDTH, row * CELL_HEIGHT, (column + 1) * CELL_WIDTH, (row + 1) * CELL_HEIGHT))
        for row in (9, 10)
        for column in range(COLUMNS)
    ]
    sheet = Image.new("RGBA", (CELL_WIDTH * 8, (CELL_HEIGHT + 24) * 3), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((4, 4), "neutral", fill="black")
    sheet.alpha_composite(neutral, (0, 24))
    for index, (direction, cell) in enumerate(zip(LOOK_DIRECTIONS, cells)):
        row = 1 + index // 8
        column = index % 8
        draw.text((column * CELL_WIDTH + 4, row * (CELL_HEIGHT + 24) + 4), direction, fill="black")
        sheet.alpha_composite(cell, (column * CELL_WIDTH, row * (CELL_HEIGHT + 24) + 24))
    sheet.convert("RGB").save(path)


def _save_previews(frames: dict[str, list[Image.Image]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    durations = {"running-right": 90, "running-left": 90, "jumping": 110, "running": 140}
    for row_id in STANDARD_ORDER:
        sequence = frames[row_id]
        sequence[0].save(
            output_dir / f"{row_id}.gif",
            save_all=True,
            append_images=sequence[1:],
            duration=durations.get(row_id, 160),
            disposal=2,
            loop=0,
            transparency=0,
        )


def build(root: Path, output_root: Path | None = None) -> Path:
    output_root = output_root or root
    manifest = load_manifest(root)
    sources = _row_sources(root, manifest)
    key = _parse_key(str(manifest.get("chromaKey", "#FF00FF")))
    threshold = float(manifest.get("chromaThreshold", 96))
    frames = _extract_rows(sources, key, threshold)
    atlas = _despill_atlas(_compose_atlas(frames), key)

    output_root.mkdir(parents=True, exist_ok=True)
    spritesheet = output_root / "spritesheet.webp"
    atlas.save(spritesheet, format="WEBP", lossless=True, method=6, exact=True)
    _save_contact_sheet(atlas, output_root / "contact-sheet.png")
    _save_direction_sheet(atlas, output_root / "look-directions.png")
    _save_previews(frames, output_root / "previews")
    if output_root == root:
        from .qa import write_qa_assets

        write_qa_assets(root, atlas, spritesheet)
    print(f"built {spritesheet}")
    return spritesheet
