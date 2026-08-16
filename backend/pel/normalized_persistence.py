"""Derived normalized-judgment persistence for ION PEL Phase 2B.2.

``persist_normalized_judgment`` is the only Phase-2B.2 write path. It turns
an already-produced ``NormalizedJudgmentV0_2_2`` into an immutable,
provenance-linked, write-once, read-back-verified
``NormalizedJudgmentArtifact``, strictly downstream of Phase 2A raw-evidence
persistence and Phase 2B.1 deterministic normalization. It writes exactly
two files -- ``judgment.json`` and ``receipt.json`` -- beneath
``{storage_root}/normalized/...``, a namespace disjoint from Phase 2A's
``{storage_root}/{run_id}/...`` evidence files, which this module reads
only (via ``read_raw_evidence``) and never modifies. No app dependency, no
t4 dependency, no network. Bounded to ``NormalizedJudgmentV0_2_2`` only --
no generic parser-output framework, no Protocol/ABC abstraction.
"""

from __future__ import annotations

import os
from pathlib import Path

from .integrity import sha256_bytes
from .normalization_models import NormalizedJudgmentV0_2_2
from .normalized_identity import (
    NORMALIZED_SCHEMA_ID,
    compute_normalized_artifact_id,
    compute_normalized_content_sha256,
    compute_normalized_schema_id_digest,
    serialize_deterministic_json,
)
from .normalized_persistence_models import (
    NormalizedJudgmentArtifact,
    NormalizedJudgmentPersistenceResult,
)
from .normalized_readback import read_normalized_judgment
from .normalized_storage import NormalizedPersistenceError, normalized_judgment_paths
from .readback import read_raw_evidence
from .storage import EvidencePersistenceError
from .validation import PELValidationError, validate_normalized_judgment_artifact

__all__ = ["persist_normalized_judgment"]


def _fsync_best_effort(handle) -> None:
    try:
        os.fsync(handle.fileno())
    except OSError:
        pass


def _cleanup(
    *, artifact_directory: Path | None, judgment_path: Path | None, receipt_path: Path | None
) -> list[str]:
    """Remove only what this call created. Never touches a pre-existing path.

    Only the leaf artifact directory is removed on failure -- the shared
    parent directories (run_id/contract/parser/version) may be reused by
    sibling parser-version artifacts and are never removed here, even if
    this call happened to create some of them. An empty leftover parent
    directory is harmless residue, not an orphan artifact, and never blocks
    a same-identity retry.
    """
    problems: list[str] = []
    for label, path in (("receipt.json", receipt_path), ("judgment.json", judgment_path)):
        if path is not None:
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                problems.append(f"could not remove {label} ({path}): {exc}")
    if artifact_directory is not None:
        try:
            if artifact_directory.exists():
                artifact_directory.rmdir()
        except OSError as exc:
            problems.append(
                f"could not remove artifact directory ({artifact_directory}): {exc}"
            )
    return problems


