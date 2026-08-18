"""ION PEL Replay Comparability v0.1 deterministic evaluator.

Implements only the frozen layered contract:

    evidence admission
    -> recorded surface compatibility
    -> replay lineage
    -> replay-set admission
    -> set completeness

No filesystem I/O, network access, provider execution, stability analysis,
semantic truth, gold evaluation, or model-reliability inference.
"""

from __future__ import annotations

from .canonical_task_binding import compute_canonical_task_binding_id
from .canonical_task_binding_models import CanonicalTaskBindingPersistenceResult, CanonicalTaskBindingV0_1
from .canonical_task_identity import compute_canonical_task_sha256

from .replay_comparability_models import (
    CONTEXT_FLAGS,
    RECORDED_SURFACE_SCOPE_ID,
    REPLAY_COMPARABILITY_CONTRACT_ID,
    REPLAY_COMPARABILITY_CONTRACT_VERSION,
    EvidenceAdmission,
    ReplayComparabilityAssessmentV0_1,
    ReplaySetContext,
    SurfaceFieldFinding,
)
from .replay_execution_descriptor_models import (
    REPLAY_EXECUTION_DESCRIPTOR_PERSISTENCE_RESULT_STATUSES,
    REPLAY_EXECUTION_DESCRIPTOR_STATUSES,
    ReplayExecutionDescriptor,
    ReplayExecutionDescriptorPersistenceResult,
)
from .validation import (
    PELValidationError,
    validate_canonical_task_binding_persistence_result,
    validate_canonical_task_binding_v0_1,
    validate_execution_plan,
    validate_task_spec,
    validate_replay_execution_descriptor,
    validate_replay_execution_descriptor_persistence_result,
)

__all__ = ["evaluate_replay_comparability"]


_SURFACE_FIELDS = (
    "task_sha256",
    "prompt_sha256",
    "model_family",
    "model_identifier",
    "adapter_id",
    "adapter_version",
    "provider_settings",
    "session_policy",
)

