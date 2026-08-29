"""TASK 14 contract test: the GovernedEvidenceSet runtime gate (v0.1).

Scope is deliberately narrow: this covers RUNTIME ORDER AND GATING only — that
the frozen TASK 13 materializer now runs as a mandatory fail-closed step between
Core Adapter governance and the first IVE engine, and that nothing else moved.

It asserts no admission, provenance, fingerprint or governed-evidence semantics.
Those stay owned and tested by the frozen modules (`test_governed_evidence_set_v0_1.py`,
`test_core_adapter_facade_v0_1.py`), which TASK 14 does not touch. Every native
object below is a stand-in, so a passing run proves the ORDER, not the governance.

Ordering is proven by observed call order over a real `Core` driving a real
`CoreAdapter` — never by source-text inspection — so it survives any later
reformatting of the modules under test.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from app.core import errors
from app.core.models import AskResult
import app.core.orchestrator as orch
import app.modules.core_adapter.facade as facade
from app.modules.core_adapter import CoreAdapter
from app.modules.governed_evidence import (
    GOVERNED_EVIDENCE_SET_ID,
    GovernanceDisposition,
    GovernedEvidenceMaterializationError,
    GovernedEvidenceSet,
    MaterializationInput,
)
from app.modules.model_gateway import ModelGateway


VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"


# --------------------------------------------------------------------- #
# stand-ins. Nothing here governs, retrieves or reasons; these carry fields
# and record calls, so the assertions below observe order, not behaviour.
# --------------------------------------------------------------------- #
class _Clock:
    def __init__(self):
        self.value = 0

    def monotonic_ms(self):
        self.value += 1
        return self.value

    def now_iso(self):
        return "2026-08-27T00:00:00Z"


class _Retrieval:
    def __init__(self, candidate_ids):
        self.count = 0
        self._candidate_ids = tuple(candidate_ids)

    def retrieve(self, question, top_k):
        self.count += 1
        return [
            SimpleNamespace(document_id=candidate_id, content="body")
            for candidate_id in self._candidate_ids
        ]


class _Builder:
    def __init__(self, pack):
        self.count = 0
        self.pack = pack

    def build(self, question, evidence):
        self.count += 1
        return self.pack


class _Bridge:
    """Stands in for the frozen runtime evidence bridge, inside the adapter."""

    backend_id = "TEST-BACKEND"
    mapping_profile_id = "TEST-PROFILE"

    def __init__(self, *, accepted=True, reasons=(), resolve_error=None):
        self.accepted = accepted
        self.reasons = reasons
        self.resolve_error = resolve_error
        self.request = SimpleNamespace()

    def resolve(self, evidence):
        if self.resolve_error is not None:
            raise self.resolve_error
        return ()

    def build_request(self, *args, **kwargs):
        return SimpleNamespace(
            accepted=self.accepted, request=self.request, reasons=self.reasons
        )


class _Engine:
    # `engine_id` is the identity the Model Gateway registers this stand-in
    # under, stated by the engine itself exactly as a real adapter states it
    # (core/ports.py IVEPort). Fidelity only — no assertion below depends on it.
    def __init__(self, provider):
        self.engine_id = provider
        self.provider = provider
        self.calls = 0

    def run(self, pack):
        self.calls += 1
        return _report(self.provider)


class _Mive:
    def __init__(self):
        self.calls = 0

    def compare(self, reports):
        self.calls += 1
        return SimpleNamespace(to_dict=lambda: {"overall_status": "compared"})


class _Renderer:
    def __init__(self):
        self.calls = 0

    def render(self, **kwargs):
        self.calls += 1
        return {"primary_answer": "answer"}


class _Pricing:
    def estimate_cost(self, model, input_tokens, output_tokens):
        return 0.5


def _report(provider):
    # `engine_id` mirrors the real IVEReport, which always carries one
    # (core/models.py). Fidelity only — no assertion below depends on it.
    return SimpleNamespace(
        engine_id=provider,
        provider=provider,
        model=provider + "-model",
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            latency_ms=1.0,
            usage_is_estimated=False,
        ),
        to_contract_dict=lambda: {"provider": provider},
    )


# --------------------------------------------------------------------- #
# native governance stand-ins, shaped as RuntimeAdmissionGateResult returns
# them. These are field carriers, not a governance engine.
# --------------------------------------------------------------------- #
def _native_for(candidate_ids):
    return SimpleNamespace(
        records=tuple(
            SimpleNamespace(
                evidence_id=candidate_id,
                status=VERIFIED,
                validation_id="VAL-" + candidate_id,
                fingerprint=SimpleNamespace(
                    algorithm="SHA256",
                    hash="FP-" + candidate_id,
                    content_id=candidate_id,
                ),
            )
            for candidate_id in candidate_ids
        ),
        validations=tuple(
            SimpleNamespace(
                validation_id="VAL-" + candidate_id,
                evidence_id=candidate_id,
                result=PASS,
                blocking_reasons=(),
                evidence_fingerprint_hash="FP-" + candidate_id,
            )
            for candidate_id in candidate_ids
        ),
        transitions=tuple(
            SimpleNamespace(
                transition_id="TR-" + candidate_id,
                evidence_id=candidate_id,
                from_status=PENDING,
                to_status=VERIFIED,
                validation_id="VAL-" + candidate_id,
            )
            for candidate_id in candidate_ids
        ),
    )


def _adapter(bridge):
    """A real CoreAdapter over a stand-in bridge — the facade logic is genuine."""
    adapter = CoreAdapter.__new__(CoreAdapter)
    adapter._bridge = bridge
    return adapter


def _pack(document_ids):
    return SimpleNamespace(
        context_pack_id="CP-001",
        documents=[
            SimpleNamespace(document_id=document_id, content="body")
            for document_id in document_ids
        ],
        metadata={"included_documents": len(tuple(document_ids))},
    )


def _core(*, retrieved=("EV-1",), submitted=None, bridge=None):
    """A real Core over stand-ins: only the seams are fake, ask() is genuine.

    The two engine stand-ins are registered in a real ModelGateway — the same
    provider-neutral boundary production uses — and returned alongside the Core
    so that the call assertions below still observe the ENGINES themselves,
    unchanged in meaning. Core holds no provider-named engine field to reach.
    """
    submitted = retrieved if submitted is None else submitted
    pack = _pack(submitted)
    core = orch.Core.__new__(orch.Core)
    # `context_char_budget` / `qdrant_collection` mirror the real Settings,
    # which always carries both (core/config.py). Fidelity only — no assertion
    # below depends on either.
    core._settings = SimpleNamespace(
        default_top_k=1,
        context_char_budget=60000,
        qdrant_collection="ion_corpus_v1",
    )
    core._clock = _Clock()
    core._retrieval = _Retrieval(retrieved)
    core._build = _Builder(pack)
    core._core_adapter = _adapter(_Bridge() if bridge is None else bridge)
    engines = {"gemini": _Engine("gemini"), "openai": _Engine("openai")}
    core._model_gateway = ModelGateway(engines)
    core._mive = _Mive()
    core._renderer = _Renderer()
    core._pricing = _Pricing()
    return core, pack, engines


def _patch_gate(monkeypatch, fn):
    """Patch the admission gate where the Core Adapter imports it."""
    monkeypatch.setattr(facade, "run_runtime_admission_gate", fn)


def _passing_gate_for(candidate_ids):
    native = _native_for(candidate_ids)

    def gate(**kwargs):
        return native

    return gate


def _unreachable_gate(**kwargs):
    raise AssertionError("admission gate must not be reached")


def _spy_materializer(monkeypatch, *, order=None, replacement=None):
    """Observe the frozen materializer without replacing what it decides.

    Returns (inputs, outputs). Unless `replacement` is given the REAL TASK 13
    materializer still runs, so a passing assertion means the real contract
    accepted the input the orchestrator built.
    """
    inputs, outputs = [], []
    real = orch.materialize_governed_evidence_set

    def spy(source):
        inputs.append(source)
        if order is not None:
            order.append("materialize")
        if replacement is not None:
            return replacement(source)
        produced = real(source)
        outputs.append(produced)
        return produced

    monkeypatch.setattr(orch, "materialize_governed_evidence_set", spy)
    return inputs, outputs


def _no_engine(*args, **kwargs):
    raise AssertionError("no IVE engine may run")


# --------------------------------------------------------------------- #
# T14-01  the gate sits between governance and the first engine
# --------------------------------------------------------------------- #
def test_task14_t01_order_is_governance_then_materialize_then_both_engines(monkeypatch):
    order = []
    core, _, engines = _core(retrieved=("EV-1",))

    def gate(**kwargs):
        order.append("governance")
        return _native_for(("EV-1",))

    _patch_gate(monkeypatch, gate)
    _spy_materializer(monkeypatch, order=order)

    def provider(engine, pack, stage, emit):
        order.append(stage)
        return _report(stage)

    core._run_engine = provider

    core.ask("Question", top_k=1)

    assert order == [
        "governance",
        "materialize",
        errors.STAGE_GEMINI,
        errors.STAGE_OPENAI,
    ]


# --------------------------------------------------------------------- #
# T14-02  materialization failure stops the turn before any engine
# --------------------------------------------------------------------- #
def test_task14_t02_materialization_failure_prevents_every_engine_call(monkeypatch):
    core, _, engines = _core(retrieved=("EV-1",))
    _patch_gate(monkeypatch, _passing_gate_for(("EV-1",)))

    def refuse(source):
        raise GovernedEvidenceMaterializationError(
            "native record EV-1 carries no fingerprint"
        )

    _spy_materializer(monkeypatch, replacement=refuse)
    core._run_engine = _no_engine

    with pytest.raises(errors.ContextPackError):
        core.ask("Question", top_k=1)

    # fail-closed all the way down: no engine, no MIVE, no render, no AskResult
    assert engines["gemini"].calls == 0
    assert engines["openai"].calls == 0
    assert core._mive.calls == 0
    assert core._renderer.calls == 0


# --------------------------------------------------------------------- #
# T14-03  GOVERNANCE_REJECTED never reaches the materializer, and both
#         legacy message contracts survive verbatim
# --------------------------------------------------------------------- #
def test_task14_t03_bridge_rejection_never_reaches_the_materializer(monkeypatch):
    core, _, engines = _core(bridge=_Bridge(accepted=False, reasons=("R1", "R2")))
    _patch_gate(monkeypatch, _unreachable_gate)
    inputs, _ = _spy_materializer(monkeypatch)
    core._run_engine = _no_engine

    with pytest.raises(errors.ContextPackError) as excinfo:
        core.ask("Question", top_k=1)

    assert str(excinfo.value) == "Runtime evidence bridge rejected: R1|R2"
    assert inputs == []
    assert engines["gemini"].calls == engines["openai"].calls == 0


def test_task14_t03b_gate_rejection_never_reaches_the_materializer(monkeypatch):
    core, _, engines = _core()

    def rejecting_gate(**kwargs):
        raise ValueError("blocked")

    _patch_gate(monkeypatch, rejecting_gate)
    inputs, _ = _spy_materializer(monkeypatch)
    core._run_engine = _no_engine

    with pytest.raises(errors.ContextPackError) as excinfo:
        core.ask("Question", top_k=1)

    assert str(excinfo.value) == "Runtime admission gate rejected: blocked"
    assert inputs == []
    assert engines["gemini"].calls == engines["openai"].calls == 0


# --------------------------------------------------------------------- #
# T14-04  OPERATIONAL_FAILURE never reaches the materializer, and the
#         original exception is still re-raised by identity
# --------------------------------------------------------------------- #
def test_task14_t04_operational_failure_never_reaches_the_materializer(monkeypatch):
    boom = RuntimeError("qdrant unreachable")
    core, _, engines = _core(bridge=_Bridge(resolve_error=boom))
    _patch_gate(monkeypatch, _unreachable_gate)
    inputs, _ = _spy_materializer(monkeypatch)
    core._run_engine = _no_engine

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=1)

    assert excinfo.value is boom  # identity, not merely the same type
    assert inputs == []
    assert engines["gemini"].calls == engines["openai"].calls == 0


# --------------------------------------------------------------------- #
# T14-05  the input is built from values already in orchestrator scope,
#         including the truncated-pack case
# --------------------------------------------------------------------- #
def test_task14_t05_materialization_input_identity_mapping_is_exact(monkeypatch):
    retrieved = ("EV-1", "EV-2", "EV-3")
    submitted = ("EV-1", "EV-2")  # a truncated Context Pack: a strict subset
    core, pack, engines = _core(retrieved=retrieved, submitted=submitted)
    _patch_gate(monkeypatch, _passing_gate_for(submitted))
    inputs, outputs = _spy_materializer(monkeypatch)

    result = core.ask("Question", top_k=3)

    assert len(inputs) == 1
    source = inputs[0]
    assert isinstance(source, MaterializationInput)

    assert source.outcome_state == "GOVERNANCE_COMPLETE"
    assert source.retrieved_candidate_ids == retrieved
    assert source.submitted_candidate_ids == submitted
    assert set(source.submitted_candidate_ids) < set(source.retrieved_candidate_ids)
    assert source.candidate_count == len(retrieved)
    assert source.governed_count == len(submitted)
    assert source.backend_id == "TEST-BACKEND"
    assert source.mapping_profile_id == "TEST-PROFILE"
    assert source.adapter_id == "ION_CORE_ADAPTER_FACADE_V0_1"
    assert source.adapter_version == "0.1"
    assert source.context_pack_id == pack.context_pack_id
    assert source.context_pack_metadata is pack.metadata
    # the SAME identity the adapter was invoked with, and the one ask() returns
    assert source.question_id == result.request_id


def test_task14_t05b_truncated_pack_accounts_not_submitted_without_a_verdict(monkeypatch):
    retrieved = ("EV-1", "EV-2", "EV-3")
    submitted = ("EV-1", "EV-2")
    core, pack, engines = _core(retrieved=retrieved, submitted=submitted)
    _patch_gate(monkeypatch, _passing_gate_for(submitted))
    _, outputs = _spy_materializer(monkeypatch)

    core.ask("Question", top_k=3)

    ges = outputs[0]
    assert isinstance(ges, GovernedEvidenceSet)
    assert [e.candidate_id for e in ges.admitted] == list(submitted)
    assert {e.disposition for e in ges.admitted} == {GovernanceDisposition.ADMITTED}

    accounting = ges.accounting
    assert accounting.retrieved_ids == retrieved
    assert accounting.submitted_ids == submitted
    assert accounting.governed_ids == submitted
    assert dict(accounting.context_pack_metadata) == pack.metadata

    # the excluded candidate is accounted for, and carries no invented verdict
    entry = accounting.not_submitted[0]
    assert tuple(e.candidate_id for e in accounting.not_submitted) == ("EV-3",)
    assert entry.accounting_state == "NOT_SUBMITTED"
    assert not hasattr(entry, "disposition")
    assert entry.candidate_id not in {e.candidate_id for e in ges.admitted}
    assert ges.rejected == ()
    assert ges.unknown == ()


# --------------------------------------------------------------------- #
# T14-06  the success path is otherwise untouched
# --------------------------------------------------------------------- #
def test_task14_t06_success_path_returns_the_unchanged_ask_result_shape(monkeypatch):
    core, _, engines = _core(retrieved=("EV-1",))
    _patch_gate(monkeypatch, _passing_gate_for(("EV-1",)))
    _spy_materializer(monkeypatch)

    result = core.ask("Question", top_k=1)

    assert isinstance(result, AskResult)
    assert {f.name for f in dataclasses.fields(AskResult)} == {
        "request_id",
        "question",
        "status",
        "rendered",
        "mive_result",
        "ive_reports",
        "metrics",
        "error_stage",
        "message",
    }
    assert result.status == "success"
    assert engines["gemini"].calls == 1
    assert engines["openai"].calls == 1

    # materialized, then deliberately dropped: no governed evidence is carried
    # into the result, in any field, at v0.1
    body = result.to_dict()
    assert GOVERNED_EVIDENCE_SET_ID not in repr(body)
    for value in body.values():
        assert not isinstance(value, GovernedEvidenceSet)


# --------------------------------------------------------------------- #
# T14-07  the authorized compatibility mapping, and its narrowness
# --------------------------------------------------------------------- #
def test_task14_t07_materialization_failure_maps_to_the_authorized_error(monkeypatch):
    core, _, engines = _core(retrieved=("EV-1",))
    _patch_gate(monkeypatch, _passing_gate_for(("EV-1",)))
    cause = GovernedEvidenceMaterializationError(
        "governed_count 1 does not match 0 returned native records"
    )

    def refuse(source):
        raise cause

    _spy_materializer(monkeypatch, replacement=refuse)
    core._run_engine = _no_engine

    with pytest.raises(errors.ContextPackError) as excinfo:
        core.ask("Question", top_k=1)

    assert str(excinfo.value) == "Governed evidence materialization failed: " + str(cause)
    assert excinfo.value.stage == errors.STAGE_CONTEXT_PACK
    assert excinfo.value.__cause__ is cause
    # distinguishable from both legacy governance-rejection contracts
    assert not str(excinfo.value).startswith("Runtime admission gate rejected: ")
    assert not str(excinfo.value).startswith("Runtime evidence bridge rejected: ")


def test_task14_t07b_only_materialization_errors_are_caught(monkeypatch):
    """No broad `Exception` handler: an operational fault still propagates."""
    core, _, engines = _core(retrieved=("EV-1",))
    _patch_gate(monkeypatch, _passing_gate_for(("EV-1",)))
    boom = RuntimeError("materializer host fault")

    def explode(source):
        raise boom

    _spy_materializer(monkeypatch, replacement=explode)
    core._run_engine = _no_engine

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=1)

    assert excinfo.value is boom
    assert engines["gemini"].calls == engines["openai"].calls == 0


# --------------------------------------------------------------------- #
# T14-08  the DEBUG-gated progress contract is unchanged
# --------------------------------------------------------------------- #
def test_task14_t08_no_new_progress_event_is_emitted(monkeypatch):
    core, _, engines = _core(retrieved=("EV-1",))
    _patch_gate(monkeypatch, _passing_gate_for(("EV-1",)))
    _spy_materializer(monkeypatch)

    seen = []
    core.ask("Question", top_k=1, progress=lambda stage, status: seen.append((stage, status)))

    # exact sequence equality: an added gate event would show up here
    assert seen == [
        ("retrieval", "started"),
        ("retrieval", "done"),
        ("context_pack", "started"),
        ("context_pack", "done"),
        (errors.STAGE_GEMINI, "started"),
        (errors.STAGE_GEMINI, "done"),
        (errors.STAGE_OPENAI, "started"),
        (errors.STAGE_OPENAI, "done"),
        ("mive", "started"),
        ("mive", "done"),
        ("answer", "ready"),
    ]
