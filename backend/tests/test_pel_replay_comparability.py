"""ION PEL Replay Comparability v0.1 deterministic evaluator tests.

Bounded to the frozen hybrid/tiered contract:

    evidence admission
    -> recorded surface compatibility
    -> replay lineage
    -> replay-set admission
    -> set completeness

No stability analysis is tested or implied.
"""

from __future__ import annotations

import dataclasses

# E05_CANONICAL_TASK_FIXTURE_v0_1
from pel.canonical_task_binding import compute_canonical_task_binding_id
from pel.canonical_task_binding_models import (
    CanonicalTaskBindingPersistenceResult,
    CanonicalTaskBindingV0_1,
)
from pel.canonical_task_identity import (
    CANONICAL_TASK_IDENTITY_CONTRACT_ID,
    CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID,
    compute_canonical_task_sha256,
)
from pel.task_freeze import freeze_task
from pel.replay_comparability_evaluator import evaluate_replay_comparability
from pel.replay_comparability_models import ReplaySetContext
from pel.models import ExecutionCondition, ExecutionPlan
from pel.replay_execution_descriptor_models import (
    ReplayExecutionDescriptor,
    ReplayExecutionDescriptorPersistenceResult,
)


SHA_A = "a" * 64
SHA_B = "b" * 64

TASK_SPEC = freeze_task(
    task_id="task-1",
    task_version="1",
    task_class="replay-comparability-test",
    semantic_boundary=None,
    bundle_filename="bundle.txt",
    bundle_bytes=b"e05-comparator-bundle",
    prompt_id="prompt-1",
    prompt_bytes=b"e05-comparator-prompt",
    output_contract_id="test-output-contract",
    created_at="2026-08-17T00:00:00+00:00",
    provenance=("e05-test-fixture",),
)
CANONICAL_TASK_SHA = compute_canonical_task_sha256(TASK_SPEC)
SHA_C = CANONICAL_TASK_SHA
SHA_D = TASK_SPEC.prompt_sha256


def _descriptor(
    *,
    descriptor_id=SHA_A,
    run_id="run-a",
    task_sha256=SHA_C,
    prompt_sha256=SHA_D,
    condition_id="cond-1",
    model_family="family-x",
    model_identifier="model-x",
    adapter_id="adapter-1",
    adapter_version="1.0.0",
    provider_settings=(("temperature", "0.0"), ("top_p", "1.0")),
    replay_index=0,
    plan_id="plan-1",
    session_policy="strict",
    persisted_at="2026-08-17T00:00:00+00:00",
):
    return ReplayExecutionDescriptor(
        descriptor_id=descriptor_id,
        run_id=run_id,
        task_sha256=task_sha256,
        prompt_sha256=prompt_sha256,
        condition_id=condition_id,
        model_family=model_family,
        model_identifier=model_identifier,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        provider_settings=provider_settings,
        replay_index=replay_index,
        plan_id=plan_id,
        session_policy=session_policy,
        persisted_at=persisted_at,
        status="EXECUTION_DESCRIPTOR_FROZEN",
    )


def _persistence(descriptor, *, readback_verified=True):
    return ReplayExecutionDescriptorPersistenceResult(
        descriptor_id=descriptor.descriptor_id,
        descriptor_bytes_sha256=SHA_B,
        readback_verified=readback_verified,
        status="EXECUTION_DESCRIPTOR_PERSISTED_VERIFIED",
    )


def _binding_evidence(descriptor):
    binding = CanonicalTaskBindingV0_1(
        binding_id=compute_canonical_task_binding_id(
            run_id=descriptor.run_id,
        ),
        run_id=descriptor.run_id,
        task_id=TASK_SPEC.task_id,
        canonical_task_sha256=CANONICAL_TASK_SHA,
        prompt_sha256=TASK_SPEC.prompt_sha256,
        identity_contract_id=CANONICAL_TASK_IDENTITY_CONTRACT_ID,
        serialization_profile_id=(
            CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID
        ),
        status="CANONICAL_TASK_BINDING_FROZEN",
    )
    persistence = CanonicalTaskBindingPersistenceResult(
        binding_id=binding.binding_id,
        binding_bytes_sha256=SHA_B,
        readback_verified=True,
        status="CANONICAL_TASK_BINDING_PERSISTED_VERIFIED",
    )
    return binding, persistence


