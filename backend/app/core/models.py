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
