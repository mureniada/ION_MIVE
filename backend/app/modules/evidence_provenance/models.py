"""In-memory canonical provenance model. No runtime side effects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CanonicalizationStatus(str, Enum):
    CANONICAL = "CANONICAL"
    REJECTED = "REJECTED"


class CanonicalizationReason(str, Enum):
    MISSING_EVIDENCE_ID = "MISSING_EVIDENCE_ID"
    MISSING_SOURCE_IDENTITY = "MISSING_SOURCE_IDENTITY"
    UNKNOWN_SOURCE_IDENTITY = "UNKNOWN_SOURCE_IDENTITY"
    MISSING_FINGERPRINT = "MISSING_FINGERPRINT"
    UNRESOLVED_FINGERPRINT_PROFILE = "UNRESOLVED_FINGERPRINT_PROFILE"
    UNPROVEN_CHECKSUM_SEMANTICS = "UNPROVEN_CHECKSUM_SEMANTICS"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    MISSING_PROVENANCE_ORIGIN = "MISSING_PROVENANCE_ORIGIN"
    MISSING_PROVENANCE_PRODUCER = "MISSING_PROVENANCE_PRODUCER"
    MISSING_PROVENANCE_CREATED_AT = "MISSING_PROVENANCE_CREATED_AT"
    LEXICAL_PROVENANCE_INCOMPLETE = "LEXICAL_PROVENANCE_INCOMPLETE"
    OPEN_ENDED_MEMORY_METADATA = "OPEN_ENDED_MEMORY_METADATA"
    AMBIGUOUS_QDRANT_DOCUMENT_ID_FALLBACK = "AMBIGUOUS_QDRANT_DOCUMENT_ID_FALLBACK"
    UNKNOWN_BACKEND = "UNKNOWN_BACKEND"
    UNKNOWN_MAPPING_PROFILE = "UNKNOWN_MAPPING_PROFILE"
    SYNTHETIC_PROVENANCE_FORBIDDEN = "SYNTHETIC_PROVENANCE_FORBIDDEN"
    MODEL_DERIVED_PROVENANCE_FORBIDDEN = "MODEL_DERIVED_PROVENANCE_FORBIDDEN"
    CONFLICTING_EVIDENCE_IDENTITY = "CONFLICTING_EVIDENCE_IDENTITY"


@dataclass(frozen=True)
class CanonicalProvenance:
    origin: str
    producer: str
    created_at: str
    chain_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeEvidenceBinding:
    backend_id: str
    runtime_evidence_id_field: str
    runtime_source_identity_field: str
    fingerprint_source_field: str
    provenance_source_field: str
    mapping_profile_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalEvidenceProvenanceRecord:
    evidence_id: str
    source_identity: str
    fingerprint: str
    fingerprint_algorithm: str
    provenance: CanonicalProvenance
    runtime_binding: RuntimeEvidenceBinding
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_identity": self.source_identity,
            "fingerprint": self.fingerprint,
            "fingerprint_algorithm": self.fingerprint_algorithm,
            "provenance": self.provenance.to_dict(),
            "runtime_binding": self.runtime_binding.to_dict(),
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True)
class CanonicalizationResult:
    status: CanonicalizationStatus
    record: CanonicalEvidenceProvenanceRecord | None = None
    reasons: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status is CanonicalizationStatus.CANONICAL
