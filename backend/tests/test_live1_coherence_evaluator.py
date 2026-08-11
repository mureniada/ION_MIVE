from __future__ import annotations

import inspect

from app.core.models import (
    ClaimDelta,
    CoherenceCountConstraint,
    CoherenceRule,
    CoherenceRuleTable,
    StageARubricAssessment,
)
from app.modules.live1 import (
    OUTCOME_FAIL,
    OUTCOME_MULTIPLE_MATCH,
    OUTCOME_NO_MATCH,
    OUTCOME_PASS,
    evaluate_coherence,
)
from tests.netguard import guarded


def _assessment(**overrides) -> StageARubricAssessment:
    fields = dict(
        core_conclusion="SAME",
        material_claims=[ClaimDelta(claim_text="c1", status="PRESERVED")],
        epistemic_stance="SAME",
        material_contradiction="NONE",
        overall_semantic_effect="MINOR_CHANGE",
    )
    fields.update(overrides)
    return StageARubricAssessment(**fields)


def _table(rules: list[CoherenceRule]) -> CoherenceRuleTable:
    return CoherenceRuleTable(rule_table_version="synthetic-v0", rules=rules, integrity={"sha256": "0" * 64})


# 1/2/3. valid single match; observed R6 allowed -> PASS
@guarded
def test_single_match_r6_allowed_is_coherence_pass():
    table = _table([
        CoherenceRule(rule_id="synthetic-a", r1="SAME", allowed_r6=["MINOR_CHANGE"]),
    ])
    result = evaluate_coherence(_assessment(overall_semantic_effect="MINOR_CHANGE"), table)
    assert result.outcome == OUTCOME_PASS
    assert result.matched_rule_id == "synthetic-a"
    assert result.matched_rule_ids == []


# 4. observed R6 not allowed -> FAIL
@guarded
def test_single_match_r6_not_allowed_is_coherence_fail():
    table = _table([
        CoherenceRule(rule_id="synthetic-b", r1="SAME", allowed_r6=["FUNDAMENTAL_CHANGE"]),
    ])
    result = evaluate_coherence(_assessment(overall_semantic_effect="MINOR_CHANGE"), table)
    assert result.outcome == OUTCOME_FAIL
    assert result.matched_rule_id == "synthetic-b"


# 5. zero matching rules -> NO_MATCH_ERROR
@guarded
def test_zero_matches_is_no_match_error():
    table = _table([
        CoherenceRule(rule_id="synthetic-c", r1="REVERSED", allowed_r6=["MINOR_CHANGE"]),
    ])
    result = evaluate_coherence(_assessment(core_conclusion="SAME"), table)
    assert result.outcome == OUTCOME_NO_MATCH
    assert result.matched_rule_id is None
    assert result.matched_rule_ids == []


# 6. multiple matching rules -> MULTIPLE_MATCH_ERROR
@guarded
def test_multiple_matches_is_multiple_match_error():
    table = _table([
        CoherenceRule(rule_id="synthetic-d", r1="SAME", allowed_r6=["MINOR_CHANGE"]),
        CoherenceRule(rule_id="synthetic-e", r4="SAME", allowed_r6=["MATERIAL_CHANGE"]),
    ])
    result = evaluate_coherence(_assessment(), table)  # r1=SAME and r4=SAME both, matches both rows
    assert result.outcome == OUTCOME_MULTIPLE_MATCH
    assert result.matched_rule_id is None
    assert sorted(result.matched_rule_ids) == ["synthetic-d", "synthetic-e"]


