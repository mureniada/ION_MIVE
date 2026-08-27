from __future__ import annotations

import json
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from types import SimpleNamespace

import pytest

from app.core.models import Evidence
from app.modules.admission import (
    AuthorityRight,
    CheckOutcome,
    EvidenceStatus,
    ValidationOutcome,
)
import app.modules.admission.claim_adjudication as ca
from app.modules.context_pack_adapter.models import (
    EvidenceAdmissionRequest,
    EvidenceReference,
    ProvenanceRecord,
)
from app.modules.retrieval.evidence_fingerprint import (
    PROFILE_ID,
    recompute_evidence_fingerprint,
)


def _bundle():
    evidence = Evidence(
        document_id="EV-001",
        source_id="SRC-001",
        title="Title",
        content="Evidence content",
        score=0.9,
        page=1,
        chunk_id="CH-001",
        metadata={},
    )
    fp = recompute_evidence_fingerprint(evidence)
    evidence.metadata.update(
        {
            "evidence_fingerprint": fp,
            "evidence_fingerprint_algorithm": "SHA256",
            "evidence_fingerprint_profile_id": PROFILE_ID,
            "ion_canonical_provenance": {
                "evidence_id": "EV-001",
                "source_identity": "SRC-001",
                "fingerprint": fp,
                "fingerprint_algorithm": "SHA256",
                "fingerprint_semantics_established": True,
                "provenance_authoritative": True,
                "provenance": {
                    "origin": "corpus-file://source.txt",
                    "producer": "ION_CORPUS_INGESTION_PROVENANCE_EMITTER_V0_1",
                    "created_at": "2026-08-22T00:00:00Z",
                },
            },
            "ion_source_provenance": {
                "source_id": "SRC-001",
                "source_type": "FILE",
                "collection_method": "OPERATOR_SUPPLIED_CORPUS_FILE",
                "collector": "",
                "collected_at": "",
                "collected_at_status": "UNKNOWN",
                "source_origin": "corpus-file://source.txt",
                "provenance_producer": "ION_CORPUS_INGESTION_PROVENANCE_EMITTER_V0_1",
                "provenance_created_at": "2026-08-22T00:00:00Z",
            },
        }
    )
    ref = EvidenceReference(
        evidence_id="EV-001",
        source_identity="SRC-001",
        fingerprint=fp,
        fingerprint_algorithm="SHA256",
        provenance=ProvenanceRecord(
            origin="corpus-file://source.txt",
            producer="ION_CORPUS_INGESTION_PROVENANCE_EMITTER_V0_1",
            created_at="2026-08-22T00:00:00Z",
        ),
    )
    request = EvidenceAdmissionRequest(
        request_id="REQ-001",
        context_pack_id="CP-001",
        question_id="Q-001",
        evidence_records=(ref,),
        requested_operation="VALIDATE_FOR_ADMISSION",
        authority_scope="REQUEST_CONSTRUCTION_ONLY",
    )
    pack = SimpleNamespace(
        context_pack_id="CP-001",
        question="Question",
        documents=[SimpleNamespace(document_id="EV-001")],
        metadata={},
    )
    return [evidence], pack, request, ref


def _run(evidence=None, pack=None, request=None):
    base_evidence, base_pack, base_request, _ = _bundle()
    return ca.run_runtime_admission_gate(
        evidence=base_evidence if evidence is None else evidence,
        pack=base_pack if pack is None else pack,
        question_id=(base_request if request is None else request).question_id,
        request=base_request if request is None else request,
    )


def test_p5_18ab_t01_deterministic_structural_claim_identical_for_identical_inputs():
    _, _, request, ref = _bundle()
    a = ca.canonical_structural_claim(request, ref)
    b = ca.canonical_structural_claim(request, ref)
    assert a == b
    assert list(json.loads(a)) == sorted(json.loads(a))


