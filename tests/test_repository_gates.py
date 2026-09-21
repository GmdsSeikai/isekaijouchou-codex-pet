from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from nemo_pet_builder.builder import load_manifest
from nemo_pet_builder.qa import combine_direction_verdicts
from nemo_pet_builder.validation import _source_errors


ROOT = Path(__file__).parents[1]


def test_source_manifest_hashes_and_paths_pass() -> None:
    assert _source_errors(ROOT, load_manifest(ROOT)) == []


def test_source_gate_rejects_absolute_path() -> None:
    manifest = copy.deepcopy(load_manifest(ROOT))
    manifest["rows"][0]["path"] = "C:\\Users\\example\\idle.png"
    errors = _source_errors(ROOT, manifest)
    assert any("must be relative" in error for error in errors)


def test_source_gate_rejects_hash_drift(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "row.png"
    source.write_bytes(b"changed")
    manifest = {
        "canonicalBase": {
            "path": "source/row.png",
            "prompt": "source/prompt.md",
            "sha256": "0" * 64,
        },
        "rows": [],
    }
    (source_dir / "prompt.md").write_text("prompt", encoding="utf-8")
    errors = _source_errors(tmp_path, manifest)
    assert any("source hash mismatch" in error for error in errors)


def test_blind_direction_gate_requires_all_expected_majorities(tmp_path: Path) -> None:
    source = ROOT / "qa" / "releases" / "v2.1.0"
    for name in (
        "direction-blind-answer-key.json",
        "direction-blind-verdicts-1.json",
        "direction-blind-verdicts-2.json",
        "direction-blind-verdicts-3.json",
    ):
        shutil.copyfile(source / name, tmp_path / name)
    assert combine_direction_verdicts(tmp_path, write=False)["ok"] is True

    for index in (1, 2):
        path = tmp_path / f"direction-blind-verdicts-{index}.json"
        verdict = json.loads(path.read_text(encoding="utf-8"))
        verdict["answers"]["H1"]["A"] = "screen-left"
        path.write_text(json.dumps(verdict), encoding="utf-8")
    failed = combine_direction_verdicts(tmp_path, write=False)
    assert failed["ok"] is False
    assert failed["warnings"]
