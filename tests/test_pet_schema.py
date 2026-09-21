from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "pet.schema.json").read_text(encoding="utf-8"))
PET = json.loads((ROOT / "pet.json").read_text(encoding="utf-8"))


def validation_errors(instance: dict[str, object]) -> list[str]:
    return [error.message for error in Draft202012Validator(SCHEMA).iter_errors(instance)]


def test_runtime_manifest_matches_schema() -> None:
    assert validation_errors(PET) == []


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("id", "Nemo_Dango"),
        ("displayName", ""),
        ("description", ""),
        ("spriteVersionNumber", 1),
        ("spritesheetPath", "atlas.png"),
    ),
)
def test_schema_rejects_invalid_runtime_values(field: str, value: object) -> None:
    candidate = copy.deepcopy(PET)
    candidate[field] = value
    assert validation_errors(candidate)


def test_schema_rejects_missing_and_extra_fields() -> None:
    missing = copy.deepcopy(PET)
    missing.pop("description")
    extra = copy.deepcopy(PET)
    extra["schemaVersion"] = 2
    assert validation_errors(missing)
    assert validation_errors(extra)
