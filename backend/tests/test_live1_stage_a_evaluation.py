from __future__ import annotations

from app.core.models import BlindedAnswer, ClaimDelta, StageARubricAssessment
from app.modules.live1 import (
    HumanBlindEvaluator,
    StageAValidationError,
    build_cross_group_record,
    build_within_group_record,
)
from app.validation import SchemaValidationError, validate_stage_a_record
from tests.netguard import guarded
from tests.util import raises


def _hashes(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i}" + "0" * 56 for i in range(n)]


def _assessment(**overrides) -> StageARubricAssessment:
    fields = dict(
        core_conclusion="SAME",
        material_claims=[ClaimDelta(claim_text="money is credit and debt", status="PRESERVED")],
        epistemic_stance="SAME",
        material_contradiction="NONE",
        overall_semantic_effect="MINOR_CHANGE",
    )
    fields.update(overrides)
    return StageARubricAssessment(**fields)


# 1. Stage A validates without R3 -- no such field exists at all
@guarded
def test_stage_a_validates_without_evidence_dependence():
    record = build_within_group_record(
        "X", _hashes("x", 3), _assessment(),
        experiment_id="live1-exp-0001", evaluator_identity="operator-david",
        rubric_version="LIVE-1 Semantic Rubric v0.1", timestamp="2026-08-11T00:00:00Z",
    )
    assert "evidence_dependence" not in record.assessment.to_dict()


# 2. Stage A validates without attribution_trace -- same
@guarded
def test_stage_a_validates_without_attribution_trace():
    record = build_within_group_record(
        "Y", _hashes("y", 3), _assessment(),
        experiment_id="live1-exp-0001", evaluator_identity="operator-david",
        rubric_version="LIVE-1 Semantic Rubric v0.1", timestamp="2026-08-11T00:00:00Z",
    )
    assert "attribution_trace" not in record.assessment.to_dict()


# 3. premature Stage-B fields are not silently accepted
@guarded
def test_stage_a_rejects_premature_stage_b_field_construction():
    with raises(TypeError):
        StageARubricAssessment(  # type: ignore[call-arg]
            core_conclusion="SAME",
            material_claims=[],
            epistemic_stance="SAME",
            material_contradiction="NONE",
            overall_semantic_effect="MINOR_CHANGE",
            evidence_dependence="MATERIAL",
        )


# 4. WITHIN_GROUP requires exactly 3 answer hashes
@guarded
def test_within_group_requires_exactly_three_hashes():
    build_within_group_record(
        "X", _hashes("x", 3), _assessment(),
        experiment_id="e", evaluator_identity="operator", rubric_version="v0.1", timestamp="t",
    )  # must not raise
    with raises(StageAValidationError):
        build_within_group_record(
            "X", _hashes("x", 2), _assessment(),
            experiment_id="e", evaluator_identity="operator", rubric_version="v0.1", timestamp="t",
        )
    with raises(StageAValidationError):
        build_within_group_record(
            "X", _hashes("x", 4), _assessment(),
            experiment_id="e", evaluator_identity="operator", rubric_version="v0.1", timestamp="t",
        )


# 5. CROSS_GROUP requires exactly 3+3
@guarded
def test_cross_group_requires_exactly_three_plus_three():
    build_cross_group_record(
        _hashes("x", 3), _hashes("y", 3), _assessment(),
        experiment_id="e", evaluator_identity="operator", rubric_version="v0.1", timestamp="t",
    )  # must not raise
    with raises(StageAValidationError):
        build_cross_group_record(
            _hashes("x", 3), _hashes("y", 2), _assessment(),
            experiment_id="e", evaluator_identity="operator", rubric_version="v0.1", timestamp="t",
        )


# 6. no run_id/arm/provider/model/slot-name key anywhere in the record
@guarded
def test_stage_a_record_contains_no_provenance_or_identity_keys():
    record = build_cross_group_record(
        _hashes("x", 3), _hashes("y", 3), _assessment(),
        experiment_id="e", evaluator_identity="operator", rubric_version="v0.1", timestamp="t",
    )
    d = record.to_dict()
    forbidden = {"run_id", "arm", "provider", "model", "slot", "context_snapshot_ref"}
    assert forbidden.isdisjoint(d.keys())
    assert forbidden.isdisjoint(d["assessment"].keys())


# 7. valid claim-level material_claims validates
@guarded
def test_claim_level_material_claims_validates():
    record = build_within_group_record(
        "X", _hashes("x", 3),
        _assessment(material_claims=[
            ClaimDelta(claim_text="claim one", status="PRESERVED"),
            ClaimDelta(claim_text="claim two", status="MODIFIED"),
        ]),
        experiment_id="e", evaluator_identity="operator", rubric_version="v0.1", timestamp="t",
    )
    assert len(record.assessment.to_dict()["material_claims"]) == 2


# 8. a scalar material_claims is rejected by the schema
@guarded
def test_scalar_material_claims_is_rejected():
    bad = {
        "experiment_id": "e", "evaluator_identity": "operator", "evaluator_type": "HUMAN",
        "evaluation_profile": "LIVE1-HUMAN-BLIND-v1", "rubric_version": "v0.1",
        "evaluation_stage": "A_ANSWER_ONLY", "comparison_scope": "WITHIN_GROUP", "timestamp": "t",
        "group_answer_hashes": {"X": _hashes("x", 3)},
        "assessment": {
            "core_conclusion": "SAME",
            "material_claims": "PRESERVED",  # scalar, not an array -- invalid
            "epistemic_stance": "SAME",
            "material_contradiction": "NONE",
            "overall_semantic_effect": "MINOR_CHANGE",
        },
    }
    with raises(SchemaValidationError):
        validate_stage_a_record(bad)


# 9. existing generic EvaluationRecord path is not regressed
@guarded
def test_existing_generic_evaluation_record_path_unaffected():
    from app.core.models import RubricAssessment

    evaluator = HumanBlindEvaluator()
    pair = (
        BlindedAnswer(label="X", text="Answer one.", answer_hash="h1"),
        BlindedAnswer(label="Y", text="Answer two.", answer_hash="h2"),
    )
    assessment = RubricAssessment(
        core_conclusion="SAME",
        material_claims=[ClaimDelta(claim_text="money is debt", status="PRESERVED")],
        evidence_dependence="MATERIAL",
        epistemic_stance="SAME",
        material_contradiction="NONE",
        overall_semantic_effect="MINOR_CHANGE",
        attribution_trace="PLAUSIBLE_LINK",
    )
    record = evaluator.build_record(
        pair, assessment,
        evaluator_identity="operator-david", rubric_version="live1-semantic-rubric-v0.1",
        evaluation_stage="ANSWER_ONLY", timestamp="2026-08-11T00:00:00Z",
    )
    assert record.evaluation_profile == "LIVE1-HUMAN-BLIND-v1"
    assert record.assessment.evidence_dependence == "MATERIAL"


# 10. (structural, applies to every test above) -- @guarded on every test
# proves no network/provider access is required or possible.