def _replace_binding_pair(context, run_id, pair):
    replaced = False
    items = []
    for binding, persistence in context.received_task_binding_evidence:
        if not replaced and binding is not None and binding.run_id == run_id:
            items.append(pair)
            replaced = True
        else:
            items.append((binding, persistence))
    if not replaced:
        raise AssertionError(f"binding evidence not found for {run_id}")
    return dataclasses.replace(
        context,
        received_task_binding_evidence=tuple(items),
    )


def _pair(**b_overrides):
    a = _descriptor(
        descriptor_id=SHA_A,
        run_id="run-a",
        replay_index=0,
    )
    fields = dict(
        descriptor_id=SHA_B,
        run_id="run-b",
        replay_index=1,
    )
    fields.update(b_overrides)
    b = _descriptor(**fields)
    return a, b


def _execution_plan_for(
    anchor,
    *,
    expected_replays=2,
    status="FROZEN",
):
    condition = ExecutionCondition(
        condition_id=anchor.condition_id,
        model_family=anchor.model_family,
        model_identifier=anchor.model_identifier,
        adapter_id=anchor.adapter_id,
        adapter_version=anchor.adapter_version,
        expected_replays=expected_replays,
        provider_settings=anchor.provider_settings,
    )

    return ExecutionPlan(
        plan_id=anchor.plan_id,
        task_id="task-1",
        conditions=(condition,),
        session_policy=anchor.session_policy,
        execution_order=(condition.condition_id,),
        stop_rule="NONE",
        gold_access_policy="NO_GOLD",
        status=status,
    )


def _context_for(
    a,
    b,
    *,
    expected_replays=2,
    received_replay_indices=(0, 1),
    omit_plan=False,
):
    evidence = []
    used_a = False
    used_b = False
    extra_ordinal = 0

    for replay_index in received_replay_indices:
        if replay_index == a.replay_index and not used_a:
            descriptor = a
            used_a = True
        elif replay_index == b.replay_index and not used_b:
            descriptor = b
            used_b = True
        else:
            extra_ordinal += 1
            descriptor = dataclasses.replace(
                a,
                descriptor_id=f"{extra_ordinal:064x}",
                run_id=f"context-extra-{extra_ordinal}",
                replay_index=replay_index,
            )

        evidence.append((descriptor, _persistence(descriptor)))

    binding_descriptors = []
    seen_run_ids = set()
    for descriptor in (a, b, *(item[0] for item in evidence)):
        if descriptor.run_id not in seen_run_ids:
            seen_run_ids.add(descriptor.run_id)
            binding_descriptors.append(descriptor)

    return ReplaySetContext(
        execution_plan=(
            None
            if omit_plan
            else _execution_plan_for(
                a,
                expected_replays=expected_replays,
            )
        ),
        received_evidence=tuple(evidence),
        task_spec=TASK_SPEC,
        received_task_binding_evidence=tuple(
            _binding_evidence(descriptor)
            for descriptor in binding_descriptors
        ),
    )



def _evaluate(a, b, *, context=None, persistence_a=None, persistence_b=None):
    return evaluate_replay_comparability(
        descriptor_a=a,
        persistence_a=_persistence(a) if persistence_a is None else persistence_a,
        descriptor_b=b,
        persistence_b=_persistence(b) if persistence_b is None else persistence_b,
        replay_set_context=context,
    )


# ---------------------------------------------------------------------------
# T01 admitted identical recorded surface
# ---------------------------------------------------------------------------

def test_t01_admitted_identical_recorded_surface():
    a, b = _pair()
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.evidence_a.admission == "ADMITTED"
    assert result.evidence_b.admission == "ADMITTED"
    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "LINEAGE_COMPATIBLE"
    assert result.replay_set_result == "REPLAY_SET_ADMISSIBLE"
    assert result.set_completeness_result == "SET_COMPLETE"


# ---------------------------------------------------------------------------
# T02 prompt hash mismatch
# ---------------------------------------------------------------------------

