"""Deterministic backend-specific canonical provenance resolver."""

from __future__ import annotations

from typing import Any

from .models import (
    CanonicalEvidenceProvenanceRecord,
    CanonicalProvenance,
    CanonicalizationReason,
    CanonicalizationResult,
    CanonicalizationStatus,
    RuntimeEvidenceBinding,
)
from .profiles import (
    BACKEND_TO_PROFILE,
    LOCAL_LEXICAL_BACKEND,
    MEMORY_BACKEND,
    PROFILE_TO_BACKEND,
    QDRANT_BACKEND,
    copy_extensions,
    get_path,
    get_value,
)
from .validation import validate_canonical_record


def _reject(*reasons: str) -> CanonicalizationResult:
    normalized = tuple(dict.fromkeys(str(r) for r in reasons if r))
    return CanonicalizationResult(
        status=CanonicalizationStatus.REJECTED,
        record=None,
        reasons=normalized,
    )


def _profile_data(data: dict[str, Any] | None) -> dict[str, Any]:
    return dict(data or {})


def _resolve_provenance(
    evidence: Any,
    data: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    source_field = str(data.get("provenance_source_field", ""))
    if source_field:
        value = get_path(evidence, source_field)
        if isinstance(value, dict):
            return dict(value), source_field

    explicit = data.get("provenance")
    if isinstance(explicit, dict):
        return dict(explicit), str(data.get("provenance_source_field", "governed_profile_data.provenance"))

    return None, source_field


def _resolve_fingerprint(
    evidence: Any,
    backend_id: str,
    data: dict[str, Any],
) -> tuple[str | None, str | None, str, tuple[str, ...]]:
    source_field = str(data.get("fingerprint_source_field", ""))
    fingerprint = None

    if source_field:
        if backend_id == LOCAL_LEXICAL_BACKEND and source_field == "index.fingerprint":
            return (
                None,
                None,
                source_field,
                (CanonicalizationReason.UNRESOLVED_FINGERPRINT_PROFILE.value,),
            )
        fingerprint = get_path(evidence, source_field)

    if fingerprint is None and "fingerprint" in data:
        fingerprint = data.get("fingerprint")
        if not source_field:
            source_field = "governed_profile_data.fingerprint"

    algorithm = data.get("fingerprint_algorithm")
    if algorithm is None:
        algorithm_source = str(data.get("fingerprint_algorithm_source_field", ""))
        if algorithm_source:
            algorithm = get_path(evidence, algorithm_source)

    semantic_ok = data.get("fingerprint_semantics_established") is True

    if backend_id == QDRANT_BACKEND and source_field == "metadata.checksum" and not semantic_ok:
        return (
            str(fingerprint) if fingerprint is not None else None,
            str(algorithm) if algorithm is not None else None,
            source_field,
            (CanonicalizationReason.UNPROVEN_CHECKSUM_SEMANTICS.value,),
        )

    if fingerprint is None or str(fingerprint).strip() == "":
        return (
            None,
            str(algorithm) if algorithm is not None else None,
            source_field,
            (CanonicalizationReason.MISSING_FINGERPRINT.value,),
        )

    if not semantic_ok:
        return (
            str(fingerprint),
            str(algorithm) if algorithm is not None else None,
            source_field,
            (CanonicalizationReason.UNRESOLVED_FINGERPRINT_PROFILE.value,),
        )

    return (
        str(fingerprint),
        str(algorithm) if algorithm is not None else None,
        source_field,
        (),
    )


def resolve_evidence_provenance(
    backend_id: str,
    evidence: Any,
    mapping_profile_id: str,
    governed_profile_data: dict[str, Any] | None = None,
) -> CanonicalizationResult:
    data = _profile_data(governed_profile_data)

    if backend_id not in BACKEND_TO_PROFILE:
        return _reject(CanonicalizationReason.UNKNOWN_BACKEND.value)

    expected_backend = PROFILE_TO_BACKEND.get(mapping_profile_id)
    if expected_backend is None or expected_backend != backend_id:
        return _reject(CanonicalizationReason.UNKNOWN_MAPPING_PROFILE.value)

    evidence_id_raw = get_value(evidence, "document_id")
    source_identity_raw = get_value(evidence, "source_id")
    metadata = get_value(evidence, "metadata", {})

    evidence_id = "" if evidence_id_raw is None else str(evidence_id_raw)
    source_identity = "" if source_identity_raw is None else str(source_identity_raw)

    pre_reasons: list[str] = []

    if not evidence_id.strip():
        pre_reasons.append(CanonicalizationReason.MISSING_EVIDENCE_ID.value)

    if not source_identity.strip():
        pre_reasons.append(CanonicalizationReason.MISSING_SOURCE_IDENTITY.value)
    elif source_identity == "unknown":
        pre_reasons.append(CanonicalizationReason.UNKNOWN_SOURCE_IDENTITY.value)

    if backend_id == QDRANT_BACKEND:
        if data.get("document_id_is_fallback") is True and data.get("document_id_semantics_established") is not True:
            pre_reasons.append(CanonicalizationReason.AMBIGUOUS_QDRANT_DOCUMENT_ID_FALLBACK.value)

    if data.get("identity_conflict") is True:
        pre_reasons.append(CanonicalizationReason.CONFLICTING_EVIDENCE_IDENTITY.value)

    if data.get("created_at_source") == "wall_clock":
        pre_reasons.append(CanonicalizationReason.SYNTHETIC_PROVENANCE_FORBIDDEN.value)

    if data.get("provenance_derived_by_model") is True:
        pre_reasons.append(CanonicalizationReason.MODEL_DERIVED_PROVENANCE_FORBIDDEN.value)

    fingerprint, fingerprint_algorithm, fingerprint_source_field, fp_reasons = _resolve_fingerprint(
        evidence,
        backend_id,
        data,
    )
    pre_reasons.extend(fp_reasons)

    allowed_algorithms = tuple(str(x) for x in data.get("allowed_fingerprint_algorithms", ()))
    if not fingerprint_algorithm or fingerprint_algorithm not in allowed_algorithms:
        pre_reasons.append(CanonicalizationReason.UNRESOLVED_FINGERPRINT_PROFILE.value)

    provenance_data, provenance_source_field = _resolve_provenance(evidence, data)

    if backend_id == MEMORY_BACKEND and (not isinstance(metadata, dict) or not metadata):
        # A separately governed provenance fixture is allowed only if explicitly declared.
        if data.get("external_governed_provenance") is not True:
            pre_reasons.append(CanonicalizationReason.OPEN_ENDED_MEMORY_METADATA.value)

    if provenance_data is None or data.get("provenance_authoritative") is not True:
        pre_reasons.append(CanonicalizationReason.MISSING_PROVENANCE.value)
        provenance_data = {}

    origin = provenance_data.get("origin")
    producer = provenance_data.get("producer")
    created_at = provenance_data.get("created_at")
    chain_id = provenance_data.get("chain_id")

    if not isinstance(origin, str) or not origin.strip():
        pre_reasons.append(CanonicalizationReason.MISSING_PROVENANCE_ORIGIN.value)

    if not isinstance(producer, str) or not producer.strip():
        pre_reasons.append(CanonicalizationReason.MISSING_PROVENANCE_PRODUCER.value)

    if not isinstance(created_at, str) or not created_at.strip():
        pre_reasons.append(CanonicalizationReason.MISSING_PROVENANCE_CREATED_AT.value)

    if backend_id == LOCAL_LEXICAL_BACKEND:
        if any(
            reason in pre_reasons
            for reason in (
                CanonicalizationReason.MISSING_PROVENANCE.value,
                CanonicalizationReason.MISSING_PROVENANCE_ORIGIN.value,
                CanonicalizationReason.MISSING_PROVENANCE_PRODUCER.value,
                CanonicalizationReason.MISSING_PROVENANCE_CREATED_AT.value,
            )
        ):
            pre_reasons.append(CanonicalizationReason.LEXICAL_PROVENANCE_INCOMPLETE.value)

    if backend_id == QDRANT_BACKEND:
        checksum = get_path(evidence, "metadata.checksum")
        if checksum is not None and fingerprint_source_field == "metadata.checksum":
            if data.get("fingerprint_semantics_established") is not True:
                pre_reasons.append(CanonicalizationReason.UNPROVEN_CHECKSUM_SEMANTICS.value)

    if pre_reasons:
        return _reject(*pre_reasons)

    provenance = CanonicalProvenance(
        origin=str(origin),
        producer=str(producer),
        created_at=str(created_at),
        chain_id=None if chain_id is None else str(chain_id),
    )

    binding = RuntimeEvidenceBinding(
        backend_id=backend_id,
        runtime_evidence_id_field="document_id",
        runtime_source_identity_field="source_id",
        fingerprint_source_field=fingerprint_source_field,
        provenance_source_field=provenance_source_field,
        mapping_profile_id=mapping_profile_id,
    )

    record = CanonicalEvidenceProvenanceRecord(
        evidence_id=evidence_id,
        source_identity=source_identity,
        fingerprint=str(fingerprint),
        fingerprint_algorithm=str(fingerprint_algorithm),
        provenance=provenance,
        runtime_binding=binding,
        extensions=copy_extensions(metadata),
    )

    validation_reasons = validate_canonical_record(
        record,
        allowed_fingerprint_algorithms=allowed_algorithms,
    )
    if validation_reasons:
        return _reject(*validation_reasons)

    return CanonicalizationResult(
        status=CanonicalizationStatus.CANONICAL,
        record=record,
        reasons=(),
    )
