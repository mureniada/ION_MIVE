"""Read-back verification for ION PEL Phase 2B.2 normalized-judgment
persistence.

Reads a previously persisted ``NormalizedJudgmentArtifact`` and its
``judgment.json`` bytes back from a caller-supplied storage root,
verifying: receipt/judgment consistency byte-for-byte; that the persisted
artifact's own five identity components (run_id, output_contract_id,
parser_id, parser_version, normalized_schema_id) reproduce its own stored
``normalized_artifact_id``; that every identity dimension the caller/path
supplied agrees with the persisted artifact; and that
``normalized_content_sha256`` reproduces from the actual read-back
judgment content, independent of the exact-byte check. Performs no writes
and alters no file.
"""

from __future__ import annotations

import json
from pathlib import Path

from .integrity import sha256_bytes
from .normalized_identity import (
    compute_normalized_artifact_id,
    compute_normalized_content_sha256,
    compute_normalized_schema_id_digest,
)
from .normalized_persistence_models import NormalizedJudgmentArtifact
from .normalized_storage import NormalizedPersistenceError, normalized_judgment_paths
from .validation import PELValidationError, validate_normalized_judgment_artifact

__all__ = ["read_normalized_judgment"]


def read_normalized_judgment(
    *,
    storage_root: Path,
    run_id: str,
    output_contract_id: str,
    parser_id: str,
    parser_version: str,
    normalized_schema_id_digest: str,
) -> tuple[NormalizedJudgmentArtifact, bytes]:
    _artifact_directory, judgment_path, receipt_path = normalized_judgment_paths(
        storage_root=storage_root,
        run_id=run_id,
        output_contract_id=output_contract_id,
        parser_id=parser_id,
        parser_version=parser_version,
        normalized_schema_id_digest=normalized_schema_id_digest,
    )

    if not judgment_path.is_file():
        raise NormalizedPersistenceError(
            "NORMALIZED_READBACK_FAILURE", f"missing judgment file: {judgment_path}"
        )
    if not receipt_path.is_file():
        raise NormalizedPersistenceError(
            "NORMALIZED_READBACK_FAILURE", f"missing receipt file: {receipt_path}"
        )

    try:
        receipt_bytes = receipt_path.read_bytes()
    except OSError as exc:
        raise NormalizedPersistenceError(
            "NORMALIZED_READBACK_FAILURE", f"could not read receipt: {exc}"
        ) from exc

    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NormalizedPersistenceError(
            "NORMALIZED_READBACK_FAILURE", f"receipt is not valid UTF-8 JSON: {exc}"
        ) from exc

    try:
        validate_normalized_judgment_artifact(payload)
    except PELValidationError as exc:
        raise NormalizedPersistenceError(
            "NORMALIZED_SCHEMA_VALIDATION_FAILURE", str(exc)
        ) from exc

    try:
        artifact = NormalizedJudgmentArtifact(**payload)
    except (TypeError, ValueError) as exc:
        raise NormalizedPersistenceError(
            "NORMALIZED_SCHEMA_VALIDATION_FAILURE",
            f"receipt does not construct a valid artifact: {exc}",
        ) from exc

    # F-01 remediation: the persisted artifact must be internally
    # self-consistent -- its own five identity components must reproduce
    # its own stored normalized_artifact_id.
    recomputed_artifact_id = compute_normalized_artifact_id(
        run_id=artifact.run_id,
        output_contract_id=artifact.output_contract_id,
        parser_id=artifact.parser_id,
        parser_version=artifact.parser_version,
        normalized_schema_id=artifact.normalized_schema_id,
    )
    if recomputed_artifact_id != artifact.normalized_artifact_id:
        raise NormalizedPersistenceError(
            "NORMALIZED_IDENTITY_MISMATCH",
            f"receipt normalized_artifact_id {artifact.normalized_artifact_id!r} does not "
            f"match recomputation from its own stored identity components "
            f"({recomputed_artifact_id!r})",
        )

    # F-01 remediation: every identity dimension the caller/path supplied
    # must agree with the persisted artifact -- a receipt cannot be
    # accepted as identity A while physically addressed as identity B.
    if artifact.run_id != run_id:
        raise NormalizedPersistenceError(
            "NORMALIZED_IDENTITY_MISMATCH",
            f"receipt run_id {artifact.run_id!r} does not match requested {run_id!r}",
        )
    if artifact.output_contract_id != output_contract_id:
        raise NormalizedPersistenceError(
            "NORMALIZED_IDENTITY_MISMATCH",
            f"receipt output_contract_id {artifact.output_contract_id!r} does not match "
            f"requested {output_contract_id!r}",
        )
    if artifact.parser_id != parser_id:
        raise NormalizedPersistenceError(
            "NORMALIZED_IDENTITY_MISMATCH",
            f"receipt parser_id {artifact.parser_id!r} does not match requested {parser_id!r}",
        )
    if artifact.parser_version != parser_version:
        raise NormalizedPersistenceError(
            "NORMALIZED_IDENTITY_MISMATCH",
            f"receipt parser_version {artifact.parser_version!r} does not match "
            f"requested {parser_version!r}",
        )
    actual_schema_digest = compute_normalized_schema_id_digest(artifact.normalized_schema_id)
    if actual_schema_digest != normalized_schema_id_digest:
        raise NormalizedPersistenceError(
            "NORMALIZED_IDENTITY_MISMATCH",
            f"receipt normalized_schema_id digest {actual_schema_digest!r} does not match "
            f"requested {normalized_schema_id_digest!r}",
        )

    try:
        judgment_bytes = judgment_path.read_bytes()
    except OSError as exc:
        raise NormalizedPersistenceError(
            "NORMALIZED_READBACK_FAILURE", f"could not read judgment bytes: {exc}"
        ) from exc

    if sha256_bytes(judgment_bytes) != artifact.artifact_bytes_sha256:
        raise NormalizedPersistenceError(
            "NORMALIZED_ARTIFACT_DIGEST_MISMATCH",
            "judgment.json bytes do not match the receipt's recorded artifact_bytes_sha256",
        )

    # F-02 remediation: exact-byte integrity does not by itself prove the
    # logical content-identity digest is correct -- recompute it
    # independently from the actual read-back judgment content. Neither
    # check substitutes for the other.
    try:
        judgment_dict = json.loads(judgment_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NormalizedPersistenceError(
            "NORMALIZED_READBACK_FAILURE", f"judgment is not valid UTF-8 JSON: {exc}"
        ) from exc
    recomputed_content_sha256 = compute_normalized_content_sha256(judgment_dict)
    if recomputed_content_sha256 != artifact.normalized_content_sha256:
        raise NormalizedPersistenceError(
            "NORMALIZED_IDENTITY_MISMATCH",
            f"receipt normalized_content_sha256 {artifact.normalized_content_sha256!r} does "
            f"not match recomputation from read-back judgment content "
            f"({recomputed_content_sha256!r})",
        )

    return artifact, judgment_bytes