def test_t02_prompt_hash_mismatch():
    a, b = _pair(prompt_sha256="e" * 64)
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_INCOMPATIBLE"
    assert "PROMPT_HASH_MISMATCH" in result.reason_codes
    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"


# ---------------------------------------------------------------------------
# T03 model identifier mismatch
# ---------------------------------------------------------------------------

def test_t03_model_identifier_mismatch():
    a, b = _pair(model_identifier="model-y")
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_INCOMPATIBLE"
    assert "MODEL_IDENTIFIER_MISMATCH" in result.reason_codes


# ---------------------------------------------------------------------------
# T04 provider settings mismatch
# ---------------------------------------------------------------------------

def test_t04_provider_settings_mismatch():
    a, b = _pair(
        provider_settings=(("temperature", "0.7"), ("top_p", "1.0"))
    )
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_INCOMPATIBLE"
    assert "PROVIDER_SETTINGS_MISMATCH" in result.reason_codes


# ---------------------------------------------------------------------------
# T05 session policy mismatch
# ---------------------------------------------------------------------------

def test_t05_session_policy_mismatch():
    a, b = _pair(session_policy="loose")
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_INCOMPATIBLE"
    assert "SESSION_POLICY_MISMATCH" in result.reason_codes


# ---------------------------------------------------------------------------
# T06 unverified descriptor evidence
# ---------------------------------------------------------------------------

def test_t06_unverified_descriptor_evidence():
    a, b = _pair()
    result = evaluate_replay_comparability(
        descriptor_a=a,
        persistence_a=_persistence(a),
        descriptor_b=b,
        persistence_b=None,
        replay_set_context=_context_for(a, b, ),
    )

    assert result.evidence_b.admission == "UNKNOWN"
    assert result.surface_comparison_started is False
    assert result.surface_result == "UNKNOWN"
    assert result.lineage_result == "UNKNOWN"
    assert result.replay_set_result == "UNKNOWN"
    assert "DESCRIPTOR_EVIDENCE_UNVERIFIED" in result.reason_codes


# ---------------------------------------------------------------------------
# T07 verification identity mismatch
# ---------------------------------------------------------------------------

def test_t07_verification_identity_mismatch():
    a, b = _pair()
    wrong = ReplayExecutionDescriptorPersistenceResult(
        descriptor_id="f" * 64,
        descriptor_bytes_sha256=SHA_B,
        readback_verified=True,
        status="EXECUTION_DESCRIPTOR_PERSISTED_VERIFIED",
    )

    result = evaluate_replay_comparability(
        descriptor_a=a,
        persistence_a=_persistence(a),
        descriptor_b=b,
        persistence_b=wrong,
        replay_set_context=_context_for(a, b, ),
    )

    assert result.surface_result == "UNKNOWN"
    assert (
        "DESCRIPTOR_VERIFICATION_IDENTITY_MISMATCH"
        in result.reason_codes
    )


# ---------------------------------------------------------------------------
# T08 same plan / same condition / distinct replay indices
# ---------------------------------------------------------------------------

def test_t08_same_lineage_distinct_replay_indices():
    a, b = _pair(replay_index=2)
    context = _context_for(a, b,
        expected_replays=3,
        received_replay_indices=(0, 1, 2),
    )
    result = _evaluate(a, b, context=context)

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "LINEAGE_COMPATIBLE"
    assert "PLAN_ID_SAME" in result.lineage_findings
    assert "CONDITION_ID_SAME" in result.lineage_findings
    assert "REPLAY_INDEX_DIFFERENT" in result.lineage_findings
    assert result.replay_set_result == "REPLAY_SET_ADMISSIBLE"
    assert result.set_completeness_result == "SET_COMPLETE"


# ---------------------------------------------------------------------------
# T09 duplicate replay slot
# ---------------------------------------------------------------------------

def test_t09_duplicate_replay_slot_conflict():
    a, b = _pair(replay_index=0)
    result = _evaluate(
        a,
        b,
        context=_context_for(a, b,
            expected_replays=2,
            received_replay_indices=(0, 1),
        ),
    )

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "LINEAGE_CONFLICT"
    assert "REPLAY_SLOT_DUPLICATE_OR_CONFLICT" in result.lineage_findings
    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert result.set_completeness_result == "SET_CONFLICTED"