_SURFACE_REASON_BY_FIELD = {
    "task_sha256": "TASK_HASH_MISMATCH",
    "prompt_sha256": "PROMPT_HASH_MISMATCH",
    "model_family": "MODEL_FAMILY_MISMATCH",
    "model_identifier": "MODEL_IDENTIFIER_MISMATCH",
    "adapter_id": "ADAPTER_ID_MISMATCH",
    "adapter_version": "ADAPTER_VERSION_MISMATCH",
    "provider_settings": "PROVIDER_SETTINGS_MISMATCH",
    "session_policy": "SESSION_POLICY_MISMATCH",
}


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _admit_descriptor(
    descriptor: ReplayExecutionDescriptor | None,
    persistence: ReplayExecutionDescriptorPersistenceResult | None,
) -> tuple[EvidenceAdmission, tuple[str, ...]]:
    reasons: list[str] = []

    if not isinstance(descriptor, ReplayExecutionDescriptor):
        return (
            EvidenceAdmission(
                descriptor_id=None,
                run_id=None,
                admission="UNKNOWN",
                verification_basis=None,
            ),
            ("DESCRIPTOR_INVALID",),
        )

    if descriptor.status not in REPLAY_EXECUTION_DESCRIPTOR_STATUSES:
        return (
            EvidenceAdmission(
                descriptor_id=descriptor.descriptor_id,
                run_id=descriptor.run_id,
                admission="UNKNOWN",
                verification_basis=None,
            ),
            ("DESCRIPTOR_STATUS_INVALID",),
        )

    try:
        validate_replay_execution_descriptor(descriptor.to_dict())
    except (PELValidationError, TypeError, ValueError):
        return (
            EvidenceAdmission(
                descriptor_id=descriptor.descriptor_id,
                run_id=descriptor.run_id,
                admission="UNKNOWN",
                verification_basis=None,
            ),
            ("DESCRIPTOR_INVALID",),
        )

    if not isinstance(
        persistence,
        ReplayExecutionDescriptorPersistenceResult,
    ):
        return (
            EvidenceAdmission(
                descriptor_id=descriptor.descriptor_id,
                run_id=descriptor.run_id,
                admission="UNKNOWN",
                verification_basis=None,
            ),
            ("DESCRIPTOR_EVIDENCE_UNVERIFIED",),
        )

    try:
        validate_replay_execution_descriptor_persistence_result(
            persistence.to_dict()
        )
    except (PELValidationError, TypeError, ValueError):
        return (
            EvidenceAdmission(
                descriptor_id=descriptor.descriptor_id,
                run_id=descriptor.run_id,
                admission="UNKNOWN",
                verification_basis=None,
            ),
            ("DESCRIPTOR_EVIDENCE_UNVERIFIED",),
        )

    if (
        persistence.status
        not in REPLAY_EXECUTION_DESCRIPTOR_PERSISTENCE_RESULT_STATUSES
    ):
        return (
            EvidenceAdmission(
                descriptor_id=descriptor.descriptor_id,
                run_id=descriptor.run_id,
                admission="UNKNOWN",
                verification_basis=None,
            ),
            ("DESCRIPTOR_EVIDENCE_UNVERIFIED",),
        )

    if persistence.descriptor_id != descriptor.descriptor_id:
        return (
            EvidenceAdmission(
                descriptor_id=descriptor.descriptor_id,
                run_id=descriptor.run_id,
                admission="UNKNOWN",
                verification_basis=None,
            ),
            ("DESCRIPTOR_VERIFICATION_IDENTITY_MISMATCH",),
        )

    if persistence.readback_verified is not True:
        return (
            EvidenceAdmission(
                descriptor_id=descriptor.descriptor_id,
                run_id=descriptor.run_id,
                admission="UNKNOWN",
                verification_basis=None,
            ),
            ("DESCRIPTOR_EVIDENCE_UNVERIFIED",),
        )

    verification_basis = (
        "ReplayExecutionDescriptorPersistenceResult:"
        f"{persistence.descriptor_bytes_sha256}"
    )

    return (
        EvidenceAdmission(
            descriptor_id=descriptor.descriptor_id,
            run_id=descriptor.run_id,
            admission="ADMITTED",
            verification_basis=verification_basis,
        ),
        tuple(reasons),
    )


def _verify_canonical_task_provenance(
    *,
    descriptor: ReplayExecutionDescriptor,
    task_spec,
    binding: CanonicalTaskBindingV0_1 | None,
    persistence: CanonicalTaskBindingPersistenceResult | None,
) -> tuple[str, tuple[str, ...]]:
    if task_spec is None:
        return "UNKNOWN", ("INSUFFICIENT_EVIDENCE",)
    try:
        validate_task_spec(task_spec.to_dict())
    except (PELValidationError, TypeError, ValueError):
        return "UNKNOWN", ("INSUFFICIENT_EVIDENCE",)
    if task_spec.status != "FROZEN":
        return "UNKNOWN", ("TASK_SPEC_NOT_FROZEN",)
    if not isinstance(binding, CanonicalTaskBindingV0_1):
        return "UNKNOWN", ("CANONICAL_TASK_BINDING_UNAVAILABLE",)
    if not isinstance(persistence, CanonicalTaskBindingPersistenceResult):
        return "UNKNOWN", ("CANONICAL_TASK_BINDING_UNVERIFIED",)
    try:
        validate_canonical_task_binding_v0_1(binding.to_dict())
        validate_canonical_task_binding_persistence_result(persistence.to_dict())
    except (PELValidationError, TypeError, ValueError):
        return "UNKNOWN", ("CANONICAL_TASK_BINDING_UNVERIFIED",)
    if persistence.binding_id != binding.binding_id:
        return "UNKNOWN", ("CANONICAL_TASK_BINDING_VERIFICATION_IDENTITY_MISMATCH",)
    if persistence.readback_verified is not True:
        return "UNKNOWN", ("CANONICAL_TASK_BINDING_UNVERIFIED",)
    expected_binding_id = compute_canonical_task_binding_id(run_id=descriptor.run_id)
    if binding.binding_id != expected_binding_id:
        return "UNKNOWN", ("CANONICAL_TASK_BINDING_VERIFICATION_IDENTITY_MISMATCH",)
    if binding.run_id != descriptor.run_id:
        return "NOT_ADMISSIBLE", ("CANONICAL_TASK_BINDING_RUN_MISMATCH",)
    if binding.task_id != task_spec.task_id:
        return "NOT_ADMISSIBLE", ("CANONICAL_TASK_BINDING_TASK_ID_MISMATCH",)
    expected_task_sha256 = compute_canonical_task_sha256(task_spec)
    if binding.canonical_task_sha256 != expected_task_sha256 or descriptor.task_sha256 != expected_task_sha256:
        return "NOT_ADMISSIBLE", ("CANONICAL_TASK_DIGEST_MISMATCH",)
    if binding.prompt_sha256 != task_spec.prompt_sha256 or descriptor.prompt_sha256 != task_spec.prompt_sha256:
        return "NOT_ADMISSIBLE", ("CANONICAL_TASK_PROMPT_MISMATCH",)
    return "ADMITTED", ()

