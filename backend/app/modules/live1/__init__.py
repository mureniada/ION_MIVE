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
from .snapshot_bridge import SnapshotValidationError, context_pack_from_snapshot

__all__ = [
    "EVALUATION_PROFILE_HUMAN_BLIND",
    "PROVIDER_GEMINI",
    "PROVIDER_OPENAI",
    "PROVIDER_SPECIFIC_ALLOWLIST",
    "EvaluationValidationError",
    "HumanBlindEvaluator",
    "ProvenanceEntry",
    "SnapshotValidationError",
    "UnsupportedGenerationParameterError",
    "assign_blind_labels",
    "context_pack_from_snapshot",
    "resolve_provenance",
    "validate_generation_parameters",
]