# ---------------------------------------------------------------------------
# T10 cross-plan surface-compatible pair
# ---------------------------------------------------------------------------

def test_t10_cross_plan_surface_compatible_but_not_replay_admissible():
    a, b = _pair(plan_id="plan-2")
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "CROSS_PLAN"
    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert "CROSS_PLAN" in result.reason_codes
    assert "CROSS_PLAN_ADMISSION_NOT_ESTABLISHED" in result.context_flags


# ---------------------------------------------------------------------------
# T11 cross-condition surface-compatible pair
# ---------------------------------------------------------------------------

def test_t11_cross_condition_surface_compatible_but_not_replay_admissible():
    a, b = _pair(condition_id="cond-2")
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "CROSS_CONDITION"
    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert "CROSS_CONDITION" in result.reason_codes


# ---------------------------------------------------------------------------
# T12 incomplete expected replay set
# ---------------------------------------------------------------------------

def test_t12_incomplete_expected_replay_set():
    a, b = _pair()
    result = _evaluate(
        a,
        b,
        context=_context_for(a, b,
            expected_replays=3,
            received_replay_indices=(0, 1),
        ),
    )

    assert result.replay_set_result == "REPLAY_SET_ADMISSIBLE"
    assert result.set_completeness_result == "SET_INCOMPLETE"
    assert "MISSING_REPLAY_SLOT" in result.reason_codes


# ---------------------------------------------------------------------------
# T13 complete expected replay set
# ---------------------------------------------------------------------------

def test_t13_complete_expected_replay_set():
    a, b = _pair()
    result = _evaluate(
        a,
        b,
        context=_context_for(a, b,
            expected_replays=2,
            received_replay_indices=(0, 1),
        ),
    )

    assert result.replay_set_result == "REPLAY_SET_ADMISSIBLE"
    assert result.set_completeness_result == "SET_COMPLETE"


# ---------------------------------------------------------------------------
# T14 conflicted replay set
# ---------------------------------------------------------------------------

def test_t14_conflicted_replay_set_from_duplicate_received_indices():
    a, b = _pair()
    result = _evaluate(
        a,
        b,
        context=_context_for(a, b,
            expected_replays=2,
            received_replay_indices=(0, 0, 1),
        ),
    )

    assert result.replay_set_result == "REPLAY_SET_ADMISSIBLE"
    assert result.set_completeness_result == "SET_CONFLICTED"
    assert "REPLAY_SLOT_CONFLICT" in result.reason_codes


# ---------------------------------------------------------------------------
# T15 unavailable expected_replays
# ---------------------------------------------------------------------------

def test_t15_unavailable_expected_replays_preserves_unknown():
    a, b = _pair()

    context = ReplaySetContext(
        execution_plan=None,
        received_evidence=(
            (a, _persistence(a)),
            (b, _persistence(b)),
        ),
    )

    result = _evaluate(a, b, context=context)

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "LINEAGE_COMPATIBLE"
    assert result.replay_set_result == "UNKNOWN"
    assert result.set_completeness_result == "UNKNOWN"
    assert "EXPECTED_REPLAYS_UNAVAILABLE" in result.reason_codes


# ---------------------------------------------------------------------------
# T16 invalid descriptor
# ---------------------------------------------------------------------------

def test_t16_invalid_descriptor_preserves_unknown():
    a, b = _pair()

    result = evaluate_replay_comparability(
        descriptor_a=None,
        persistence_a=None,
        descriptor_b=b,
        persistence_b=_persistence(b),
        replay_set_context=_context_for(a, b, ),
    )

    assert result.evidence_a.admission == "UNKNOWN"
    assert result.surface_result == "UNKNOWN"
    assert result.surface_comparison_started is False
    assert "DESCRIPTOR_INVALID" in result.reason_codes


# ---------------------------------------------------------------------------
# T17 UNKNOWN preservation
# ---------------------------------------------------------------------------

