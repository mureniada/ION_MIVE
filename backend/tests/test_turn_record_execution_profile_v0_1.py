"""TASK 20.3A contract test: Turn Record execution-policy provenance (TR20).

Scope is the PURE CONTRACT only, isolated here from `test_turn_record_v0_1.py`
for clean separation: what `ExecutionProfileBinding` may hold, how it binds
onto `TurnRecord`, and the two COMPLETED success branches this binding now
selects between —

    BRANCH A (no binding, or a bound mode other than "SINGLE"):
        the ORIGINAL comparison-applicable law, unchanged (TASK 18).

    BRANCH B (bound to mode "SINGLE"):
        exactly one model execution, no comparison outcome, no comparison
        latency — because none ran, by policy, not by failure.

This phase is NON-LIVE: nothing here exercises `Core`, the Model Gateway, a
provider adapter, or MIVE. It proves the pure contract only. Where a frozen
TASK 13/18 object is used below it is a REAL one, produced through its own
public entry point, exactly as `test_turn_record_v0_1.py` already does.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.modules.turn_record import (
    ExecutionProfileBinding,
    ModelExecutionBinding,
    TurnConfigurationBinding,
    TurnFailure,
    TurnRecordMaterializationError,
    materialize_failed_turn_record,
    materialize_turn_record,
)


def _real_governed_evidence_set(
    *, retrieved=("EV-1", "EV-2", "EV-3"), submitted=("EV-1", "EV-2"),
    context_pack_id="CP-001", question_id="TURN-1",
):
    from types import SimpleNamespace

    from app.modules.governed_evidence import (
        MaterializationInput,
        materialize_governed_evidence_set,
    )

    def _native(candidate_ids):
        return SimpleNamespace(
            records=tuple(
                SimpleNamespace(
                    evidence_id=cid, status="VERIFIED", validation_id="VAL-" + cid,
                    fingerprint=SimpleNamespace(
                        algorithm="SHA256", hash="FP-" + cid, content_id=cid
                    ),
                )
                for cid in candidate_ids
            ),
            validations=tuple(
                SimpleNamespace(
                    validation_id="VAL-" + cid, evidence_id=cid, result="PASS",
                    blocking_reasons=(), evidence_fingerprint_hash="FP-" + cid,
                )
                for cid in candidate_ids
            ),
            transitions=tuple(
                SimpleNamespace(
                    transition_id="TR-" + cid, evidence_id=cid,
                    from_status="PENDING", to_status="VERIFIED",
                    validation_id="VAL-" + cid,
                )
                for cid in candidate_ids
            ),
        )

    return materialize_governed_evidence_set(
        MaterializationInput(
            outcome_state="GOVERNANCE_COMPLETE",
            native_result=_native(submitted),
            retrieved_candidate_ids=retrieved,
            submitted_candidate_ids=submitted,
            candidate_count=len(retrieved),
            governed_count=len(submitted),
            backend_id="TEST-BACKEND",
            mapping_profile_id="TEST-PROFILE",
            adapter_id="ION_CORE_ADAPTER_FACADE_V0_1",
            adapter_version="0.1",
            context_pack_id=context_pack_id,
            question_id=question_id,
            context_pack_metadata={"included_documents": len(submitted)},
        )
    )


def _execution(engine_id="gemini", provider="gemini", model="gemini-3.1-flash-lite"):
    return ModelExecutionBinding(
        engine_id=engine_id, provider=provider, requested_model=model,
        input_tokens=1200, output_tokens=250, latency_ms=2100.5,
        usage_is_estimated=False, estimated_cost=0.000675,
    )


def _configuration():
    return TurnConfigurationBinding(
        effective_top_k=5, context_char_budget=60000,
        retrieval_collection="ion_corpus_v1", app_version="0.1.0",
        pricing_as_of="2026-07-13",
    )


def _single_binding(**overrides):
    kwargs = dict(profile_id="STANDARD_GEMINI", profile_version="0.1", mode="SINGLE")
    kwargs.update(overrides)
    return ExecutionProfileBinding(**kwargs)


def _materialize(**overrides):
    kwargs = dict(
        turn_id="TURN-1",
        question="is money credit or debt?",
        governed_basis=_real_governed_evidence_set(),
        context_pack_id="CP-001",
        model_executions=(_execution(), _execution("openai", "openai", "gpt-5.4-mini")),
        mive_overall_status="partial_agreement",
        comparison_latency_ms=21.261,
        configuration=_configuration(),
        turn_started_at="2026-08-29T00:00:00+00:00",
        turn_closed_at="2026-08-29T00:00:04+00:00",
        retrieval_latency_ms=120.5,
        pipeline_latency_ms=80361.252,
    )
    kwargs.update(overrides)
    return materialize_turn_record(**kwargs)


def _materialize_single(**overrides):
    kwargs = dict(
        turn_id="TURN-1",
        question="is money credit or debt?",
        governed_basis=_real_governed_evidence_set(),
        context_pack_id="CP-001",
        model_executions=(_execution(),),
        mive_overall_status=None,
        comparison_latency_ms=None,
        execution_profile=_single_binding(),
        configuration=_configuration(),
        turn_started_at="2026-08-29T00:00:00+00:00",
        turn_closed_at="2026-08-29T00:00:04+00:00",
        retrieval_latency_ms=120.5,
        pipeline_latency_ms=47801.534,
    )
    kwargs.update(overrides)
    return materialize_turn_record(**kwargs)


# --------------------------------------------------------------------- #
# TR20-01 / TR20-02 / TR20-03  ExecutionProfileBinding shape
# --------------------------------------------------------------------- #
def test_tr20_01_execution_profile_binding_exact_field_set():
    assert {f.name for f in dataclasses.fields(ExecutionProfileBinding)} == {
        "profile_id", "profile_version", "mode",
    }


def test_tr20_02_execution_profile_binding_is_frozen():
    binding = _single_binding()
    for field, value in (
        ("profile_id", "OTHER"), ("profile_version", "9.9"), ("mode", "OTHER"),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(binding, field, value)


def test_tr20_03_execution_profile_binding_structural_validation():
    for field in ("profile_id", "profile_version", "mode"):
        for refused in ("", None, 7, " STANDARD_GEMINI", "STANDARD_GEMINI ", "\tx\n"):
            with pytest.raises(TurnRecordMaterializationError):
                _single_binding(**{field: refused})
    # a well-shaped binding constructs cleanly
    binding = _single_binding()
    assert (binding.profile_id, binding.profile_version, binding.mode) == (
        "STANDARD_GEMINI", "0.1", "SINGLE",
    )


# --------------------------------------------------------------------- #
# TR20-04  binding STANDARD_GEMINI's own values without importing its type
# --------------------------------------------------------------------- #
def test_tr20_04_turn_record_binds_standard_gemini_values_without_importing_it():
    # the caller reads its own real ExecutionProfile and converts here —
    # turn_record never imports execution_profile to do this
    from app.modules.execution_profile import STANDARD_GEMINI

    binding = ExecutionProfileBinding(
        profile_id=STANDARD_GEMINI.profile_id,
        profile_version=STANDARD_GEMINI.profile_version,
        mode=STANDARD_GEMINI.mode.value,
    )
    record = _materialize_single(execution_profile=binding)
    assert record.execution_profile.profile_id == "STANDARD_GEMINI"
    assert record.execution_profile.profile_version == "0.1"
    assert record.execution_profile.mode == "SINGLE"
    assert isinstance(record.execution_profile.mode, str)


# --------------------------------------------------------------------- #
# TR20-05 .. TR20-10  COMPLETED SINGLE branch
# --------------------------------------------------------------------- #
def test_tr20_05_completed_single_allows_exactly_one_model_execution():
    record = _materialize_single()
    assert len(record.model_executions) == 1
    assert record.execution_profile.mode == "SINGLE"


def test_tr20_06_completed_single_requires_mive_overall_status_none():
    record = _materialize_single()
    assert record.mive_overall_status is None


def test_tr20_07_completed_single_requires_comparison_latency_none():
    record = _materialize_single()
    assert record.comparison_latency_ms is None


def test_tr20_08_completed_single_rejects_two_model_executions():
    with pytest.raises(TurnRecordMaterializationError):
        _materialize_single(
            model_executions=(_execution(), _execution("openai", "openai", "gpt-5.4-mini")),
        )


def test_tr20_09_completed_single_rejects_non_none_mive_status():
    with pytest.raises(TurnRecordMaterializationError):
        _materialize_single(mive_overall_status="partial_agreement")


def test_tr20_10_completed_single_rejects_zero_comparison_latency():
    """NO MEASUREMENT IS NOT ZERO DURATION — 0.0 is refused exactly like any
    other non-None value; it is not treated as a safe stand-in for absence."""
    with pytest.raises(TurnRecordMaterializationError):
        _materialize_single(comparison_latency_ms=0.0)
    with pytest.raises(TurnRecordMaterializationError):
        _materialize_single(comparison_latency_ms=21.261)


# --------------------------------------------------------------------- #
# TR20-11 .. TR20-13  legacy / no-profile comparison-applicable branch
# --------------------------------------------------------------------- #
def test_tr20_11_legacy_no_profile_completed_still_requires_mive_status():
    with pytest.raises(TurnRecordMaterializationError):
        _materialize(mive_overall_status=None)


def test_tr20_12_legacy_no_profile_completed_still_requires_comparison_latency():
    with pytest.raises(TurnRecordMaterializationError):
        _materialize(comparison_latency_ms=None)


def test_tr20_13_legacy_no_profile_existing_fixture_remains_value_valid():
    record = _materialize()
    assert record.execution_profile is None
    assert record.mive_overall_status == "partial_agreement"
    assert record.comparison_latency_ms == 21.261
    assert len(record.model_executions) == 2


# a bound mode this contract does not recognize is treated as
# comparison-applicable — Turn Record is not the execution-profile authority
def test_tr20_13b_unrecognized_bound_mode_is_comparison_applicable():
    unrecognized = ExecutionProfileBinding(
        profile_id="FUTURE_PROFILE", profile_version="0.1", mode="VERIFY",
    )
    with pytest.raises(TurnRecordMaterializationError):
        _materialize(execution_profile=unrecognized, mive_overall_status=None)
    # supplying the comparison facts succeeds, exactly as branch A requires
    record = _materialize(execution_profile=unrecognized)
    assert record.execution_profile.mode == "VERIFY"
    assert record.mive_overall_status == "partial_agreement"


# --------------------------------------------------------------------- #
# TR20-14 / TR20-15  FAILED records
# --------------------------------------------------------------------- #
def test_tr20_14_failed_record_may_carry_a_profile_binding():
    record = materialize_failed_turn_record(
        turn_id="TURN-1",
        turn_started_at="2026-08-29T00:00:00+00:00",
        turn_closed_at="2026-08-29T00:00:04+00:00",
        failure=TurnFailure(error_type="ProviderError", error_stage="gemini"),
        configuration=_configuration(),
        execution_profile=_single_binding(),
    )
    assert record.execution_profile == _single_binding()
    assert record.model_executions == ()  # gemini failed; nothing completed


def test_tr20_15_failed_record_may_remain_profile_less():
    record = materialize_failed_turn_record(
        turn_id="TURN-1",
        turn_started_at="2026-08-29T00:00:00+00:00",
        turn_closed_at="2026-08-29T00:00:04+00:00",
        failure=TurnFailure(error_type="IonError", error_stage="configuration"),
        configuration=_configuration(),
    )
    assert record.execution_profile is None


# --------------------------------------------------------------------- #
# TR20-16 / TR20-17  import closure and mechanism-freedom
# --------------------------------------------------------------------- #
def test_tr20_16_turn_record_package_does_not_import_execution_profile():
    import ast
    from pathlib import Path

    import app.modules.turn_record as turn_record
    import app.modules.turn_record.materializer as materializer
    import app.modules.turn_record.models as models

    for module in (turn_record, models, materializer):
        path = Path(module.__file__).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "execution_profile", path.name
                if node.module:
                    assert "execution_profile" not in node.module, path.name
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "execution_profile" not in alias.name, path.name

    # and no execution_profile type is reachable through the live namespace
    for module in (turn_record, models, materializer):
        for name in ("ExecutionProfile", "ExecutionMode", "resolve_execution_profile"):
            assert not hasattr(module, name), (module.__name__, name)


def test_tr20_17_turn_record_contains_no_execution_selection_or_routing_logic():
    import app.modules.turn_record as turn_record
    import app.modules.turn_record.materializer as materializer
    import app.modules.turn_record.models as models

    all_field_names = set()
    for cls in (ExecutionProfileBinding,):
        all_field_names |= {f.name for f in dataclasses.fields(cls)}

    for absent in (
        "engine_id", "engine_ids", "select_engine", "route", "routing",
        "retry", "fallback", "dispatch", "timeout",
    ):
        assert absent not in all_field_names, absent

    for module in (turn_record, models, materializer):
        for name in ("ModelGateway", "GeminiIVE", "OpenAIIVE"):
            assert not hasattr(module, name), (module.__name__, name)
