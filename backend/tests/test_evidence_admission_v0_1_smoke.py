from __future__ import annotations

from app.modules.admission import (
    AuthorityGrant,
    AuthorityRegistry,
    AuthorityRight,
    CheckOutcome,
    EvidenceRecord,
    EvidenceStatus,
    EvidenceValidator,
    Fingerprint,
    PromotionAuthorization,
    PromotionContext,
    PromotionDecisionValue,
    PromotionEngine,
    PromotionOutcome,
    PromotionTarget,
    Provenance,
    SourceRef,
    StateTransitionEngine,
    ValidationContext,
    ValidationOutcome,
)


def _pending() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="EV-001",
        claim="Bounded claim",
        source=SourceRef(type="file", identifier="SOURCE-001"),
        provenance=Provenance(
            origin="external_observer",
            collector="collector",
            collection_method="runtime_capture",
            timestamp="2026-08-22T14:38:23Z",
        ),
        fingerprint=Fingerprint(algorithm="SHA256", hash="abc", content_id="OBJ-001"),
        status=EvidenceStatus.PENDING,
    )


def _pass_validation(record: EvidenceRecord):
    validator = EvidenceValidator()
    return validator.validate(
        record,
        ValidationContext(
            actual_fingerprint_hash="abc",
            claim_binding=CheckOutcome.PASS,
            scope=CheckOutcome.PASS,
            effectivity=CheckOutcome.PASS,
            contradiction=CheckOutcome.PASS,
            authorization_boundary=CheckOutcome.PASS,
        ),
        validation_id="VAL-001",
    )


def test_unknown_validation_blocks_verified():
    record = _pending()
    result = EvidenceValidator().validate(
        record,
        ValidationContext(
            actual_fingerprint_hash="abc",
            claim_binding=CheckOutcome.UNKNOWN,
            scope=CheckOutcome.PASS,
            effectivity=CheckOutcome.PASS,
            contradiction=CheckOutcome.PASS,
            authorization_boundary=CheckOutcome.PASS,
        ),
        validation_id="VAL-U",
    )
    assert result.result == ValidationOutcome.UNKNOWN


def test_identity_mismatch_fails():
    record = _pending()
    result = EvidenceValidator().validate(
        record,
        ValidationContext(
            actual_fingerprint_hash="different",
            claim_binding=CheckOutcome.PASS,
            scope=CheckOutcome.PASS,
            effectivity=CheckOutcome.PASS,
            contradiction=CheckOutcome.PASS,
            authorization_boundary=CheckOutcome.PASS,
        ),
        validation_id="VAL-F",
    )
    assert result.result == ValidationOutcome.FAIL


def test_pass_validation_can_transition_to_verified():
    record = _pending()
    validation = _pass_validation(record)
    outcome = StateTransitionEngine().transition(
        record,
        EvidenceStatus.VERIFIED,
        actor="validator",
        authority=AuthorityRight.VALIDATION_RIGHT,
        reason="VALIDATION_PASS",
        validation=validation,
        transition_id="TR-001",
    )
    assert outcome.record.status == EvidenceStatus.VERIFIED
    assert outcome.record.evidence_id == record.evidence_id


def test_pending_cannot_promote_directly():
    record = _pending()
    try:
        StateTransitionEngine().transition(
            record,
            EvidenceStatus.PROMOTED,
            actor="promoter",
            authority=AuthorityRight.PROMOTION_RIGHT,
            reason="INVALID_DIRECT_PROMOTION",
        )
    except ValueError:
        return
    raise AssertionError("PENDING -> PROMOTED must be blocked")


def test_verified_requires_separate_promotion_authority():
    record = _pending()
    validation = _pass_validation(record)
    verified = StateTransitionEngine().transition(
        record,
        EvidenceStatus.VERIFIED,
        actor="validator",
        authority=AuthorityRight.VALIDATION_RIGHT,
        reason="VALIDATION_PASS",
        validation=validation,
        transition_id="TR-002",
    ).record

    result = PromotionEngine().evaluate(
        verified,
        validation,
        None,
        AuthorityRegistry(),
        PromotionContext(
            requested_target=PromotionTarget.KNOWLEDGE_GRAPH,
            requested_scope={"claim_scope": "bounded_claim_only"},
            validated_scope={"claim_scope": "bounded_claim_only"},
            current_fingerprint_hash="abc",
            contradiction_reopened=False,
            existing_conflict=False,
            audit_available=True,
            now="2026-08-22T18:00:00Z",
        ),
        promotion_id="PROM-NOAUTH",
    )
    assert result.result != PromotionOutcome.PROMOTED


