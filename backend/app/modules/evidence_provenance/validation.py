"""Fail-closed canonical provenance validation."""

from __future__ import annotations

from .models import CanonicalEvidenceProvenanceRecord, CanonicalizationReason
from .profiles import PROFILE_TO_BACKEND


def validate_canonical_record(
    record: CanonicalEvidenceProvenanceRecord,
    *,
    allowed_fingerprint_algorithms: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []

    if not isinstance(record.evidence_id, str) or not record.evidence_id.strip():
        reasons.append(CanonicalizationReason.MISSING_EVIDENCE_ID.value)

    if not isinstance(record.source_identity, str) or not record.source_identity.strip():
        reasons.append(CanonicalizationReason.MISSING_SOURCE_IDENTITY.value)
    elif record.source_identity == "unknown":
        reasons.append(CanonicalizationReason.UNKNOWN_SOURCE_IDENTITY.value)

    if not isinstance(record.fingerprint, str) or not record.fingerprint.strip():
        reasons.append(CanonicalizationReason.MISSING_FINGERPRINT.value)

    if (
        not isinstance(record.fingerprint_algorithm, str)
        or not record.fingerprint_algorithm.strip()
        or record.fingerprint_algorithm not in allowed_fingerprint_algorithms
    ):
        reasons.append(CanonicalizationReason.UNRESOLVED_FINGERPRINT_PROFILE.value)

    if not isinstance(record.provenance.origin, str) or not record.provenance.origin.strip():
        reasons.append(CanonicalizationReason.MISSING_PROVENANCE_ORIGIN.value)

    if not isinstance(record.provenance.producer, str) or not record.provenance.producer.strip():
        reasons.append(CanonicalizationReason.MISSING_PROVENANCE_PRODUCER.value)

    if not isinstance(record.provenance.created_at, str) or not record.provenance.created_at.strip():
        reasons.append(CanonicalizationReason.MISSING_PROVENANCE_CREATED_AT.value)

    expected_backend = PROFILE_TO_BACKEND.get(record.runtime_binding.mapping_profile_id)
    if expected_backend is None:
        reasons.append(CanonicalizationReason.UNKNOWN_MAPPING_PROFILE.value)
    elif expected_backend != record.runtime_binding.backend_id:
        reasons.append(CanonicalizationReason.UNKNOWN_MAPPING_PROFILE.value)

    return tuple(dict.fromkeys(reasons))
