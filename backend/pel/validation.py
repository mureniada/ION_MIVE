"""PEL-local JSON Schema validation for ION PEL Phase 1.

Validates contract dicts against the canonical JSON Schemas in `schemas/`,
under Draft 2020-12 semantics. Schemas are read-only from the repository's
`schemas/` directory, located by walking up from this file. Independent of
`backend/app/validation/validators.py` — no import from `app` or `t4`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

__all__ = [
    "PELValidationError",
    "validate_execution_plan",
    "validate_normalized_judgment_artifact",
    "validate_normalized_judgment_persistence_result",
    "validate_normalized_judgment_v0_2_2",
    "validate_persistence_result",
    "validate_raw_evidence_artifact",
    "validate_replay_execution_descriptor",
    "validate_replay_execution_descriptor_persistence_result",
    "validate_run_record",
    "validate_task_spec",
]


class PELValidationError(Exception):
    """A PEL contract dict did not satisfy its canonical schema."""


@lru_cache(maxsize=1)
def _schemas_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if (candidate / "pel_task_spec.schema.json").exists():
            return candidate
    raise PELValidationError("Could not locate the repository's schemas/ directory.")


@lru_cache(maxsize=8)
def _load(name: str) -> dict[str, Any]:
    path = _schemas_dir() / name
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(instance: dict[str, Any], schema_name: str) -> None:
    schema = _load(schema_name)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    first = errors[0]
    location = "/".join(str(p) for p in first.absolute_path) or "<root>"
    raise PELValidationError(
        f"{schema_name}: invalid at '{location}': {first.message}"
    ) from first


def validate_task_spec(payload: dict) -> None:
    _validate(payload, "pel_task_spec.schema.json")


def validate_execution_plan(payload: dict) -> None:
    _validate(payload, "pel_execution_plan.schema.json")


def validate_run_record(payload: dict) -> None:
    _validate(payload, "pel_run_record.schema.json")


def validate_raw_evidence_artifact(payload: dict) -> None:
    _validate(payload, "pel_raw_evidence_artifact.schema.json")


def validate_persistence_result(payload: dict) -> None:
    _validate(payload, "pel_persistence_result.schema.json")


def validate_normalized_judgment_v0_2_2(payload: dict) -> None:
    _validate(payload, "pel_normalized_judgment_v0_2_2.schema.json")


def validate_normalized_judgment_artifact(payload: dict) -> None:
    _validate(payload, "pel_normalized_judgment_artifact.schema.json")


def validate_normalized_judgment_persistence_result(payload: dict) -> None:
    _validate(payload, "pel_normalized_judgment_persistence_result.schema.json")


def validate_replay_execution_descriptor(payload: dict) -> None:
    _validate(payload, "pel_replay_execution_descriptor_v0_1.schema.json")


def validate_replay_execution_descriptor_persistence_result(payload: dict) -> None:
    _validate(payload, "pel_replay_execution_descriptor_persistence_result.schema.json")
