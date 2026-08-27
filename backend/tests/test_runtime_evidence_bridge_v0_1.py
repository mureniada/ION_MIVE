from __future__ import annotations

import copy
import inspect
from dataclasses import dataclass, field

from app.modules.evidence_provenance.profiles import (
    LOCAL_LEXICAL_BACKEND,
    LOCAL_LEXICAL_PROFILE,
    MEMORY_BACKEND,
    MEMORY_PROFILE,
    QDRANT_BACKEND,
    QDRANT_PROFILE,
)
from app.modules.runtime_evidence_bridge import (
    ADAPTER_SCHEMA_VERSION,
    ADAPTER_VERSION,
    BRIDGE_ID,
    CONTEXT_PACK_VERSION,
    BridgeStatus,
    RuntimeEvidenceBridge,
)
import app.modules.runtime_evidence_bridge.bridge as bridge_module


CREATED_AT = "2026-08-22T21:30:00Z"
PROVENANCE_CREATED_AT = "2026-08-20T10:00:00Z"


@dataclass
class FakeEvidence:
    document_id: str
    source_id: str
    content: str = "content"
    score: float = 0.5
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeDocument:
    document_id: str
    source: str
    content: str = "content"


@dataclass
class FakePack:
    context_pack_id: str
    documents: list[FakeDocument]
    metadata: dict = field(default_factory=dict)


def governed_package(*, fingerprint="abc123", chain_id=None):
    provenance = {
        "origin": "qdrant://collection/item",
        "producer": "governed-ingestion",
        "created_at": PROVENANCE_CREATED_AT,
    }
    if chain_id is not None:
        provenance["chain_id"] = chain_id
    return {
        "fingerprint": fingerprint,
        "fingerprint_algorithm": "SHA256",
        "fingerprint_semantics_established": True,
        "provenance_authoritative": True,
        "provenance": provenance,
    }


def evidence(doc_id="d1", source="s1", *, governed=True, checksum="legacy"):
    metadata = {"checksum": checksum, "ingestion_version": "v1"}
    if governed:
        metadata["ion_canonical_provenance"] = governed_package()
    return FakeEvidence(document_id=doc_id, source_id=source, metadata=metadata)


def pack_for(*items):
    return FakePack(
        context_pack_id="cp_test",
        documents=[FakeDocument(document_id=e.document_id, source=e.source_id) for e in items],
        metadata={"truncated": False},
    )


def bridge_for(backend, profile):
    return RuntimeEvidenceBridge(backend_id=backend, mapping_profile_id=profile)


def run(bridge, items, pack=None, *, question_id="req-1", created_at=CREATED_AT):
    resolutions = bridge.resolve(items)
    final_pack = pack if pack is not None else pack_for(*items)
    return bridge.build_request(
        final_pack,
        resolutions,
        question_id=question_id,
        adapter_created_at=created_at,
    )


def test_p5_14_t01_valid_memory_backed_evidence_produces_valid_bridge_result():
    b = bridge_for(MEMORY_BACKEND, MEMORY_PROFILE)
    result = run(b, [evidence()])
    assert result.status is BridgeStatus.VALID


def test_p5_14_t02_valid_governed_lexical_fixture_produces_valid_bridge_result():
    b = bridge_for(LOCAL_LEXICAL_BACKEND, LOCAL_LEXICAL_PROFILE)
    result = run(b, [evidence()])
    assert result.accepted


def test_p5_14_t03_valid_governed_qdrant_fixture_produces_valid_bridge_result():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert result.accepted


def test_p5_14_t04_resolver_rejected_fails_bridge_closed():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence(governed=False)])
    assert result.status is BridgeStatus.REJECTED
    assert result.request is None


def test_p5_14_t05_missing_canonical_rejoin_match_rejected():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    item = evidence()
    resolutions = b.resolve([item])
    missing_pack = FakePack("cp_test", [FakeDocument("different", item.source_id)])
    result = b.build_request(missing_pack, resolutions, question_id="req-1", adapter_created_at=CREATED_AT)
    assert result.status is BridgeStatus.REJECTED
    assert result.reasons[0].startswith("CANONICAL_REJOIN_MISSING:")


def test_p5_14_t06_duplicate_canonical_rejoin_match_rejected():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    item = evidence()
    one = b.resolve([item])[0]
    result = b.build_request(pack_for(item), (one, one), question_id="req-1", adapter_created_at=CREATED_AT)
    assert result.status is BridgeStatus.REJECTED
    assert result.reasons[0].startswith("CANONICAL_REJOIN_AMBIGUOUS:")


