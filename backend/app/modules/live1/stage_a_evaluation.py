"""LIVE-1 Stage-A (ANSWER_ONLY) HUMAN_BLIND group recording, v0.1.

Additive, LIVE-1-specific representation for the two Stage-A comparison
units the frozen protocol requires -- WITHIN_GROUP (one anonymous group of
exactly three answers) and CROSS_GROUP (two anonymous groups of exactly
three answers each) -- neither of which the generic, pair-only
EvaluationRecord (evaluation.py) can represent. Deliberately excludes R3
(evidence_dependence) and attribution_trace: those are Stage-B-only
concepts with no field anywhere in this module's types, not merely
optional or defaulted.

Does not replace or modify evaluation.py/EvaluationRecord -- both remain
available unchanged for their existing (pair, ANSWER_ONLY or
EVIDENCE_AWARE_ATTRIBUTION) use.
"""

from __future__ import annotations

from ...core.models import StageAGroupEvaluationRecord, StageARubricAssessment
from ...validation import validate_stage_a_record

EVALUATION_PROFILE_HUMAN_BLIND = "LIVE1-HUMAN-BLIND-v1"
STAGE_A_STAGE = "A_ANSWER_ONLY"
WITHIN_GROUP = "WITHIN_GROUP"
CROSS_GROUP = "CROSS_GROUP"
VALID_GROUP_LABELS = frozenset({"X", "Y"})


class StageAValidationError(Exception):
    """A Stage-A HUMAN_BLIND group-evaluation input/record failed validation."""


def _build(
    *, comparison_scope: str, group_answer_hashes: dict[str, list[str]],
    assessment: StageARubricAssessment, experiment_id: str, evaluator_identity: str,
    rubric_version: str, timestamp: str, evaluation_profile: str,
) -> StageAGroupEvaluationRecord:
    if evaluation_profile != EVALUATION_PROFILE_HUMAN_BLIND:
        raise StageAValidationError(
            f"Stage-A HUMAN_BLIND recording only supports {EVALUATION_PROFILE_HUMAN_BLIND!r}, "
            f"got {evaluation_profile!r}"
        )
    record = StageAGroupEvaluationRecord(
        experiment_id=experiment_id,
        evaluator_identity=evaluator_identity,
        evaluator_type="HUMAN",
        evaluation_profile=evaluation_profile,
        rubric_version=rubric_version,
        evaluation_stage=STAGE_A_STAGE,
        comparison_scope=comparison_scope,
        timestamp=timestamp,
        group_answer_hashes=group_answer_hashes,
        assessment=assessment,
    )
    # Final guarantee: the record satisfies the canonical Stage-A schema.
    validate_stage_a_record(record.to_dict())
    return record


def build_within_group_record(
    group_label: str, answer_hashes: list[str], assessment: StageARubricAssessment,
    *, experiment_id: str, evaluator_identity: str, rubric_version: str, timestamp: str,
    evaluation_profile: str = EVALUATION_PROFILE_HUMAN_BLIND,
) -> StageAGroupEvaluationRecord:
    """One anonymous group's own three answers, assessed for mutual
    (within-arm) stability. Requires no provenance/arm/provider/model
    argument -- only already-blinded answer hashes."""
    if group_label not in VALID_GROUP_LABELS:
        raise StageAValidationError(
            f"group_label must be one of {sorted(VALID_GROUP_LABELS)}, got {group_label!r}"
        )
    if len(answer_hashes) != 3:
        raise StageAValidationError(
            f"WITHIN_GROUP requires exactly 3 answer hashes, got {len(answer_hashes)}"
        )
    return _build(
        comparison_scope=WITHIN_GROUP,
        group_answer_hashes={group_label: list(answer_hashes)},
        assessment=assessment, experiment_id=experiment_id,
        evaluator_identity=evaluator_identity, rubric_version=rubric_version,
        timestamp=timestamp, evaluation_profile=evaluation_profile,
    )


def build_cross_group_record(
    group_x_hashes: list[str], group_y_hashes: list[str], assessment: StageARubricAssessment,
    *, experiment_id: str, evaluator_identity: str, rubric_version: str, timestamp: str,
    evaluation_profile: str = EVALUATION_PROFILE_HUMAN_BLIND,
) -> StageAGroupEvaluationRecord:
    """Anonymous Group X's three answers versus anonymous Group Y's three
    answers, assessed as two whole groups."""
    if len(group_x_hashes) != 3 or len(group_y_hashes) != 3:
        raise StageAValidationError(
            f"CROSS_GROUP requires exactly 3+3 answer hashes, got "
            f"{len(group_x_hashes)}+{len(group_y_hashes)}"
        )
    return _build(
        comparison_scope=CROSS_GROUP,
        group_answer_hashes={"X": list(group_x_hashes), "Y": list(group_y_hashes)},
        assessment=assessment, experiment_id=experiment_id,
        evaluator_identity=evaluator_identity, rubric_version=rubric_version,
        timestamp=timestamp, evaluation_profile=evaluation_profile,
    )
