"""Structural verification (E3 v0.1) — pure comparison proofs.

Covers: missing document_id -> FAIL, missing evidence_fingerprint -> FAIL,
duplicate logical document_id -> FAIL, missing expected id -> FAIL,
unexpected id -> FAIL, evidence-fingerprint mismatch -> FAIL, vector-schema
mismatch -> FAIL, all exact structural matches -> PASS, and that
`verify_candidate` performs no Qdrant call, no network, no embedding, no
filesystem and no mutation anywhere on its call path (`guarded`).
"""

from __future__ import annotations

import hashlib

from app.modules.content_engine import ContentBuildResult
from app.modules.derived_index import (
    BACKEND_FAKE,
    DISTANCE_COSINE,
    EmbeddingProfile,
    ExpectedDerivedIndexDescriptor,
    VectorSchema,
)
from app.modules.derived_index_lifecycle import (
    VERIFICATION_STATUS_FAIL,
    VERIFICATION_STATUS_PASS,
    CandidateMaterializationReceipt,
    MeasuredDerivedIndexDescriptor,
    MeasuredPointDescriptor,
    verify_candidate,
)
from app.modules.retrieval.evidence_fingerprint import ALGORITHM as EVIDENCE_FINGERPRINT_ALGORITHM
from app.modules.retrieval.evidence_fingerprint import PROFILE_ID as EVIDENCE_FINGERPRINT_PROFILE_ID
from tests.netguard import guarded

CREATED_AT = "2026-09-03T09:00:00Z"
MATERIALIZED_AT = "2026-09-03T09:05:00Z"
MEASURED_AT = "2026-09-03T09:10:00Z"
VERIFIED_AT = "2026-09-03T09:15:00Z"
PACK_FINGERPRINT = hashlib.sha256(b"pack").hexdigest()
DIMENSION = 8


def _fp(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _record(document_id: str) -> dict:
    return {
        "document_id": document_id,
        "source_id": "alpha",
        "source_version": "1.0.0",
        "title": "alpha",
        "content": f"content for {document_id}",
        "page": None,
        "chunk_id": document_id,
        "checksum": _fp(f"checksum-{document_id}"),
        "ingestion_version": "v1",
        "evidence_fingerprint": _fp(document_id),
        "evidence_fingerprint_algorithm": EVIDENCE_FINGERPRINT_ALGORITHM,
        "evidence_fingerprint_profile_id": EVIDENCE_FINGERPRINT_PROFILE_ID,
        "ion_source_provenance": {"source_id": "alpha", "provenance_created_at": CREATED_AT},
        "ion_canonical_provenance": {"evidence_id": document_id},
    }


def _build_result(document_ids=("doc-1", "doc-2")) -> ContentBuildResult:
    return ContentBuildResult(
        content_engine_contract_version="0.1",
        content_engine_version="0.1",
        pack_id="ion_test_pack",
        pack_version="1.0.0",
        pack_canonical_fingerprint=PACK_FINGERPRINT,
        chunk_chars=1200,
        overlap=200,
        provenance_created_at=CREATED_AT,
        records=tuple(_record(d) for d in document_ids),
    )


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        backend=BACKEND_FAKE,
        model_name=None,
        model_revision=None,
        implementation_revision="ion-e3d-fake-impl-2026-09-03",
        dimension=DIMENSION,
        normalization_profile="L2_NORMALIZED_BY_ADAPTER",
    )


def _schema(**overrides) -> VectorSchema:
    kwargs = dict(dimension=DIMENSION, distance_metric=DISTANCE_COSINE, vector_name=None)
    kwargs.update(overrides)
    return VectorSchema(**kwargs)


def _expected(document_ids=("doc-1", "doc-2")) -> ExpectedDerivedIndexDescriptor:
    return ExpectedDerivedIndexDescriptor.create(
        _build_result(document_ids), _profile(), _schema()
    )


def _candidate_receipt(expected, *, collection="ion_candidate_blue", written=None) -> CandidateMaterializationReceipt:
    written = expected.record_count if written is None else written
    return CandidateMaterializationReceipt.create(
        expected_derived_index_fingerprint=expected.derived_index_fingerprint,
        candidate_physical_collection=collection,
        embedding_profile=expected.embedding_profile,
        vector_schema=expected.vector_schema,
        expected_record_count=expected.record_count,
        written_point_count=written,
        materialized_at=MATERIALIZED_AT,
        materializer_implementation_revision="ion-e3d-materializer-v0-1",
    )


def _measured(
    document_ids=("doc-1", "doc-2"),
    *,
    collection="ion_candidate_blue",
    schema=None,
    corrupt=None,
) -> MeasuredDerivedIndexDescriptor:
    """`corrupt` maps a document_id to an override dict for that point's fields."""
    corrupt = corrupt or {}
    points = []
    for i, document_id in enumerate(document_ids):
        overrides = corrupt.get(document_id, {})
        points.append(
            MeasuredPointDescriptor(
                qdrant_point_id=f"pt-{i}",
                document_id=overrides.get("document_id", document_id),
                evidence_fingerprint=overrides.get("evidence_fingerprint", _fp(document_id)),
            )
        )
    return MeasuredDerivedIndexDescriptor.create(
        candidate_physical_collection=collection,
        vector_schema=schema or _schema(),
        reported_point_count=len(points),
        enumerated_point_count=len(points),
        measured_points=tuple(points),
        measured_at=MEASURED_AT,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
    )