@guarded
def test_no_match_and_multiple_match_are_distinct_from_coherence_fail():
    table_zero = _table([CoherenceRule(rule_id="x", r1="REVERSED", allowed_r6=["MINOR_CHANGE"])])
    table_multi = _table([
        CoherenceRule(rule_id="y1", r1="SAME", allowed_r6=["MINOR_CHANGE"]),
        CoherenceRule(rule_id="y2", r5="NONE", allowed_r6=["MINOR_CHANGE"]),
    ])
    zero_result = evaluate_coherence(_assessment(), table_zero)
    multi_result = evaluate_coherence(_assessment(), table_multi)
    assert zero_result.outcome != OUTCOME_FAIL
    assert multi_result.outcome != OUTCOME_FAIL
    assert zero_result.outcome == OUTCOME_NO_MATCH
    assert multi_result.outcome == OUTCOME_MULTIPLE_MATCH


# r2_counts matching
@guarded
def test_r2_count_constraint_matches_within_bounds():
    table = _table([
        CoherenceRule(
            rule_id="synthetic-f",
            r2_counts={"contradicted": CoherenceCountConstraint(min=0, max=0)},
            allowed_r6=["MINOR_CHANGE"],
        ),
    ])
    assessment = _assessment(material_claims=[
        ClaimDelta(claim_text="c1", status="PRESERVED"),
        ClaimDelta(claim_text="c2", status="ADDED"),
    ])
    result = evaluate_coherence(assessment, table)
    assert result.outcome == OUTCOME_PASS


@guarded
def test_r2_count_constraint_excludes_out_of_bounds():
    table = _table([
        CoherenceRule(
            rule_id="synthetic-g",
            r2_counts={"contradicted": CoherenceCountConstraint(max=0)},
            allowed_r6=["MINOR_CHANGE"],
        ),
    ])
    assessment = _assessment(material_claims=[ClaimDelta(claim_text="c1", status="CONTRADICTED")])
    result = evaluate_coherence(assessment, table)
    assert result.outcome == OUTCOME_NO_MATCH


# 13. deterministic repeated evaluation
@guarded
def test_repeated_evaluation_is_deterministic():
    table = _table([CoherenceRule(rule_id="synthetic-h", r1="SAME", allowed_r6=["MINOR_CHANGE"])])
    assessment = _assessment()
    first = evaluate_coherence(assessment, table)
    second = evaluate_coherence(assessment, table)
    assert first.to_dict() == second.to_dict()


# 14. unconstrained (omitted) fields match regardless of value
@guarded
def test_unconstrained_dimension_matches_any_value():
    table = _table([CoherenceRule(rule_id="synthetic-i", allowed_r6=["MINOR_CHANGE"])])  # no r1/r4/r5 constraint at all
    result_same = evaluate_coherence(_assessment(core_conclusion="SAME"), table)
    result_reversed = evaluate_coherence(_assessment(core_conclusion="REVERSED"), table)
    assert result_same.outcome == OUTCOME_PASS
    assert result_reversed.outcome == OUTCOME_PASS


# 15. no FIRST_MATCH/order dependence
@guarded
def test_no_first_match_or_row_order_dependence():
    rule_a = CoherenceRule(rule_id="order-a", r1="SAME", allowed_r6=["MINOR_CHANGE"])
    rule_b = CoherenceRule(rule_id="order-b", r4="SAME", allowed_r6=["MATERIAL_CHANGE"])
    table_ab = _table([rule_a, rule_b])
    table_ba = _table([rule_b, rule_a])
    result_ab = evaluate_coherence(_assessment(), table_ab)
    result_ba = evaluate_coherence(_assessment(), table_ba)
    # Both orders detect the same overlap -- neither silently picks "the first" match.
    assert result_ab.outcome == OUTCOME_MULTIPLE_MATCH
    assert result_ba.outcome == OUTCOME_MULTIPLE_MATCH
    assert sorted(result_ab.matched_rule_ids) == sorted(result_ba.matched_rule_ids)


# 17. no original-answer-text dependency -- structural: the function signature
# accepts only an assessment and a rule table, nothing resembling raw answer text.
@guarded
def test_evaluator_signature_has_no_answer_text_parameter():
    sig = inspect.signature(evaluate_coherence)
    param_names = set(sig.parameters.keys())
    assert param_names == {"assessment", "validated_rule_table"}
