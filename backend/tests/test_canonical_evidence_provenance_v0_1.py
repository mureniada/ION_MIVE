from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.evidence_provenance import (
    CanonicalizationReason,
    CanonicalizationStatus,
    resolve_evidence_provenance,
)
from app.modules.evidence_provenance.profiles import (
    LOCAL_LEXICAL_PROFILE,
    MEMORY_PROFILE,
    QDRANT_PROFILE,
)

ALG = "ION_TEST_EVIDENCE_SHA256_V0_1"
QALG = "ION_QDRANT_CHECKSUM_SHA256_V0_1"


@dataclass
class EvidenceFixture:
    document_id: str | None = "doc-1"
    source_id: str | None = "source-1"
    title: str = "Title"
    content: str = "Evidence content"
    score: float = 0.5
    page: int | str | None = None
    chunk_id: str | None = "chunk-1"
    metadata: dict = field(default_factory=dict)


def provenance():
    return {
        "origin": "fixture://source",
        "producer": "fixture-producer",
        "created_at": "2026-08-22T00:00:00Z",
        "chain_id": "chain-1",
    }


def memory_evidence():
    return EvidenceFixture(
        metadata={
            "fingerprint": "fp-memory-001",
            "fingerprint_algorithm": ALG,
            "provenance": provenance(),
        }
    )


def memory_profile():
    return {
        "fingerprint_source_field": "metadata.fingerprint",
        "fingerprint_algorithm_source_field": "metadata.fingerprint_algorithm",
        "fingerprint_semantics_established": True,
        "allowed_fingerprint_algorithms": [ALG],
        "provenance_source_field": "metadata.provenance",
        "provenance_authoritative": True,
    }


def lexical_evidence(prov=None):
    return EvidenceFixture(
        document_id="fragment-1",
        source_id="material-1",
        chunk_id="fragment-1",
        metadata={"provenance": provenance() if prov is None else prov},
    )


def lexical_profile():
    return {
        "fingerprint": "fp-lexical-fragment-001",
        "fingerprint_algorithm": ALG,
        "fingerprint_source_field": "fixture.fragment_digest",
        "fingerprint_semantics_established": True,
        "allowed_fingerprint_algorithms": [ALG],
        "provenance_source_field": "metadata.provenance",
        "provenance_authoritative": True,
    }


def qdrant_evidence(source_id="source-q", include_checksum=True):
    metadata = {"ingestion_version": "v1"}
    if include_checksum:
        metadata["checksum"] = "checksum-q-001"
    return EvidenceFixture(
        document_id="qdoc-1",
        source_id=source_id,
        metadata=metadata,
    )


def qdrant_profile(include_provenance=True, semantics=True):
    data = {
        "fingerprint_source_field": "metadata.checksum",
        "fingerprint_algorithm": QALG,
        "fingerprint_semantics_established": semantics,
        "allowed_fingerprint_algorithms": [QALG],
        "provenance_source_field": "governed_profile_data.provenance",
        "provenance_authoritative": include_provenance,
    }
    if include_provenance:
        data["provenance"] = provenance()
    return data


def reason(result, value):
    return value in result.reasons


def test_d4_t01_valid_canonical_record_accepted():
    r = resolve_evidence_provenance("memory", memory_evidence(), MEMORY_PROFILE, memory_profile())
    assert r.status is CanonicalizationStatus.CANONICAL
    assert r.record.evidence_id == "doc-1"
    assert r.record.source_identity == "source-1"


def test_d4_t02_missing_evidence_id_rejected():
    e = memory_evidence()
    e.document_id = None
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.MISSING_EVIDENCE_ID.value)


def test_d4_t03_empty_evidence_id_rejected():
    e = memory_evidence()
    e.document_id = ""
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.MISSING_EVIDENCE_ID.value)


def test_d4_t04_missing_source_identity_rejected():
    e = memory_evidence()
    e.source_id = None
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.MISSING_SOURCE_IDENTITY.value)


