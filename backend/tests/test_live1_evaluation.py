from __future__ import annotations

from app.core.models import BlindedAnswer, ClaimDelta, RubricAssessment
from app.modules.live1 import EvaluationValidationError, HumanBlindEvaluator
from app.validation import SchemaValidationError
from tests.netguard import guarded
from tests.util import raises


def _pair():
    return (
        BlindedAnswer(label="X", text="Answer one.", answer_hash="h1"),
        BlindedAnswer(label="Y", text="Answer two.", answer_hash="h2"),
    )


def _assessment(**overrides) -> RubricAssessment:
    fields = dict(
        core_conclusion="SAME",
        material_claims=[ClaimDelta(claim_text="money is debt", status="PRESERVED")],
        evidence_dependence="MATERIAL",
        epistemic_stance="SAME",
        material_contradiction="NONE",
        overall_semantic_effect="MINOR_CHANGE",
        attribution_trace="PLAUSIBLE_LINK",
    )
    fields.update(overrides)
    return RubricAssessment(**fields)


@guarded
def test_human_blind_evaluation_record_validates():
    evaluator = HumanBlindEvaluator()
    record = evaluator.build_record(
        _pair(), _assessment(),
        evaluator_identity="operator-david",
        rubric_version="live1-semantic-rubric-v0.1",
        evaluation_stage="ANSWER_ONLY",
        timestamp="2026-08-11T00:00:00Z",
    )
    assert record.evaluation_profile == "LIVE1-HUMAN-BLIND-v1"
    assert record.blind_labels == ["X", "Y"]


@guarded
def test_invalid_core_conclusion_enum_is_rejected():
    evaluator = HumanBlindEvaluator()
    bad = _assessment(core_conclusion="MAYBE")  # not in the frozen enum
    with raises(SchemaValidationError):
        evaluator.build_record(
            _pair(), bad,
            evaluator_identity="operator-david",
            rubric_version="live1-semantic-rubric-v0.1",
            evaluation_stage="ANSWER_ONLY",
            timestamp="2026-08-11T00:00:00Z",
        )


@guarded
def test_invalid_claim_status_enum_is_rejected():
    evaluator = HumanBlindEvaluator()
    bad = _assessment(material_claims=[ClaimDelta(claim_text="x", status="MAYBE_CHANGED")])
    with raises(SchemaValidationError):
        evaluator.build_record(
            _pair(), bad,
            evaluator_identity="operator-david",
            rubric_version="live1-semantic-rubric-v0.1",
            evaluation_stage="ANSWER_ONLY",
            timestamp="2026-08-11T00:00:00Z",
        )


@guarded
def test_answer_only_stage_omits_evidence_attribution_input():
    """Stage A (ANSWER_ONLY) requires no evidence/context argument at all --
    the evaluator method signature does not even accept one for building the
    record; only evaluation_stage distinguishes the two stages."""
    evaluator = HumanBlindEvaluator()
    record = evaluator.build_record(
        _pair(), _assessment(attribution_trace="NOT_DETERMINABLE"),
        evaluator_identity="operator-david",
        rubric_version="live1-semantic-rubric-v0.1",
        evaluation_stage="ANSWER_ONLY",
        timestamp="2026-08-11T00:00:00Z",
    )
    assert record.evaluation_stage == "ANSWER_ONLY"


@guarded
def test_evidence_aware_stage_can_be_recorded_after_stage_a_is_fixed():
    evaluator = HumanBlindEvaluator()
    record = evaluator.build_record(
        _pair(), _assessment(attribution_trace="DIRECT_EVIDENCE_LINK"),
        evaluator_identity="operator-david",
        rubric_version="live1-semantic-rubric-v0.1",
        evaluation_stage="EVIDENCE_AWARE_ATTRIBUTION",
        timestamp="2026-08-11T00:05:00Z",
    )
    assert record.evaluation_stage == "EVIDENCE_AWARE_ATTRIBUTION"
    assert record.assessment.attribution_trace == "DIRECT_EVIDENCE_LINK"


@guarded
def test_wrong_evaluation_profile_is_rejected():
    evaluator = HumanBlindEvaluator()
    with raises(EvaluationValidationError):
        evaluator.build_record(
            _pair(), _assessment(),
            evaluator_identity="operator-david",
            rubric_version="live1-semantic-rubric-v0.1",
            evaluation_stage="ANSWER_ONLY",
            timestamp="2026-08-11T00:00:00Z",
            evaluation_profile="LLM_JUDGE-v1",  # not implemented, must be rejected
        )


@guarded
def test_invalid_evaluation_stage_is_rejected():
    evaluator = HumanBlindEvaluator()
    with raises(EvaluationValidationError):
        evaluator.build_record(
            _pair(), _assessment(),
            evaluator_identity="operator-david",
            rubric_version="live1-semantic-rubric-v0.1",
            evaluation_stage="NOT_A_REAL_STAGE",
            timestamp="2026-08-11T00:00:00Z",
        )
