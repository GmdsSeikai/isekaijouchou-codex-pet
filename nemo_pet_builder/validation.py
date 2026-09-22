from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image
from jsonschema import Draft202012Validator

from .builder import (
    ATLAS_SIZE,
    CELL_HEIGHT,
    CELL_WIDTH,
    COLUMNS,
    STANDARD_ORDER,
    decoded_pixel_hash,
    load_manifest,
    sha256_file,
)
from .qa import LOOK_DIRECTIONS, combine_direction_verdicts
from .project import find_qa_evidence, project_version


def _errors_for_schema(instance_path: Path, schema_path: Path) -> list[str]:
    instance = json.loads(instance_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [f"{instance_path.name}: {error.message}" for error in sorted(validator.iter_errors(instance), key=str)]


def _atlas_errors(path: Path, root: Path) -> list[str]:
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
        expected = load_manifest(root)["frameCounts"][row_id]
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
    resolved_root = root.resolve()
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
                continue
            resolved = (root / candidate).resolve()
            try:
                resolved.relative_to(resolved_root)
            except ValueError:
                errors.append(f"source/generation-manifest.json: {field} escapes repository: {relative}")
                continue
            if not resolved.is_file():
                errors.append(f"source/generation-manifest.json: missing {field}: {relative}")
        relative = record.get("path")
        expected = record.get("sha256")
        if isinstance(relative, str) and isinstance(expected, str):
            candidate = Path(relative)
            if candidate.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", relative):
                continue
            resolved = (root / candidate).resolve()
            try:
                resolved.relative_to(resolved_root)
            except ValueError:
                continue
            if resolved.is_file() and sha256_file(resolved) != expected:
                errors.append(f"source hash mismatch: {relative}")
        layout = record.get("layoutGuide")
        if layout is not None:
            if not isinstance(layout, str):
                errors.append(f"source/generation-manifest.json: invalid layoutGuide: {layout}")
            else:
                candidate = Path(layout)
                resolved = (root / candidate).resolve()
                try:
                    resolved.relative_to(resolved_root)
                except ValueError:
                    errors.append(f"source/generation-manifest.json: layoutGuide escapes repository: {layout}")
                else:
                    if candidate.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", layout) or not resolved.is_file():
                        errors.append(f"source/generation-manifest.json: missing or invalid layoutGuide: {layout}")
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
    digest = decoded_pixel_hash(spritesheet)
    version = project_version(root)
    summary = root / "qa" / "releases" / f"v{version}" / "QA-SUMMARY.md"
    if not summary.is_file():
        errors.append(f"missing release QA summary: {summary.relative_to(root).as_posix()}")
    try:
        evidence = find_qa_evidence(root, digest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [*errors, f"qa/evidence-index.json: {error}"]
    if evidence is None:
        return [*errors, f"qa/evidence-index.json: no audited evidence for decoded spritesheet SHA-256 {digest}"]
    evidence_path = evidence.get("path")
    if not isinstance(evidence_path, str):
        return [*errors, "qa/evidence-index.json: matched evidence must include a relative path"]
    candidate = Path(evidence_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return [*errors, "qa/evidence-index.json: evidence path must be repository-relative and cannot escape the repository"]
    qa_dir = (root / candidate).resolve()
    try:
        qa_dir.relative_to(root.resolve())
    except ValueError:
        return [*errors, "qa/evidence-index.json: evidence path escapes the repository"]
    source_release = evidence.get("reviewedRelease")
    if not isinstance(source_release, str):
        errors.append("qa/evidence-index.json: matched evidence has invalid release provenance")
    elif evidence_path.replace("\\", "/") != f"qa/releases/{source_release}":
        errors.append("qa/evidence-index.json: evidence path does not match its declared reviewedRelease")
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
            errors.append(f"missing release QA artifact: {candidate.as_posix()}/{name}")
    if errors:
        return errors
    answer_key = json.loads((qa_dir / "direction-blind-answer-key.json").read_text(encoding="utf-8"))
    expected_pair_ids = [*(f"H{index}" for index in range(1, 8)), *(f"V{index}" for index in range(1, 8))]
    pairs = answer_key.get("pairs") if isinstance(answer_key, dict) else None
    pair_ids = [pair.get("id") for pair in pairs if isinstance(pair, dict)] if isinstance(pairs, list) else []
    shape_errors: list[str] = []
    if not isinstance(answer_key, dict) or answer_key.get("schemaVersion") != 1:
        shape_errors.append("direction-blind-answer-key.json: unsupported schemaVersion")
    if not isinstance(pairs, list) or len(pairs) != len(expected_pair_ids) or pair_ids != expected_pair_ids:
        shape_errors.append("direction-blind-answer-key.json: expected exactly the unique H1-H7 and V1-V7 pairs in order")
    for pair in pairs if isinstance(pairs, list) else []:
        pair_id = pair.get("id") if isinstance(pair, dict) else "unknown"
        axis = "horizontal" if isinstance(pair_id, str) and pair_id.startswith("H") else "vertical"
        expected_keys = {"id", "axis", "A", "B"}
        if not isinstance(pair, dict) or set(pair) != expected_keys:
            shape_errors.append(f"direction-blind-answer-key.json: {pair_id} must contain exactly id, axis, A, and B")
            continue
        labels = {"screen-left", "screen-right"} if axis == "horizontal" else {"up", "down"}
        if pair.get("axis") != axis or any(
            not isinstance(pair.get(label), str) or pair.get(label) not in labels for label in ("A", "B")
        ):
            shape_errors.append(f"direction-blind-answer-key.json: {pair_id} has an invalid axis or classification")

    reviewer_ids: list[str] = []
    for index in range(1, 4):
        name = f"direction-blind-verdicts-{index}.json"
        verdict = json.loads((qa_dir / name).read_text(encoding="utf-8"))
        if not isinstance(verdict, dict):
            shape_errors.append(f"{name}: reviewer payload must be an object")
            continue
        reviewer = verdict.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            shape_errors.append(f"{name}: reviewer identity must be a non-empty string")
        else:
            reviewer_ids.append(reviewer)
        if verdict.get("schemaVersion") != 1:
            shape_errors.append(f"{name}: unsupported schemaVersion")
        if verdict.get("independent") is not True:
            shape_errors.append(f"{name}: independent must be true")
        answers = verdict.get("answers")
        if not isinstance(answers, dict) or set(answers) != set(expected_pair_ids):
            shape_errors.append(f"{name}: answers must cover exactly H1-H7 and V1-V7")
            continue
        for pair_id in expected_pair_ids:
            answer = answers.get(pair_id)
            axis = "horizontal" if pair_id.startswith("H") else "vertical"
            labels = {"screen-left", "screen-right"} if axis == "horizontal" else {"up", "down"}
            if not isinstance(answer, dict) or set(answer) != {"A", "B"}:
                shape_errors.append(f"{name}: {pair_id} must contain exactly A and B classifications")
            elif any(
                not isinstance(answer.get(label), str) or answer.get(label) not in labels for label in ("A", "B")
            ):
                shape_errors.append(f"{name}: {pair_id} has an invalid classification")
    if set(reviewer_ids) != {"anonymous-1", "anonymous-2", "anonymous-3"} or len(reviewer_ids) != 3:
        shape_errors.append("direction-blind-verdicts: expected reviewer identities anonymous-1, anonymous-2, and anonymous-3")
    if shape_errors:
        return [*errors, *(f"{candidate.as_posix()}/{error}" for error in shape_errors)]

    atlas_report = json.loads((qa_dir / "atlas-validation.json").read_text(encoding="utf-8"))
    if atlas_report.get("ok") is not True or atlas_report.get("spritesheetSha256") != digest:
        errors.append(f"{candidate.as_posix()}/atlas-validation.json: report is stale or failed")
    if atlas_report.get("warnings") or atlas_report.get("errors"):
        errors.append(f"{candidate.as_posix()}/atlas-validation.json: warnings and errors must be empty")
    for name in (
        "animation-metrics.json",
        "final-visual-qa.json",
        "look-continuity.json",
        "direction-semantics.json",
    ):
        report = json.loads((qa_dir / name).read_text(encoding="utf-8"))
        if report.get("spritesheetSha256") != digest:
            errors.append(f"{candidate.as_posix()}/{name}: stale spritesheet hash")
        if report.get("ok") is not True or report.get("warnings") or report.get("errors"):
            errors.append(f"{candidate.as_posix()}/{name}: report is not a clean pass")
        if report.get("reviewRequired") is True:
            errors.append(f"{candidate.as_posix()}/{name}: reviewRequired must be false")
    semantics = json.loads((qa_dir / "direction-semantics.json").read_text(encoding="utf-8"))
    directions = semantics.get("directions", [])
    if [item.get("direction") for item in directions] != list(LOOK_DIRECTIONS):
        errors.append(f"{candidate.as_posix()}/direction-semantics.json: expected all 16 directions in order")
    if any(item.get("status") != "pass" for item in directions):
        errors.append(f"{candidate.as_posix()}/direction-semantics.json: every direction must pass")
    computed = combine_direction_verdicts(qa_dir, write=False)
    committed = json.loads((qa_dir / "direction-blind-validation.json").read_text(encoding="utf-8"))
    if committed != computed:
        errors.append(f"{candidate.as_posix()}/direction-blind-validation.json: result does not match reviewer verdicts")
    if computed.get("spritesheetSha256") != digest:
        errors.append(f"{candidate.as_posix()}/direction-blind-validation.json: stale spritesheet hash")
    if (
        computed.get("ok") is not True
        or computed.get("warnings")
        or computed.get("unconfirmed")
        or computed.get("reviewRequired") is not False
    ):
        errors.append(f"{candidate.as_posix()}/direction-blind-validation.json: strict blind QA failed")
    derived_reviewer_count = len(reviewer_ids)
    derived_classification_count = len(pair_ids) * 2
    derived_status = "pass" if computed.get("ok") is True and not computed.get("warnings") and not computed.get("unconfirmed") else "fail"
    if evidence.get("reviewerCount") != derived_reviewer_count:
        errors.append("qa/evidence-index.json: reviewerCount does not match the reviewer payloads")
    if evidence.get("classificationCount") != derived_classification_count:
        errors.append("qa/evidence-index.json: classificationCount does not match the answer-key classifications")
    if evidence.get("reviewStatus") != derived_status:
        errors.append("qa/evidence-index.json: reviewStatus does not match the computed reviewer result")
    if evidence.get("warnings") != computed.get("warnings") or evidence.get("unconfirmed") != computed.get("unconfirmed"):
        errors.append("qa/evidence-index.json: warnings or unconfirmed results do not match the computed reviewer result")
    return errors


def validate_repository(
    root: Path, strict: bool = False, output_dir: Path | None = None
) -> dict[str, object]:
    errors: list[str] = []
    manifest = load_manifest(root)
    pet_path = root / "pet.json"
    schema_path = root / "schemas" / "pet.schema.json"
    spritesheet = (output_dir or root) / "spritesheet.webp"
    if not schema_path.is_file():
        errors.append("missing schemas/pet.schema.json")
    elif pet_path.is_file():
        errors.extend(_errors_for_schema(pet_path, schema_path))
    else:
        errors.append("missing pet.json")
    if not spritesheet.is_file():
        errors.append("missing spritesheet.webp")
    else:
        errors.extend(_atlas_errors(spritesheet, root))

    errors.extend(_source_errors(root, manifest))
    errors.extend(_repository_hygiene_errors(root))
    if strict and spritesheet.is_file():
        errors.extend(_strict_qa_errors(root, spritesheet))

    result = {"ok": not errors, "strict": strict, "errors": errors}
    if errors:
        raise ValueError("validation failed:\n- " + "\n- ".join(errors))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
