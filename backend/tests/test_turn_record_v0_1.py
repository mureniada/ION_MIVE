"""TASK 18.2 contract test: the Product Turn Record vocabulary (v0.1).

Scope is the PURE CONTRACT only: what a `TurnRecord` may hold, what it refuses,
and what it structurally cannot carry. The live wiring is proven separately in
`test_orchestrator_turn_record_v0_1.py`.

Nothing here asserts governance, admission, provenance, comparison or provider
semantics. Those stay owned and tested by the frozen modules, which TASK 18
does not touch. Where a frozen object is used below it is a REAL one, produced
through its own public entry point, so a passing assertion proves genuine
structural compatibility rather than shape similarity.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules import turn_record
import app.modules.turn_record.materializer as materializer
import app.modules.turn_record.models as models
from app.modules.turn_record import (
    QUESTION_NORMALIZATION_STRIP,
    TURN_IDENTITY_BASIS_REQUEST_ID,
    TURN_RECORD_CONTRACT_ID,
    TURN_RECORD_VERSION,
    GovernedEvidenceBinding,
    ModelExecutionBinding,
    TurnClosureState,
    TurnConfigurationBinding,
    TurnFailure,
    TurnRecord,
    TurnRecordMaterializationError,
    materialize_turn_record,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATHS = (
    Path(models.__file__).resolve(),
    Path(materializer.__file__).resolve(),
    Path(turn_record.__file__).resolve(),
)

VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"


# --------------------------------------------------------------------- #
# builders. Field carriers only — nothing here governs, compares or reasons.
# --------------------------------------------------------------------- #
def _native(candidate_ids):
    """Shaped exactly as RuntimeAdmissionGateResult returns its three lists."""
    return SimpleNamespace(
        records=tuple(
            SimpleNamespace(
                evidence_id=cid,
                status=VERIFIED,
                validation_id="VAL-" + cid,
                fingerprint=SimpleNamespace(
                    algorithm="SHA256", hash="FP-" + cid, content_id=cid
                ),
            )
            for cid in candidate_ids
        ),
        validations=tuple(
            SimpleNamespace(
                validation_id="VAL-" + cid,
                evidence_id=cid,
                result=PASS,
                blocking_reasons=(),
                evidence_fingerprint_hash="FP-" + cid,
            )
            for cid in candidate_ids
        ),
        transitions=tuple(
            SimpleNamespace(
                transition_id="TR-" + cid,
                evidence_id=cid,
                from_status=PENDING,
                to_status=VERIFIED,
                validation_id="VAL-" + cid,
            )
            for cid in candidate_ids
        ),
    )


def _real_governed_evidence_set(
    *, retrieved=("EV-1", "EV-2", "EV-3"), submitted=("EV-1", "EV-2"),
    context_pack_id="CP-001", question_id="TURN-1",
):
    """A GENUINE frozen GovernedEvidenceSet, via its own public entry point."""
    from app.modules.governed_evidence import (
        MaterializationInput,
        materialize_governed_evidence_set,
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
        engine_id=engine_id,
        provider=provider,
        requested_model=model,
        input_tokens=1200,
        output_tokens=250,
        latency_ms=2100.5,
        usage_is_estimated=False,
        estimated_cost=0.000675,
    )


def _configuration():
    return TurnConfigurationBinding(
        effective_top_k=5,
        context_char_budget=60000,
        retrieval_collection="ion_corpus_v1",
        app_version="0.1.0",
        pricing_as_of="2026-07-13",
    )


def _materialize(**overrides):
    kwargs = dict(
        turn_id="TURN-1",
        question="is money credit or debt?",
        governed_basis=_real_governed_evidence_set(),
        context_pack_id="CP-001",
        model_executions=(_execution(), _execution("openai", "openai", "gpt-5.4-mini")),
        mive_overall_status="partial_agreement",
        configuration=_configuration(),
        turn_started_at="2026-08-29T00:00:00+00:00",
        turn_closed_at="2026-08-29T00:00:04+00:00",
        retrieval_latency_ms=120.5,
        comparison_latency_ms=21.261,
        pipeline_latency_ms=80361.252,
    )
    kwargs.update(overrides)
    return materialize_turn_record(**kwargs)


def _field_names(cls):
    return {f.name for f in dataclasses.fields(cls)}


def _all_field_names():
    names = set()
    for cls in (
        TurnRecord,
        GovernedEvidenceBinding,
        ModelExecutionBinding,
        TurnConfigurationBinding,
        TurnFailure,
    ):
        names |= _field_names(cls)
    return names


def _identifiers(path):
    """Every identifier the parsed module actually uses. Docstrings excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return names


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute, relative = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.add((node.level, node.module or ""))
            else:
                absolute.add(node.module or "")
    return absolute, relative


