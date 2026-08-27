from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class AdapterValidationState(str, Enum):
    VALID = "VALID"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    INVALID_IDENTITY = "INVALID_IDENTITY"
    INVALID_FINGERPRINT = "INVALID_FINGERPRINT"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"


@dataclass(frozen=True)
class ProvenanceRecord:
    origin: str
    producer: str
    created_at: str
    chain_id: Optional[str] = None


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    source_identity: str
    fingerprint: str
    fingerprint_algorithm: str
    provenance: ProvenanceRecord


@dataclass(frozen=True)
class AdapterMetadata:
    producer: str
    created_at: str
    schema_version: str
    adapter_version: str


@dataclass(frozen=True)
class ContextPackEnvelope:
    context_pack_id: str
    context_pack_version: str
    question_id: str
    evidence_references: Tuple[EvidenceReference, ...]
    metadata: AdapterMetadata


@dataclass(frozen=True)
class EvidenceAdmissionRequest:
    request_id: str
    context_pack_id: str
    question_id: str
    evidence_records: Tuple[EvidenceReference, ...]
    requested_operation: str
    authority_scope: str


@dataclass(frozen=True)
class AdapterValidationResult:
    status: AdapterValidationState
    reasons: Tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.status == AdapterValidationState.VALID
