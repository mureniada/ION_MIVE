"""Storage-safety primitives for ION PEL ReplayExecutionDescriptor
persistence.

Reuses Phase 2A's path-safety primitives (``require_storage_root``,
``require_storage_component``) unchanged, translated to this object's own
closed failure-code set. Phase 2A's evidence directory
(``{storage_root}/{run_id}/raw.bin``, ``.../receipt.json``) and Phase
2B.2's ``{storage_root}/normalized/...`` namespace are never written to,
modified, or nested into by this module -- this object uses the disjoint
``{storage_root}/replay-execution/...`` namespace. No app dependency, no
t4 dependency, no network.
"""

from __future__ import annotations

from pathlib import Path

from .storage import EvidencePersistenceError, require_storage_component, require_storage_root

__all__ = [
    "REPLAY_EXECUTION_DESCRIPTOR_FAILURE_CODES",
    "ReplayExecutionDescriptorPersistenceError",
    "replay_execution_descriptor_path",
]

#: IC-style closed failure-code set, frozen by
#: ION_PEL_REPLAY_EXECUTION_DESCRIPTOR_CONTRACT_FREEZE_v0.1.md section 18,
#: extended by exactly one code from
#: ION_PEL_REPLAY_EXECUTION_DESCRIPTOR_FAILURE_CODE_CLOSURE_v0.1.md.
#: An undocumented code is rejected.
REPLAY_EXECUTION_DESCRIPTOR_FAILURE_CODES = (
    "EXECUTION_DESCRIPTOR_STORAGE_ROOT_VIOLATION",
    "EXECUTION_DESCRIPTOR_SOURCE_RAW_NOT_FOUND",
    "EXECUTION_DESCRIPTOR_TASK_SHA256_MISMATCH",
    "EXECUTION_DESCRIPTOR_PROMPT_SHA256_MISMATCH",
    "EXECUTION_DESCRIPTOR_ALREADY_EXISTS",
    "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE",
    "EXECUTION_DESCRIPTOR_WRITE_FAILURE",
    "EXECUTION_DESCRIPTOR_READBACK_FAILURE",
    "EXECUTION_DESCRIPTOR_DIGEST_MISMATCH",
    "EXECUTION_DESCRIPTOR_IDENTITY_MISMATCH",
    "EXECUTION_DESCRIPTOR_CONDITION_PROVENANCE_MISMATCH",
)

_NAMESPACE = "replay-execution"
_DESCRIPTOR_FILENAME = "descriptor.json"


class ReplayExecutionDescriptorPersistenceError(RuntimeError):
    """A ReplayExecutionDescriptor persistence operation refused to proceed."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in REPLAY_EXECUTION_DESCRIPTOR_FAILURE_CODES:
            raise AssertionError(f"undocumented failure code {code!r}")
        super().__init__(f"{code}: {detail}")
        self.code = code


def _safe_root(storage_root: Path) -> Path:
    try:
        return require_storage_root(storage_root)
    except EvidencePersistenceError as exc:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_STORAGE_ROOT_VIOLATION",
            f"storage root violation: {storage_root!r}",
        ) from exc


def _safe_component(value: str, *, field_name: str) -> str:
    try:
        return require_storage_component(value, field_name=field_name)
    except EvidencePersistenceError as exc:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_STORAGE_ROOT_VIOLATION",
            f"{field_name}: unsafe storage path component {value!r}",
        ) from exc


def replay_execution_descriptor_path(
    *, storage_root: Path, run_id: str, schema_id_digest: str
) -> tuple[Path, Path]:
    """Return ``(descriptor_directory, descriptor_path)``.

    Rooted at ``{storage_root}/replay-execution/{run_id}/{schema_id_digest}/``
    -- a namespace disjoint from Phase 2A's ``{storage_root}/{run_id}/``
    files and Phase 2B.2's ``{storage_root}/normalized/...`` files. Every
    dynamic segment passes through the same safe-component check Phase 2A
    uses.
    """
    resolved_root = _safe_root(storage_root)
    safe_run_id = _safe_component(run_id, field_name="run_id")
    safe_schema_digest = _safe_component(schema_id_digest, field_name="schema_id_digest")

    expected_parent = (resolved_root / _NAMESPACE / safe_run_id).resolve()
    descriptor_directory = (expected_parent / safe_schema_digest).resolve()
    if descriptor_directory.parent != expected_parent:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_STORAGE_ROOT_VIOLATION",
            f"descriptor directory does not resolve beneath the expected "
            f"path: {descriptor_directory}",
        )

    descriptor_path = descriptor_directory / _DESCRIPTOR_FILENAME
    return descriptor_directory, descriptor_path
