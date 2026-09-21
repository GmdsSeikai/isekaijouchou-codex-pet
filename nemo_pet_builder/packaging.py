from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from .builder import build, decoded_pixel_hash
from .validation import validate_repository


def package(root: Path) -> Path:
    validate_repository(root, strict=False)
    pet = json.loads((root / "pet.json").read_text(encoding="utf-8"))
    pet_id = pet["id"]
    version = "2.1.0"
    install_dir = root / "dist" / pet_id
    install_dir.mkdir(parents=True, exist_ok=True)
    for name in ("pet.json", "spritesheet.webp"):
        (install_dir / name).write_bytes((root / name).read_bytes())

    zip_path = root / "dist" / f"{pet_id}-codex-pet-v{version}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in ("pet.json", "spritesheet.webp"):
            info = zipfile.ZipInfo(f"{pet_id}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (root / name).read_bytes())
    checksum = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (root / "dist" / "SHA256SUMS").write_text(
        f"{checksum}  {zip_path.name}\n", encoding="utf-8"
    )
    print(f"packaged {zip_path}")
    return zip_path


def check_release(root: Path) -> None:
    validate_repository(root, strict=True)
    with tempfile.TemporaryDirectory(prefix="nemo-dango-release-") as temporary:
        rebuilt = build(root, Path(temporary))
        expected = decoded_pixel_hash(root / "spritesheet.webp")
        actual = decoded_pixel_hash(rebuilt)
        if actual != expected:
            raise ValueError(f"decoded RGBA hash mismatch: expected {expected}, got {actual}")
    zip_path = package(root)
    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(archive.namelist())
    expected_names = ["nemo-dango/pet.json", "nemo-dango/spritesheet.webp"]
    if names != expected_names:
        raise ValueError(f"release ZIP contains {names}, expected {expected_names}")
    print(f"release check passed; decoded RGBA SHA-256 {expected}")
