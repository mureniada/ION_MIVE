"""LIVE-1 pure coherence evaluator, v0.2 infrastructure only.

evaluate_coherence(assessment, validated_rule_table) -> CoherenceResult.

Matches on R1/R4/R5/R2-count conditions only -- R6 is never itself a
matching input (S3); it is checked only as the matched rule's allowed_r6
membership test, after matching completes. Requires exactly one matching
rule (S4): zero is NO_MATCH_ERROR, more than one is MULTIPLE_MATCH_ERROR
-- both distinct from COHERENCE_FAIL, since a rule-table applicability
defect is not evidence the human rubric itself is incoherent. No
FIRST_MATCH/row-order precedence and no MOST_SPECIFIC tie-breaking exist
anywhere in this module -- every candidate rule is evaluated and all
matches are collected before any decision is made.

No substantive rule content is defined here. No network. No provider SDK
import. Not wired into container.py/Core.ask().
"""

from __future__ import annotations

from ...core.models import (
    CoherenceFeatureVector,
    CoherenceResult,
    CoherenceRule,
    CoherenceRuleTable,
    StageARubricAssessment,
)
from .coherence_features import extract_coherence_features

OUTCOME_PASS = "COHERENCE_PASS"
OUTCOME_FAIL = "COHERENCE_FAIL"
OUTCOME_NO_MATCH = "NO_MATCH_ERROR"
OUTCOME_MULTIPLE_MATCH = "MULTIPLE_MATCH_ERROR"

_R2_KEY_TO_COUNT_ATTR = {
    "preserved": "preserved_count",
    "added": "added_count",
    "removed": "removed_count",
    "modified": "modified_count",
    "contradicted": "contradicted_count",
}


def _rule_matches(rule: CoherenceRule, features: CoherenceFeatureVector) -> bool:
    if rule.r1 is not None and rule.r1 != features.r1:
        return False
    if rule.r4 is not None and rule.r4 != features.r4:
        return False
    if rule.r5 is not None and rule.r5 != features.r5:
        return False
    for key, constraint in rule.r2_counts.items():
        observed = getattr(features, _R2_KEY_TO_COUNT_ATTR[key])
        if constraint.min is not None and observed < constraint.min:
            return False
        if constraint.max is not None and observed > constraint.max:
            return False
    return True


def evaluate_coherence(
    assessment: StageARubricAssessment, validated_rule_table: CoherenceRuleTable,
) -> CoherenceResult:
    features = extract_coherence_features(assessment)
    matched = [rule for rule in validated_rule_table.rules if _rule_matches(rule, features)]

    if len(matched) == 0:
        return CoherenceResult(outcome=OUTCOME_NO_MATCH, feature_vector=features)
    if len(matched) > 1:
        return CoherenceResult(
            outcome=OUTCOME_MULTIPLE_MATCH,
            matched_rule_ids=[rule.rule_id for rule in matched],
            feature_vector=features,
        )

    rule = matched[0]
    outcome = OUTCOME_PASS if features.observed_r6 in rule.allowed_r6 else OUTCOME_FAIL
    return CoherenceResult(outcome=outcome, matched_rule_id=rule.rule_id, feature_vector=features)