def test_t17_missing_plan_context_preserves_unknown_not_negative_admission():
    a, b = _pair()
    result = _evaluate(
        a,
        b,
        context=_context_for(a, b, omit_plan=True),
    )

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "LINEAGE_COMPATIBLE"
    assert result.replay_set_result == "UNKNOWN"
    assert result.set_completeness_result == "UNKNOWN"
    assert "PLAN_CONTEXT_UNAVAILABLE" in result.reason_codes


# ---------------------------------------------------------------------------
# T18 reason-code completeness
# ---------------------------------------------------------------------------

def test_t18_multiple_surface_mismatches_are_all_reported():
    a, b = _pair(
        prompt_sha256="e" * 64,
        model_identifier="model-y",
        session_policy="loose",
    )
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_INCOMPATIBLE"
    assert "PROMPT_HASH_MISMATCH" in result.reason_codes
    assert "MODEL_IDENTIFIER_MISMATCH" in result.reason_codes
    assert "SESSION_POLICY_MISMATCH" in result.reason_codes


# ---------------------------------------------------------------------------
# T19 order-insensitive provider-setting equality
# ---------------------------------------------------------------------------

def test_t19_provider_settings_are_order_insensitive_mapping_equality():
    a = _descriptor(
        descriptor_id=SHA_A,
        run_id="run-a",
        replay_index=0,
        provider_settings=(("temperature", "0.0"), ("top_p", "1.0")),
    )
    b = _descriptor(
        descriptor_id=SHA_B,
        run_id="run-b",
        replay_index=1,
        provider_settings=(("top_p", "1.0"), ("temperature", "0.0")),
    )

    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_COMPATIBLE"
    provider_finding = next(
        finding
        for finding in result.surface_field_findings
        if finding.field == "provider_settings"
    )
    assert provider_finding.result == "SAME"


# ---------------------------------------------------------------------------
# T20 no full-context / runtime / temporal / stability overclaim
# ---------------------------------------------------------------------------

def test_t20_no_overclaim_beyond_comparability_contract():
    a, b = _pair()
    result = _evaluate(a, b, context=_context_for(a, b, ))

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.replay_set_result == "REPLAY_SET_ADMISSIBLE"
    assert result.set_completeness_result == "SET_COMPLETE"

    assert result.full_execution_context_established is False
    assert result.actual_runtime_condition_established is False
    assert result.cross_plan_admission_established is False
    assert result.temporal_comparability_established is False

    payload = result.to_dict()
    assert "stability" not in payload
    assert "stable" not in payload
    assert "model_reliability" not in payload
    assert "semantic_truth" not in payload

# ---------------------------------------------------------------------------
# E-01 regression: caller-declared indices are not replay evidence
# ---------------------------------------------------------------------------

def test_e01_no_phantom_replay_completeness():
    a, b = _pair()

    # Only two replay members have descriptor + persistence evidence.
    # expected_replays=3 must therefore remain incomplete.
    context = _context_for(
        a,
        b,
        expected_replays=3,
        received_replay_indices=(0, 1),
    )

    result = _evaluate(a, b, context=context)

    assert result.evidence_a.admission == "ADMITTED"
    assert result.evidence_b.admission == "ADMITTED"
    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.replay_set_result == "REPLAY_SET_ADMISSIBLE"
    assert result.set_completeness_result == "SET_INCOMPLETE"
    assert "MISSING_REPLAY_SLOT" in result.reason_codes

# ---------------------------------------------------------------------------
# E-02 regression: unverified replay-set member preserves UNKNOWN
# ---------------------------------------------------------------------------

def test_e02_unverified_set_member_preserves_unknown():
    a, b = _pair()

    c = dataclasses.replace(
        a,
        descriptor_id="3" * 64,
        run_id="run-c",
        replay_index=2,
    )

    context = ReplaySetContext(
        execution_plan=_execution_plan_for(
            a,
            expected_replays=3,
        ),
        received_evidence=(
            (a, _persistence(a)),
            (b, _persistence(b)),
            (c, _persistence(c, readback_verified=False)),
        ),
        task_spec=TASK_SPEC,
        received_task_binding_evidence=(
            _binding_evidence(a),
            _binding_evidence(b),
            _binding_evidence(c),
        ),
    )

    result = _evaluate(a, b, context=context)

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "LINEAGE_COMPATIBLE"

    # An unverified enumerated set member prevents Layer-4 admission.
    assert result.replay_set_result == "UNKNOWN"
    assert result.set_completeness_result == "UNKNOWN"
    assert "DESCRIPTOR_EVIDENCE_UNVERIFIED" in result.reason_codes

