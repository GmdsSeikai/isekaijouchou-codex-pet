from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from .builder import build, decoded_pixel_hash
from .project import project_version
from .validation import validate_repository


def canonical_pet_json(root: Path) -> bytes:
    pet = json.loads((root / "pet.json").read_text(encoding="utf-8"))
    return (json.dumps(pet, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def package(root: Path, output_dir: Path | None = None) -> Path:
    validate_repository(root, strict=False)
    pet = json.loads((root / "pet.json").read_text(encoding="utf-8"))
    pet_id = pet["id"]
    version = project_version(root)
    dist_dir = output_dir or root / "dist"
    install_dir = dist_dir / pet_id
    install_dir.mkdir(parents=True, exist_ok=True)

    pet_bytes = canonical_pet_json(root)
    spritesheet_bytes = (root / pet["spritesheetPath"]).read_bytes()
    (install_dir / "pet.json").write_bytes(pet_bytes)
    (install_dir / "spritesheet.webp").write_bytes(spritesheet_bytes)

    zip_path = dist_dir / f"{pet_id}-codex-pet-v{version}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in (
            (f"{pet_id}/pet.json", pet_bytes),
            (f"{pet_id}/spritesheet.webp", spritesheet_bytes),
        ):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    checksum = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (dist_dir / "SHA256SUMS").write_text(f"{checksum}  {zip_path.name}\n", encoding="utf-8", newline="\n")
    print(f"packaged {zip_path}")
    return zip_path


def check_release(root: Path, output_dir: Path | None = None) -> None:
    validate_repository(root, strict=True)
    with tempfile.TemporaryDirectory(prefix="codex-pet-release-") as temporary:
        temporary_root = Path(temporary)
        rebuilt = build(root, temporary_root / "build")
        expected = decoded_pixel_hash(root / "spritesheet.webp")
        actual = decoded_pixel_hash(rebuilt)
        if actual != expected:
            raise ValueError(f"decoded RGBA hash mismatch: expected {expected}, got {actual}")

        zip_path = package(root, output_dir or temporary_root / "package")
        pet_id = json.loads((root / "pet.json").read_text(encoding="utf-8"))["id"]
        expected_names = [f"{pet_id}/pet.json", f"{pet_id}/spritesheet.webp"]
        with zipfile.ZipFile(zip_path) as archive:
            names = sorted(archive.namelist())
            if names != expected_names:
                raise ValueError(f"release ZIP contains {names}, expected {expected_names}")
            if archive.read(f"{pet_id}/pet.json") != canonical_pet_json(root):
                raise ValueError("release ZIP pet.json is not canonical")
    print(f"release check passed; decoded RGBA SHA-256 {expected}")
