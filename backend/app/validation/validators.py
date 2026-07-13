"""Validate contract dicts against the canonical JSON Schemas (the source of truth).

Uses `jsonschema`. Schemas are located by env override `ION_SCHEMAS_DIR`, else by
walking up from this file to find a `schemas/` directory. Provider adapters call
`validate_ive_report` after normalization; invalid output raises a precise error
and is never silently repaired (docs/05).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema


class SchemaValidationError(Exception):
    """Raised when a contract dict does not satisfy its canonical schema."""


@lru_cache(maxsize=1)
def _schemas_dir() -> Path:
    override = os.environ.get("ION_SCHEMAS_DIR")
    if override:
        p = Path(override)
        if (p / "context_pack.schema.json").exists():
            return p
        raise SchemaValidationError(f"ION_SCHEMAS_DIR has no schemas: {p}")
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if (candidate / "context_pack.schema.json").exists():
            return candidate
    raise SchemaValidationError(
        "Could not locate schemas/ directory; set ION_SCHEMAS_DIR."
    )


@lru_cache(maxsize=8)
def _load(name: str) -> dict[str, Any]:
    path = _schemas_dir() / name
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(instance: dict[str, Any], schema_name: str) -> None:
    schema = _load(schema_name)
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as exc:
        # jsonschema messages can echo values; keep it short and path-focused.
        location = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise SchemaValidationError(
            f"{schema_name}: invalid at '{location}': {exc.message}"
        ) from None


def validate_context_pack(instance: dict[str, Any]) -> None:
    _validate(instance, "context_pack.schema.json")


def validate_ive_report(instance: dict[str, Any]) -> None:
    _validate(instance, "ive_report.schema.json")


def validate_mive_result(instance: dict[str, Any]) -> None:
    _validate(instance, "mive_result.schema.json")