def test_d4_t05_unknown_source_identity_rejected():
    e = memory_evidence()
    e.source_id = "unknown"
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.UNKNOWN_SOURCE_IDENTITY.value)


def test_d4_t06_missing_fingerprint_rejected():
    e = memory_evidence()
    del e.metadata["fingerprint"]
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.MISSING_FINGERPRINT.value)


def test_d4_t07_missing_fingerprint_algorithm_rejected():
    e = memory_evidence()
    del e.metadata["fingerprint_algorithm"]
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.UNRESOLVED_FINGERPRINT_PROFILE.value)


def test_d4_t08_unrecognized_fingerprint_profile_rejected():
    e = memory_evidence()
    e.metadata["fingerprint_algorithm"] = "UNRECOGNIZED"
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.UNRESOLVED_FINGERPRINT_PROFILE.value)


def test_d4_t09_missing_provenance_origin_rejected():
    e = memory_evidence()
    del e.metadata["provenance"]["origin"]
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.MISSING_PROVENANCE_ORIGIN.value)


def test_d4_t10_missing_provenance_producer_rejected():
    e = memory_evidence()
    del e.metadata["provenance"]["producer"]
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.MISSING_PROVENANCE_PRODUCER.value)


def test_d4_t11_missing_provenance_created_at_rejected():
    e = memory_evidence()
    del e.metadata["provenance"]["created_at"]
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.MISSING_PROVENANCE_CREATED_AT.value)


def test_d4_t12_synthetic_wall_clock_provenance_rejected():
    p = memory_profile()
    p["created_at_source"] = "wall_clock"
    r = resolve_evidence_provenance("memory", memory_evidence(), MEMORY_PROFILE, p)
    assert reason(r, CanonicalizationReason.SYNTHETIC_PROVENANCE_FORBIDDEN.value)


def test_d4_t13_llm_derived_provenance_forbidden():
    p = memory_profile()
    p["provenance_derived_by_model"] = True
    r = resolve_evidence_provenance("memory", memory_evidence(), MEMORY_PROFILE, p)
    assert reason(r, CanonicalizationReason.MODEL_DERIVED_PROVENANCE_FORBIDDEN.value)


def test_d4_t14_retrieval_score_excluded_from_identity():
    e1 = memory_evidence()
    e2 = memory_evidence()
    e1.score = 0.1
    e2.score = 0.99
    r1 = resolve_evidence_provenance("memory", e1, MEMORY_PROFILE, memory_profile())
    r2 = resolve_evidence_provenance("memory", e2, MEMORY_PROFILE, memory_profile())
    assert r1.record.to_dict() == r2.record.to_dict()


def test_d4_t15_runtime_request_uuid_excluded_from_identity():
    p1 = memory_profile()
    p2 = memory_profile()
    p1["runtime_request_id"] = "request-a"
    p2["runtime_request_id"] = "request-b"
    r1 = resolve_evidence_provenance("memory", memory_evidence(), MEMORY_PROFILE, p1)
    r2 = resolve_evidence_provenance("memory", memory_evidence(), MEMORY_PROFILE, p2)
    assert r1.record.to_dict() == r2.record.to_dict()


def test_d4_t16_deterministic_replay():
    e = memory_evidence()
    p = memory_profile()
    r1 = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, p)
    r2 = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, p)
    assert r1 == r2


def test_d4_t17_unknown_backend_rejected():
    r = resolve_evidence_provenance("other", memory_evidence(), MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.UNKNOWN_BACKEND.value)


def test_d4_t18_unknown_mapping_profile_rejected():
    r = resolve_evidence_provenance("memory", memory_evidence(), "UNKNOWN_PROFILE", memory_profile())
    assert reason(r, CanonicalizationReason.UNKNOWN_MAPPING_PROFILE.value)


def test_d4_t19_lexical_identity_mapping():
    r = resolve_evidence_provenance("local_lexical", lexical_evidence(), LOCAL_LEXICAL_PROFILE, lexical_profile())
    assert r.status is CanonicalizationStatus.CANONICAL
    assert r.record.evidence_id == "fragment-1"
    assert r.record.source_identity == "material-1"