def test_p5_18ab_t02_structural_claim_changes_for_any_bound_identity_change():
    _, _, request, ref = _bundle()
    base = ca.canonical_structural_claim(request, ref)
    request_variants = [
        replace(request, request_id="REQ-002"),
        replace(request, context_pack_id="CP-002"),
        replace(request, question_id="Q-002"),
        replace(request, requested_operation="OTHER"),
        replace(request, authority_scope="OTHER"),
    ]
    ref_variants = [
        replace(ref, evidence_id="EV-002"),
        replace(ref, source_identity="SRC-002"),
        replace(ref, fingerprint="f" * 64),
        replace(ref, fingerprint_algorithm="OTHER"),
    ]
    assert all(ca.canonical_structural_claim(v, ref) != base for v in request_variants)
    assert all(ca.canonical_structural_claim(request, v) != base for v in ref_variants)


def test_p5_18ab_t03_duplicate_evidence_id_rejected():
    evidence, pack, request, ref = _bundle()
    request = replace(request, evidence_records=(ref, ref))
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t04_missing_evidence_id_rejected():
    evidence, pack, request, ref = _bundle()
    request = replace(request, evidence_records=(replace(ref, evidence_id=""),))
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t05_source_identity_mismatch_rejected():
    evidence, pack, request, ref = _bundle()
    request = replace(request, evidence_records=(replace(ref, source_identity="SRC-X"),))
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t06_stored_fingerprint_mismatch_rejected():
    evidence, pack, request, ref = _bundle()
    request = replace(request, evidence_records=(replace(ref, fingerprint="0" * 64),))
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t07_recomputed_fingerprint_mismatch_rejected():
    evidence, pack, request, _ = _bundle()
    evidence = [replace(evidence[0], content="changed after fingerprint")]
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t08_fingerprint_algorithm_mismatch_rejected():
    evidence, pack, request, ref = _bundle()
    request = replace(
        request, evidence_records=(replace(ref, fingerprint_algorithm="SHA512"),)
    )
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t09_fingerprint_profile_mismatch_rejected():
    evidence, pack, request, _ = _bundle()
    evidence[0].metadata["evidence_fingerprint_profile_id"] = "WRONG"
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t10_missing_canonical_provenance_rejected():
    evidence, pack, request, _ = _bundle()
    evidence[0].metadata.pop("ion_canonical_provenance")
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t11_missing_source_provenance_rejected():
    evidence, pack, request, _ = _bundle()
    evidence[0].metadata.pop("ion_source_provenance")
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t12_canonical_evidence_id_mismatch_rejected():
    evidence, pack, request, _ = _bundle()
    evidence[0].metadata["ion_canonical_provenance"]["evidence_id"] = "EV-X"
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t13_canonical_source_identity_mismatch_rejected():
    evidence, pack, request, _ = _bundle()
    evidence[0].metadata["ion_canonical_provenance"]["source_identity"] = "SRC-X"
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t14_source_type_unknown_rejected():
    evidence, pack, request, _ = _bundle()
    evidence[0].metadata["ion_source_provenance"]["source_type"] = "UNKNOWN"
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t15_collection_method_unknown_rejected():
    evidence, pack, request, _ = _bundle()
    evidence[0].metadata["ion_source_provenance"]["collection_method"] = "UNKNOWN"
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )


def test_p5_18ab_t16_historical_collector_unknown_remains_none():
    result = _run()
    assert result.records[0].provenance.collector is None


def test_p5_18ab_t17_historical_collected_at_unknown_remains_none():
    result = _run()
    assert result.records[0].provenance.timestamp is None


def test_p5_18ab_t18_provenance_producer_is_not_relabelled_as_collector():
    evidence, pack, request, _ = _bundle()
    producer = evidence[0].metadata["ion_source_provenance"]["provenance_producer"]
    result = ca.run_runtime_admission_gate(
        evidence=evidence, pack=pack, question_id=request.question_id, request=request
    )
    assert result.records[0].provenance.collector is None
    assert result.records[0].provenance.collector != producer


def test_p5_18ab_t19_provenance_created_at_is_not_relabelled_as_collection_timestamp():
    evidence, pack, request, _ = _bundle()
    created = evidence[0].metadata["ion_source_provenance"]["provenance_created_at"]
    result = ca.run_runtime_admission_gate(
        evidence=evidence, pack=pack, question_id=request.question_id, request=request
    )
    assert result.records[0].provenance.timestamp is None
    assert result.records[0].provenance.timestamp != created


