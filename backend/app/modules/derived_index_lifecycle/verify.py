"""Structural verification (E3 v0.1) — a PURE comparison, nothing else.

No Qdrant client, no network, no embedding, no filesystem, no mutation, no
clock. `verify_candidate` takes three already-constructed objects — an
`ExpectedDerivedIndexDescriptor`, the `CandidateMaterializationReceipt` that
built the candidate, and the `MeasuredDerivedIndexDescriptor` that observed
it — and one caller-supplied `verified_at`, and returns a `VerificationReceipt`.

Verification scope is exactly `STRUCTURAL_V0_1`: record-set completeness,
per-record evidence-fingerprint equality, vector-schema equality, and
candidate/expected identity binding. It is NOT a claim of universal vector-
byte reproduction, remote provider execution, or that the declared model or
implementation revision was actually loaded/executed.

Bindings are checked first (Section 25 of the E3D authorization): a binding
mismatch does not raise — it is folded into `bindings_match = False`, which
alone is enough to force `status = FAIL`. Only a malformed object contract
(wrong type, etc.) raises, and that already happens inside the models
themselves.
"""

from __future__ import annotations

from ..derived_index import ExpectedDerivedIndexDescriptor
from .models import (
    VERIFICATION_SCOPE_STRUCTURAL_V0_1,
    CandidateMaterializationReceipt,
    MeasuredDerivedIndexDescriptor,
    VerificationReceipt,
)

__all__ = ["verify_candidate"]


def verify_candidate(
    *,
    expected_derived_index_descriptor: ExpectedDerivedIndexDescriptor,
    candidate_receipt: CandidateMaterializationReceipt,
    measured_descriptor: MeasuredDerivedIndexDescriptor,
    verified_at: str,
    verifier_implementation_revision: str,
) -> VerificationReceipt:
    bindings_match = (
        candidate_receipt.expected_derived_index_fingerprint
        == expected_derived_index_descriptor.derived_index_fingerprint
        and candidate_receipt.candidate_physical_collection
        == measured_descriptor.candidate_physical_collection
        and candidate_receipt.embedding_profile == expected_derived_index_descriptor.embedding_profile
        and candidate_receipt.vector_schema == expected_derived_index_descriptor.vector_schema
    )

    schema_match = measured_descriptor.vector_schema == expected_derived_index_descriptor.vector_schema

    expected_by_id = {
        record.document_id: record.evidence_fingerprint
        for record in expected_derived_index_descriptor.record_set
    }
    expected_ids = set(expected_by_id)

    seen_document_ids: dict[str, int] = {}
    measured_fingerprint_by_first_seen_id: dict[str, str | None] = {}
    missing_payload_details: list[str] = []
    for point in measured_descriptor.measured_points:
        if point.document_id is None:
            missing_payload_details.append(f"{point.qdrant_point_id}:document_id")
        else:
            seen_document_ids[point.document_id] = seen_document_ids.get(point.document_id, 0) + 1
            if point.document_id not in measured_fingerprint_by_first_seen_id:
                measured_fingerprint_by_first_seen_id[point.document_id] = point.evidence_fingerprint
        if point.evidence_fingerprint is None:
            missing_payload_details.append(f"{point.qdrant_point_id}:evidence_fingerprint")

    measured_ids = set(seen_document_ids)
    duplicate_document_ids = tuple(
        sorted(document_id for document_id, count in seen_document_ids.items() if count > 1)
    )
    missing_document_ids = tuple(sorted(expected_ids - measured_ids))
    unexpected_document_ids = tuple(sorted(measured_ids - expected_ids))
    missing_required_payload_details = tuple(sorted(set(missing_payload_details)))

    evidence_fingerprint_mismatches: list[str] = []
    comparable_ids = (expected_ids & measured_ids) - set(duplicate_document_ids)
    for document_id in sorted(comparable_ids):
        measured_fp = measured_fingerprint_by_first_seen_id.get(document_id)
        if measured_fp is not None and measured_fp != expected_by_id[document_id]:
            evidence_fingerprint_mismatches.append(document_id)

    return VerificationReceipt.create(
        verification_scope=VERIFICATION_SCOPE_STRUCTURAL_V0_1,
        expected_derived_index_fingerprint=expected_derived_index_descriptor.derived_index_fingerprint,
        candidate_receipt_fingerprint=candidate_receipt.candidate_receipt_fingerprint,
        measured_state_fingerprint=measured_descriptor.measured_state_fingerprint,
        expected_record_count=expected_derived_index_descriptor.record_count,
        candidate_expected_record_count=candidate_receipt.expected_record_count,
        candidate_written_point_count=candidate_receipt.written_point_count,
        qdrant_reported_point_count=measured_descriptor.reported_point_count,
        enumerated_point_count=measured_descriptor.enumerated_point_count,
        missing_document_ids=missing_document_ids,
        unexpected_document_ids=unexpected_document_ids,
        duplicate_document_ids=duplicate_document_ids,
        missing_required_payload_details=missing_required_payload_details,
        evidence_fingerprint_mismatches=tuple(sorted(set(evidence_fingerprint_mismatches))),
        bindings_match=bindings_match,
        schema_match=schema_match,
        embedding_execution_binding=candidate_receipt.embedding_execution_binding,
        verified_at=verified_at,
        verifier_implementation_revision=verifier_implementation_revision,
    )
