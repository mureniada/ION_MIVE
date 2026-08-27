"""Pure in-memory canonical provenance materializer for P5.18-K v0.1."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .evidence_fingerprint import (
    ALGORITHM,
    PROFILE_ID,
    compute_fingerprint_from_record,
)
from .source_provenance import (
    KNOWN,
    PROVENANCE_PRODUCER,
    SOURCE_FILE_SHA256_ALGORITHM,
    SOURCE_FILE_SHA256_BASIS,
    SOURCE_TYPE,
    COLLECTION_METHOD,
    validate_source_provenance,
)

MATERIALIZER_ID = "ION_CANONICAL_PROVENANCE_MATERIALIZER_V0_1"
MATERIALIZER_VERSION = "0.1"


class CanonicalProvenanceMaterializationError(ValueError):
    """Raised when a candidate record is not eligible for canonical materialization."""


_REQUIRED_RECORD_FIELDS = (
    "document_id",
    "source_id",
    "title",
    "content",
    "page",
    "chunk_id",
    "checksum",
    "evidence_fingerprint",
    "evidence_fingerprint_algorithm",
    "evidence_fingerprint_profile_id",
    "ion_source_provenance",
)


def _require_record_field(record: Mapping[str, Any], field: str) -> Any:
    if field not in record:
        raise CanonicalProvenanceMaterializationError(
            f"missing required materialization field: {field}"
        )
    return record[field]


def materialize_canonical_provenance(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an eligible canonical package without mutating or persisting input."""

    if not isinstance(record, Mapping):
        raise CanonicalProvenanceMaterializationError("record must be a mapping")

    for field in _REQUIRED_RECORD_FIELDS:
        _require_record_field(record, field)

    document_id = record["document_id"]
    source_id = record["source_id"]

    if not isinstance(document_id, str) or not document_id:
        raise CanonicalProvenanceMaterializationError(
            "document_id must be a non-empty string"
        )
    if not isinstance(source_id, str) or not source_id or source_id == "unknown":
        raise CanonicalProvenanceMaterializationError(
            "source_id must be governed and non-empty"
        )

    if record["evidence_fingerprint_algorithm"] != ALGORITHM:
        raise CanonicalProvenanceMaterializationError(
            "evidence fingerprint algorithm mismatch"
        )
    if record["evidence_fingerprint_profile_id"] != PROFILE_ID:
        raise CanonicalProvenanceMaterializationError(
            "evidence fingerprint profile mismatch"
        )

    try:
        actual_fingerprint = compute_fingerprint_from_record(record)
    except (KeyError, TypeError, ValueError) as exc:
        raise CanonicalProvenanceMaterializationError(
            "unable to independently recompute evidence fingerprint"
        ) from exc

    expected_fingerprint = record["evidence_fingerprint"]
    if not isinstance(expected_fingerprint, str) or expected_fingerprint != actual_fingerprint:
        raise CanonicalProvenanceMaterializationError(
            "stored evidence fingerprint does not match independent recomputation"
        )

    candidate_provenance = record["ion_source_provenance"]
    try:
        provenance = validate_source_provenance(candidate_provenance)
    except (TypeError, ValueError) as exc:
        raise CanonicalProvenanceMaterializationError(
            "source provenance does not conform to the frozen contract"
        ) from exc

    if provenance["source_id"] != source_id:
        raise CanonicalProvenanceMaterializationError(
            "source provenance source_id does not match evidence source_id"
        )
    if provenance["source_type"] != SOURCE_TYPE:
        raise CanonicalProvenanceMaterializationError("source_type mismatch")
    if provenance["collection_method"] != COLLECTION_METHOD:
        raise CanonicalProvenanceMaterializationError("collection_method mismatch")
    if provenance["provenance_producer"] != PROVENANCE_PRODUCER:
        raise CanonicalProvenanceMaterializationError(
            "provenance producer mismatch"
        )
    if provenance["provenance_created_at_status"] != KNOWN:
        raise CanonicalProvenanceMaterializationError(
            "provenance_created_at must be KNOWN"
        )
    if provenance["source_file_sha256_algorithm"] != SOURCE_FILE_SHA256_ALGORITHM:
        raise CanonicalProvenanceMaterializationError(
            "source-file SHA256 algorithm mismatch"
        )
    if provenance["source_file_sha256_basis"] != SOURCE_FILE_SHA256_BASIS:
        raise CanonicalProvenanceMaterializationError(
            "source-file SHA256 basis mismatch"
        )
    if provenance["source_file_sha256"] != record["checksum"]:
        raise CanonicalProvenanceMaterializationError(
            "source provenance SHA256 does not match record checksum"
        )

    return {
        "evidence_id": document_id,
        "source_identity": source_id,
        "fingerprint": expected_fingerprint,
        "fingerprint_algorithm": ALGORITHM,
        "provenance": {
            "origin": provenance["source_origin"],
            "producer": provenance["provenance_producer"],
            "created_at": provenance["provenance_created_at"],
        },
        "fingerprint_semantics_established": True,
        "provenance_authoritative": True,
    }
