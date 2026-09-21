from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image
from jsonschema import Draft202012Validator

from .builder import ATLAS_SIZE, CELL_HEIGHT, CELL_WIDTH, COLUMNS, STANDARD_ORDER, load_manifest, sha256_file
from .qa import LOOK_DIRECTIONS, combine_direction_verdicts


def _errors_for_schema(instance_path: Path, schema_path: Path) -> list[str]:
    instance = json.loads(instance_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [f"{instance_path.name}: {error.message}" for error in sorted(validator.iter_errors(instance), key=str)]


def _atlas_errors(path: Path) -> list[str]:
    errors: list[str] = []
    with Image.open(path) as opened:
        if opened.format != "WEBP":
            errors.append(f"spritesheet.webp: expected WEBP, got {opened.format}")
        if opened.mode != "RGBA":
            errors.append(f"spritesheet.webp: expected RGBA, got {opened.mode}")
        image = opened.convert("RGBA")
    if image.size != ATLAS_SIZE:
        errors.append(f"spritesheet.webp: expected {ATLAS_SIZE[0]}x{ATLAS_SIZE[1]}, got {image.width}x{image.height}")
        return errors
    for row, row_id in enumerate(STANDARD_ORDER):
        expected = load_manifest(path.parent)["frameCounts"][row_id]
        for column in range(COLUMNS):
            cell = image.crop((column * CELL_WIDTH, row * CELL_HEIGHT, (column + 1) * CELL_WIDTH, (row + 1) * CELL_HEIGHT))
            visible = cell.getchannel("A").getbbox() is not None
            if column < expected and not visible:
                errors.append(f"spritesheet.webp: row {row} column {column} must be populated")
            if column >= expected and visible:
                errors.append(f"spritesheet.webp: row {row} column {column} must be transparent")
    for row in (9, 10):
        for column in range(COLUMNS):
            cell = image.crop((column * CELL_WIDTH, row * CELL_HEIGHT, (column + 1) * CELL_WIDTH, (row + 1) * CELL_HEIGHT))
            if cell.getchannel("A").getbbox() is None:
                errors.append(f"spritesheet.webp: look row {row} column {column} is empty")
    transparent_residue = sum(
        alpha == 0 and (red != 0 or green != 0 or blue != 0)
        for red, green, blue, alpha in image.get_flattened_data()
    )
    if transparent_residue:
        errors.append(f"spritesheet.webp: {transparent_residue} transparent pixels retain hidden RGB")
    chroma_residue = sum(
        alpha > 0 and red > 220 and blue > 220 and green < 80
        for red, green, blue, alpha in image.get_flattened_data()
    )
    if chroma_residue:
        errors.append(f"spritesheet.webp: {chroma_residue} visible chroma-key pixels remain")
    return errors


def _source_errors(root: Path, manifest: dict[str, object]) -> list[str]:
    errors: list[str] = []
    canonical = manifest.get("canonicalBase", {})
    records = [canonical, *manifest.get("rows", [])]
    for record in records:
        if not isinstance(record, dict):
            errors.append("source/generation-manifest.json: source record must be an object")
            continue
        for field in ("path", "prompt"):
            relative = record.get(field)
            if not isinstance(relative, str):
                errors.append(f"source/generation-manifest.json: missing {field}")
                continue
            candidate = Path(relative)
            if candidate.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", relative):
                errors.append(f"source/generation-manifest.json: {field} must be relative: {relative}")
            elif not (root / candidate).is_file():
                errors.append(f"source/generation-manifest.json: missing {field}: {relative}")
        relative = record.get("path")
        expected = record.get("sha256")
        if isinstance(relative, str) and isinstance(expected, str) and (root / relative).is_file():
            if sha256_file(root / relative) != expected:
                errors.append(f"source hash mismatch: {relative}")
        layout = record.get("layoutGuide")
        if layout is not None and (not isinstance(layout, str) or not (root / layout).is_file()):
            errors.append(f"source/generation-manifest.json: missing layoutGuide: {layout}")
    temporary_patterns = ("*candidate*", "*repaired*", "*.tmp", "*.bak")
    for pattern in temporary_patterns:
        for path in (root / "source").rglob(pattern):
            errors.append(f"temporary source file is not allowed: {path.relative_to(root).as_posix()}")
    return errors


def _repository_hygiene_errors(root: Path) -> list[str]:
    errors: list[str] = []
    text_suffixes = {".json", ".md", ".py", ".toml", ".yml", ".yaml", ".txt"}
    excluded_parts = {".git", ".venv", "archive"}
    absolute_pattern = re.compile(r"(?:[A-Za-z]:\\(?:Users|home)\\|/(?:home|Users)/)")
    secret_pattern = re.compile(
        "(?:" + "github" + "_pat_|" + "gh" + "p_|" + "sk-" + r"[A-Za-z0-9_-]{20,})"
    )
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        if any(part in excluded_parts for part in path.relative_to(root).parts):
            continue
        text = path.read_text(encoding="utf-8")
        if absolute_pattern.search(text):
            errors.append(f"local absolute path found in {path.relative_to(root).as_posix()}")
        if secret_pattern.search(text):
            errors.append(f"credential-like value found in {path.relative_to(root).as_posix()}")
    return errors


def _strict_qa_errors(root: Path, spritesheet: Path) -> list[str]:
    errors: list[str] = []
    qa_dir = root / "qa" / "releases" / "v2.1.0"
    digest = sha256_file(spritesheet)
    required = (
        "atlas-validation.json",
        "animation-metrics.json",
        "final-visual-qa.json",
        "look-continuity.json",
        "direction-semantics.json",
        "direction-blind-answer-key.json",
        "direction-blind-verdicts-1.json",
        "direction-blind-verdicts-2.json",
        "direction-blind-verdicts-3.json",
        "direction-blind-validation.json",
        "direction-blind-pairs.png",
    )
    for name in required:
        if not (qa_dir / name).is_file():
            errors.append(f"missing release QA artifact: qa/releases/v2.1.0/{name}")
    if errors:
        return errors
    atlas_report = json.loads((qa_dir / "atlas-validation.json").read_text(encoding="utf-8"))
    if atlas_report.get("ok") is not True or atlas_report.get("spritesheetSha256") != digest:
        errors.append("qa/releases/v2.1.0/atlas-validation.json: report is stale or failed")
    if atlas_report.get("warnings") or atlas_report.get("errors"):
        errors.append("qa/releases/v2.1.0/atlas-validation.json: warnings and errors must be empty")
    for name in (
        "animation-metrics.json",
        "final-visual-qa.json",
        "look-continuity.json",
        "direction-semantics.json",
    ):
        report = json.loads((qa_dir / name).read_text(encoding="utf-8"))
        if report.get("spritesheetSha256") != digest:
            errors.append(f"qa/releases/v2.1.0/{name}: stale spritesheet hash")
        if report.get("ok") is not True or report.get("warnings") or report.get("errors"):
            errors.append(f"qa/releases/v2.1.0/{name}: report is not a clean pass")
        if report.get("reviewRequired") is True:
            errors.append(f"qa/releases/v2.1.0/{name}: reviewRequired must be false")
    semantics = json.loads((qa_dir / "direction-semantics.json").read_text(encoding="utf-8"))
    directions = semantics.get("directions", [])
    if [item.get("direction") for item in directions] != list(LOOK_DIRECTIONS):
        errors.append("qa/releases/v2.1.0/direction-semantics.json: expected all 16 directions in order")
    if any(item.get("status") != "pass" for item in directions):
        errors.append("qa/releases/v2.1.0/direction-semantics.json: every direction must pass")
    computed = combine_direction_verdicts(qa_dir, write=False)
    committed = json.loads((qa_dir / "direction-blind-validation.json").read_text(encoding="utf-8"))
    if committed != computed:
        errors.append("qa/releases/v2.1.0/direction-blind-validation.json: result does not match reviewer verdicts")
    if computed.get("spritesheetSha256") != digest:
        errors.append("qa/releases/v2.1.0/direction-blind-validation.json: stale spritesheet hash")
    if (
        computed.get("ok") is not True
        or computed.get("warnings")
        or computed.get("unconfirmed")
        or computed.get("reviewRequired") is not False
    ):
        errors.append("qa/releases/v2.1.0/direction-blind-validation.json: strict blind QA failed")
    return errors


def validate_repository(root: Path, strict: bool = False) -> dict[str, object]:
    errors: list[str] = []
    manifest = load_manifest(root)
    pet_path = root / "pet.json"
    schema_path = root / "schemas" / "pet.schema.json"
    spritesheet = root / "spritesheet.webp"
    if not schema_path.is_file():
        errors.append("missing schemas/pet.schema.json")
    elif pet_path.is_file():
        errors.extend(_errors_for_schema(pet_path, schema_path))
    else:
        errors.append("missing pet.json")
    if not spritesheet.is_file():
        errors.append("missing spritesheet.webp")
    else:
        errors.extend(_atlas_errors(spritesheet))

    errors.extend(_source_errors(root, manifest))
    errors.extend(_repository_hygiene_errors(root))
    if strict and spritesheet.is_file():
        errors.extend(_strict_qa_errors(root, spritesheet))

    result = {"ok": not errors, "strict": strict, "errors": errors}
    if errors:
        raise ValueError("validation failed:\n- " + "\n- ".join(errors))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
