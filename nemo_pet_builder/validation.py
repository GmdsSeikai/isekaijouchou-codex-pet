from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from jsonschema import Draft202012Validator

from .builder import ATLAS_SIZE, CELL_HEIGHT, CELL_WIDTH, COLUMNS, STANDARD_ORDER, load_manifest, sha256_file


def _errors_for_schema(instance_path: Path, schema_path: Path) -> list[str]:
    instance = json.loads(instance_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [f"{instance_path.name}: {error.message}" for error in sorted(validator.iter_errors(instance), key=str)]


def _atlas_errors(path: Path) -> list[str]:
    errors: list[str] = []
    with Image.open(path) as opened:
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

    for row in manifest.get("rows", []):
        source = root / row["path"]
        if not source.is_file():
            errors.append(f"missing source: {row['path']}")
        elif sha256_file(source) != row["sha256"]:
            errors.append(f"source hash mismatch: {row['path']}")

    result = {"ok": not errors, "strict": strict, "errors": errors}
    if errors:
        raise ValueError("validation failed:\n- " + "\n- ".join(errors))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
