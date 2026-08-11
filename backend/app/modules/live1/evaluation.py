"""LIVE-1 evaluation, v0.1: HUMAN_BLIND only (core/ports.py::EvaluationPort).

There is no judge logic to write for HUMAN_BLIND: a human fills in the
RubricAssessment. This module's only job is structural -- take that
already-filled assessment plus identity/labels/timestamp and produce a
schema-valid EvaluationRecord. No scoring, no automation, no provider call.

FUTURE / NOT IMPLEMENTED: LLM_JUDGE, HYBRID, DUAL_JUDGE. EvaluationPort is a
plain Protocol so a future class could implement one of these later; no such
class exists here.
"""

from __future__ import annotations

from ...core.models import BlindedAnswer, EvaluationRecord, RubricAssessment
from ...validation import validate_evaluation_record

EVALUATION_PROFILE_HUMAN_BLIND = "LIVE1-HUMAN-BLIND-v1"

VALID_EVALUATION_STAGES = frozenset({"ANSWER_ONLY", "EVIDENCE_AWARE_ATTRIBUTION"})


class EvaluationValidationError(Exception):
    """A HUMAN_BLIND evaluation input/record failed validation."""


class HumanBlindEvaluator:
    """Structural EvaluationPort implementation for evaluation_profile
    LIVE1-HUMAN-BLIND-v1. Wraps an already-completed human RubricAssessment
    into a schema-validated EvaluationRecord. Implements no judgment itself.
    """

    evaluation_profile = EVALUATION_PROFILE_HUMAN_BLIND

    def build_record(
        self,
        pair: tuple[BlindedAnswer, BlindedAnswer],
        assessment: RubricAssessment,
        *,
        evaluator_identity: str,
        rubric_version: str,
        evaluation_stage: str,
        timestamp: str,
        evaluation_profile: str = EVALUATION_PROFILE_HUMAN_BLIND,
    ) -> EvaluationRecord:
        if evaluation_profile != self.evaluation_profile:
            raise EvaluationValidationError(
                f"HumanBlindEvaluator only supports {self.evaluation_profile!r}, got {evaluation_profile!r}"
            )
        if evaluation_stage not in VALID_EVALUATION_STAGES:
            raise EvaluationValidationError(
                f"evaluation_stage must be one of {sorted(VALID_EVALUATION_STAGES)}, got {evaluation_stage!r}"
            )

        record = EvaluationRecord(
            evaluator_identity=evaluator_identity,
            evaluator_type="HUMAN",
            evaluation_profile=evaluation_profile,
            rubric_version=rubric_version,
            timestamp=timestamp,
            answer_hashes=[a.answer_hash for a in pair],
            blind_labels=[a.label for a in pair],
            evaluation_stage=evaluation_stage,
            assessment=assessment,
        )

        # Final guarantee: the record satisfies the canonical LIVE-1 rubric schema.
        validate_evaluation_record(record.to_dict())
        return record
