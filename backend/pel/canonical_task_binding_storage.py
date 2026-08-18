"""Storage-safety primitives for CanonicalTaskBinding v0.1."""

from __future__ import annotations

from pathlib import Path

from .storage import (
    EvidencePersistenceError,
    require_storage_component,
    require_storage_root,
)


CANONICAL_TASK_BINDING_FAILURE_CODES = (
    "CANONICAL_TASK_BINDING_ALREADY_EXISTS",
    "CANONICAL_TASK_BINDING_SCHEMA_VALIDATION_FAILURE",
    "CANONICAL_TASK_BINDING_SOURCE_MISMATCH",
    "CANONICAL_TASK_BINDING_STORAGE_ROOT_VIOLATION",
    "CANONICAL_TASK_BINDING_WRITE_FAILURE",
    "CANONICAL_TASK_BINDING_READBACK_FAILURE",
    "CANONICAL_TASK_BINDING_IDENTITY_MISMATCH",
)

_NAMESPACE = "canonical-task-binding"
_BINDING_FILENAME = "binding.json"


__all__ = [
    "CANONICAL_TASK_BINDING_FAILURE_CODES",
    "CanonicalTaskBindingPersistenceError",
    "canonical_task_binding_path",
]


class CanonicalTaskBindingPersistenceError(Exception):
    def __init__(self, code: str, detail: str):
        if code not in CANONICAL_TASK_BINDING_FAILURE_CODES:
            raise AssertionError(f"undocumented failure code {code!r}")
        super().__init__(f"{code}: {detail}")
        self.code = code


def _safe_root(storage_root: Path) -> Path:
    try:
        return require_storage_root(storage_root)
    except EvidencePersistenceError as exc:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_STORAGE_ROOT_VIOLATION",
            f"storage root violation: {storage_root!r}",
        ) from exc


def _safe_component(value: str, *, field_name: str) -> str:
    try:
        return require_storage_component(value, field_name=field_name)
    except EvidencePersistenceError as exc:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_STORAGE_ROOT_VIOLATION",
            f"{field_name}: unsafe storage path component {value!r}",
        ) from exc


def canonical_task_binding_path(
    *,
    storage_root: Path,
    run_id: str,
    binding_id: str,
) -> tuple[Path, Path]:
    resolved_root = _safe_root(storage_root)
    safe_run_id = _safe_component(run_id, field_name="run_id")
    safe_binding_id = _safe_component(binding_id, field_name="binding_id")

    expected_parent = (
        resolved_root / _NAMESPACE / safe_run_id
    ).resolve()

    binding_directory = (
        expected_parent / safe_binding_id
    ).resolve()

    if binding_directory.parent != expected_parent:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_STORAGE_ROOT_VIOLATION",
            f"binding directory escaped expected parent: {binding_directory}",
        )

    return binding_directory, binding_directory / _BINDING_FILENAME