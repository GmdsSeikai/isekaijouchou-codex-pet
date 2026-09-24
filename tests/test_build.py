from __future__ import annotations

import zipfile
import json
from pathlib import Path

from PIL import Image, ImageChops

from nemo_pet_builder.builder import ATLAS_SIZE, build
from nemo_pet_builder.packaging import check_release, decoded_pixel_hash, package
from nemo_pet_builder.project import find_qa_evidence, release_info
from nemo_pet_builder.validation import validate_repository


ROOT = Path(__file__).parents[1]


def test_clean_source_rebuild_matches_committed_pixels(tmp_path: Path) -> None:
    rebuilt = build(ROOT, tmp_path)
    assert decoded_pixel_hash(rebuilt) == decoded_pixel_hash(ROOT / "spritesheet.webp")
    assert validate_repository(ROOT, strict=True, output_dir=tmp_path)["ok"] is True
    with Image.open(rebuilt) as image:
        assert image.size == ATLAS_SIZE
        assert image.mode == "RGBA"


def test_running_left_is_framewise_mirror_of_running_right(tmp_path: Path) -> None:
    rebuilt = build(ROOT, tmp_path)
    with Image.open(rebuilt) as opened:
        atlas = opened.convert("RGBA")
    right = atlas.crop((0, 208, 1536, 416))
    left = atlas.crop((0, 416, 1536, 624))
    expected = Image.new("RGBA", left.size, (0, 0, 0, 0))
    for column in range(8):
        frame = right.crop((column * 192, 0, (column + 1) * 192, 208))
        expected.alpha_composite(frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (column * 192, 0))
    assert ImageChops.difference(left, expected).getbbox() is None


def test_release_zip_has_only_runtime_files(tmp_path: Path) -> None:
    zip_path = package(ROOT, tmp_path)
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == [
            "nemo-dango/pet.json",
            "nemo-dango/spritesheet.webp",
        ]


def test_release_info_resolves_version_and_rejects_mismatched_tag() -> None:
    info = release_info(ROOT, tag="v" + release_info(ROOT)["version"], check_tag=True)
    assert info["zipName"].endswith(".zip")
    assert info["spritesheetSha256"] == decoded_pixel_hash(ROOT / "spritesheet.webp")
    assert info["qaSourceRelease"] == find_qa_evidence(ROOT, info["spritesheetSha256"])["reviewedRelease"]

    import pytest

    with pytest.raises(ValueError, match="release tag mismatch"):
        release_info(ROOT, tag="v0.0.0", check_tag=True)


def test_packaging_is_independent_of_pet_json_line_endings(tmp_path: Path, monkeypatch) -> None:
    import codex_pet_builder.packaging as packaging

    monkeypatch.setattr(packaging, "validate_repository", lambda *_args, **_kwargs: {})
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="9.8.7"\n', encoding="utf-8")
    (project / "spritesheet.webp").write_bytes(b"same image bytes")
    pet = {"id": "line-ending-fixture", "displayName": "Line Ending", "description": "test", "spriteVersionNumber": 2, "spritesheetPath": "spritesheet.webp"}

    lf_root = tmp_path / "lf"
    crlf_root = tmp_path / "crlf"
    for root, newline in ((lf_root, b"\n"), (crlf_root, b"\r\n")):
        root.mkdir()
        (root / "pyproject.toml").write_bytes((project / "pyproject.toml").read_bytes())
        (root / "spritesheet.webp").write_bytes((project / "spritesheet.webp").read_bytes())
        serialized = json.dumps(pet, ensure_ascii=False, indent=2).replace("\n", newline.decode()) + newline.decode()
        (root / "pet.json").write_bytes(serialized.encode("utf-8"))

    lf_zip = package(lf_root, tmp_path / "out-lf")
    crlf_zip = package(crlf_root, tmp_path / "out-crlf")
    assert lf_zip.read_bytes() == crlf_zip.read_bytes()


def test_check_release_writes_no_artifacts_into_repository(tmp_path: Path, monkeypatch) -> None:
    import codex_pet_builder.packaging as packaging

    monkeypatch.setattr(packaging, "validate_repository", lambda *_args, **_kwargs: {})

    def copy_build(_root: Path, output_root: Path) -> Path:
        output_root.mkdir(parents=True, exist_ok=True)
        target = output_root / "spritesheet.webp"
        target.write_bytes((ROOT / "spritesheet.webp").read_bytes())
        return target

    monkeypatch.setattr(packaging, "build", copy_build)
    dist = ROOT / "dist"
    before = {
        item.relative_to(dist).as_posix(): item.read_bytes()
        for item in dist.rglob("*")
        if item.is_file()
    }
    packaging.check_release(ROOT)
    after = {
        item.relative_to(dist).as_posix(): item.read_bytes()
        for item in dist.rglob("*")
        if item.is_file()
    }
    assert after == before
