from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .status import (
    AuthorityRight,
    CheckOutcome,
    EvidenceStatus,
    PromotionDecisionValue,
    PromotionOutcome,
    PromotionTarget,
    ValidationOutcome,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SourceRef:
    type: str
    identifier: str
    location: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.type:
            raise ValueError("source.type is required")
        if not self.identifier:
            raise ValueError("source.identifier is required")


@dataclass(frozen=True)
class Provenance:
    origin: str
    collection_method: str
    collector: Optional[str] = None
    timestamp: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.origin:
            raise ValueError("provenance.origin is required")
        if not self.collection_method:
            raise ValueError("provenance.collection_method is required")


@dataclass(frozen=True)
class Fingerprint:
    algorithm: Optional[str] = None
    hash: Optional[str] = None
    content_id: Optional[str] = None


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    claim: str
    source: SourceRef
    provenance: Provenance
    status: EvidenceStatus = EvidenceStatus.UNKNOWN
    fingerprint: Optional[Fingerprint] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    validation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("evidence_id is required")
        if not self.claim:
            raise ValueError("claim is required")

    def with_status(
        self,
        status: EvidenceStatus,
        *,
        validation_id: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> "EvidenceRecord":
        return replace(
            self,
            status=status,
            validation_id=self.validation_id if validation_id is None else validation_id,
            updated_at=updated_at or utc_now_iso(),
        )


@dataclass(frozen=True)
class ValidationCheck:
    check_id: str
    name: str
    required: bool
    result: CheckOutcome
    reason: str


@dataclass(frozen=True)
class ValidationResult:
    validation_id: str
    evidence_id: str
    profile_id: str
    result: ValidationOutcome
    checks: Tuple[ValidationCheck, ...]
    blocking_reasons: Tuple[str, ...] = ()
    receipt_id: Optional[str] = None
    validated_at: str = field(default_factory=utc_now_iso)
    evidence_fingerprint_hash: Optional[str] = None
    supersedes_validation_id: Optional[str] = None


@dataclass(frozen=True)
class TransitionRecord:
    transition_id: str
    evidence_id: str
    from_status: EvidenceStatus
    to_status: EvidenceStatus
    actor: str
    authority: AuthorityRight
    reason: str
    timestamp: str = field(default_factory=utc_now_iso)
    validation_id: Optional[str] = None
    promotion_id: Optional[str] = None
    receipt_id: Optional[str] = None


@dataclass(frozen=True)
class PromotionAuthorization:
    authorization_id: str
    evidence_id: str
    validation_id: str
    target: PromotionTarget
    scope: Dict[str, Any]
    authorized_by: str
    authority_basis: AuthorityRight
    decision: PromotionDecisionValue
    issued_at: str
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    reason: str = ""


@dataclass(frozen=True)
class PromotionResult:
    promotion_id: str
    authorization_id: Optional[str]
    evidence_id: str
    validation_id: Optional[str]
    target: PromotionTarget
    result: PromotionOutcome
    effective_scope: Dict[str, Any]
    gate_results: Tuple[ValidationCheck, ...]
    blocking_reasons: Tuple[str, ...] = ()
    promoted_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class PromotionRevocation:
    revocation_id: str
    promotion_id: str
    evidence_id: str
    target: PromotionTarget
    reason: str
    revoked_by: str
    post_revocation_state: EvidenceStatus
    revoked_at: str = field(default_factory=utc_now_iso)
