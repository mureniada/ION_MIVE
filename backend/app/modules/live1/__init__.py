"""LIVE-1 minimum architecture (v0.1) -- not wired into container.py/Core.ask().

Provides: canonical replay snapshot -> ContextPack bridge, blinding support,
and the HUMAN_BLIND evaluation profile. See core/models.py (LiveRunConfig,
GenerationControlSurface, RubricAssessment, EvaluationRecord, BlindedAnswer)
and core/ports.py (EvaluationPort) for the shared domain types.

FUTURE / NOT IMPLEMENTED: LLM_JUDGE, HYBRID, DUAL_JUDGE, Semantic Parallax,
any provider call. This module makes no network connection and imports no
provider SDK.
"""

from .blinding import ProvenanceEntry, assign_blind_labels, resolve_provenance
from .evaluation import EVALUATION_PROFILE_HUMAN_BLIND, EvaluationValidationError, HumanBlindEvaluator
from .generation_control import (
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    PROVIDER_SPECIFIC_ALLOWLIST,
    UnsupportedGenerationParameterError,
    validate_generation_parameters,
)
from .openai_execution import (
    LiveOpenAIPolicyError,
    LiveOpenAIResult,
    build_openai_request_kwargs,
    run_live_openai,
)
from .snapshot_bridge import SnapshotValidationError, context_pack_from_snapshot
from .stage_a_evaluation import (
    CROSS_GROUP,
    STAGE_A_STAGE,
    WITHIN_GROUP,
    StageAValidationError,
    build_cross_group_record,
    build_within_group_record,
)

__all__ = [
    "CROSS_GROUP",
    "EVALUATION_PROFILE_HUMAN_BLIND",
    "PROVIDER_GEMINI",
    "PROVIDER_OPENAI",
    "PROVIDER_SPECIFIC_ALLOWLIST",
    "STAGE_A_STAGE",
    "WITHIN_GROUP",
    "EvaluationValidationError",
    "HumanBlindEvaluator",
    "LiveOpenAIPolicyError",
    "LiveOpenAIResult",
    "ProvenanceEntry",
    "SnapshotValidationError",
    "StageAValidationError",
    "UnsupportedGenerationParameterError",
    "assign_blind_labels",
    "build_cross_group_record",
    "build_openai_request_kwargs",
    "build_within_group_record",
    "context_pack_from_snapshot",
    "resolve_provenance",
    "run_live_openai",
    "validate_generation_parameters",
]
