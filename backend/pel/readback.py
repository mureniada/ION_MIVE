"""Read-back verification for ION PEL Phase 2A raw-evidence persistence.

Reads a previously persisted raw-evidence artifact and its raw bytes back
from a caller-supplied storage root, verifying receipt/raw-file consistency
byte-for-byte. Performs no writes and alters no file.
"""

from __future__ import annotations

import json
from pathlib import Path

from .evidence_models import RawEvidenceArtifact
from .integrity import sha256_bytes
from .storage import EvidencePersistenceError, evidence_paths
from .validation import PELValidationError, validate_raw_evidence_artifact

__all__ = ["read_raw_evidence"]


def read_raw_evidence(
    *, storage_root: Path, run_id: str
) -> tuple[RawEvidenceArtifact, bytes]:
    _run_directory, raw_path, receipt_path = evidence_paths(
        storage_root=storage_root, run_id=run_id
    )

    if not raw_path.is_file():
        raise EvidencePersistenceError(
            "READBACK_FAILURE", f"missing raw evidence file: {raw_path}"
        )
    if not receipt_path.is_file():
        raise EvidencePersistenceError(
            "READBACK_FAILURE", f"missing receipt file: {receipt_path}"
        )

    try:
        receipt_bytes = receipt_path.read_bytes()
    except OSError as exc:
        raise EvidencePersistenceError(
            "READBACK_FAILURE", f"could not read receipt: {exc}"
        ) from exc

    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidencePersistenceError(
            "READBACK_FAILURE", f"receipt is not valid UTF-8 JSON: {exc}"
        ) from exc

    try:
        validate_raw_evidence_artifact(payload)
    except PELValidationError as exc:
        raise EvidencePersistenceError("SCHEMA_VALIDATION_FAILURE", str(exc)) from exc

    try:
        artifact = RawEvidenceArtifact(**payload)
    except (TypeError, ValueError) as exc:
        raise EvidencePersistenceError(
            "SCHEMA_VALIDATION_FAILURE",
            f"receipt does not construct a valid artifact: {exc}",
        ) from exc

    if artifact.run_id != run_id:
        raise EvidencePersistenceError(
            "RUN_ID_MISMATCH",
            f"receipt run_id {artifact.run_id!r} does not match requested {run_id!r}",
        )

    try:
        raw_bytes = raw_path.read_bytes()
    except OSError as exc:
        raise EvidencePersistenceError(
            "READBACK_FAILURE", f"could not read raw evidence bytes: {exc}"
        ) from exc

    if len(raw_bytes) != artifact.byte_count:
        raise EvidencePersistenceError(
            "READBACK_FAILURE",
            f"raw byte count {len(raw_bytes)} does not match receipt byte_count "
            f"{artifact.byte_count}",
        )

    if sha256_bytes(raw_bytes) != artifact.sha256:
        raise EvidencePersistenceError(
            "READBACK_DIGEST_MISMATCH",
            "raw evidence bytes do not match the receipt's recorded SHA-256",
        )

    return artifact, raw_bytes
