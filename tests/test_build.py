from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image, ImageChops

from nemo_pet_builder.builder import ATLAS_SIZE, build
from nemo_pet_builder.packaging import decoded_pixel_hash, package


ROOT = Path(__file__).parents[1]


def test_clean_source_rebuild_matches_committed_pixels(tmp_path: Path) -> None:
    rebuilt = build(ROOT, tmp_path)
    assert decoded_pixel_hash(rebuilt) == decoded_pixel_hash(ROOT / "spritesheet.webp")
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


def test_release_zip_has_only_runtime_files() -> None:
    zip_path = package(ROOT)
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == [
            "nemo-dango/pet.json",
            "nemo-dango/spritesheet.webp",
        ]