def _surface_value(
    descriptor: ReplayExecutionDescriptor,
    field: str,
):
    value = getattr(descriptor, field)
    if field == "provider_settings":
        return dict(value)
    return value


def _compare_surface(
    descriptor_a: ReplayExecutionDescriptor,
    descriptor_b: ReplayExecutionDescriptor,
) -> tuple[
    tuple[SurfaceFieldFinding, ...],
    str,
    tuple[str, ...],
]:
    findings: list[SurfaceFieldFinding] = []
    reasons: list[str] = []
    any_difference = False

    for field in _SURFACE_FIELDS:
        value_a = _surface_value(descriptor_a, field)
        value_b = _surface_value(descriptor_b, field)

        if value_a == value_b:
            findings.append(
                SurfaceFieldFinding(
                    field=field,
                    result="SAME",
                )
            )
            continue

        any_difference = True
        reason = _SURFACE_REASON_BY_FIELD[field]
        _append_unique(reasons, reason)
        findings.append(
            SurfaceFieldFinding(
                field=field,
                result="DIFFERENT",
                reason_code=reason,
            )
        )

    result = (
        "SURFACE_INCOMPATIBLE"
        if any_difference
        else "SURFACE_COMPATIBLE"
    )

    return tuple(findings), result, tuple(reasons)