def test_exact_promotion_authorization_can_promote():
    record = _pending()
    validation = _pass_validation(record)
    verified = StateTransitionEngine().transition(
        record,
        EvidenceStatus.VERIFIED,
        actor="validator",
        authority=AuthorityRight.VALIDATION_RIGHT,
        reason="VALIDATION_PASS",
        validation=validation,
        transition_id="TR-003",
    ).record

    registry = AuthorityRegistry(
        [
            AuthorityGrant(
                actor="operator",
                right=AuthorityRight.PROMOTION_RIGHT,
                targets=frozenset({PromotionTarget.KNOWLEDGE_GRAPH}),
            )
        ]
    )
    auth = PromotionAuthorization(
        authorization_id="PAUTH-001",
        evidence_id="EV-001",
        validation_id="VAL-001",
        target=PromotionTarget.KNOWLEDGE_GRAPH,
        scope={"claim_scope": "bounded_claim_only"},
        authorized_by="operator",
        authority_basis=AuthorityRight.PROMOTION_RIGHT,
        decision=PromotionDecisionValue.AUTHORIZE,
        issued_at="2026-08-22T17:59:00Z",
        valid_from="2026-08-22T17:59:00Z",
        valid_until="2026-08-22T19:00:00Z",
    )
    promotion = PromotionEngine().evaluate(
        verified,
        validation,
        auth,
        registry,
        PromotionContext(
            requested_target=PromotionTarget.KNOWLEDGE_GRAPH,
            requested_scope={"claim_scope": "bounded_claim_only"},
            validated_scope={"claim_scope": "bounded_claim_only"},
            current_fingerprint_hash="abc",
            now="2026-08-22T18:00:00Z",
        ),
        promotion_id="PROM-001",
    )
    assert promotion.result == PromotionOutcome.PROMOTED

    promoted = StateTransitionEngine().transition(
        verified,
        EvidenceStatus.PROMOTED,
        actor="operator",
        authority=AuthorityRight.PROMOTION_RIGHT,
        reason="EXPLICIT_PROMOTION_AUTHORIZATION",
        promotion=promotion,
        transition_id="TR-004",
    )
    assert promoted.record.status == EvidenceStatus.PROMOTED


def test_wrong_target_blocks_promotion():
    record = _pending()
    validation = _pass_validation(record)
    verified = StateTransitionEngine().transition(
        record,
        EvidenceStatus.VERIFIED,
        actor="validator",
        authority=AuthorityRight.VALIDATION_RIGHT,
        reason="VALIDATION_PASS",
        validation=validation,
        transition_id="TR-005",
    ).record

    registry = AuthorityRegistry(
        [
            AuthorityGrant(
                actor="operator",
                right=AuthorityRight.PROMOTION_RIGHT,
                targets=frozenset({PromotionTarget.KNOWLEDGE_GRAPH}),
            )
        ]
    )
    auth = PromotionAuthorization(
        authorization_id="PAUTH-002",
        evidence_id="EV-001",
        validation_id="VAL-001",
        target=PromotionTarget.KNOWLEDGE_GRAPH,
        scope={"claim_scope": "bounded_claim_only"},
        authorized_by="operator",
        authority_basis=AuthorityRight.PROMOTION_RIGHT,
        decision=PromotionDecisionValue.AUTHORIZE,
        issued_at="2026-08-22T17:59:00Z",
    )
    promotion = PromotionEngine().evaluate(
        verified,
        validation,
        auth,
        registry,
        PromotionContext(
            requested_target=PromotionTarget.AUTOMATION_INPUT,
            requested_scope={"claim_scope": "bounded_claim_only"},
            validated_scope={"claim_scope": "bounded_claim_only"},
            current_fingerprint_hash="abc",
            now="2026-08-22T18:00:00Z",
        ),
        promotion_id="PROM-WRONG-TARGET",
    )
    assert promotion.result == PromotionOutcome.BLOCKED
