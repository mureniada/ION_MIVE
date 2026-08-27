from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .models import EvidenceRecord, ValidationCheck, ValidationResult, utc_now_iso
from .profiles import DEFAULT_VALIDATOR_PROFILE, ValidatorProfile
from .status import CheckOutcome, EvidenceStatus, ValidationOutcome


@dataclass(frozen=True)
class ValidationContext:
    actual_fingerprint_hash: Optional[str] = None
    claim_binding: CheckOutcome = CheckOutcome.UNKNOWN
    scope: CheckOutcome = CheckOutcome.UNKNOWN
    effectivity: CheckOutcome = CheckOutcome.UNKNOWN
    receipt: CheckOutcome = CheckOutcome.NOT_APPLICABLE
    contradiction: CheckOutcome = CheckOutcome.UNKNOWN
    authorization_boundary: CheckOutcome = CheckOutcome.PASS
    receipt_id: Optional[str] = None


class EvidenceValidator:
    def validate(
        self,
        record: EvidenceRecord,
        context: ValidationContext,
        *,
        validation_id: str,
        profile: ValidatorProfile = DEFAULT_VALIDATOR_PROFILE,
        validated_at: Optional[str] = None,
    ) -> ValidationResult:
        if record.status != EvidenceStatus.PENDING:
            raise ValueError("Validator entry requires EvidenceRecord status PENDING")
        if not validation_id:
            raise ValueError("validation_id is required")

        checks = []

        checks.append(
            self._identity_check(record, context, profile.identity_required)
        )
        checks.append(
            self._provenance_check(record, profile.provenance_required)
        )
        checks.append(
            ValidationCheck(
                check_id="V03",
                name="claim_to_evidence_binding",
                required=profile.claim_binding_required,
                result=context.claim_binding,
                reason="Bounded claim/evidence binding supplied by validation context",
            )
        )
        checks.append(
            ValidationCheck(
                check_id="V04",
                name="scope",
                required=profile.scope_required,
                result=context.scope,
                reason="Bounded scope result supplied by validation context",
            )
        )
        checks.append(
            ValidationCheck(
                check_id="V05",
                name="temporal_effectivity",
                required=profile.temporal_effectivity_required,
                result=context.effectivity,
                reason="Effectivity result supplied by validation context",
            )
        )
        checks.append(
            ValidationCheck(
                check_id="V06",
                name="receipt_integrity",
                required=profile.receipt_required,
                result=(
                    context.receipt
                    if profile.receipt_required
                    else CheckOutcome.NOT_APPLICABLE
                ),
                reason="Receipt/integrity gate",
            )
        )
        checks.append(
            ValidationCheck(
                check_id="V07",
                name="contradiction",
                required=profile.contradiction_check_required,
                result=context.contradiction,
                reason="Material contradiction gate",
            )
        )
        checks.append(
            ValidationCheck(
                check_id="V08",
                name="authorization_boundary",
                required=profile.authorization_boundary_required,
                result=context.authorization_boundary,
                reason="Validation must not imply promotion or action authority",
            )
        )

        result, blockers = self._aggregate(tuple(checks))

        return ValidationResult(
            validation_id=validation_id,
            evidence_id=record.evidence_id,
            profile_id=profile.profile_id,
            result=result,
            checks=tuple(checks),
            blocking_reasons=blockers,
            receipt_id=context.receipt_id,
            validated_at=validated_at or utc_now_iso(),
            evidence_fingerprint_hash=(
                record.fingerprint.hash if record.fingerprint is not None else None
            ),
        )

    @staticmethod
    def _identity_check(
        record: EvidenceRecord,
        context: ValidationContext,
        required: bool,
    ) -> ValidationCheck:
        if not required:
            return ValidationCheck(
                "V01",
                "evidence_identity",
                False,
                CheckOutcome.NOT_APPLICABLE,
                "Identity check not required by profile",
            )

        expected = record.fingerprint.hash if record.fingerprint else None
        actual = context.actual_fingerprint_hash
        algorithm = record.fingerprint.algorithm if record.fingerprint else None

        if algorithm is None:
            outcome = CheckOutcome.UNKNOWN
            reason = "Required fingerprint algorithm is unavailable"
        elif algorithm.upper() != "SHA256":
            outcome = CheckOutcome.UNKNOWN
            reason = "Unsupported fingerprint algorithm"
        elif not expected or not actual:
            outcome = CheckOutcome.UNKNOWN
            reason = "Required fingerprint identity is unavailable"
        elif expected == actual:
            outcome = CheckOutcome.PASS
            reason = "Fingerprint matched bound evidence identity"
        else:
            outcome = CheckOutcome.FAIL
            reason = "Fingerprint mismatch"

        return ValidationCheck("V01", "evidence_identity", True, outcome, reason)

    @staticmethod
    def _provenance_check(
        record: EvidenceRecord,
        required: bool,
    ) -> ValidationCheck:
        if not required:
            return ValidationCheck(
                "V02",
                "provenance",
                False,
                CheckOutcome.NOT_APPLICABLE,
                "Provenance check not required by profile",
            )

        p = record.provenance
        if not p.origin or not p.collection_method:
            outcome = CheckOutcome.UNKNOWN
            reason = "Mandatory provenance is incomplete"
        elif not p.collector or not p.timestamp:
            outcome = CheckOutcome.UNKNOWN
            reason = "Default profile requires collector and timestamp for complete provenance"
        else:
            outcome = CheckOutcome.PASS
            reason = "Required provenance fields are present"

        return ValidationCheck("V02", "provenance", True, outcome, reason)

    @staticmethod
    def _aggregate(
        checks: Tuple[ValidationCheck, ...],
    ) -> Tuple[ValidationOutcome, Tuple[str, ...]]:
        required = [c for c in checks if c.required]
        fail = [c for c in required if c.result == CheckOutcome.FAIL]
        unknown = [c for c in required if c.result == CheckOutcome.UNKNOWN]

        if fail:
            return (
                ValidationOutcome.FAIL,
                tuple(f"{c.check_id}:{c.reason}" for c in fail),
            )
        if unknown:
            return (
                ValidationOutcome.UNKNOWN,
                tuple(f"{c.check_id}:{c.reason}" for c in unknown),
            )
        return ValidationOutcome.PASS, ()