# ---------------------------------------------------------------------------
# E-03 regression: admitted member must also match replay-set surface
# ---------------------------------------------------------------------------

def test_e03_surface_incompatible_set_member_not_admissible():
    a, b = _pair()

    c = dataclasses.replace(
        a,
        descriptor_id="4" * 64,
        run_id="run-c",
        replay_index=2,
        prompt_sha256="f" * 64,
    )

    context = ReplaySetContext(
        execution_plan=_execution_plan_for(
            a,
            expected_replays=3,
        ),
        received_evidence=(
            (a, _persistence(a)),
            (b, _persistence(b)),
            (c, _persistence(c)),
        ),
        task_spec=TASK_SPEC,
        received_task_binding_evidence=(
            _binding_evidence(a),
            _binding_evidence(b),
            _binding_evidence(c),
        ),
    )

    result = _evaluate(a, b, context=context)

    # The directly compared pair remains surface-compatible.
    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "LINEAGE_COMPATIBLE"

    # But admitted evidence is not automatically a member of this replay set.
    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert result.set_completeness_result == "UNKNOWN"
    assert "PROMPT_HASH_MISMATCH" in result.reason_codes

# ---------------------------------------------------------------------------
# E-04 regression: caller assertion cannot establish governing context
# ---------------------------------------------------------------------------

def test_e04_caller_assertion_cannot_establish_governing_context():
    context_fields = {
        field.name
        for field in dataclasses.fields(ReplaySetContext)
    }

    # The old caller-authority inputs no longer exist.
    assert "plan_context_available" not in context_fields
    assert "condition_context_available" not in context_fields
    assert "expected_replay_set_identity_available" not in context_fields
    assert "expected_replays" not in context_fields

    a, b = _pair()

    # DRAFT is structurally valid, but it is not an eligible
    # governing source for replay-set admission.
    draft_plan = _execution_plan_for(
        a,
        expected_replays=2,
        status="DRAFT",
    )

    context = ReplaySetContext(
        execution_plan=draft_plan,
        received_evidence=(
            (a, _persistence(a)),
            (b, _persistence(b)),
        ),
    )

    result = _evaluate(a, b, context=context)

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.lineage_result == "LINEAGE_COMPATIBLE"
    assert result.replay_set_result == "UNKNOWN"
    assert result.set_completeness_result == "UNKNOWN"
    assert "INSUFFICIENT_EVIDENCE" in result.reason_codes

# ---------------------------------------------------------------------------
# E-05 canonical task provenance regression surface — C01-C10
# ---------------------------------------------------------------------------

def test_c01_verified_binding_admits_task_provenance():
    a, b = _pair()
    result = _evaluate(a, b, context=_context_for(a, b))

    assert result.replay_set_result == "REPLAY_SET_ADMISSIBLE"


def test_c02_missing_binding_preserves_unknown():
    a, b = _pair()
    context = dataclasses.replace(
        _context_for(a, b),
        received_task_binding_evidence=(),
    )
    result = _evaluate(a, b, context=context)

    assert result.replay_set_result == "UNKNOWN"
    assert "CANONICAL_TASK_BINDING_UNAVAILABLE" in result.reason_codes


def test_c03_unverified_binding_preserves_unknown():
    a, b = _pair()
    context = _context_for(a, b)
    binding, _persistence_result = next(
        pair
        for pair in context.received_task_binding_evidence
        if pair[0] is not None and pair[0].run_id == a.run_id
    )
    context = _replace_binding_pair(
        context,
        a.run_id,
        (binding, None),
    )
    result = _evaluate(a, b, context=context)

    assert result.replay_set_result == "UNKNOWN"
    assert "CANONICAL_TASK_BINDING_UNVERIFIED" in result.reason_codes


