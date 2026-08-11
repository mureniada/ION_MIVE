from __future__ import annotations

from app.core.models import ClaimDelta, StageARubricAssessment
from app.modules.live1 import extract_coherence_features
from tests.netguard import guarded


def _assessment(**overrides) -> StageARubricAssessment:
    fields = dict(
        core_conclusion="SHIFTED",
        material_claims=[
            ClaimDelta(claim_text="c1", status="PRESERVED"),
            ClaimDelta(claim_text="c2", status="PRESERVED"),
            ClaimDelta(claim_text="c3", status="ADDED"),
            ClaimDelta(claim_text="c4", status="REMOVED"),
            ClaimDelta(claim_text="c5", status="MODIFIED"),
            ClaimDelta(claim_text="c6", status="CONTRADICTED"),
        ],
        epistemic_stance="WEAKER",
        material_contradiction="PARTIAL",
        overall_semantic_effect="MATERIAL_CHANGE",
    )
    fields.update(overrides)
    return StageARubricAssessment(**fields)


# 1. deterministic, correct counts
@guarded
def test_counts_are_computed_correctly():
    features = extract_coherence_features(_assessment())
    assert features.total_claim_count == 6
    assert features.preserved_count == 2
    assert features.added_count == 1
    assert features.removed_count == 1
    assert features.modified_count == 1
    assert features.contradicted_count == 1
    assert features.non_preserved_count == 4  # total - preserved, self-defining


@guarded
def test_categorical_fields_pass_through_exactly():
    features = extract_coherence_features(_assessment())
    assert features.r1 == "SHIFTED"
    assert features.r4 == "WEAKER"
    assert features.r5 == "PARTIAL"
    assert features.observed_r6 == "MATERIAL_CHANGE"


@guarded
def test_zero_claims_produces_zero_counts():
    features = extract_coherence_features(_assessment(material_claims=[]))
    assert features.total_claim_count == 0
    assert features.preserved_count == 0
    assert features.non_preserved_count == 0


# 12. deterministic repeated feature extraction
@guarded
def test_repeated_extraction_is_deterministic():
    assessment = _assessment()
    first = extract_coherence_features(assessment)
    second = extract_coherence_features(assessment)
    assert first.to_dict() == second.to_dict()


# no changed_count field exists (S7)
@guarded
def test_no_changed_count_field_exists():
    features = extract_coherence_features(_assessment())
    d = features.to_dict()
    assert "changed_count" not in d


# no provenance/arm/group/Stage-B field exists on the output (S8)
@guarded
def test_no_provenance_or_stage_b_field_exists():
    features = extract_coherence_features(_assessment())
    d = features.to_dict()
    forbidden = {"run_id", "arm", "provider", "model", "evidence_dependence", "attribution_trace"}
    assert forbidden.isdisjoint(d.keys())