def test_p5_18ab_t20_dedicated_runtime_profile_exact_flags():
    p = ca.RUNTIME_VALIDATOR_PROFILE
    assert p.profile_id == "ION_RUNTIME_STRUCTURAL_ADMISSION_VALIDATOR_PROFILE_V0_1"
    assert p.identity_required is True
    assert p.provenance_required is False
    assert p.claim_binding_required is True
    assert p.scope_required is False
    assert p.temporal_effectivity_required is False
    assert p.receipt_required is False
    assert p.contradiction_check_required is False
    assert p.authorization_boundary_required is True


def _flatten_enum_values(value):
    if isinstance(value, Enum):
        yield value.value
        return
    if is_dataclass(value):
        for field in fields(value):
            yield from _flatten_enum_values(getattr(value, field.name))
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten_enum_values(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten_enum_values(item)


def test_p5_18ab_t21_nonrequired_semantic_gates_preserve_unknown_without_synthetic_pass():
    result = _run()
    validation = result.validations[0]
    assert validation.result == ValidationOutcome.PASS

    checks = {check.check_id: check for check in validation.checks}
    assert set(checks) == {"V01", "V02", "V03", "V04", "V05", "V06", "V07", "V08"}

    expected_nonrequired = {
        "V02": CheckOutcome.NOT_APPLICABLE,
        "V04": CheckOutcome.UNKNOWN,
        "V05": CheckOutcome.UNKNOWN,
        "V06": CheckOutcome.NOT_APPLICABLE,
        "V07": CheckOutcome.UNKNOWN,
    }
    for check_id, expected_result in expected_nonrequired.items():
        check = checks[check_id]
        assert check.required is False
        assert check.result == expected_result
        assert check.result != CheckOutcome.PASS

    for check_id in ("V01", "V03", "V08"):
        check = checks[check_id]
        assert check.required is True
        assert check.result == CheckOutcome.PASS


def test_p5_18ab_t22_validator_fail_blocks_transition(monkeypatch):
    evidence, pack, request, _ = _bundle()
    calls = []

    def fake_validate(self, *args, **kwargs):
        return SimpleNamespace(result=ValidationOutcome.FAIL)

    def fake_transition(self, *args, **kwargs):
        calls.append(1)
        raise AssertionError("transition must not execute")

    monkeypatch.setattr(ca.EvidenceValidator, "validate", fake_validate)
    monkeypatch.setattr(ca.StateTransitionEngine, "transition", fake_transition)
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )
    assert calls == []


def test_p5_18ab_t23_validator_unknown_blocks_transition(monkeypatch):
    evidence, pack, request, _ = _bundle()
    calls = []

    def fake_validate(self, *args, **kwargs):
        return SimpleNamespace(result=ValidationOutcome.UNKNOWN)

    def fake_transition(self, *args, **kwargs):
        calls.append(1)
        raise AssertionError("transition must not execute")

    monkeypatch.setattr(ca.EvidenceValidator, "validate", fake_validate)
    monkeypatch.setattr(ca.StateTransitionEngine, "transition", fake_transition)
    with pytest.raises(ValueError):
        ca.run_runtime_admission_gate(
            evidence=evidence, pack=pack, question_id=request.question_id, request=request
        )
    assert calls == []


def test_p5_18ab_t24_pass_transitions_pending_to_verified_with_validation_right():
    result = _run()
    tr = result.transitions[0]
    assert tr.from_status == EvidenceStatus.PENDING
    assert tr.to_status == EvidenceStatus.VERIFIED
    assert tr.authority == AuthorityRight.VALIDATION_RIGHT
    assert result.records[0].status == EvidenceStatus.VERIFIED


def test_p5_18ab_t25_transition_actor_is_exact_runtime_validator_actor():
    result = _run()
    assert result.transitions[0].actor == "ION_RUNTIME_ADMISSION_VALIDATOR_V0_1"


def test_p5_18ab_t26_no_promoted_transition_occurs():
    result = _run()
    assert all(tr.to_status != EvidenceStatus.PROMOTED for tr in result.transitions)