def test_d4_t20_lexical_incomplete_provenance_rejected():
    bad = provenance()
    del bad["producer"]
    r = resolve_evidence_provenance("local_lexical", lexical_evidence(bad), LOCAL_LEXICAL_PROFILE, lexical_profile())
    assert reason(r, CanonicalizationReason.LEXICAL_PROVENANCE_INCOMPLETE.value)
    assert reason(r, CanonicalizationReason.MISSING_PROVENANCE_PRODUCER.value)


def test_d4_t21_lexical_index_fingerprint_not_silently_promoted():
    p = lexical_profile()
    p.pop("fingerprint")
    p["fingerprint_source_field"] = "index.fingerprint"
    r = resolve_evidence_provenance("local_lexical", lexical_evidence(), LOCAL_LEXICAL_PROFILE, p)
    assert reason(r, CanonicalizationReason.UNRESOLVED_FINGERPRINT_PROFILE.value)


def test_d4_t22_lexical_complete_governed_provenance_accepted():
    r = resolve_evidence_provenance("local_lexical", lexical_evidence(), LOCAL_LEXICAL_PROFILE, lexical_profile())
    assert r.status is CanonicalizationStatus.CANONICAL
    assert r.record.provenance.origin == "fixture://source"


def test_d4_t23_memory_metadata_preservation():
    e = memory_evidence()
    e.metadata["custom_trace"] = "trace-1"
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert r.status is CanonicalizationStatus.CANONICAL
    assert r.record.extensions["custom_trace"] == "trace-1"
    assert r.record.extensions["provenance"] == provenance()


def test_d4_t24_memory_missing_canonical_metadata_rejected():
    e = EvidenceFixture(metadata={})
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.OPEN_ENDED_MEMORY_METADATA.value)


def test_d4_t25_memory_unknown_source_fallback_rejected():
    e = memory_evidence()
    e.source_id = "unknown"
    r = resolve_evidence_provenance("memory", e, MEMORY_PROFILE, memory_profile())
    assert reason(r, CanonicalizationReason.UNKNOWN_SOURCE_IDENTITY.value)


def test_d4_t26_memory_governed_complete_metadata_accepted():
    r = resolve_evidence_provenance("memory", memory_evidence(), MEMORY_PROFILE, memory_profile())
    assert r.status is CanonicalizationStatus.CANONICAL
    assert r.record.runtime_binding.mapping_profile_id == MEMORY_PROFILE


def test_d4_t27_qdrant_checksum_alone_insufficient():
    r = resolve_evidence_provenance("qdrant", qdrant_evidence(), QDRANT_PROFILE, qdrant_profile(semantics=False))
    assert reason(r, CanonicalizationReason.UNPROVEN_CHECKSUM_SEMANTICS.value)


def test_d4_t28_qdrant_missing_mandatory_provenance_rejected():
    r = resolve_evidence_provenance("qdrant", qdrant_evidence(), QDRANT_PROFILE, qdrant_profile(include_provenance=False))
    assert reason(r, CanonicalizationReason.MISSING_PROVENANCE.value)
    assert reason(r, CanonicalizationReason.MISSING_PROVENANCE_ORIGIN.value)


def test_d4_t29_qdrant_unknown_source_fallback_rejected():
    r = resolve_evidence_provenance("qdrant", qdrant_evidence(source_id="unknown"), QDRANT_PROFILE, qdrant_profile())
    assert reason(r, CanonicalizationReason.UNKNOWN_SOURCE_IDENTITY.value)


def test_d4_t30_qdrant_governed_complete_mapping_accepted():
    r = resolve_evidence_provenance("qdrant", qdrant_evidence(), QDRANT_PROFILE, qdrant_profile())
    assert r.status is CanonicalizationStatus.CANONICAL
    assert r.record.fingerprint == "checksum-q-001"
    assert r.record.fingerprint_algorithm == QALG
    assert r.record.runtime_binding.mapping_profile_id == QDRANT_PROFILE