# --------------------------------------------------------------------- #
# T18-01  immutability
# --------------------------------------------------------------------- #
def test_t18_01_turn_record_and_every_binding_is_immutable():
    record = _materialize()

    for target, field, value in (
        (record, "turn_id", "OTHER"),
        (record, "closure_state", TurnClosureState.FAILED),
        (record, "question", "rewritten"),
        (record.governed_evidence, "governed_count", 99),
        (record.model_executions[0], "requested_model", "other-model"),
        (record.configuration, "effective_top_k", 99),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(target, field, value)

    # the execution collection is a tuple, so it cannot be appended to either
    assert isinstance(record.model_executions, tuple)


# --------------------------------------------------------------------- #
# T18-02  determinism
# --------------------------------------------------------------------- #
def test_t18_02_same_supplied_facts_produce_value_equal_records():
    first, second = _materialize(), _materialize()
    assert first is not second
    assert first == second
    assert first.governed_evidence == second.governed_evidence
    assert first.model_executions == second.model_executions
    assert first.configuration == second.configuration


# --------------------------------------------------------------------- #
# T18-03  the Product module owns no clock, identity, randomness or I/O
# --------------------------------------------------------------------- #
def test_t18_03_no_clock_identity_randomness_io_or_environment_use():
    allowed_stdlib = {"__future__", "dataclasses", "enum", "typing"}
    own_modules = {"materializer", "models"}

    for path in MODULE_PATHS:
        absolute, relative = _imports(path)
        for module in absolute:
            assert module.split(".")[0] in allowed_stdlib, (path.name, module)
        for level, module in relative:
            assert level == 1, (path.name, level, module)
            assert module in own_modules, (path.name, module)

        used = _identifiers(path)
        for forbidden in (
            # clock / identity / randomness
            "now", "utcnow", "now_iso", "monotonic", "sleep",
            "uuid", "uuid4", "uuid5", "random", "time", "datetime",
            # I/O, network, environment, persistence
            "open", "read_text", "read_bytes", "write_text", "write_bytes",
            "environ", "getenv", "urlopen", "socket", "requests", "httpx",
            "dump", "dumps", "save", "persist", "store", "commit",
            # governance / evidence material a Turn Record must never copy
            "admitted", "rejected", "unknown", "not_submitted", "disposition",
            "native_record", "native_validation", "native_transition",
            "fingerprint", "provenance", "claim", "content",
            # judgements a Turn Record must never make
            "sort", "sorted", "rank", "score", "confidence",
            "authority", "sufficiency", "summarize", "truncate",
        ):
            assert forbidden not in used, (path.name, forbidden)


# --------------------------------------------------------------------- #
# T18-04  closure vocabulary
# --------------------------------------------------------------------- #
def test_t18_04_closure_vocabulary_is_exactly_completed_and_failed():
    assert {state.name for state in TurnClosureState} == {"COMPLETED", "FAILED"}
    assert {state.value for state in TurnClosureState} == {"COMPLETED", "FAILED"}
    for absent in ("CLARIFY", "WAITING_FOR_USER", "DIRECT_RESPONSE", "ABORTED"):
        assert not hasattr(TurnClosureState, absent), absent


def test_t18_04b_the_materializer_produces_completed_only():
    assert _materialize().closure_state is TurnClosureState.COMPLETED
    # no parameter exists through which a caller could ask for another state
    import inspect

    assert "closure_state" not in inspect.signature(materialize_turn_record).parameters


# --------------------------------------------------------------------- #
# T18-05 / T18-06  closure state and failure are mutually consistent
# --------------------------------------------------------------------- #
def test_t18_05_completed_record_requires_no_failure():
    assert _materialize().failure is None

    with pytest.raises(TurnRecordMaterializationError):
        dataclasses.replace(
            _materialize(), failure=TurnFailure(error_type="RuntimeError")
        )


def test_t18_06_failed_record_requires_a_failure():
    completed = _materialize()

    with pytest.raises(TurnRecordMaterializationError):
        dataclasses.replace(completed, closure_state=TurnClosureState.FAILED)

    failed = dataclasses.replace(
        completed,
        closure_state=TurnClosureState.FAILED,
        failure=TurnFailure(
            error_type="ProviderError", error_stage="gemini",
            error_message="gemini call failed",
        ),
    )
    assert failed.closure_state is TurnClosureState.FAILED
    assert failed.failure.error_stage == "gemini"
    # the two nullable members really are nullable: the runtime has failure
    # paths that carry neither a stage nor controlled text
    bare = TurnFailure(error_type="RuntimeError")
    assert bare.error_stage is None and bare.error_message is None


def test_t18_06b_closure_state_must_be_the_product_enum():
    with pytest.raises(TurnRecordMaterializationError):
        dataclasses.replace(_materialize(), closure_state="COMPLETED")


# --------------------------------------------------------------------- #
# T18-07 / T18-08  identity is supplied, never minted
# --------------------------------------------------------------------- #
def test_t18_07_turn_id_is_carried_verbatim_and_never_minted():
    for supplied in ("TURN-1", "9f2c4a7e1b6d40f3", "x"):
        record = _materialize(
            turn_id=supplied,
            governed_basis=_real_governed_evidence_set(question_id=supplied),
        )
        assert record.turn_id == supplied
        assert record.governed_evidence.question_id == supplied

    for refused in ("", None, 7, b"TURN-1"):
        with pytest.raises(TurnRecordMaterializationError):
            _materialize(turn_id=refused)


def test_t18_08_identity_and_contract_literals_are_fixed_and_exact():
    record = _materialize()
    assert record.turn_identity_basis == "CORE_ASK_REQUEST_ID_V0_1"
    assert record.turn_identity_basis == TURN_IDENTITY_BASIS_REQUEST_ID
    assert record.turn_record_contract_id == "ION_TURN_RECORD_V0_1"
    assert record.turn_record_contract_id == TURN_RECORD_CONTRACT_ID
    assert record.turn_record_version == "0.1"
    assert record.turn_record_version == TURN_RECORD_VERSION


# --------------------------------------------------------------------- #
# T18-09 / T18-10 / T18-11  the governed basis is bound, never duplicated
# --------------------------------------------------------------------- #
def test_t18_09_governed_evidence_is_bound_by_reference_not_copied():
    binding = _materialize().governed_evidence

    assert _field_names(GovernedEvidenceBinding) == {
        "governed_evidence_set_id",
        "governed_evidence_set_version",
        "question_id",
        "context_pack_id",
        "backend_id",
        "mapping_profile_id",
        "adapter_id",
        "adapter_version",
        "retrieved_count",
        "submitted_count",
        "governed_count",
    }

    # no evidence, verdict or native governance object has anywhere to enter
    for absent in (
        "admitted", "rejected", "unknown", "not_submitted", "accounting",
        "disposition", "native_status", "native_record", "native_validation",
        "native_transition", "fingerprint", "evidence", "content",
        "retrieved_ids", "submitted_ids", "governed_ids", "context_pack_metadata",
    ):
        assert not hasattr(binding, absent), absent

    # the counts are the accounting the upstream set actually reported
    assert (binding.retrieved_count, binding.submitted_count, binding.governed_count) == (3, 2, 2)


def test_t18_10_a_real_frozen_governed_evidence_set_is_accepted_verbatim():
    """Neither production module imports the other; the join is structural."""
    from app.modules.governed_evidence import GovernedEvidenceSet

    ges = _real_governed_evidence_set()
    assert isinstance(ges, GovernedEvidenceSet)

    record = _materialize(governed_basis=ges)
    binding = record.governed_evidence

    assert binding.governed_evidence_set_id == ges.governed_evidence_set_id
    assert binding.governed_evidence_set_version == ges.governed_evidence_set_version
    assert binding.question_id == ges.question_id
    assert binding.context_pack_id == ges.context_pack_id
    assert binding.backend_id == ges.backend_id
    assert binding.mapping_profile_id == ges.mapping_profile_id
    assert binding.adapter_id == ges.adapter_id
    assert binding.adapter_version == ges.adapter_version
    assert binding.retrieved_count == ges.accounting.retrieved_count
    assert binding.governed_count == ges.accounting.governed_count
    assert binding.submitted_count == len(ges.accounting.submitted_ids)

    # the governed set itself is nowhere inside the record, in any field
    body = repr(record)
    assert "GovernedEvidenceSet" not in body
    assert "ADMITTED" not in body
    for value in (getattr(record, f.name) for f in dataclasses.fields(record)):
        assert not isinstance(value, GovernedEvidenceSet)


def test_t18_11_no_governed_set_instance_id_is_invented():
    record = _materialize()
    names = _field_names(GovernedEvidenceBinding) | _field_names(TurnRecord)
    for invented in (
        "governed_evidence_set_instance_id",
        "governed_evidence_instance_id",
        "evidence_set_id",
        "ges_id",
        "turn_record_id",
    ):
        assert invented not in names, invented
    # the only governed-set identity present is the deterministic contract one
    assert record.governed_evidence.governed_evidence_set_id == "ION_GOVERNED_EVIDENCE_SET_V0_1"


def test_t18_11b_a_malformed_governed_basis_fails_closed():
    for broken in (
        None,
        SimpleNamespace(),
        SimpleNamespace(accounting=SimpleNamespace()),
    ):
        with pytest.raises(TurnRecordMaterializationError):
            _materialize(governed_basis=broken)


# --------------------------------------------------------------------- #
# T18-12  one turn names one Context Pack
# --------------------------------------------------------------------- #
def test_t18_12_context_pack_identity_mismatch_fails_closed():
    with pytest.raises(TurnRecordMaterializationError) as excinfo:
        _materialize(context_pack_id="CP-OTHER")
    assert "Context Pack" in str(excinfo.value)

    # the law is structural, so no construction path can bypass the materializer
    record = _materialize()
    with pytest.raises(TurnRecordMaterializationError):
        dataclasses.replace(record, context_pack_id="CP-OTHER")

    for refused in ("", None, 7):
        with pytest.raises(TurnRecordMaterializationError):
            _materialize(context_pack_id=refused)


# --------------------------------------------------------------------- #
# T18-13 / T18-14  model execution is identity and measurement only
# --------------------------------------------------------------------- #
def test_t18_13_model_execution_carries_no_report_or_provider_output():
    assert _field_names(ModelExecutionBinding) == {
        "engine_id",
        "provider",
        "requested_model",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "usage_is_estimated",
        "estimated_cost",
    }
    for absent in (
        "raw_response", "raw_text", "response", "report", "abstract",
        "highlights", "claims", "concepts", "relations", "evidence_mapping",
        "uncertainty", "confidence", "text", "content", "prompt", "messages",
        "reported_model",
    ):
        assert not hasattr(_execution(), absent), absent


def test_t18_14_no_execution_profile_or_policy_semantics_exist():
    names = _all_field_names()
    for absent in (
        "execution_profile", "profile", "profile_id", "arm", "policy",
        "dispatch_policy", "retry_policy", "fallback_policy",
        "termination_policy", "timeout_policy", "mode", "strategy",
    ):
        assert absent not in names, absent
    # and no such name is reachable through the package namespace either
    for name in ("ExecutionProfile", "ModelExecutionProfile", "DispatchPolicy"):
        assert not hasattr(turn_record, name), name


def test_t18_14b_executions_must_be_present_typed_and_distinct():
    with pytest.raises(TurnRecordMaterializationError):
        _materialize(model_executions=())
    with pytest.raises(TurnRecordMaterializationError):
        _materialize(model_executions=(_execution(), _execution()))  # same engine_id
    with pytest.raises(TurnRecordMaterializationError):
        _materialize(model_executions=(SimpleNamespace(engine_id="x"),))
    with pytest.raises(TurnRecordMaterializationError):
        _materialize(model_executions="gemini")

    # a measurement the runtime did not produce stays absent, never estimated
    empty = ModelExecutionBinding(engine_id="e", provider="p", requested_model="m")
    assert empty.input_tokens is None
    assert empty.output_tokens is None
    assert empty.latency_ms is None
    assert empty.estimated_cost is None
    assert empty.usage_is_estimated is False


# --------------------------------------------------------------------- #
# T18-15 / T18-16  configuration is closed, minimal and secret-free
# --------------------------------------------------------------------- #
def test_t18_15_configuration_field_set_is_exact_and_closed():
    assert _field_names(TurnConfigurationBinding) == {
        "effective_top_k",
        "context_char_budget",
        "retrieval_collection",
        "app_version",
        "pricing_as_of",
    }
    # provider models are NOT configuration: they belong to the execution
    for absent in ("gemini_model", "openai_model", "model", "models", "settings"):
        assert not hasattr(_configuration(), absent), absent
    with pytest.raises(TurnRecordMaterializationError):
        _materialize(configuration=SimpleNamespace(effective_top_k=5))


def test_t18_16_no_secret_endpoint_or_environment_field_exists():
    # compared on whole underscore-separated parts, so a legitimate name is
    # never condemned for merely containing a token (input_tokens vs token)
    for name in _all_field_names():
        parts = name.split("_")
        for token in (
            "url", "uri", "endpoint", "host", "port", "dsn",
            "key", "apikey", "api", "secret", "token", "password",
            "credential", "credentials", "auth", "env", "environ", "settings",
        ):
            assert token not in parts, (token, name)

    # and no rendered record text can carry one either
    record = _materialize()
    for leaked in ("http://", "https://", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        assert leaked not in repr(record), leaked


# --------------------------------------------------------------------- #
# T18-17  the question is recorded, never normalized here
# --------------------------------------------------------------------- #
def test_t18_17_question_normalization_binding_is_exact_and_verified():
    record = _materialize()
    assert record.question_normalization == "STRIP"
    assert record.question_normalization == QUESTION_NORMALIZATION_STRIP
    assert record.question == "is money credit or debt?"

    # an unnormalized question is REFUSED, never silently normalized
    for unnormalized in ("  padded", "padded  ", "\tq\n"):
        with pytest.raises(TurnRecordMaterializationError) as excinfo:
            _materialize(question=unnormalized)
        assert "never normalizes" in str(excinfo.value)

    for refused in ("", None, 7):
        with pytest.raises(TurnRecordMaterializationError):
            _materialize(question=refused)


# --------------------------------------------------------------------- #
# T18-18  latency is named for exactly what was measured
# --------------------------------------------------------------------- #
def test_t18_18_pipeline_latency_claims_nothing_end_to_end():
    names = _all_field_names()
    assert "pipeline_latency_ms" in names
    for overclaim in (
        "total_latency_ms", "turn_total_latency_ms", "end_to_end_latency_ms",
        "total_ms", "duration_ms", "elapsed_ms", "render_latency_ms",
    ):
        assert overclaim not in names, overclaim

    record = _materialize()
    assert record.pipeline_latency_ms == 80361.252   # carried verbatim, not rounded
    assert record.retrieval_latency_ms == 120.5
    assert record.comparison_latency_ms == 21.261

    for refused in (-1.0, "120", None, True):
        with pytest.raises(TurnRecordMaterializationError):
            _materialize(pipeline_latency_ms=refused)


def test_t18_18b_timestamps_are_supplied_by_the_caller():
    record = _materialize()
    assert record.turn_started_at == "2026-08-29T00:00:00+00:00"
    assert record.turn_closed_at == "2026-08-29T00:00:04+00:00"
    for refused in ("", None, 0):
        with pytest.raises(TurnRecordMaterializationError):
            _materialize(turn_started_at=refused)
        with pytest.raises(TurnRecordMaterializationError):
            _materialize(turn_closed_at=refused)


# --------------------------------------------------------------------- #
# T18-19 / T18-20  structural absence
# --------------------------------------------------------------------- #
def test_t18_19_no_answer_evidence_content_or_event_trace_field_exists():
    names = _all_field_names()
    for absent in (
        "rendered", "answer", "primary_answer", "response", "ask_result",
        "mive_result", "ive_reports", "reports", "evidence", "documents",
        "excerpt", "content", "raw_response",
        "events", "event_trace", "progress", "progress_events", "trace", "log",
    ):
        assert absent not in names, absent
    # the comparison outcome is a single opaque status, not the result object
    assert _materialize().mive_overall_status == "partial_agreement"


def test_t18_20_no_authority_admission_or_sufficiency_field_exists():
    names = _all_field_names()
    for absent in (
        "admitted", "rejected", "unknown", "disposition", "verdict",
        "authority", "authoritative", "sufficiency", "sufficient",
        "admission", "promotion", "provenance", "fingerprint",
        "confidence", "score", "relevance", "truth",
    ):
        assert absent not in names, absent


def test_t18_20b_no_session_dialogue_or_future_layer_field_exists():
    names = _all_field_names()
    for absent in (
        "session_id", "session", "conversation_id", "conversation",
        "parent_turn_id", "parent_turn", "turn_ordinal", "history", "memory",
        "dialogue_instruction", "dialogue_profile", "clarify",
    ):
        assert absent not in names, absent

    # the two later Product layers are absent, not nullable: no field, and no
    # placeholder that would assert a layer ran and produced nothing
    for name in names:
        parts = name.split("_")
        assert not ("context" in parts and "assembly" in parts), name
        assert not ("projection" in parts), name


# --------------------------------------------------------------------- #
# T18-21 / T18-22  the public surface is closed and neutral
# --------------------------------------------------------------------- #
def test_t18_21_public_exports_are_exact_and_closed():
    assert set(turn_record.__all__) == {
        "QUESTION_NORMALIZATION_STRIP",
        "TURN_IDENTITY_BASIS_REQUEST_ID",
        "TURN_RECORD_CONTRACT_ID",
        "TURN_RECORD_MATERIALIZER_ID",
        "TURN_RECORD_MATERIALIZER_VERSION",
        "TURN_RECORD_VERSION",
        "GovernedEvidenceBinding",
        "ModelExecutionBinding",
        "TurnClosureState",
        "TurnConfigurationBinding",
        "TurnFailure",
        "TurnRecord",
        "TurnRecordMaterializationError",
        "materialize_turn_record",
    }
    assert len(turn_record.__all__) == len(set(turn_record.__all__))
    for name in turn_record.__all__:
        assert hasattr(turn_record, name), name


def test_t18_22_no_runtime_provider_or_transport_name_is_reachable():
    for module in (turn_record, models, materializer):
        for name in (
            "Core", "Settings", "build_core", "AskResult", "Metrics",
            "GovernedEvidenceSet", "GovernanceDisposition", "MaterializationInput",
            "materialize_governed_evidence_set", "CoreAdapter", "CoreAdapterOutcome",
            "run_runtime_admission_gate", "build_qdrant_runtime_bridge",
            "ContextPack", "ContextDocument", "Evidence", "IVEReport", "MIVEResult",
            "QdrantRetrieval", "GeminiIVE", "OpenAIIVE", "MIVEComparator",
            "DeterministicRenderer", "PricingTable", "SystemClock",
            "Path", "os", "json", "uuid", "datetime", "time", "random",
        ):
            assert not hasattr(module, name), (module.__name__, name)


# --------------------------------------------------------------------- #
# T18-23  the deferred later layers are not named in production source
#
# The frozen production-unwired proofs detect any production file naming those
# layers. This asserts the same law from the TASK 18 side, so a future edit to
# this package cannot break those proofs silently.
# --------------------------------------------------------------------- #
def test_t18_23_production_source_names_no_deferred_layer():
    deferred = ("model" + "_context", "response" + "_evidence")
    for path in MODULE_PATHS:
        source = path.read_text(encoding="utf-8")
        for token in deferred:
            assert token not in source, (path.name, token)
    # the scan is not vacuous: a token that IS present is detected the same way
    assert "governed_evidence" in Path(models.__file__).read_text(encoding="utf-8")
