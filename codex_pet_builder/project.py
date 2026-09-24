from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from .builder import decoded_pixel_hash


def project_metadata(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    if not path.is_file():
        raise ValueError("missing pyproject.toml: release version has no authoritative source")
    metadata = tomllib.loads(path.read_text(encoding="utf-8"))
    project = metadata.get("project")
    if not isinstance(project, dict):
        raise ValueError("pyproject.toml: missing [project] table")
    version = project.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise ValueError("pyproject.toml: project.version must be a semantic version")
    return project


def project_version(root: Path) -> str:
    return str(project_metadata(root)["version"])


def project_qa_paths(root: Path) -> tuple[Path, Path]:
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    tools = metadata.get("tool", {})
    settings = tools.get("codex-pet", {}) if isinstance(tools, dict) else None
    if not isinstance(settings, dict):
        raise ValueError("pyproject.toml: [tool.codex-pet] must be a table")
    paths = []
    for key in ("qa-evidence-index", "qa-summary"):
        value = settings.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"pyproject.toml: [tool.codex-pet].{key} must be a relative path")
        candidate = Path(value)
        resolved = (root / candidate).resolve()
        if candidate.is_absolute() or not resolved.is_relative_to(root.resolve()):
            raise ValueError(f"pyproject.toml: [tool.codex-pet].{key} must stay inside the project")
        paths.append(resolved)
    return paths[0], paths[1]


def find_qa_evidence(root: Path, spritesheet_sha256: str) -> dict[str, Any] | None:
    path, _ = project_qa_paths(root)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or not isinstance(data.get("evidenceSets"), list):
        raise ValueError(f"{path.name}: unsupported or malformed evidence index")
    if any(not isinstance(entry, dict) for entry in data["evidenceSets"]):
        raise ValueError(f"{path.name}: every evidence set must be an object")
    matches = [entry for entry in data["evidenceSets"] if entry.get("spritesheetSha256") == spritesheet_sha256]
    if len(matches) > 1:
        raise ValueError(f"{path.name}: duplicate evidence for spritesheet {spritesheet_sha256}")
    return matches[0] if matches else None


def _tag_at_head(root: Path) -> str:
    try:
        tags = subprocess.check_output(
            ["git", "tag", "--points-at", "HEAD"], cwd=root, text=True, encoding="utf-8"
        ).splitlines()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("cannot read Git tags at HEAD; pass --tag explicitly") from error
    if len(tags) != 1:
        raise ValueError("expected exactly one Git tag at HEAD; pass --tag explicitly")
    return tags[0]


def release_info(root: Path, *, tag: str | None = None, check_tag: bool = False) -> dict[str, Any]:
    project = project_metadata(root)
    version = str(project["version"])
    pet_path = root / "pet.json"
    if not pet_path.is_file():
        raise ValueError("missing pet.json")
    pet = json.loads(pet_path.read_text(encoding="utf-8"))
    spritesheet = root / pet["spritesheetPath"]
    if not spritesheet.is_file():
        raise ValueError(f"missing spritesheet: {spritesheet.name}")
    digest = decoded_pixel_hash(spritesheet)
    evidence = find_qa_evidence(root, digest)
    if evidence is None:
        raise ValueError(f"no QA evidence is indexed for decoded spritesheet SHA-256 {digest}")
    kind = evidence.get("kind")
    if kind not in {"human-visual", "synthetic-fixture"}:
        raise ValueError("QA evidence kind must be human-visual or synthetic-fixture")

    resolved_tag = tag
    if check_tag:
        if kind != "human-visual":
            raise ValueError("synthetic fixture evidence cannot be used for a tagged release")
        resolved_tag = resolved_tag or _tag_at_head(root)
        expected = f"v{version}"
        if resolved_tag != expected:
            raise ValueError(f"release tag mismatch: expected {expected}, got {resolved_tag}")

    evidence_path = evidence.get("path")
    if not isinstance(evidence_path, str):
        raise ValueError("QA evidence index: matched evidence is missing path")
    _, summary_path = project_qa_paths(root)
    release_notes = summary_path.relative_to(root.resolve()).as_posix()
    if not summary_path.is_file():
        raise ValueError(f"missing release QA summary: {release_notes}")
    return {
        "version": version,
        "expectedTag": f"v{version}",
        "tag": resolved_tag,
        "petId": pet["id"],
        "displayName": pet["displayName"],
        "zipName": f"{pet['id']}-codex-pet-v{version}.zip",
        "qaEvidencePath": evidence_path,
        "qaEvidenceKind": kind,
        "qaSourceRelease": evidence.get("reviewedRelease"),
        "qaSummaryPath": release_notes,
        "spritesheetSha256": digest,
    }