def test_p5_14_t07_raw_retrieval_item_omitted_by_pack_is_omitted_from_envelope():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    first = evidence("d1", "s1")
    second = evidence("d2", "s2")
    final_pack = FakePack("cp_test", [FakeDocument("d1", "s1")], {"truncated": True})
    result = run(b, [first, second], final_pack)
    assert result.accepted
    assert [r.evidence_id for r in result.envelope.evidence_references] == ["d1"]


def test_p5_14_t08_envelope_evidence_set_equals_pack_documents_exactly():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    items = [evidence("d1", "s1"), evidence("d2", "s2")]
    final_pack = pack_for(*items)
    result = run(b, items, final_pack)
    assert tuple(r.evidence_id for r in result.envelope.evidence_references) == tuple(
        d.document_id for d in final_pack.documents
    )


def test_p5_14_t09_evidence_id_preserved():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence("doc-exact", "src")])
    assert result.envelope.evidence_references[0].evidence_id == "doc-exact"


def test_p5_14_t10_source_identity_preserved():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence("doc", "source-exact")])
    assert result.envelope.evidence_references[0].source_identity == "source-exact"


def test_p5_14_t11_fingerprint_preserved():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    item = evidence()
    item.metadata["ion_canonical_provenance"] = governed_package(fingerprint="fingerprint-exact")
    result = run(b, [item])
    assert result.envelope.evidence_references[0].fingerprint == "fingerprint-exact"


def test_p5_14_t12_fingerprint_algorithm_preserved():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert result.envelope.evidence_references[0].fingerprint_algorithm == "SHA256"


def test_p5_14_t13_provenance_origin_preserved():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert result.envelope.evidence_references[0].provenance.origin == "qdrant://collection/item"


def test_p5_14_t14_provenance_producer_preserved():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert result.envelope.evidence_references[0].provenance.producer == "governed-ingestion"


def test_p5_14_t15_provenance_created_at_preserved():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert result.envelope.evidence_references[0].provenance.created_at == PROVENANCE_CREATED_AT


def test_p5_14_t16_question_id_equals_core_ask_request_id_binding_input():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()], question_id="core-request-id")
    assert result.envelope.question_id == "core-request-id"
    assert result.request.question_id == "core-request-id"


def test_p5_14_t17_context_pack_version_equals_governed_0_1_constant():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert CONTEXT_PACK_VERSION == "0.1"
    assert result.envelope.context_pack_version == CONTEXT_PACK_VERSION


def test_p5_14_t18_adapter_schema_version_equals_governed_0_1_constant():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert ADAPTER_SCHEMA_VERSION == "0.1"
    assert result.envelope.metadata.schema_version == ADAPTER_SCHEMA_VERSION


def test_p5_14_t19_adapter_version_equals_governed_0_1_constant():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert ADAPTER_VERSION == "0.1"
    assert result.envelope.metadata.adapter_version == ADAPTER_VERSION


def test_p5_14_t20_adapter_producer_equals_governed_bridge_identifier():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()])
    assert BRIDGE_ID == "ION_RUNTIME_EVIDENCE_BRIDGE_V0_1"
    assert result.envelope.metadata.producer == BRIDGE_ID


def test_p5_14_t21_adapter_created_at_is_request_event_field_only():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    result = run(b, [evidence()], created_at=CREATED_AT)
    ref = result.envelope.evidence_references[0]
    assert result.envelope.metadata.created_at == CREATED_AT
    assert ref.provenance.created_at == PROVENANCE_CREATED_AT
    assert ref.provenance.created_at != result.envelope.metadata.created_at


def test_p5_14_t22_no_evidence_or_context_pack_mutation():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    item = evidence()
    final_pack = pack_for(item)
    item_before = copy.deepcopy(item)
    pack_before = copy.deepcopy(final_pack)
    result = run(b, [item], final_pack)
    assert result.accepted
    assert item == item_before
    assert final_pack == pack_before


def test_p5_14_t23_no_retrieval_qdrant_llm_admission_transition_or_promotion_capability():
    source = inspect.getsource(bridge_module)
    forbidden = (
        "qdrant_client",
        ".retrieve(",
        "requests.",
        "httpx.",
        "openai",
        "gemini",
        "admission.transitions",
        "admission.promotion",
        "promotion.",
    )
    assert all(token not in source for token in forbidden)


def test_p5_14_t24_deterministic_result_for_same_exact_bridge_inputs():
    b = bridge_for(QDRANT_BACKEND, QDRANT_PROFILE)
    item = evidence()
    final_pack = pack_for(item)
    first = run(b, [item], final_pack, question_id="req-d", created_at=CREATED_AT)
    second = run(b, [item], final_pack, question_id="req-d", created_at=CREATED_AT)
    assert first == second
    assert first.request.request_id == second.request.request_id
