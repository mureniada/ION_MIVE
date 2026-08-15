"""Raw-evidence persistence for ION PEL Phase 2A.

``persist_raw_evidence`` is the only Phase-2A write path. It writes exactly
two files — raw evidence bytes and a receipt — beneath an explicit,
caller-supplied storage root, and only after every pre-write check in
section 8.1 of the mandate passes. Raw bytes are never normalized, decoded,
or interpreted. No app dependency, no t4 dependency, no network.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .evidence_models import PersistenceResult, RawEvidenceArtifact
from .integrity import sha256_bytes
from .models import RunRecord
from .readback import read_raw_evidence
from .storage import EvidencePersistenceError, evidence_paths
from .validation import (
    PELValidationError,
    validate_raw_evidence_artifact,
    validate_run_record,
)

__all__ = ["persist_raw_evidence"]


def _serialize_receipt(payload: dict) -> bytes:
    """The Phase-2A deterministic JSON serialization convention (section 7).

    Not RFC 8785, not canonical JSON — a deterministic, sorted-key, compact
    serialization local to Phase 2A.
    """
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
        + b"\n"
    )


def _fsync_best_effort(handle) -> None:
    try:
        os.fsync(handle.fileno())
    except OSError:
        pass


def _cleanup(*, run_directory: Path | None, raw_path: Path | None,
             receipt_path: Path | None) -> list[str]:
    """Remove only what this call created. Never touches a pre-existing path."""
    problems: list[str] = []
    for label, path in (("receipt.json", receipt_path), ("raw.bin", raw_path)):
        if path is not None:
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                problems.append(f"could not remove {label} ({path}): {exc}")
    if run_directory is not None:
        try:
            if run_directory.exists():
                run_directory.rmdir()
        except OSError as exc:
            problems.append(f"could not remove run directory ({run_directory}): {exc}")
    return problems


def persist_raw_evidence(
    *,
    storage_root: Path,
    run_record: RunRecord,
    raw_bytes: bytes,
    persisted_at: str,
) -> PersistenceResult:
    # -- section 8.1: pre-write validation. No filesystem mutation above this
    # point; every failure here leaves the storage root unchanged. --

    # 1. validate run_record.to_dict() against the Phase-1 run-record schema
    try:
        validate_run_record(run_record.to_dict())
    except PELValidationError as exc:
        raise EvidencePersistenceError("SCHEMA_VALIDATION_FAILURE", str(exc)) from exc

    # 2. run_record.run_status must be RAW_FROZEN
    if run_record.run_status != "RAW_FROZEN":
        raise EvidencePersistenceError(
            "SCHEMA_VALIDATION_FAILURE",
            f"run_record.run_status must be RAW_FROZEN, got {run_record.run_status!r}",
        )

    # 3. run_record.raw_sha256 must equal SHA-256(exact supplied raw_bytes)
    computed_sha256 = sha256_bytes(raw_bytes)
    if run_record.raw_sha256 != computed_sha256:
        raise EvidencePersistenceError(
            "RAW_DIGEST_MISMATCH",
            f"run_record.raw_sha256 {run_record.raw_sha256!r} does not match "
            f"SHA-256 of the supplied raw_bytes {computed_sha256!r}",
        )

    # 4. run_record.raw_bytes must equal len(raw_bytes)
    if run_record.raw_bytes != len(raw_bytes):
        raise EvidencePersistenceError(
            "RAW_BYTE_COUNT_MISMATCH",
            f"run_record.raw_bytes {run_record.raw_bytes} does not match "
            f"len(raw_bytes) {len(raw_bytes)}",
        )

    # 5. require a safe run_id, and resolve the (unwritten) evidence paths
    run_directory, raw_path, receipt_path = evidence_paths(
        storage_root=storage_root, run_id=run_record.run_id
    )

    # 6. require non-empty raw_artifact_id and persisted_at
    if not run_record.raw_artifact_id:
        raise EvidencePersistenceError(
            "SCHEMA_VALIDATION_FAILURE", "run_record.raw_artifact_id must be non-empty"
        )
    if not persisted_at:
        raise EvidencePersistenceError(
            "SCHEMA_VALIDATION_FAILURE", "persisted_at must be non-empty"
        )

    # -- section 8.3: the write sequence. Everything from here that creates a
    # path is tracked so a failure can clean up exactly what this call made. --
    created_run_directory = False
    created_raw = False
    created_receipt = False
    try:
        # 1. create exactly the run directory with exist_ok=False
        try:
            run_directory.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise EvidencePersistenceError(
                "EVIDENCE_ALREADY_EXISTS",
                f"evidence already exists for run_id {run_record.run_id!r}: "
                f"{run_directory}",
            ) from exc
        except OSError as exc:
            raise EvidencePersistenceError(
                "WRITE_FAILURE", f"could not create run directory {run_directory}: {exc}"
            ) from exc
        created_run_directory = True

        # 2-3. write raw.bin using exclusive binary creation; flush and fsync
        try:
            with open(raw_path, "xb") as handle:
                # The exclusive-create open() above has already created this
                # file on disk; cleanup must know that the instant it has,
                # not only once every subsequent write/flush/close succeeds.
                created_raw = True
                handle.write(raw_bytes)
                handle.flush()
                _fsync_best_effort(handle)
        except OSError as exc:
            raise EvidencePersistenceError(
                "WRITE_FAILURE", f"could not write raw evidence bytes: {exc}"
            ) from exc

        # 4. construct RawEvidenceArtifact
        artifact = RawEvidenceArtifact(
            evidence_id=run_record.raw_artifact_id,
            run_id=run_record.run_id,
            task_sha256=run_record.task_sha256,
            prompt_sha256=run_record.prompt_sha256,
            relative_path=f"{run_record.run_id}/raw.bin",
            sha256=run_record.raw_sha256,
            byte_count=run_record.raw_bytes,
            capture_mode=run_record.capture_mode,
            persisted_at=persisted_at,
            status="RAW_FROZEN",
        )

        # 5. validate RawEvidenceArtifact schema
        try:
            validate_raw_evidence_artifact(artifact.to_dict())
        except PELValidationError as exc:
            raise EvidencePersistenceError("SCHEMA_VALIDATION_FAILURE", str(exc)) from exc

        # 6. serialize receipt bytes (section 7)
        receipt_bytes = _serialize_receipt(artifact.to_dict())

        # 7-8. write receipt.json using exclusive binary creation; flush and fsync
        try:
            with open(receipt_path, "xb") as handle:
                # Same reasoning as raw.bin above: exclusive-create open()
                # has already created this file on disk.
                created_receipt = True
                handle.write(receipt_bytes)
                handle.flush()
                _fsync_best_effort(handle)
        except OSError as exc:
            raise EvidencePersistenceError(
                "RECEIPT_WRITE_FAILURE", f"could not write receipt: {exc}"
            ) from exc

        # 9. read-back verification
        read_artifact, read_bytes = read_raw_evidence(
            storage_root=storage_root, run_id=run_record.run_id
        )
        if read_bytes != raw_bytes:
            raise EvidencePersistenceError(
                "READBACK_DIGEST_MISMATCH",
                "read-back raw bytes do not match the bytes just written",
            )

        # 10-11. only then return the PersistenceResult
        return PersistenceResult(
            evidence_id=read_artifact.evidence_id,
            run_id=read_artifact.run_id,
            raw_sha256=read_artifact.sha256,
            raw_bytes=read_artifact.byte_count,
            receipt_sha256=sha256_bytes(receipt_bytes),
            readback_verified=True,
            status="PERSISTED_VERIFIED",
        )
    except Exception as exc:
        # section 8.4: remove only what this call created; never invent a
        # second failure code merely because cleanup itself had trouble.
        cleanup_problems = _cleanup(
            run_directory=run_directory if created_run_directory else None,
            raw_path=raw_path if created_raw else None,
            receipt_path=receipt_path if created_receipt else None,
        )
        if isinstance(exc, EvidencePersistenceError) and cleanup_problems:
            raise EvidencePersistenceError(
                exc.code,
                f"{exc}; additionally, cleanup after failure encountered: "
                f"{'; '.join(cleanup_problems)}",
            ) from exc
        raise