def test_c04_binding_run_id_mismatch_not_admissible():
    a, b = _pair()
    context = _context_for(a, b)
    binding, persistence = next(
        pair
        for pair in context.received_task_binding_evidence
        if pair[0] is not None and pair[0].run_id == a.run_id
    )
    tampered = dataclasses.replace(binding, run_id="wrong-run")
    context = _replace_binding_pair(
        context,
        a.run_id,
        (tampered, persistence),
    )
    result = _evaluate(a, b, context=context)

    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert "CANONICAL_TASK_BINDING_RUN_MISMATCH" in result.reason_codes


def test_c05_binding_task_id_mismatch_not_admissible():
    a, b = _pair()
    context = _context_for(a, b)
    binding, persistence = next(
        pair
        for pair in context.received_task_binding_evidence
        if pair[0] is not None and pair[0].run_id == a.run_id
    )
    tampered = dataclasses.replace(binding, task_id="task-other")
    context = _replace_binding_pair(
        context,
        a.run_id,
        (tampered, persistence),
    )
    result = _evaluate(a, b, context=context)

    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert "CANONICAL_TASK_BINDING_TASK_ID_MISMATCH" in result.reason_codes


def test_c06_binding_canonical_digest_mismatch_not_admissible():
    a, b = _pair()
    context = _context_for(a, b)
    binding, persistence = next(
        pair
        for pair in context.received_task_binding_evidence
        if pair[0] is not None and pair[0].run_id == a.run_id
    )
    tampered = dataclasses.replace(
        binding,
        canonical_task_sha256="e" * 64,
    )
    context = _replace_binding_pair(
        context,
        a.run_id,
        (tampered, persistence),
    )
    result = _evaluate(a, b, context=context)

    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert "CANONICAL_TASK_DIGEST_MISMATCH" in result.reason_codes


def test_c07_descriptor_task_digest_mismatch_not_admissible():
    original_a, original_b = _pair()
    a = dataclasses.replace(original_a, task_sha256="e" * 64)
    b = dataclasses.replace(original_b, task_sha256="e" * 64)
    result = _evaluate(a, b, context=_context_for(a, b))

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert "CANONICAL_TASK_DIGEST_MISMATCH" in result.reason_codes


def test_c08_descriptor_prompt_digest_mismatch_not_admissible():
    original_a, original_b = _pair()
    a = dataclasses.replace(original_a, prompt_sha256="e" * 64)
    b = dataclasses.replace(original_b, prompt_sha256="e" * 64)
    result = _evaluate(a, b, context=_context_for(a, b))

    assert result.surface_result == "SURFACE_COMPATIBLE"
    assert result.replay_set_result == "REPLAY_SET_NOT_ADMISSIBLE"
    assert "CANONICAL_TASK_PROMPT_MISMATCH" in result.reason_codes


def test_c09_historical_descriptor_without_binding_remains_unknown():
    a, b = _pair()
    context = ReplaySetContext(
        execution_plan=_execution_plan_for(a),
        received_evidence=(
            (a, _persistence(a)),
            (b, _persistence(b)),
        ),
        task_spec=TASK_SPEC,
        received_task_binding_evidence=(),
    )
    result = _evaluate(a, b, context=context)

    assert result.replay_set_result == "UNKNOWN"
    assert "CANONICAL_TASK_BINDING_UNAVAILABLE" in result.reason_codes


def test_c10_matching_hash_alone_does_not_establish_provenance():
    a, b = _pair()
    assert a.task_sha256 == CANONICAL_TASK_SHA
    assert b.task_sha256 == CANONICAL_TASK_SHA
    assert a.prompt_sha256 == TASK_SPEC.prompt_sha256
    assert b.prompt_sha256 == TASK_SPEC.prompt_sha256

    context = ReplaySetContext(
        execution_plan=_execution_plan_for(a),
        received_evidence=(
            (a, _persistence(a)),
            (b, _persistence(b)),
        ),
        task_spec=TASK_SPEC,
        received_task_binding_evidence=(),
    )
    result = _evaluate(a, b, context=context)

    assert result.replay_set_result == "UNKNOWN"
    assert "CANONICAL_TASK_BINDING_UNAVAILABLE" in result.reason_codes