def _compare_lineage(
    descriptor_a: ReplayExecutionDescriptor,
    descriptor_b: ReplayExecutionDescriptor,
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    findings: list[str] = []
    reasons: list[str] = []

    plan_same = descriptor_a.plan_id == descriptor_b.plan_id
    condition_same = (
        descriptor_a.condition_id == descriptor_b.condition_id
    )
    replay_index_same = (
        descriptor_a.replay_index == descriptor_b.replay_index
    )

    findings.append(
        "PLAN_ID_SAME" if plan_same else "PLAN_ID_DIFFERENT"
    )
    findings.append(
        "CONDITION_ID_SAME"
        if condition_same
        else "CONDITION_ID_DIFFERENT"
    )
    findings.append(
        "REPLAY_INDEX_SAME"
        if replay_index_same
        else "REPLAY_INDEX_DIFFERENT"
    )

    slot_conflict = (
        plan_same
        and condition_same
        and replay_index_same
        and descriptor_a.run_id != descriptor_b.run_id
    )

    if slot_conflict:
        findings.append("REPLAY_SLOT_DUPLICATE_OR_CONFLICT")
        reasons.append("REPLAY_SLOT_DUPLICATE_OR_CONFLICT")
        return tuple(findings), "LINEAGE_CONFLICT", tuple(reasons)

    if not plan_same:
        reasons.append("CROSS_PLAN")
        if not condition_same:
            reasons.append("CROSS_CONDITION")
        return tuple(findings), "CROSS_PLAN", tuple(reasons)

    if not condition_same:
        reasons.append("CROSS_CONDITION")
        return tuple(findings), "CROSS_CONDITION", tuple(reasons)

    return tuple(findings), "LINEAGE_COMPATIBLE", tuple(reasons)


def _resolve_replay_set(
    *,
    descriptor_a: ReplayExecutionDescriptor,
    descriptor_b: ReplayExecutionDescriptor,
    surface_result: str,
    lineage_result: str,
    context: ReplaySetContext | None,
) -> tuple[str, tuple[str, ...], int | None]:
    reasons: list[str] = []

    if surface_result == "UNKNOWN" or lineage_result == "UNKNOWN":
        return "UNKNOWN", tuple(reasons), None

    if surface_result == "SURFACE_INCOMPATIBLE":
        return "REPLAY_SET_NOT_ADMISSIBLE", tuple(reasons), None

    if lineage_result in (
        "LINEAGE_CONFLICT",
        "CROSS_PLAN",
        "CROSS_CONDITION",
    ):
        return "REPLAY_SET_NOT_ADMISSIBLE", tuple(reasons), None

    # Governing context must be structurally supplied.
    # Caller-controlled booleans are not authority.
    if context is None or context.execution_plan is None:
        return (
            "UNKNOWN",
            (
                "PLAN_CONTEXT_UNAVAILABLE",
                "CONDITION_CONTEXT_UNAVAILABLE",
                "EXPECTED_REPLAY_SET_IDENTITY_UNAVAILABLE",
                "EXPECTED_REPLAYS_UNAVAILABLE",
            ),
            None,
        )

    plan = context.execution_plan

    try:
        validate_execution_plan(plan.to_dict())
    except (PELValidationError, TypeError, ValueError):
        return "UNKNOWN", ("INSUFFICIENT_EVIDENCE",), None

    # v0.1 governing-source policy:
    # DRAFT is structurally valid but not authoritative enough.
    if plan.status not in ("FROZEN", "CLOSED"):
        return "UNKNOWN", ("INSUFFICIENT_EVIDENCE",), None

    # E-05 canonical task authority.
    task_spec = context.task_spec
    if task_spec is None:
        return "UNKNOWN", ("INSUFFICIENT_EVIDENCE",), None

    try:
        validate_task_spec(task_spec.to_dict())
    except (PELValidationError, TypeError, ValueError):
        return "UNKNOWN", ("INSUFFICIENT_EVIDENCE",), None

    if task_spec.status != "FROZEN":
        return "UNKNOWN", ("TASK_SPEC_NOT_FROZEN",), None

    if plan.task_id != task_spec.task_id:
        return (
            "REPLAY_SET_NOT_ADMISSIBLE",
            ("EXECUTION_PLAN_TASK_ID_MISMATCH",),
            None,
        )

    def task_provenance_for(descriptor):
        expected_binding_id = compute_canonical_task_binding_id(
            run_id=descriptor.run_id
        )
        candidates = [
            item
            for item in context.received_task_binding_evidence
            if item[0] is not None
            and (
                item[0].binding_id == expected_binding_id
                or item[0].run_id == descriptor.run_id
            )
        ]

        if len(candidates) > 1:
            return "UNKNOWN", ("INSUFFICIENT_EVIDENCE",)

        if not candidates:
            return _verify_canonical_task_provenance(
                descriptor=descriptor,
                task_spec=task_spec,
                binding=None,
                persistence=None,
            )

        binding, persistence = candidates[0]
        return _verify_canonical_task_provenance(
            descriptor=descriptor,
            task_spec=task_spec,
            binding=binding,
            persistence=persistence,
        )

    # Bind both directly compared descriptors to this plan.
    if (
        descriptor_a.plan_id != plan.plan_id
        or descriptor_b.plan_id != plan.plan_id
    ):
        return "REPLAY_SET_NOT_ADMISSIBLE", ("CROSS_PLAN",), None

    # The pair must resolve to one embedded governing condition.
    if descriptor_a.condition_id != descriptor_b.condition_id:
        return "REPLAY_SET_NOT_ADMISSIBLE", ("CROSS_CONDITION",), None

    governing_condition = next(
        (
            condition
            for condition in plan.conditions
            if condition.condition_id == descriptor_a.condition_id
        ),
        None,
    )

    if governing_condition is None:
        return "REPLAY_SET_NOT_ADMISSIBLE", ("CROSS_CONDITION",), None

    # Bind the recorded execution surface to the governing condition.
    for descriptor in (descriptor_a, descriptor_b):
        for field in (
            "model_family",
            "model_identifier",
            "adapter_id",
            "adapter_version",
        ):
            if getattr(descriptor, field) != getattr(governing_condition, field):
                return (
                    "REPLAY_SET_NOT_ADMISSIBLE",
                    (_SURFACE_REASON_BY_FIELD[field],),
                    None,
                )

        if (
            dict(descriptor.provider_settings)
            != dict(governing_condition.provider_settings)
        ):
            return (
                "REPLAY_SET_NOT_ADMISSIBLE",
                ("PROVIDER_SETTINGS_MISMATCH",),
                None,
            )

        if descriptor.session_policy != plan.session_policy:
            return (
                "REPLAY_SET_NOT_ADMISSIBLE",
                ("SESSION_POLICY_MISMATCH",),
                None,
            )

    for descriptor in (descriptor_a, descriptor_b):
        provenance_result, provenance_reasons = task_provenance_for(descriptor)

        if provenance_result == "UNKNOWN":
            return "UNKNOWN", provenance_reasons, None

        if provenance_result == "NOT_ADMISSIBLE":
            return "REPLAY_SET_NOT_ADMISSIBLE", provenance_reasons, None

    # Every enumerated replay-set member must itself have admitted evidence,
    # match the pair's frozen recorded surface, and belong to this
    # plan/condition lineage.
    for descriptor, persistence in context.received_evidence:
        admission, admission_reasons = _admit_descriptor(
            descriptor,
            persistence,
        )

        if admission.admission != "ADMITTED":
            for reason in admission_reasons:
                _append_unique(reasons, reason)

            if not admission_reasons:
                _append_unique(reasons, "INSUFFICIENT_EVIDENCE")

            return "UNKNOWN", tuple(reasons), None

        assert isinstance(descriptor, ReplayExecutionDescriptor)

        _member_findings, member_surface_result, member_surface_reasons = (
            _compare_surface(descriptor_a, descriptor)
        )

        if member_surface_result == "UNKNOWN":
            for reason in member_surface_reasons:
                _append_unique(reasons, reason)

            if not member_surface_reasons:
                _append_unique(reasons, "INSUFFICIENT_EVIDENCE")

            return "UNKNOWN", tuple(reasons), None

        if member_surface_result == "SURFACE_INCOMPATIBLE":
            for reason in member_surface_reasons:
                _append_unique(reasons, reason)

            return "REPLAY_SET_NOT_ADMISSIBLE", tuple(reasons), None

        if descriptor.plan_id != plan.plan_id:
            return "REPLAY_SET_NOT_ADMISSIBLE", ("CROSS_PLAN",), None

        if descriptor.condition_id != governing_condition.condition_id:
            return "REPLAY_SET_NOT_ADMISSIBLE", ("CROSS_CONDITION",), None

        member_provenance_result, member_provenance_reasons = (
            task_provenance_for(descriptor)
        )

        if member_provenance_result == "UNKNOWN":
            return "UNKNOWN", member_provenance_reasons, None

        if member_provenance_result == "NOT_ADMISSIBLE":
            return (
                "REPLAY_SET_NOT_ADMISSIBLE",
                member_provenance_reasons,
                None,
            )

    # expected_replays is derived from the governing ExecutionCondition,
    # never from a caller-supplied scalar.
    return (
        "REPLAY_SET_ADMISSIBLE",
        (),
        governing_condition.expected_replays,
    )



def _resolve_completeness(
    *,
    descriptor_a: ReplayExecutionDescriptor,
    descriptor_b: ReplayExecutionDescriptor,
    lineage_result: str,
    replay_set_result: str,
    context: ReplaySetContext | None,
    expected_replays: int | None,
) -> tuple[str, tuple[str, ...]]:
    if lineage_result == "LINEAGE_CONFLICT":
        return "SET_CONFLICTED", ("REPLAY_SLOT_CONFLICT",)

    if replay_set_result != "REPLAY_SET_ADMISSIBLE":
        return "UNKNOWN", ()

    if context is None:
        return "UNKNOWN", ("EXPECTED_REPLAYS_UNAVAILABLE",)

    if expected_replays is None:
        return "UNKNOWN", ("EXPECTED_REPLAYS_UNAVAILABLE",)

    admitted_descriptors: list[ReplayExecutionDescriptor] = []
    admission_reasons: list[str] = []

    for descriptor, persistence in context.received_evidence:
        admission, reasons = _admit_descriptor(
            descriptor,
            persistence,
        )

        if admission.admission != "ADMITTED":
            for reason in reasons:
                _append_unique(admission_reasons, reason)

            if not reasons:
                _append_unique(
                    admission_reasons,
                    "INSUFFICIENT_EVIDENCE",
                )

            return "UNKNOWN", tuple(admission_reasons)

        assert isinstance(descriptor, ReplayExecutionDescriptor)
        admitted_descriptors.append(descriptor)

    slot_runs: dict[tuple[str, str, int], str] = {}

    for descriptor in (descriptor_a, descriptor_b):
        key = (
            descriptor.plan_id,
            descriptor.condition_id,
            descriptor.replay_index,
        )
        existing_run = slot_runs.get(key)

        if existing_run is not None and existing_run != descriptor.run_id:
            return "SET_CONFLICTED", ("REPLAY_SLOT_CONFLICT",)

        slot_runs[key] = descriptor.run_id

    received_indices: set[int] = set()

    for descriptor in admitted_descriptors:
        key = (
            descriptor.plan_id,
            descriptor.condition_id,
            descriptor.replay_index,
        )
        existing_run = slot_runs.get(key)

        if existing_run is not None and existing_run != descriptor.run_id:
            return "SET_CONFLICTED", ("REPLAY_SLOT_CONFLICT",)

        slot_runs[key] = descriptor.run_id
        received_indices.add(descriptor.replay_index)

    required_pair_indices = {
        descriptor_a.replay_index,
        descriptor_b.replay_index,
    }

    if not required_pair_indices.issubset(received_indices):
        return "SET_INCOMPLETE", ("MISSING_REPLAY_SLOT",)

    received_count = len(received_indices)

    if received_count < expected_replays:
        return "SET_INCOMPLETE", ("MISSING_REPLAY_SLOT",)

    if received_count > expected_replays:
        return "SET_CONFLICTED", ("REPLAY_SLOT_CONFLICT",)

    return "SET_COMPLETE", ()



def evaluate_replay_comparability(
    *,
    descriptor_a: ReplayExecutionDescriptor | None,
    persistence_a: ReplayExecutionDescriptorPersistenceResult | None,
    descriptor_b: ReplayExecutionDescriptor | None,
    persistence_b: ReplayExecutionDescriptorPersistenceResult | None,
    replay_set_context: ReplaySetContext | None = None,
) -> ReplayComparabilityAssessmentV0_1:
    """Evaluate the frozen Replay Comparability v0.1 contract.

    The function is pure and side-effect free. It evaluates only the
    supplied preserved evidence and explicit replay-set context.
    """

    reason_codes: list[str] = []

    evidence_a, admission_reasons_a = _admit_descriptor(
        descriptor_a,
        persistence_a,
    )
    evidence_b, admission_reasons_b = _admit_descriptor(
        descriptor_b,
        persistence_b,
    )

    for reason in admission_reasons_a + admission_reasons_b:
        _append_unique(reason_codes, reason)

    both_admitted = (
        evidence_a.admission == "ADMITTED"
        and evidence_b.admission == "ADMITTED"
    )

    context_flags = [
        "FULL_CONTEXT_NOT_ESTABLISHED",
        "ACTUAL_RUNTIME_CONDITION_NOT_ESTABLISHED",
        "TEMPORAL_COMPARABILITY_NOT_ESTABLISHED",
        "CAPTURE_MODE_RELEVANCE_NOT_ESTABLISHED",
        "FULL_PLAN_EQUIVALENCE_NOT_ESTABLISHED",
    ]

    if not both_admitted:
        return ReplayComparabilityAssessmentV0_1(
            contract_id=REPLAY_COMPARABILITY_CONTRACT_ID,
            contract_version=REPLAY_COMPARABILITY_CONTRACT_VERSION,
            surface_scope_id=RECORDED_SURFACE_SCOPE_ID,
            evidence_a=evidence_a,
            evidence_b=evidence_b,
            surface_comparison_started=False,
            surface_field_findings=(),
            surface_result="UNKNOWN",
            lineage_findings=(),
            lineage_result="UNKNOWN",
            replay_set_result="UNKNOWN",
            set_completeness_result="UNKNOWN",
            reason_codes=tuple(reason_codes),
            context_flags=tuple(context_flags),
            full_execution_context_established=False,
            actual_runtime_condition_established=False,
            cross_plan_admission_established=False,
            temporal_comparability_established=False,
        )

    assert descriptor_a is not None
    assert descriptor_b is not None

    surface_findings, surface_result, surface_reasons = (
        _compare_surface(descriptor_a, descriptor_b)
    )
    for reason in surface_reasons:
        _append_unique(reason_codes, reason)

    lineage_findings, lineage_result, lineage_reasons = (
        _compare_lineage(descriptor_a, descriptor_b)
    )
    for reason in lineage_reasons:
        _append_unique(reason_codes, reason)

    if lineage_result == "CROSS_PLAN":
        context_flags.append("CROSS_PLAN_ADMISSION_NOT_ESTABLISHED")

    (
        replay_set_result,
        replay_set_reasons,
        expected_replays,
    ) = _resolve_replay_set(
        descriptor_a=descriptor_a,
        descriptor_b=descriptor_b,
        surface_result=surface_result,
        lineage_result=lineage_result,
        context=replay_set_context,
    )
    for reason in replay_set_reasons:
        _append_unique(reason_codes, reason)

    completeness_result, completeness_reasons = _resolve_completeness(
        descriptor_a=descriptor_a,
        descriptor_b=descriptor_b,
        lineage_result=lineage_result,
        replay_set_result=replay_set_result,
        context=replay_set_context,
        expected_replays=expected_replays,
    )
    for reason in completeness_reasons:
        _append_unique(reason_codes, reason)

    return ReplayComparabilityAssessmentV0_1(
        contract_id=REPLAY_COMPARABILITY_CONTRACT_ID,
        contract_version=REPLAY_COMPARABILITY_CONTRACT_VERSION,
        surface_scope_id=RECORDED_SURFACE_SCOPE_ID,
        evidence_a=evidence_a,
        evidence_b=evidence_b,
        surface_comparison_started=True,
        surface_field_findings=surface_findings,
        surface_result=surface_result,
        lineage_findings=lineage_findings,
        lineage_result=lineage_result,
        replay_set_result=replay_set_result,
        set_completeness_result=completeness_result,
        reason_codes=tuple(reason_codes),
        context_flags=tuple(context_flags),
        full_execution_context_established=False,
        actual_runtime_condition_established=False,
        cross_plan_admission_established=False,
        temporal_comparability_established=False,
    )