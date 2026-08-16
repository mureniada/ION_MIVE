"""Storage-safety primitives for ION PEL Phase 2B.2 normalized-judgment
persistence.

Reuses Phase 2A's path-safety primitives (``require_storage_root``,
``require_storage_component``) unchanged, translated to this phase's own
closed failure-code set. Phase 2A's evidence directory
(``{storage_root}/{run_id}/raw.bin``, ``.../receipt.json``) is never
written to, modified, or nested into by this module -- Phase 2B.2 uses the
disjoint ``{storage_root}/normalized/...`` namespace. No app dependency,
no t4 dependency, no network.
"""

from __future__ import annotations

from pathlib import Path

from .storage import EvidencePersistenceError, require_storage_component, require_storage_root

__all__ = [
    "NORMALIZED_PERSISTENCE_FAILURE_CODES",
    "NormalizedPersistenceError",
    "normalized_judgment_paths",
]

#: IC-style closed failure-code set, frozen by
#: ION_PEL_PHASE2B2_DERIVED_ARTIFACT_PERSISTENCE_CONTRACT_FREEZE_v0.1.md
#: section 14. An undocumented code is rejected.
NORMALIZED_PERSISTENCE_FAILURE_CODES = (
    "NORMALIZED_ALREADY_EXISTS",
    "STORAGE_ROOT_VIOLATION",
    "SOURCE_RAW_NOT_FOUND",
    "SOURCE_RAW_DIGEST_MISMATCH",
    "SOURCE_EVIDENCE_ID_MISMATCH",
    "NORMALIZED_SCHEMA_VALIDATION_FAILURE",
    "NORMALIZED_WRITE_FAILURE",
    "NORMALIZED_RECEIPT_WRITE_FAILURE",
    "NORMALIZED_READBACK_FAILURE",
    "NORMALIZED_ARTIFACT_DIGEST_MISMATCH",
    "NORMALIZED_RECEIPT_DIGEST_MISMATCH",
    "NORMALIZED_IDENTITY_MISMATCH",
)

_NAMESPACE = "normalized"
_JUDGMENT_FILENAME = "judgment.json"
_RECEIPT_FILENAME = "receipt.json"


class NormalizedPersistenceError(RuntimeError):
    """A Phase-2B.2 normalized-judgment-persistence operation refused to proceed."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in NORMALIZED_PERSISTENCE_FAILURE_CODES:
            raise AssertionError(f"undocumented failure code {code!r}")
        super().__init__(f"{code}: {detail}")
        self.code = code


def _safe_root(storage_root: Path) -> Path:
    try:
        return require_storage_root(storage_root)
    except EvidencePersistenceError as exc:
        raise NormalizedPersistenceError(
            exc.code, f"storage root violation: {storage_root!r}"
        ) from exc


def _safe_component(value: str, *, field_name: str) -> str:
    try:
        return require_storage_component(value, field_name=field_name)
    except EvidencePersistenceError as exc:
        raise NormalizedPersistenceError(
            exc.code, f"{field_name}: unsafe storage path component {value!r}"
        ) from exc


def normalized_judgment_paths(
    *,
    storage_root: Path,
    run_id: str,
    output_contract_id: str,
    parser_id: str,
    parser_version: str,
    normalized_schema_id_digest: str,
) -> tuple[Path, Path, Path]:
    """Return ``(artifact_directory, judgment_path, receipt_path)``.

    Rooted at ``{storage_root}/normalized/{run_id}/{output_contract_id}/
    {parser_id}/{parser_version}/{normalized_schema_id_digest}/`` -- a
    namespace disjoint from Phase 2A's ``{storage_root}/{run_id}/`` files.
    Every dynamic segment passes through the same safe-component check
    Phase 2A uses.
    """
    resolved_root = _safe_root(storage_root)
    safe_run_id = _safe_component(run_id, field_name="run_id")
    safe_contract = _safe_component(output_contract_id, field_name="output_contract_id")
    safe_parser = _safe_component(parser_id, field_name="parser_id")
    safe_version = _safe_component(parser_version, field_name="parser_version")
    safe_schema_digest = _safe_component(
        normalized_schema_id_digest, field_name="normalized_schema_id_digest"
    )

    expected_parent = (
        resolved_root
        / _NAMESPACE
        / safe_run_id
        / safe_contract
        / safe_parser
        / safe_version
    ).resolve()
    artifact_directory = (expected_parent / safe_schema_digest).resolve()
    if artifact_directory.parent != expected_parent:
        raise NormalizedPersistenceError(
            "STORAGE_ROOT_VIOLATION",
            f"normalized artifact directory does not resolve beneath the expected "
            f"path: {artifact_directory}",
        )

    judgment_path = artifact_directory / _JUDGMENT_FILENAME
    receipt_path = artifact_directory / _RECEIPT_FILENAME
    return artifact_directory, judgment_path, receipt_path
