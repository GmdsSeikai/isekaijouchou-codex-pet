"""Exercise the public CLI with a generated, copyright-free second pet."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from codex_pet_builder.builder import STANDARD_ORDER, decoded_pixel_hash
from codex_pet_builder.project import release_info


REPO = Path(__file__).parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cli(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "nemo_pet_builder", *arguments, "--root", str(root)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def make_fixture(root: Path) -> None:
    root.mkdir()
    write_json(
        root / "pet.json",
        {
            "id": "sample-orbit",
            "displayName": "Sample Orbit",
            "description": "Synthetic shapes for builder tests.",
            "spriteVersionNumber": 2,
            "spritesheetPath": "spritesheet.webp",
        },
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sample-orbit-builder"\nversion = "9.8.7"\n'
        '[tool.codex-pet]\nqa-evidence-index = "checks/index.json"\n'
        'qa-summary = "checks/summary.md"\n',
        encoding="utf-8",
    )
    (root / "schemas").mkdir()
    shutil.copyfile(REPO / "schemas" / "pet.schema.json", root / "schemas" / "pet.schema.json")
    (root / "checks").mkdir()
    (root / "checks" / "summary.md").write_text(
        "# Synthetic fixture\n\nGenerated shapes; no human visual review.\n", encoding="utf-8"
    )
    (root / "source" / "prompts").mkdir(parents=True)
    (root / "source" / "rows").mkdir()
    base = root / "source" / "canonical-base.png"
    Image.new("RGB", (64, 64), (20, 140, 230)).save(base)
    (root / "source" / "prompts" / "base.md").write_text("Synthetic circles.\n", encoding="utf-8")
    records = []
    for index, row_id in enumerate((*STANDARD_ORDER, "look-row-9", "look-row-10")):
        count = 8 if row_id.startswith("look-row") else 4
        strip = Image.new("RGB", (count * 72, 72), (255, 0, 255))
        draw = ImageDraw.Draw(strip)
        for frame in range(count):
            x = frame * 72 + 20 + (frame % 3)
            draw.ellipse((x, 18 + index % 3, x + 30, 49 + index % 3), fill=(20, 140, 230))
            draw.ellipse((x + 16, 28, x + 20, 32), fill=(250, 240, 20))
        source = root / "source" / "rows" / f"{row_id}.png"
        strip.save(source)
        prompt = root / "source" / "prompts" / f"{row_id}.md"
        prompt.write_text(f"Synthetic {row_id} shapes.\n", encoding="utf-8")
        record = {
            "id": row_id,
            "path": f"source/rows/{row_id}.png",
            "prompt": f"source/prompts/{row_id}.md",
            "frameCount": count,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
        if row_id == "running-left":
            record["derivedFrom"] = "running-right"
        records.append(record)
    write_json(
        root / "source" / "generation-manifest.json",
        {
            "schemaVersion": 1,
            "petId": "sample-orbit",
            "chromaKey": "#FF00FF",
            "chromaThreshold": 50,
            "canonicalBase": {
                "path": "source/canonical-base.png",
                "prompt": "source/prompts/base.md",
                "sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
            },
            "frameCounts": {record["id"]: record["frameCount"] for record in records},
            "rows": records,
        },
    )


def test_synthetic_second_pet_runs_existing_cli_without_human_review(tmp_path: Path) -> None:
    root = tmp_path / "sample-orbit"
    make_fixture(root)
    run_cli(root, "build")
    digest = decoded_pixel_hash(root / "spritesheet.webp")
    write_json(
        root / "checks" / "index.json",
        {"schemaVersion": 1, "evidenceSets": [
            {"kind": "synthetic-fixture", "spritesheetSha256": digest, "path": "checks/synthetic"}
        ]},
    )
    write_json(
        root / "checks" / "synthetic" / "synthetic-validation.json",
        {"kind": "synthetic-fixture", "ok": True, "spritesheetSha256": digest},
    )

    assert '"qaEvidenceKind": "synthetic-fixture"' in run_cli(root, "validate", "--strict")
    package_output = tmp_path / "package"
    run_cli(root, "package", "--output-dir", str(package_output))
    zip_path = package_output / "sample-orbit-codex-pet-v9.8.7.zip"
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == ["sample-orbit/pet.json", "sample-orbit/spritesheet.webp"]
    run_cli(root, "check-release", "--output-dir", str(tmp_path / "check"))
    info = release_info(root)
    assert info["petId"] == "sample-orbit"
    assert info["qaEvidenceKind"] == "synthetic-fixture"
    assert info["qaSummaryPath"] == "checks/summary.md"
    with pytest.raises(ValueError, match="synthetic fixture evidence"):
        release_info(root, tag="v9.8.7", check_tag=True)
