"""Readback verification for CanonicalTaskBinding v0.1."""

from __future__ import annotations

import json
from pathlib import Path

from .canonical_task_binding import compute_canonical_task_binding_id
from .canonical_task_binding_models import CanonicalTaskBindingV0_1
from .canonical_task_binding_storage import (
    CanonicalTaskBindingPersistenceError,
    canonical_task_binding_path,
)
from .validation import (
    PELValidationError,
    validate_canonical_task_binding_v0_1,
)


__all__ = ["read_canonical_task_binding"]


def read_canonical_task_binding(
    *,
    storage_root: Path,
    run_id: str,
) -> tuple[CanonicalTaskBindingV0_1, bytes]:
    expected_binding_id = compute_canonical_task_binding_id(
        run_id=run_id
    )

    _directory, binding_path = canonical_task_binding_path(
        storage_root=storage_root,
        run_id=run_id,
        binding_id=expected_binding_id,
    )

    if not binding_path.is_file():
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_READBACK_FAILURE",
            f"missing binding file: {binding_path}",
        )

    try:
        binding_bytes = binding_path.read_bytes()
    except OSError as exc:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_READBACK_FAILURE",
            f"could not read binding: {exc}",
        ) from exc

    try:
        payload = json.loads(binding_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_SCHEMA_VALIDATION_FAILURE",
            f"binding JSON could not be decoded: {exc}",
        ) from exc

    if not isinstance(payload, dict):
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_SCHEMA_VALIDATION_FAILURE",
            "binding JSON root must be an object",
        )

    try:
        validate_canonical_task_binding_v0_1(payload)
        binding = CanonicalTaskBindingV0_1(**payload)
    except (PELValidationError, TypeError, ValueError) as exc:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_SCHEMA_VALIDATION_FAILURE",
            str(exc),
        ) from exc

    if binding.binding_id != expected_binding_id:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_IDENTITY_MISMATCH",
            f"binding_id {binding.binding_id!r} does not match "
            f"expected {expected_binding_id!r}",
        )

    if binding.run_id != run_id:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_IDENTITY_MISMATCH",
            f"binding run_id {binding.run_id!r} does not match "
            f"requested run_id {run_id!r}",
        )

    return binding, binding_bytes