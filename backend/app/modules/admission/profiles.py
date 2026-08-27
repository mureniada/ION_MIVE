from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidatorProfile:
    profile_id: str
    identity_required: bool = True
    provenance_required: bool = True
    claim_binding_required: bool = True
    scope_required: bool = True
    temporal_effectivity_required: bool = True
    receipt_required: bool = False
    contradiction_check_required: bool = True
    authorization_boundary_required: bool = True


@dataclass(frozen=True)
class PromotionProfile:
    profile_id: str
    verified_state_required: bool = True
    validation_binding_required: bool = True
    evidence_identity_required: bool = True
    explicit_authority_required: bool = True
    target_binding_required: bool = True
    scope_compatibility_required: bool = True
    effectivity_check_required: bool = True
    contradiction_reopen_check_required: bool = True
    existing_promotion_conflict_check_required: bool = True
    audit_record_required: bool = True
    automatic_promotion_allowed: bool = False


DEFAULT_VALIDATOR_PROFILE = ValidatorProfile(
    profile_id="ION_EVIDENCE_VALIDATOR_PROFILE_DEFAULT_V0_1"
)

DEFAULT_PROMOTION_PROFILE = PromotionProfile(
    profile_id="ION_PROMOTION_PROFILE_DEFAULT_V0_1"
)
