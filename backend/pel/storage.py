"""Storage-safety primitives for ION PEL Phase 2A raw-evidence persistence.

All evidence persistence is rooted beneath an explicit, caller-supplied
storage root. There is no implicit or default repository storage location,
and this module never creates the root itself. No app dependency, no t4
dependency, no network.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "EVIDENCE_PERSISTENCE_FAILURE_CODES",
    "EvidencePersistenceError",
    "evidence_paths",
    "require_storage_component",
    "require_storage_root",
]

#: IC-style closed failure-code set. An undocumented code is rejected.
EVIDENCE_PERSISTENCE_FAILURE_CODES = (
    "EVIDENCE_ALREADY_EXISTS",
    "STORAGE_ROOT_VIOLATION",
    "RUN_ID_MISMATCH",
    "RAW_DIGEST_MISMATCH",
    "RAW_BYTE_COUNT_MISMATCH",
    "WRITE_FAILURE",
    "RECEIPT_WRITE_FAILURE",
    "READBACK_FAILURE",
    "READBACK_DIGEST_MISMATCH",
    "SCHEMA_VALIDATION_FAILURE",
)

_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RAW_FILENAME = "raw.bin"
_RECEIPT_FILENAME = "receipt.json"


class EvidencePersistenceError(RuntimeError):
    """A Phase-2A evidence-persistence operation refused to proceed."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in EVIDENCE_PERSISTENCE_FAILURE_CODES:
            raise AssertionError(f"undocumented failure code {code!r}")
        super().__init__(f"{code}: {detail}")
        self.code = code


def require_storage_root(storage_root: Path) -> Path:
    """Resolve and validate a caller-supplied storage root.

    The root must already exist and be a directory. It is never created here.
    """
    try:
        resolved = Path(storage_root).resolve(strict=True)
    except OSError as exc:
        raise EvidencePersistenceError(
            "STORAGE_ROOT_VIOLATION",
            f"storage root does not resolve: {storage_root!r}: {exc}",
        ) from exc
    if not resolved.is_dir():
        raise EvidencePersistenceError(
            "STORAGE_ROOT_VIOLATION",
            f"storage root is not a directory: {resolved}",
        )
    return resolved


def require_storage_component(value: str, *, field_name: str) -> str:
    """Reject any value unsafe as a single filesystem path component.

    Never sanitizes or rewrites the value — an unsafe value is refused, not
    repaired.
    """
    if value in (".", ".."):
        raise EvidencePersistenceError(
            "STORAGE_ROOT_VIOLATION",
            f"{field_name} must not be '.' or '..', got {value!r}",
        )
    if not isinstance(value, str) or not _SAFE_COMPONENT_RE.fullmatch(value):
        raise EvidencePersistenceError(
            "STORAGE_ROOT_VIOLATION",
            f"{field_name} is not a safe single path component: {value!r}",
        )
    return value


def evidence_paths(*, storage_root: Path, run_id: str) -> tuple[Path, Path, Path]:
    """Return ``(run_directory, raw_path, receipt_path)``, all beneath ``storage_root``."""
    resolved_root = require_storage_root(storage_root)
    safe_run_id = require_storage_component(run_id, field_name="run_id")

    run_directory = (resolved_root / safe_run_id).resolve()
    if run_directory.parent != resolved_root:
        raise EvidencePersistenceError(
            "STORAGE_ROOT_VIOLATION",
            f"run directory does not resolve as a direct child of the storage "
            f"root: {run_directory}",
        )

    raw_path = run_directory / _RAW_FILENAME
    receipt_path = run_directory / _RECEIPT_FILENAME
    return run_directory, raw_path, receipt_path