def persist_normalized_judgment(
    *,
    storage_root: Path,
    judgment: NormalizedJudgmentV0_2_2,
    persisted_at: str,
) -> NormalizedJudgmentPersistenceResult:
    # -- pre-write validation and source verification. No filesystem
    # mutation above this point; every failure here leaves the storage
    # root unchanged. --

    if not persisted_at:
        raise NormalizedPersistenceError(
            "NORMALIZED_SCHEMA_VALIDATION_FAILURE", "persisted_at must be non-empty"
        )

    # 1. verify the source raw evidence artifact. run_id is the physical
    # source-addressing key (evidence_id is a provenance field only).
    try:
        raw_artifact, _raw_bytes = read_raw_evidence(
            storage_root=storage_root, run_id=judgment.run_id
        )
    except EvidencePersistenceError as exc:
        if exc.code == "STORAGE_ROOT_VIOLATION":
            raise NormalizedPersistenceError(exc.code, str(exc)) from exc
        raise NormalizedPersistenceError(
            "SOURCE_RAW_NOT_FOUND",
            f"could not read source raw evidence for run_id {judgment.run_id!r}: {exc}",
        ) from exc

    if raw_artifact.sha256 != judgment.source_raw_sha256:
        raise NormalizedPersistenceError(
            "SOURCE_RAW_DIGEST_MISMATCH",
            f"judgment.source_raw_sha256 {judgment.source_raw_sha256!r} does not match "
            f"raw evidence sha256 {raw_artifact.sha256!r} for run_id {judgment.run_id!r}",
        )
    if raw_artifact.evidence_id != judgment.evidence_id:
        raise NormalizedPersistenceError(
            "SOURCE_EVIDENCE_ID_MISMATCH",
            f"judgment.evidence_id {judgment.evidence_id!r} does not match raw evidence "
            f"evidence_id {raw_artifact.evidence_id!r} for run_id {judgment.run_id!r}",
        )

    # 2. compute identity and digests (frozen contract sections 7, 8)
    normalized_schema_id = NORMALIZED_SCHEMA_ID
    normalized_artifact_id = compute_normalized_artifact_id(
        run_id=judgment.run_id,
        output_contract_id=judgment.output_contract_id,
        parser_id=judgment.parser_id,
        parser_version=judgment.parser_version,
        normalized_schema_id=normalized_schema_id,
    )
    judgment_dict = judgment.to_dict()
    judgment_bytes = serialize_deterministic_json(judgment_dict)
    artifact_bytes_sha256 = sha256_bytes(judgment_bytes)
    normalized_content_sha256 = compute_normalized_content_sha256(judgment_dict)
    schema_digest = compute_normalized_schema_id_digest(normalized_schema_id)

    # 3. resolve the (unwritten) storage paths (frozen contract section 10)
    artifact_directory, judgment_path, receipt_path = normalized_judgment_paths(
        storage_root=storage_root,
        run_id=judgment.run_id,
        output_contract_id=judgment.output_contract_id,
        parser_id=judgment.parser_id,
        parser_version=judgment.parser_version,
        normalized_schema_id_digest=schema_digest,
    )
    relative_path = (
        f"normalized/{judgment.run_id}/{judgment.output_contract_id}/"
        f"{judgment.parser_id}/{judgment.parser_version}/{schema_digest}/judgment.json"
    )

    # -- the write sequence. Everything from here that creates a path is
    # tracked so a failure can clean up exactly what this call made. --
    created_directory = False
    created_judgment = False
    created_receipt = False
    try:
        # 1. create the artifact leaf directory with exist_ok=False; shared
        # parent directories (parents=True) are tolerated if they already
        # exist from a prior, different parser-version artifact.
        try:
            artifact_directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise NormalizedPersistenceError(
                "NORMALIZED_ALREADY_EXISTS",
                f"normalized artifact already exists for identity "
                f"{normalized_artifact_id!r}: {artifact_directory}",
            ) from exc
        except OSError as exc:
            raise NormalizedPersistenceError(
                "NORMALIZED_WRITE_FAILURE",
                f"could not create normalized artifact directory {artifact_directory}: {exc}",
            ) from exc
        created_directory = True

        # 2. write judgment.json using exclusive binary creation; flush and fsync
        try:
            with open(judgment_path, "xb") as handle:
                created_judgment = True
                handle.write(judgment_bytes)
                handle.flush()
                _fsync_best_effort(handle)
        except OSError as exc:
            raise NormalizedPersistenceError(
                "NORMALIZED_WRITE_FAILURE", f"could not write judgment bytes: {exc}"
            ) from exc

        # 3. construct NormalizedJudgmentArtifact
        artifact = NormalizedJudgmentArtifact(
            normalized_artifact_id=normalized_artifact_id,
            run_id=judgment.run_id,
            evidence_id=judgment.evidence_id,
            source_raw_sha256=judgment.source_raw_sha256,
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,
            normalized_schema_id=normalized_schema_id,
            relative_path=relative_path,
            normalized_content_sha256=normalized_content_sha256,
            artifact_bytes_sha256=artifact_bytes_sha256,
            persisted_at=persisted_at,
            status="NORMALIZED_FROZEN",
        )

        # 4. validate NormalizedJudgmentArtifact schema
        try:
            validate_normalized_judgment_artifact(artifact.to_dict())
        except PELValidationError as exc:
            raise NormalizedPersistenceError(
                "NORMALIZED_SCHEMA_VALIDATION_FAILURE", str(exc)
            ) from exc

        # 5. serialize receipt bytes (frozen contract section 8/11)
        receipt_bytes = serialize_deterministic_json(artifact.to_dict())

        # 6. write receipt.json using exclusive binary creation; flush and fsync
        try:
            with open(receipt_path, "xb") as handle:
                created_receipt = True
                handle.write(receipt_bytes)
                handle.flush()
                _fsync_best_effort(handle)
        except OSError as exc:
            raise NormalizedPersistenceError(
                "NORMALIZED_RECEIPT_WRITE_FAILURE", f"could not write receipt: {exc}"
            ) from exc

        # 7. read-back verification of both files
        read_artifact, read_judgment_bytes = read_normalized_judgment(
            storage_root=storage_root,
            run_id=judgment.run_id,
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,
            normalized_schema_id_digest=schema_digest,
        )
        if read_judgment_bytes != judgment_bytes:
            raise NormalizedPersistenceError(
                "NORMALIZED_ARTIFACT_DIGEST_MISMATCH",
                "read-back judgment bytes do not match the bytes just written",
            )
        if receipt_path.read_bytes() != receipt_bytes:
            raise NormalizedPersistenceError(
                "NORMALIZED_RECEIPT_DIGEST_MISMATCH",
                "read-back receipt bytes do not match the bytes just written",
            )

        # 8. only then return the NormalizedJudgmentPersistenceResult
        return NormalizedJudgmentPersistenceResult(
            normalized_artifact_id=read_artifact.normalized_artifact_id,
            normalized_content_sha256=read_artifact.normalized_content_sha256,
            artifact_bytes_sha256=read_artifact.artifact_bytes_sha256,
            receipt_sha256=sha256_bytes(receipt_bytes),
            readback_verified=True,
            status="NORMALIZED_PERSISTED_VERIFIED",
        )
    except Exception as exc:
        # cleanup: remove only what this call created; never invent a
        # second failure code merely because cleanup itself had trouble.
        cleanup_problems = _cleanup(
            artifact_directory=artifact_directory if created_directory else None,
            judgment_path=judgment_path if created_judgment else None,
            receipt_path=receipt_path if created_receipt else None,
        )
        if isinstance(exc, NormalizedPersistenceError) and cleanup_problems:
            raise NormalizedPersistenceError(
                exc.code,
                f"{exc}; additionally, cleanup after failure encountered: "
                f"{'; '.join(cleanup_problems)}",
            ) from exc
        raise