def _verify(expected, candidate, measured):
    return verify_candidate(
        expected_derived_index_descriptor=expected,
        candidate_receipt=candidate,
        measured_descriptor=measured,
        verified_at=VERIFIED_AT,
        verifier_implementation_revision="ion-e3d-verifier-v0-1",
    )


@guarded
def test_all_exact_structural_matches_pass():
    expected = _expected()
    candidate = _candidate_receipt(expected)
    measured = _measured()
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_PASS
    assert receipt.bindings_match is True
    assert receipt.schema_match is True
    assert receipt.missing_document_ids == ()
    assert receipt.unexpected_document_ids == ()
    assert receipt.duplicate_document_ids == ()
    assert receipt.missing_required_payload_details == ()
    assert receipt.evidence_fingerprint_mismatches == ()


@guarded
def test_missing_document_id_on_a_point_fails():
    expected = _expected()
    candidate = _candidate_receipt(expected)
    measured = _measured(corrupt={"doc-1": {"document_id": None}})
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert "pt-0:document_id" in receipt.missing_required_payload_details
    # doc-1 is also now missing from the expected side (no measured point claims it)
    assert "doc-1" in receipt.missing_document_ids


@guarded
def test_missing_evidence_fingerprint_on_a_point_fails():
    expected = _expected()
    candidate = _candidate_receipt(expected)
    measured = _measured(corrupt={"doc-1": {"evidence_fingerprint": None}})
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert "pt-0:evidence_fingerprint" in receipt.missing_required_payload_details


@guarded
def test_duplicate_logical_document_id_fails():
    expected = _expected()
    candidate = _candidate_receipt(expected)
    measured = _measured(document_ids=("doc-1", "doc-1"))
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert receipt.duplicate_document_ids == ("doc-1",)
    # doc-2 was never measured at all
    assert "doc-2" in receipt.missing_document_ids


@guarded
def test_missing_expected_document_id_fails():
    expected = _expected(("doc-1", "doc-2"))
    candidate = _candidate_receipt(expected)
    measured = _measured(document_ids=("doc-1",))
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert receipt.missing_document_ids == ("doc-2",)


@guarded
def test_unexpected_document_id_fails():
    expected = _expected(("doc-1", "doc-2"))
    candidate = _candidate_receipt(expected)
    measured = _measured(document_ids=("doc-1", "doc-2", "doc-3"))
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert receipt.unexpected_document_ids == ("doc-3",)


@guarded
def test_evidence_fingerprint_mismatch_fails():
    expected = _expected()
    candidate = _candidate_receipt(expected)
    measured = _measured(corrupt={"doc-1": {"evidence_fingerprint": _fp("wrong-value")}})
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert receipt.evidence_fingerprint_mismatches == ("doc-1",)


@guarded
def test_vector_schema_mismatch_fails():
    expected = _expected()
    candidate = _candidate_receipt(expected)
    measured = _measured(schema=_schema(dimension=16))
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert receipt.schema_match is False


@guarded
def test_binding_mismatch_on_expected_fingerprint_fails_without_raising():
    expected = _expected()
    other_expected = _expected(("doc-9", "doc-10"))
    candidate = _candidate_receipt(other_expected, collection="ion_candidate_blue")
    measured = _measured(collection="ion_candidate_blue")
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert receipt.bindings_match is False


@guarded
def test_binding_mismatch_on_candidate_collection_fails_without_raising():
    expected = _expected()
    candidate = _candidate_receipt(expected, collection="ion_candidate_blue")
    measured = _measured(collection="ion_candidate_green")
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert receipt.bindings_match is False


@guarded
def test_candidate_written_count_mismatch_against_expected_fails():
    expected = _expected()
    candidate = _candidate_receipt(expected, written=expected.record_count)
    measured = _measured(document_ids=("doc-1",))  # measured fewer than candidate claims
    receipt = _verify(expected, candidate, measured)
    assert receipt.status == VERIFICATION_STATUS_FAIL
    assert receipt.enumerated_point_count != receipt.expected_record_count


@guarded
def test_verification_scope_is_structural_v0_1():
    expected = _expected()
    candidate = _candidate_receipt(expected)
    measured = _measured()
    receipt = _verify(expected, candidate, measured)
    assert receipt.verification_scope == "STRUCTURAL_V0_1"


@guarded
def test_verify_performs_no_network_no_filesystem():
    import socket

    original_connect = socket.socket.connect

    def _blocked(*args, **kwargs):  # pragma: no cover - only triggers on violation
        raise AssertionError("verify_candidate must never touch a socket")

    socket.socket.connect = _blocked
    try:
        expected = _expected()
        candidate = _candidate_receipt(expected)
        measured = _measured()
        receipt = _verify(expected, candidate, measured)
        assert receipt.status == VERIFICATION_STATUS_PASS
    finally:
        socket.socket.connect = original_connect
