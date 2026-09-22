from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from nemo_pet_builder.builder import load_manifest
from nemo_pet_builder.qa import combine_direction_verdicts
from nemo_pet_builder.project import find_qa_evidence, release_info
from nemo_pet_builder.validation import _source_errors, _strict_qa_errors


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


def test_source_gate_rejects_existing_file_outside_repository(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    external_source = tmp_path / "external.png"
    external_prompt = tmp_path / "external.md"
    external_source.write_bytes(b"external art")
    external_prompt.write_text("external prompt", encoding="utf-8")
    manifest = {
        "canonicalBase": {
            "path": "../external.png",
            "prompt": "../external.md",
            "sha256": "0" * 64,
        },
        "rows": [],
    }
    errors = _source_errors(root, manifest)
    assert any("path escapes repository" in error for error in errors)
    assert any("prompt escapes repository" in error for error in errors)


def test_strict_qa_rejects_unindexed_pixel_hash(monkeypatch) -> None:
    import nemo_pet_builder.validation as validation

    monkeypatch.setattr(validation, "decoded_pixel_hash", lambda _path: "0" * 64)
    errors = _strict_qa_errors(ROOT, ROOT / "spritesheet.webp")
    assert any("no audited evidence" in error for error in errors)


def test_strict_qa_rejects_mislabelled_evidence_path(monkeypatch) -> None:
    import nemo_pet_builder.validation as validation

    monkeypatch.setattr(
        validation,
        "find_qa_evidence",
        lambda *_args: {
            "path": "qa/releases/v2.1.0",
            "reviewedRelease": "v9.9.9",
            "reviewerCount": 3,
            "classificationCount": 28,
            "reviewStatus": "pass",
            "warnings": [],
            "unconfirmed": [],
        },
    )
    errors = _strict_qa_errors(ROOT, ROOT / "spritesheet.webp")
    assert any("does not match its declared reviewedRelease" in error for error in errors)


def test_strict_qa_rejects_reduced_blind_evidence_with_unchanged_index(tmp_path: Path, monkeypatch) -> None:
    import nemo_pet_builder.validation as validation

    evidence = json.loads((ROOT / "qa" / "evidence-index.json").read_text(encoding="utf-8"))["evidenceSets"][0]
    source = ROOT / evidence["path"]
    qa_dir = tmp_path / evidence["path"]
    shutil.copytree(source, qa_dir)
    monkeypatch.setattr(validation, "project_version", lambda _root: "2.1.0")
    monkeypatch.setattr(validation, "find_qa_evidence", lambda *_args: copy.deepcopy(evidence))
    monkeypatch.setattr(validation, "decoded_pixel_hash", lambda _path: evidence["spritesheetSha256"])

    answer_key_path = qa_dir / "direction-blind-answer-key.json"
    answer_key = json.loads(answer_key_path.read_text(encoding="utf-8"))
    answer_key["pairs"].pop()
    answer_key_path.write_text(json.dumps(answer_key), encoding="utf-8")
    for index in range(1, 4):
        verdict_path = qa_dir / f"direction-blind-verdicts-{index}.json"
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        verdict["answers"].pop("V7")
        verdict_path.write_text(json.dumps(verdict), encoding="utf-8")
    result_path = qa_dir / "direction-blind-validation.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["results"].pop()
    result_path.write_text(json.dumps(result), encoding="utf-8")

    errors = _strict_qa_errors(tmp_path, ROOT / "spritesheet.webp")
    assert any("expected exactly the unique H1-H7 and V1-V7 pairs" in error for error in errors)


def test_blind_direction_gate_requires_all_expected_majorities(tmp_path: Path) -> None:
    source = ROOT / find_qa_evidence(ROOT, release_info(ROOT)["spritesheetSha256"])["path"]
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
