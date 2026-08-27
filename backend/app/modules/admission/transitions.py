from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
from uuid import uuid4

from .models import (
    EvidenceRecord,
    PromotionResult,
    PromotionRevocation,
    TransitionRecord,
    ValidationResult,
    utc_now_iso,
)
from .status import (
    AuthorityRight,
    EvidenceStatus,
    PromotionOutcome,
    ValidationOutcome,
)


_ALLOWED = {
    EvidenceStatus.UNKNOWN: {
        EvidenceStatus.PENDING,
        EvidenceStatus.REJECTED,
    },
    EvidenceStatus.PENDING: {
        EvidenceStatus.UNKNOWN,
        EvidenceStatus.VERIFIED,
        EvidenceStatus.REJECTED,
    },
    EvidenceStatus.VERIFIED: {
        EvidenceStatus.PENDING,
        EvidenceStatus.REJECTED,
        EvidenceStatus.PROMOTED,
    },
    EvidenceStatus.PROMOTED: {
        EvidenceStatus.VERIFIED,
        EvidenceStatus.PENDING,
        EvidenceStatus.REJECTED,
    },
    EvidenceStatus.REJECTED: set(),
}


@dataclass(frozen=True)
class TransitionOutcome:
    record: EvidenceRecord
    transition: TransitionRecord


class StateTransitionEngine:
    def transition(
        self,
        record: EvidenceRecord,
        to_status: EvidenceStatus,
        *,
        actor: str,
        authority: AuthorityRight,
        reason: str,
        validation: Optional[ValidationResult] = None,
        promotion: Optional[PromotionResult] = None,
        revocation: Optional[PromotionRevocation] = None,
        receipt_id: Optional[str] = None,
        transition_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> TransitionOutcome:
        if not actor:
            raise ValueError("actor is required")
        if not reason:
            raise ValueError("reason is required")
        if to_status not in _ALLOWED[record.status]:
            raise ValueError(
                f"Forbidden transition: {record.status.value} -> {to_status.value}"
            )

        self._enforce_transition_contract(
            record,
            to_status,
            authority=authority,
            validation=validation,
            promotion=promotion,
            revocation=revocation,
        )

        ts = timestamp or utc_now_iso()
        new_validation_id = (
            validation.validation_id
            if validation is not None and to_status == EvidenceStatus.VERIFIED
            else record.validation_id
        )
        new_record = record.with_status(
            to_status,
            validation_id=new_validation_id,
            updated_at=ts,
        )

        tr = TransitionRecord(
            transition_id=transition_id or f"TR-{uuid4().hex}",
            evidence_id=record.evidence_id,
            from_status=record.status,
            to_status=to_status,
            actor=actor,
            authority=authority,
            reason=reason,
            timestamp=ts,
            validation_id=validation.validation_id if validation else None,
            promotion_id=promotion.promotion_id if promotion else None,
            receipt_id=receipt_id,
        )
        return TransitionOutcome(record=new_record, transition=tr)

    @staticmethod
    def _enforce_transition_contract(
        record: EvidenceRecord,
        to_status: EvidenceStatus,
        *,
        authority: AuthorityRight,
        validation: Optional[ValidationResult],
        promotion: Optional[PromotionResult],
        revocation: Optional[PromotionRevocation],
    ) -> None:
        if record.status == EvidenceStatus.UNKNOWN and to_status == EvidenceStatus.PENDING:
            if authority not in {
                AuthorityRight.COLLECTION_RIGHT,
                AuthorityRight.ADMISSION_RIGHT,
            }:
                raise PermissionError("UNKNOWN -> PENDING requires collection/admission right")

        if record.status == EvidenceStatus.UNKNOWN and to_status == EvidenceStatus.REJECTED:
            if authority not in {
                AuthorityRight.ADMISSION_RIGHT,
                AuthorityRight.VALIDATION_RIGHT,
            }:
                raise PermissionError("UNKNOWN -> REJECTED requires admission/validation right")

        if record.status == EvidenceStatus.PENDING:
            if authority != AuthorityRight.VALIDATION_RIGHT:
                raise PermissionError("PENDING transitions require VALIDATION_RIGHT")
            if validation is None:
                raise ValueError("PENDING transition requires ValidationResult")
            if validation.evidence_id != record.evidence_id:
                raise ValueError("ValidationResult evidence identity mismatch")
            expected = {
                EvidenceStatus.VERIFIED: ValidationOutcome.PASS,
                EvidenceStatus.REJECTED: ValidationOutcome.FAIL,
                EvidenceStatus.UNKNOWN: ValidationOutcome.UNKNOWN,
            }[to_status]
            if validation.result != expected:
                raise ValueError(
                    f"{record.status.value} -> {to_status.value} requires validation {expected.value}"
                )

        if record.status == EvidenceStatus.VERIFIED and to_status == EvidenceStatus.PROMOTED:
            if authority != AuthorityRight.PROMOTION_RIGHT:
                raise PermissionError("VERIFIED -> PROMOTED requires PROMOTION_RIGHT")
            if promotion is None or promotion.result != PromotionOutcome.PROMOTED:
                raise ValueError("VERIFIED -> PROMOTED requires successful PromotionResult")
            if promotion.evidence_id != record.evidence_id:
                raise ValueError("PromotionResult evidence identity mismatch")

        if record.status == EvidenceStatus.VERIFIED and to_status in {
            EvidenceStatus.PENDING,
            EvidenceStatus.REJECTED,
        }:
            if authority != AuthorityRight.VALIDATION_RIGHT:
                raise PermissionError("VERIFIED reopen/invalidation requires VALIDATION_RIGHT")
            if to_status == EvidenceStatus.REJECTED:
                if validation is None or validation.result != ValidationOutcome.FAIL:
                    raise ValueError("VERIFIED -> REJECTED requires FAIL revalidation")

        if record.status == EvidenceStatus.PROMOTED:
            if revocation is None:
                raise ValueError("PROMOTED transition requires PromotionRevocation")
            if revocation.evidence_id != record.evidence_id:
                raise ValueError("PromotionRevocation evidence identity mismatch")
            if revocation.post_revocation_state != to_status:
                raise ValueError("PromotionRevocation post state mismatch")
            if authority not in {
                AuthorityRight.PROMOTION_RIGHT,
                AuthorityRight.VALIDATION_RIGHT,
            }:
                raise PermissionError("Promotion revocation requires promotion/validation right")
