from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .authorities import AuthorityRegistry
from .models import (
    EvidenceRecord,
    PromotionAuthorization,
    PromotionResult,
    ValidationCheck,
    ValidationResult,
    utc_now_iso,
)
from .profiles import DEFAULT_PROMOTION_PROFILE, PromotionProfile
from .status import (
    AuthorityRight,
    CheckOutcome,
    EvidenceStatus,
    PromotionDecisionValue,
    PromotionOutcome,
    PromotionTarget,
    ValidationOutcome,
)


@dataclass(frozen=True)
class PromotionContext:
    requested_target: PromotionTarget
    requested_scope: Dict[str, Any]
    validated_scope: Dict[str, Any]
    current_fingerprint_hash: Optional[str]
    contradiction_reopened: bool = False
    existing_conflict: bool = False
    audit_available: bool = True
    now: Optional[str] = None


class PromotionEngine:
    def evaluate(
        self,
        record: EvidenceRecord,
        validation: ValidationResult,
        authorization: Optional[PromotionAuthorization],
        authority_registry: AuthorityRegistry,
        context: PromotionContext,
        *,
        promotion_id: str,
        profile: PromotionProfile = DEFAULT_PROMOTION_PROFILE,
    ) -> PromotionResult:
        if not promotion_id:
            raise ValueError("promotion_id is required")

        gates = []

        gates.append(self._verified_gate(record, profile.verified_state_required))
        gates.append(
            self._validation_binding_gate(
                record, validation, profile.validation_binding_required
            )
        )
        gates.append(
            self._identity_gate(
                record,
                validation,
                context.current_fingerprint_hash,
                profile.evidence_identity_required,
            )
        )
        gates.append(
            self._authority_gate(
                authorization,
                authority_registry,
                context.requested_target,
                profile.explicit_authority_required,
            )
        )
        gates.append(
            self._target_gate(
                authorization,
                context.requested_target,
                profile.target_binding_required,
            )
        )
        gates.append(
            self._scope_gate(
                authorization,
                context,
                profile.scope_compatibility_required,
            )
        )
        gates.append(
            self._effectivity_gate(
                authorization,
                context.now,
                profile.effectivity_check_required,
            )
        )
        gates.append(
            ValidationCheck(
                "P08",
                "contradiction_reopen",
                profile.contradiction_reopen_check_required,
                (
                    CheckOutcome.FAIL
                    if context.contradiction_reopened
                    else CheckOutcome.PASS
                ),
                (
                    "Underlying evidence was reopened by material contradiction"
                    if context.contradiction_reopened
                    else "No blocking contradiction reopen"
                ),
            )
        )
        gates.append(
            ValidationCheck(
                "P09",
                "existing_promotion_conflict",
                profile.existing_promotion_conflict_check_required,
                CheckOutcome.FAIL if context.existing_conflict else CheckOutcome.PASS,
                (
                    "Existing incompatible active promotion requires adjudication"
                    if context.existing_conflict
                    else "No incompatible active promotion conflict"
                ),
            )
        )
        gates.append(
            ValidationCheck(
                "P10",
                "auditability",
                profile.audit_record_required,
                CheckOutcome.PASS if context.audit_available else CheckOutcome.FAIL,
                "Audit recording is available"
                if context.audit_available
                else "Required audit recording is unavailable",
            )
        )

        result, blockers = self._aggregate(tuple(gates), authorization)

        return PromotionResult(
            promotion_id=promotion_id,
            authorization_id=authorization.authorization_id if authorization else None,
            evidence_id=record.evidence_id,
            validation_id=validation.validation_id if validation else None,
            target=context.requested_target,
            result=result,
            effective_scope=dict(context.requested_scope),
            gate_results=tuple(gates),
            blocking_reasons=blockers,
            promoted_at=context.now or utc_now_iso(),
        )

    @staticmethod
    def _verified_gate(record: EvidenceRecord, required: bool) -> ValidationCheck:
        result = (
            CheckOutcome.PASS
            if record.status == EvidenceStatus.VERIFIED
            else CheckOutcome.FAIL
        )
        return ValidationCheck(
            "P01",
            "verified_state",
            required,
            result if required else CheckOutcome.NOT_APPLICABLE,
            "EvidenceRecord is VERIFIED"
            if result == CheckOutcome.PASS
            else "EvidenceRecord is not VERIFIED",
        )

    @staticmethod
    def _validation_binding_gate(
        record: EvidenceRecord,
        validation: ValidationResult,
        required: bool,
    ) -> ValidationCheck:
        bound = (
            validation.evidence_id == record.evidence_id
            and validation.result == ValidationOutcome.PASS
            and (
                record.validation_id is None
                or record.validation_id == validation.validation_id
            )
        )
        return ValidationCheck(
            "P02",
            "validation_binding",
            required,
            (
                CheckOutcome.PASS if bound else CheckOutcome.FAIL
            ) if required else CheckOutcome.NOT_APPLICABLE,
            "Bound PASS ValidationResult matched EvidenceRecord"
            if bound
            else "PASS validation binding mismatch or absent",
        )

    @staticmethod
    def _identity_gate(
        record: EvidenceRecord,
        validation: ValidationResult,
        current_hash: Optional[str],
        required: bool,
    ) -> ValidationCheck:
        if not required:
            return ValidationCheck(
                "P03", "evidence_identity", False, CheckOutcome.NOT_APPLICABLE,
                "Identity check not required by profile"
            )
        expected = record.fingerprint.hash if record.fingerprint else None
        validated = validation.evidence_fingerprint_hash
        if not expected or not validated or not current_hash:
            result = CheckOutcome.UNKNOWN
            reason = "Promotion-time evidence identity cannot be fully established"
        elif expected == validated == current_hash:
            result = CheckOutcome.PASS
            reason = "Validated and current evidence fingerprints match"
        else:
            result = CheckOutcome.FAIL
            reason = "Evidence identity changed or validation fingerprint mismatched"
        return ValidationCheck("P03", "evidence_identity", True, result, reason)

    @staticmethod
    def _authority_gate(
        authorization: Optional[PromotionAuthorization],
        registry: AuthorityRegistry,
        target: PromotionTarget,
        required: bool,
    ) -> ValidationCheck:
        if not required:
            return ValidationCheck(
                "P04", "authority", False, CheckOutcome.NOT_APPLICABLE,
                "Explicit authority not required by profile"
            )
        if authorization is None:
            return ValidationCheck(
                "P04", "authority", True, CheckOutcome.UNKNOWN,
                "PromotionAuthorization is absent"
            )
        if authorization.authority_basis != AuthorityRight.PROMOTION_RIGHT:
            return ValidationCheck(
                "P04", "authority", True, CheckOutcome.FAIL,
                "Authorization basis is not PROMOTION_RIGHT"
            )
        ok = registry.has_right(
            authorization.authorized_by,
            AuthorityRight.PROMOTION_RIGHT,
            target,
        )
        return ValidationCheck(
            "P04",
            "authority",
            True,
            CheckOutcome.PASS if ok else CheckOutcome.UNKNOWN,
            "Bound promotion right established"
            if ok
            else "Bound promotion right is not established in the authority registry",
        )

    @staticmethod
    def _target_gate(
        authorization: Optional[PromotionAuthorization],
        target: PromotionTarget,
        required: bool,
    ) -> ValidationCheck:
        if not required:
            return ValidationCheck(
                "P05", "target", False, CheckOutcome.NOT_APPLICABLE,
                "Target binding not required by profile"
            )
        if authorization is None:
            result = CheckOutcome.UNKNOWN
            reason = "PromotionAuthorization is absent"
        elif authorization.target == target:
            result = CheckOutcome.PASS
            reason = "Requested target matches authorization"
        else:
            result = CheckOutcome.FAIL
            reason = "Requested target differs from authorization"
        return ValidationCheck("P05", "target", True, result, reason)

    @staticmethod
    def _scope_gate(
        authorization: Optional[PromotionAuthorization],
        context: PromotionContext,
        required: bool,
    ) -> ValidationCheck:
        if not required:
            return ValidationCheck(
                "P06", "scope", False, CheckOutcome.NOT_APPLICABLE,
                "Scope compatibility not required by profile"
            )
        if authorization is None:
            return ValidationCheck(
                "P06", "scope", True, CheckOutcome.UNKNOWN,
                "PromotionAuthorization is absent"
            )
        ok = (
            _scope_within(context.requested_scope, context.validated_scope)
            and _scope_within(context.requested_scope, authorization.scope)
        )
        return ValidationCheck(
            "P06",
            "scope",
            True,
            CheckOutcome.PASS if ok else CheckOutcome.FAIL,
            "Requested scope is within validation and authorization boundaries"
            if ok
            else "Requested scope exceeds validation or authorization boundary",
        )

    @staticmethod
    def _effectivity_gate(
        authorization: Optional[PromotionAuthorization],
        now: Optional[str],
        required: bool,
    ) -> ValidationCheck:
        if not required:
            return ValidationCheck(
                "P07", "effectivity", False, CheckOutcome.NOT_APPLICABLE,
                "Effectivity check not required by profile"
            )
        if authorization is None:
            return ValidationCheck(
                "P07", "effectivity", True, CheckOutcome.UNKNOWN,
                "PromotionAuthorization is absent"
            )
        try:
            current = _parse_iso(now or utc_now_iso())
            lower = _parse_iso(authorization.valid_from) if authorization.valid_from else None
            upper = _parse_iso(authorization.valid_until) if authorization.valid_until else None
        except ValueError:
            return ValidationCheck(
                "P07", "effectivity", True, CheckOutcome.UNKNOWN,
                "Effectivity timestamp could not be parsed"
            )
        if lower is not None and current < lower:
            return ValidationCheck(
                "P07", "effectivity", True, CheckOutcome.FAIL,
                "Authorization is not yet effective"
            )
        if upper is not None and current > upper:
            return ValidationCheck(
                "P07", "effectivity", True, CheckOutcome.FAIL,
                "Authorization has expired"
            )
        return ValidationCheck(
            "P07", "effectivity", True, CheckOutcome.PASS,
            "Authorization is within effectivity horizon"
        )

    @staticmethod
    def _aggregate(
        gates: Tuple[ValidationCheck, ...],
        authorization: Optional[PromotionAuthorization],
    ) -> Tuple[PromotionOutcome, Tuple[str, ...]]:
        required = [g for g in gates if g.required]
        failures = [g for g in required if g.result == CheckOutcome.FAIL]
        unknowns = [g for g in required if g.result == CheckOutcome.UNKNOWN]

        if failures:
            return (
                PromotionOutcome.BLOCKED,
                tuple(f"{g.check_id}:{g.reason}" for g in failures),
            )
        if unknowns:
            return (
                PromotionOutcome.UNKNOWN,
                tuple(f"{g.check_id}:{g.reason}" for g in unknowns),
            )
        if authorization is None:
            return PromotionOutcome.UNKNOWN, ("P04:PromotionAuthorization is absent",)
        if authorization.decision == PromotionDecisionValue.DENY:
            return PromotionOutcome.DENIED, ()
        return PromotionOutcome.PROMOTED, ()


def _scope_within(requested: Dict[str, Any], boundary: Dict[str, Any]) -> bool:
    for key, value in requested.items():
        if key not in boundary:
            return False
        boundary_value = boundary[key]
        if isinstance(value, dict):
            if not isinstance(boundary_value, dict):
                return False
            if not _scope_within(value, boundary_value):
                return False
        elif boundary_value != value:
            return False
    return True


def _parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
