"""Provider- and transport-independent domain models.

Plain stdlib dataclasses. Validation against the canonical JSON Schemas in
`schemas/` is performed with `jsonschema` in `app/validation/` — the shipped
schemas are the single source of truth for contract shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Evidence:
    """One retrieved fragment. Retrieval returns these; it does not interpret."""

    document_id: str
    source_id: str
    title: str
    content: str
    score: float
    page: str | int | None = None
    chunk_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Context Pack (both providers receive an identical instance)
# --------------------------------------------------------------------------- #
@dataclass
class ContextDocument:
    document_id: str
    title: str
    content: str
    source: str
    page: str | int | None = None
    chunk_id: str | None = None


@dataclass
class ContextPack:
    context_pack_id: str
    question: str
    documents: list[ContextDocument]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_pack_id": self.context_pack_id,
            "question": self.question,
            "documents": [_prune(asdict(d)) for d in self.documents],
            "metadata": self.metadata,
        }


# --------------------------------------------------------------------------- #
# IVE report (canonical, provider-independent)
# --------------------------------------------------------------------------- #
@dataclass
class Claim:
    claim_id: str
    statement: str
    evidence_document_ids: list[str]
    confidence: float


@dataclass
class Concept:
    name: str
    description: str


@dataclass
class Relation:
    source: str
    relation: str
    target: str
    evidence_document_ids: list[str]


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    usage_is_estimated: bool = False


@dataclass
class IVEReport:
    engine_id: str
    provider: str
    model: str
    question: str
    abstract: str
    highlights: list[str]
    claims: list[Claim]
    concepts: list[Concept]
    relations: list[Relation]
    evidence_mapping: dict[str, list[str]]
    uncertainty: list[str]
    confidence: float
    raw_response: str | None = None
    # not part of the schema contract; kept for telemetry, stripped before validation
    usage: Usage = field(default_factory=Usage)

    def to_contract_dict(self) -> dict[str, Any]:
        """Schema-shaped dict (excludes `usage`, includes optional raw_response)."""
        return {
            "engine_id": self.engine_id,
            "provider": self.provider,
            "model": self.model,
            "question": self.question,
            "abstract": self.abstract,
            "highlights": list(self.highlights),
            "claims": [asdict(c) for c in self.claims],
            "concepts": [asdict(c) for c in self.concepts],
            "relations": [asdict(r) for r in self.relations],
            "evidence_mapping": {k: list(v) for k, v in self.evidence_mapping.items()},
            "uncertainty": list(self.uncertainty),
            "confidence": self.confidence,
            "raw_response": self.raw_response,
        }


# --------------------------------------------------------------------------- #
# MIVE result
# --------------------------------------------------------------------------- #
@dataclass
class MIVEResult:
    question: str
    engine_ids: list[str]
    agreements: list[dict[str, Any]]
    partial_agreements: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    unique_findings: list[dict[str, Any]]
    unsupported_findings: list[dict[str, Any]]
    shared_uncertainty: list[str]
    overall_status: str
    comparison_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Telemetry + final result
# --------------------------------------------------------------------------- #
@dataclass
class ProviderMetrics:
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    estimated_cost: float | None = None
    usage_is_estimated: bool = False


@dataclass
class Metrics:
    request_id: str
    timestamp: str
    question: str
    retrieved_chunks: int
    context_characters: int
    context_documents: int
    retrieval_latency_ms: float
    comparison_latency_ms: float
    total_latency_ms: float
    providers: list[ProviderMetrics]
    total_estimated_cost: float | None
    status: str
    error_stage: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AskResult:
    request_id: str
    question: str
    status: str
    rendered: dict[str, Any]
    mive_result: dict[str, Any] | None
    ive_reports: list[dict[str, Any]]
    metrics: dict[str, Any]
    error_stage: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _prune(d: dict[str, Any]) -> dict[str, Any]:
    """Drop optional keys that are None so schema `additionalProperties` stays clean."""
    return {k: v for k, v in d.items() if v is not None}


# --------------------------------------------------------------------------- #
# LIVE-1 experiment configuration (v0.1 — architecture only, not wired into
# Core.ask()/container.py; see backend/app/modules/live1/). Kept deliberately
# separate from the T4 run-record contract rather than merged into it.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GenerationControlSurface:
    """The generation parameters LIVE-1 can freeze, plus an explicit escape
    hatch for provider-only parameters (e.g. Gemini's `seed`/`top_k`, which
    OpenAI's Responses API does not expose at all — see modules/live1).

    No values are chosen here; this is a shape, not a policy.
    """

    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    provider_specific: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_output_tokens": self.max_output_tokens,
            "provider_specific": dict(self.provider_specific),
        }


@dataclass(frozen=True)
class LiveRunConfig:
    """One frozen, immutable LIVE-1 experiment run configuration.

    `reported_model` is never defaulted to `requested_model` — it stays
    `None` (honest UNKNOWN) until a provider response actually supplies one.
    """

    experiment_id: str
    run_id: str
    arm: str
    provider: str
    requested_model: str
    context_snapshot_ref: str
    context_snapshot_sha256: str
    prompt_version: str
    generation: GenerationControlSurface
    tools_policy: str
    evaluation_profile: str
    rubric_version: str
    reported_model: str | None = None
    prompt_sha256: str | None = None
    max_output_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "arm": self.arm,
            "provider": self.provider,
            "requested_model": self.requested_model,
            "reported_model": self.reported_model,
            "context_snapshot_ref": self.context_snapshot_ref,
            "context_snapshot_sha256": self.context_snapshot_sha256,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "generation": self.generation.to_dict(),
            "tools_policy": self.tools_policy,
            "max_output_tokens": self.max_output_tokens,
            "evaluation_profile": self.evaluation_profile,
            "rubric_version": self.rubric_version,
        }


# --------------------------------------------------------------------------- #
# LIVE-1 Semantic Rubric v0.1 / evaluation (HUMAN_BLIND only — see
# backend/app/modules/live1/evaluation.py. LLM_JUDGE / HYBRID / DUAL_JUDGE are
# FUTURE / NOT IMPLEMENTED: EvaluationPort is deliberately just a Protocol so
# they *could* be added later, but no such class exists in this codebase.)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ClaimDelta:
    claim_text: str
    status: str  # PRESERVED | ADDED | REMOVED | MODIFIED | CONTRADICTED


@dataclass(frozen=True)
class RubricAssessment:
    """LIVE-1 Semantic Rubric v0.1 (R1-R6 + ATTRIBUTION_TRACE)."""

    core_conclusion: str            # SAME | SHIFTED | REVERSED | UNRESOLVED
    material_claims: list[ClaimDelta]
    evidence_dependence: str        # NONE | WEAK | MATERIAL | DIRECT
    epistemic_stance: str           # STRONGER | SAME | WEAKER | SHIFT_TO_UNCERTAINTY | SHIFT_FROM_UNCERTAINTY
    material_contradiction: str     # NONE | PARTIAL | DIRECT
    overall_semantic_effect: str    # SEMANTICALLY_EQUIVALENT | MINOR_CHANGE | MATERIAL_CHANGE | FUNDAMENTAL_CHANGE
    attribution_trace: str          # NO_VISIBLE_LINK | PLAUSIBLE_LINK | DIRECT_EVIDENCE_LINK | NOT_DETERMINABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "core_conclusion": self.core_conclusion,
            "material_claims": [asdict(c) for c in self.material_claims],
            "evidence_dependence": self.evidence_dependence,
            "epistemic_stance": self.epistemic_stance,
            "material_contradiction": self.material_contradiction,
            "overall_semantic_effect": self.overall_semantic_effect,
            "attribution_trace": self.attribution_trace,
        }


@dataclass(frozen=True)
class BlindedAnswer:
    """An answer stripped of provider/model/arm identity for blind evaluation.
    Carries only what a blinded human evaluator may see."""

    label: str  # "X" | "Y" — neutral, independently assignable
    text: str
    answer_hash: str


@dataclass(frozen=True)
class EvaluationRecord:
    """Output of one EvaluationPort.evaluate() call (docs: LIVE-1 rubric)."""

    evaluator_identity: str
    evaluator_type: str          # e.g. "HUMAN" — LLM_JUDGE/HYBRID/DUAL_JUDGE: FUTURE / NOT IMPLEMENTED
    evaluation_profile: str      # "LIVE1-HUMAN-BLIND-v1" for v0.1
    rubric_version: str
    timestamp: str
    answer_hashes: list[str]
    blind_labels: list[str]      # e.g. ["X", "Y"] — never the real arm/provider
    evaluation_stage: str        # ANSWER_ONLY | EVIDENCE_AWARE_ATTRIBUTION
    assessment: RubricAssessment

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluator_identity": self.evaluator_identity,
            "evaluator_type": self.evaluator_type,
            "evaluation_profile": self.evaluation_profile,
            "rubric_version": self.rubric_version,
            "timestamp": self.timestamp,
            "answer_hashes": list(self.answer_hashes),
            "blind_labels": list(self.blind_labels),
            "evaluation_stage": self.evaluation_stage,
            "assessment": self.assessment.to_dict(),
        }


# --------------------------------------------------------------------------- #
# LIVE-1 Stage-A (ANSWER_ONLY) HUMAN_BLIND group recording (v0.1) -- additive,
# parallel to EvaluationRecord above (which stays unchanged). EvaluationRecord
# only represents one blinded pair; the frozen LIVE-1 protocol also needs two
# comparison units a pair cannot express: WITHIN_GROUP (one anonymous group
# of exactly three answers) and CROSS_GROUP (two anonymous groups of exactly
# three each). StageARubricAssessment covers only R1/R2/R4/R5/R6 -- R3
# (evidence_dependence) and attribution_trace are Stage-B-only concepts with
# no field here at all, not optional or defaulted.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StageARubricAssessment:
    """LIVE-1 Semantic Rubric v0.1, Stage A (ANSWER_ONLY) fields only."""

    core_conclusion: str                # R1: SAME | SHIFTED | REVERSED | UNRESOLVED
    material_claims: list[ClaimDelta]   # R2: claim-level, not a scalar summary
    epistemic_stance: str               # R4: STRONGER | SAME | WEAKER | SHIFT_TO_UNCERTAINTY | SHIFT_FROM_UNCERTAINTY
    material_contradiction: str         # R5: NONE | PARTIAL | DIRECT
    overall_semantic_effect: str        # R6: SEMANTICALLY_EQUIVALENT | MINOR_CHANGE | MATERIAL_CHANGE | FUNDAMENTAL_CHANGE

    def to_dict(self) -> dict[str, Any]:
        return {
            "core_conclusion": self.core_conclusion,
            "material_claims": [asdict(c) for c in self.material_claims],
            "epistemic_stance": self.epistemic_stance,
            "material_contradiction": self.material_contradiction,
            "overall_semantic_effect": self.overall_semantic_effect,
        }


@dataclass(frozen=True)
class StageAGroupEvaluationRecord:
    """LIVE-1 Stage-A (ANSWER_ONLY) HUMAN_BLIND group-comparison record.
    Represents WITHIN_GROUP or CROSS_GROUP comparison units. Kept fully
    separate from EvaluationRecord; neither replaces the other."""

    experiment_id: str
    evaluator_identity: str
    evaluator_type: str          # "HUMAN"
    evaluation_profile: str      # "LIVE1-HUMAN-BLIND-v1"
    rubric_version: str
    evaluation_stage: str        # fixed "A_ANSWER_ONLY"
    comparison_scope: str        # "WITHIN_GROUP" | "CROSS_GROUP"
    timestamp: str
    group_answer_hashes: dict[str, list[str]]   # {"X": [h,h,h]} or {"X":[...], "Y":[...]}
    assessment: StageARubricAssessment

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "evaluator_identity": self.evaluator_identity,
            "evaluator_type": self.evaluator_type,
            "evaluation_profile": self.evaluation_profile,
            "rubric_version": self.rubric_version,
            "evaluation_stage": self.evaluation_stage,
            "comparison_scope": self.comparison_scope,
            "timestamp": self.timestamp,
            "group_answer_hashes": {k: list(v) for k, v in self.group_answer_hashes.items()},
            "assessment": self.assessment.to_dict(),
        }
