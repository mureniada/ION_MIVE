"""TASK 18.2 runtime test: Turn Record materialization on the success path.

Scope is deliberately narrow: this covers RUNTIME WIRING only — that a real
`Core.ask()` closes a successful turn by materializing exactly one immutable
`TurnRecord`, that the record binds the turn's real facts, and that nothing
else moved. The pure contract is proven in `test_turn_record_v0_1.py`.

It asserts no governance, admission, provenance or comparison semantics. Those
stay owned and tested by the frozen modules, which TASK 18 does not touch.
Every native object below is a stand-in, so a passing run proves the WIRING,
not the governance.

The fixture is a real `Core` over stand-in seams, driving a real `CoreAdapter`
and the real frozen governed-evidence materializer: only the seams are fake,
`ask()` itself is genuine.
"""

from __future__ import annotations

import builtins
import logging
from types import SimpleNamespace

import pytest

from app.core import errors
from app.core.models import AskResult
import app.core.orchestrator as orch
import app.modules.core_adapter.facade as facade
from app.modules.core_adapter import CoreAdapter
from app.modules.governed_evidence import (
    GovernedEvidenceMaterializationError,
    GovernedEvidenceSet,
)
from app.modules.model_gateway import ModelGateway
from app.modules.turn_record import TurnClosureState, TurnRecord

VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"

# The models the two engine stand-ins are CONFIGURED with. Named once so the
# construction below and the requested-model assertion read the same fact from
# the same place; Core holds no provider-named engine field to read it back
# from now that execution goes through the Model Gateway.
GEMINI_MODEL = "gemini-3.1-flash-lite"
OPENAI_MODEL = "gpt-5.4-mini"


# --------------------------------------------------------------------- #
# stand-ins. Nothing here governs, retrieves or reasons; these carry fields
# and record calls, so the assertions below observe wiring, not behaviour.
# --------------------------------------------------------------------- #
class _Clock:
    """Distinct, ordered values on both channels, so call SITES are provable."""

    def __init__(self, *, iso_error=None, iso_fails_from=0):
        self.monotonic_calls = 0
        self.iso_calls = 0
        self.iso_log: list[str] = []
        self.iso_error = iso_error
        self.iso_fails_from = iso_fails_from

    def monotonic_ms(self):
        self.monotonic_calls += 1
        return float(self.monotonic_calls)

    def now_iso(self):
        if self.iso_error is not None and self.iso_calls >= self.iso_fails_from:
            raise self.iso_error
        value = f"ISO-{self.iso_calls}"
        self.iso_calls += 1
        self.iso_log.append(value)
        return value


class _Retrieval:
    def __init__(self, candidate_ids, *, error=None):
        self._candidate_ids = tuple(candidate_ids)
        self.error = error

    def retrieve(self, question, top_k):
        if self.error is not None:
            raise self.error
        return [
            SimpleNamespace(document_id=cid, content="body") for cid in self._candidate_ids
        ]


class _Builder:
    def __init__(self, pack, *, error=None):
        self.pack = pack
        self.error = error

    def build(self, question, evidence):
        if self.error is not None:
            raise self.error
        return self.pack


class _Bridge:
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
    """Carries the full IVEPort identity surface a real adapter exposes."""

    def __init__(self, engine_id, provider, model, *, error=None):
        self._engine_id = engine_id
        self.provider = provider
        self.model = model
        self.error = error
        self.calls = 0

    @property
    def engine_id(self):
        return self._engine_id

    def run(self, pack):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return _report(self._engine_id, self.provider, self.model)


class _Mive:
    def __init__(self, order=None, error=None):
        self.calls = 0
        self._order = order
        self.error = error

    def compare(self, reports):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self._order is not None:
            self._order.append("mive")
        # shaped as the real MIVEResult serializes: to_dict() carries the status
        return SimpleNamespace(
            to_dict=lambda: {
                "overall_status": "partial_agreement",
                "engine_ids": ["gemini", "openai"],
            }
        )


class _Renderer:
    def __init__(self, order=None, clock=None, error=None):
        self.calls = 0
        self._order = order
        self._clock = clock
        self.error = error
        self.iso_calls_at_render = None

    def render(self, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self._order is not None:
            self._order.append("render")
        if self._clock is not None:
            self.iso_calls_at_render = self._clock.iso_calls
        return {"primary_answer": "answer"}


class _Pricing:
    def __init__(self, error=None):
        self.error = error

    def estimate_cost(self, model, input_tokens, output_tokens):
        if self.error is not None:
            raise self.error
        return 0.5


def _report(engine_id, provider, model):
    return SimpleNamespace(
        engine_id=engine_id,
        provider=provider,
        model=model,
        usage=SimpleNamespace(
            input_tokens=11, output_tokens=5, latency_ms=1.5, usage_is_estimated=False
        ),
        to_contract_dict=lambda: {"engine_id": engine_id, "provider": provider},
    )


def _native_for(candidate_ids):
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


def _adapter(bridge):
    """A real CoreAdapter over a stand-in bridge — the facade logic is genuine."""
    adapter = CoreAdapter.__new__(CoreAdapter)
    adapter._bridge = bridge
    return adapter


def _pack(document_ids):
    return SimpleNamespace(
        context_pack_id="CP-001",
        documents=[
            SimpleNamespace(document_id=did, content="body") for did in document_ids
        ],
        metadata={"included_documents": len(tuple(document_ids))},
    )


def _settings():
    """Carries the settings surface `ask()` actually reads — nothing more."""
    return SimpleNamespace(
        default_top_k=1,
        context_char_budget=60000,
        qdrant_collection="ion_corpus_v1",
    )


def _core(
    *, retrieved=("EV-1", "EV-2", "EV-3"), submitted=("EV-1", "EV-2"),
    bridge=None, order=None, gemini_error=None, openai_error=None,
    renderer_error=None, retrieval_error=None, builder_error=None,
    mive_error=None, pricing_error=None, clock=None,
):
    """A real Core over stand-ins: only the seams are fake, ask() is genuine."""
    pack = _pack(submitted)
    clock = _Clock() if clock is None else clock
    renderer = _Renderer(order=order, clock=clock, error=renderer_error)

    core = orch.Core.__new__(orch.Core)
    core._settings = _settings()
    core._clock = clock
    core._retrieval = _Retrieval(retrieved, error=retrieval_error)
    core._build = _Builder(pack, error=builder_error)
    core._core_adapter = _adapter(_Bridge() if bridge is None else bridge)
    # The stand-ins are registered in a real ModelGateway — the same
    # provider-neutral boundary production uses — under the identity each one
    # states about itself. Only the seam changes; ask() is still genuine.
    core._model_gateway = ModelGateway(
        {
            "gemini": _Engine("gemini", "gemini", GEMINI_MODEL, error=gemini_error),
            "openai": _Engine("openai", "openai", OPENAI_MODEL, error=openai_error),
        }
    )
    core._mive = _Mive(order=order, error=mive_error)
    core._renderer = renderer
    core._pricing = _Pricing(error=pricing_error)
    return core, pack, clock, renderer


def _patch_gate(monkeypatch, candidate_ids, order=None):
    native = _native_for(candidate_ids)

    def gate(**kwargs):
        if order is not None:
            order.append("governance")
        return native

    monkeypatch.setattr(facade, "run_runtime_admission_gate", gate)


def _spy_governed(monkeypatch, order=None):
    """Observe the frozen TASK 13 materializer without replacing its decision."""
    outputs = []
    real = orch.materialize_governed_evidence_set

    def spy(source):
        produced = real(source)
        if order is not None:
            order.append("governed_evidence")
        outputs.append(produced)
        return produced

    monkeypatch.setattr(orch, "materialize_governed_evidence_set", spy)
    return outputs


def _spy_turn_record(monkeypatch, order=None):
    """Observe the TASK 18 materializer without replacing what it produces."""
    inputs, outputs = [], []
    real = orch.materialize_turn_record

    def spy(**kwargs):
        inputs.append(kwargs)
        if order is not None:
            order.append("turn_record")
        produced = real(**kwargs)
        outputs.append(produced)
        return produced

    monkeypatch.setattr(orch, "materialize_turn_record", spy)
    return inputs, outputs


def _spy_failed_turn_record(monkeypatch, *, replacement=None):
    """Observe the FAILED materializer without replacing what it produces."""
    inputs, outputs = [], []
    real = orch.materialize_failed_turn_record

    def spy(**kwargs):
        inputs.append(kwargs)
        if replacement is not None:
            return replacement(**kwargs)
        produced = real(**kwargs)
        outputs.append(produced)
        return produced

    monkeypatch.setattr(orch, "materialize_failed_turn_record", spy)
    return inputs, outputs


def _spy_both(monkeypatch):
    """Both closure paths at once, so exactly-one can be asserted across them."""
    completed = _spy_turn_record(monkeypatch)
    failed = _spy_failed_turn_record(monkeypatch)
    return completed[1], failed[1]


# --------------------------------------------------------------------- #
# T18-R01  one successful turn, exactly one record
# --------------------------------------------------------------------- #
def test_t18_r01_a_successful_turn_materializes_exactly_one_turn_record(monkeypatch):
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    inputs, outputs = _spy_turn_record(monkeypatch)

    result = core.ask("Question", top_k=3)

    assert len(inputs) == 1
    assert len(outputs) == 1
    record = outputs[0]
    assert isinstance(record, TurnRecord)
    assert record.closure_state is TurnClosureState.COMPLETED
    assert record.failure is None
    assert isinstance(result, AskResult)
    assert result.status == "success"


# --------------------------------------------------------------------- #
# T18-R02  the record binds the turn's own identity
# --------------------------------------------------------------------- #
def test_t18_r02_turn_id_equals_the_ask_result_request_id(monkeypatch):
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _, outputs = _spy_turn_record(monkeypatch)

    result = core.ask("Question", top_k=3)
    record = outputs[0]

    assert record.turn_id == result.request_id
    assert record.turn_identity_basis == "CORE_ASK_REQUEST_ID_V0_1"
    # the same identity the governed basis was bound under
    assert record.governed_evidence.question_id == result.request_id


# --------------------------------------------------------------------- #
# T18-R03 / T18-R04  ordering: after governance, after the gate, after render
# --------------------------------------------------------------------- #
def test_t18_r03_r04_record_is_materialized_after_the_gate_and_after_render(monkeypatch):
    order = []
    core, _, _, _ = _core(order=order)
    _patch_gate(monkeypatch, ("EV-1", "EV-2"), order=order)
    _spy_governed(monkeypatch, order=order)
    _spy_turn_record(monkeypatch, order=order)

    core.ask("Question", top_k=3)

    assert order == ["governance", "governed_evidence", "mive", "render", "turn_record"]


def test_t18_r04b_a_failing_renderer_closes_the_turn_as_failed(monkeypatch):
    """Superseded TASK 18.2 expectation: this used to assert NO record."""
    boom = RuntimeError("renderer fault")
    core, _, _, _ = _core(renderer_error=boom)
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    completed, failed = _spy_both(monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=3)

    assert excinfo.value is boom          # the original failure still wins
    assert completed == []                # never recorded as a success
    assert len(failed) == 1
    assert failed[0].closure_state is TurnClosureState.FAILED


# --------------------------------------------------------------------- #
# T18-R05  the bound basis IS the real governed evidence set of this turn
# --------------------------------------------------------------------- #
def test_t18_r05_the_bound_basis_is_the_real_materialized_governed_set(monkeypatch):
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    governed = _spy_governed(monkeypatch)
    inputs, outputs = _spy_turn_record(monkeypatch)

    core.ask("Question", top_k=3)

    ges = governed[0]
    assert isinstance(ges, GovernedEvidenceSet)
    # identity, not merely an equal-looking object
    assert inputs[0]["governed_basis"] is ges

    binding = outputs[0].governed_evidence
    assert binding.governed_evidence_set_id == ges.governed_evidence_set_id
    assert binding.governed_evidence_set_version == ges.governed_evidence_set_version
    assert binding.backend_id == "TEST-BACKEND"
    assert binding.mapping_profile_id == "TEST-PROFILE"
    assert binding.adapter_id == "ION_CORE_ADAPTER_FACADE_V0_1"
    assert binding.adapter_version == "0.1"
    # the real accounting of this turn: 3 retrieved, 2 submitted, 2 governed
    assert (binding.retrieved_count, binding.submitted_count, binding.governed_count) == (3, 2, 2)

    # no governed evidence is carried into the record itself
    body = repr(outputs[0])
    assert "GovernedEvidenceSet" not in body
    assert "ADMITTED" not in body


# --------------------------------------------------------------------- #
# T18-R06  the record names the turn's real Context Pack
# --------------------------------------------------------------------- #
def test_t18_r06_context_pack_id_matches_the_real_context_pack(monkeypatch):
    core, pack, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _, outputs = _spy_turn_record(monkeypatch)

    core.ask("Question", top_k=3)
    record = outputs[0]

    assert record.context_pack_id == pack.context_pack_id == "CP-001"
    assert record.governed_evidence.context_pack_id == pack.context_pack_id


# --------------------------------------------------------------------- #
# T18-R07 / T18-R08  both executions are represented truthfully
# --------------------------------------------------------------------- #
def test_t18_r07_r08_both_model_executions_are_recorded_truthfully(monkeypatch):
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _, outputs = _spy_turn_record(monkeypatch)

    result = core.ask("Question", top_k=3)
    executions = outputs[0].model_executions

    assert len(executions) == 2
    assert [e.engine_id for e in executions] == ["gemini", "openai"]
    assert [e.provider for e in executions] == ["gemini", "openai"]
    # the models the adapters were actually configured with, in order
    assert [e.requested_model for e in executions] == [
        GEMINI_MODEL,
        OPENAI_MODEL,
    ]
    assert [e.requested_model for e in executions] == [
        "gemini-3.1-flash-lite",
        "gpt-5.4-mini",
    ]

    # the figures agree with the Product's own telemetry for the same turn
    for execution, reported in zip(executions, result.metrics["providers"], strict=True):
        assert execution.provider == reported["provider"]
        assert execution.requested_model == reported["model"]
        assert execution.input_tokens == reported["input_tokens"]
        assert execution.output_tokens == reported["output_tokens"]
        assert execution.latency_ms == reported["latency_ms"]
        assert execution.estimated_cost == reported["estimated_cost"]
        assert execution.usage_is_estimated == reported["usage_is_estimated"]

    # no provider-reported model identity is claimed anywhere
    for execution in executions:
        assert not hasattr(execution, "reported_model")


# --------------------------------------------------------------------- #
# T18-R09 / T18-R10 / T18-R11  the record stays out of every output channel
# --------------------------------------------------------------------- #
def test_t18_r09_the_record_is_not_carried_into_ask_result(monkeypatch):
    import dataclasses

    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _, outputs = _spy_turn_record(monkeypatch)

    result = core.ask("Question", top_k=3)

    # the frozen AskResult shape is untouched
    assert {f.name for f in dataclasses.fields(AskResult)} == {
        "request_id", "question", "status", "rendered", "mive_result",
        "ive_reports", "metrics", "error_stage", "message",
    }
    body = result.to_dict()
    assert "ION_TURN_RECORD_V0_1" not in repr(body)
    assert "turn_id" not in repr(body)
    for value in body.values():
        assert not isinstance(value, TurnRecord)
    assert outputs[0] not in body.values()


def test_t18_r10_the_record_is_not_carried_into_the_rendered_output(monkeypatch):
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _spy_turn_record(monkeypatch)

    result = core.ask("Question", top_k=3)

    assert result.rendered == {"primary_answer": "answer"}
    assert "ION_TURN_RECORD_V0_1" not in repr(result.rendered)


def test_t18_r11_r12_the_progress_stream_is_byte_identical(monkeypatch):
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _spy_turn_record(monkeypatch)

    seen = []
    core.ask("Question", top_k=3, progress=lambda stage, status: seen.append((stage, status)))

    # exact sequence equality: a new closure event would show up here
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
    assert not any("turn" in stage for stage, _ in seen)


# --------------------------------------------------------------------- #
# T18-R13  nothing is written, stored or logged
# --------------------------------------------------------------------- #
def test_t18_r13_no_filesystem_write_or_log_record_occurs(monkeypatch, caplog):
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _spy_turn_record(monkeypatch)

    def refuse_open(*args, **kwargs):
        raise AssertionError(f"a turn must open no file: {args!r}")

    monkeypatch.setattr(builtins, "open", refuse_open)

    with caplog.at_level(logging.DEBUG):
        core.ask("Question", top_k=3)

    assert caplog.records == []


# --------------------------------------------------------------------- #
# T18-R14  the closing timestamp comes from the injected clock, after render
# --------------------------------------------------------------------- #
def test_t18_r14_turn_closed_at_comes_from_the_clock_after_render(monkeypatch):
    core, _, clock, renderer = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _, outputs = _spy_turn_record(monkeypatch)

    core.ask("Question", top_k=3)
    record = outputs[0]

    # every timestamp in the record came from the injected clock
    assert record.turn_started_at in clock.iso_log
    assert record.turn_closed_at in clock.iso_log

    # turn start is the first reading, taken before validation
    assert record.turn_started_at == "ISO-0"
    assert clock.iso_log[0] == record.turn_started_at

    # the closing reading was taken AFTER the renderer completed
    closed_index = clock.iso_log.index(record.turn_closed_at)
    assert closed_index >= renderer.iso_calls_at_render
    assert closed_index > clock.iso_log.index(record.turn_started_at)
    assert record.turn_closed_at == clock.iso_log[-1]


# --------------------------------------------------------------------- #
# T18-R15  the pipeline span is recorded for exactly what it measures
# --------------------------------------------------------------------- #
def test_t18_r15_pipeline_latency_is_the_existing_pre_render_span(monkeypatch):
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _, outputs = _spy_turn_record(monkeypatch)

    result = core.ask("Question", top_k=3)
    record = outputs[0]

    # the same measured span the Product already reports — no second regime
    assert record.pipeline_latency_ms == result.metrics["total_latency_ms"]
    assert record.retrieval_latency_ms == result.metrics["retrieval_latency_ms"]
    assert record.comparison_latency_ms == result.metrics["comparison_latency_ms"]

    # and it claims nothing end-to-end: the span closes before the renderer,
    # so the record carries no field that could be read as a total turn time
    names = {f.name for f in __import__("dataclasses").fields(record)}
    for overclaim in ("total_latency_ms", "end_to_end_latency_ms", "duration_ms"):
        assert overclaim not in names, overclaim


# --------------------------------------------------------------------- #
# T18-R16  no failure path materializes a record at v0.1
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "make,ask_kwargs",
    [
        pytest.param(lambda: _core(), {"question": "   "}, id="F01-empty-question"),
        pytest.param(lambda: _core(), {"top_k": 0}, id="F02-invalid-top-k"),
        pytest.param(lambda: _core(), {"top_k": "many"}, id="F02b-non-numeric-top-k"),
        pytest.param(
            lambda: _core(retrieval_error=errors.RetrievalError("store down")), {},
            id="F03-retrieval-ion-error",
        ),
        pytest.param(
            lambda: _core(retrieval_error=RuntimeError("socket reset")), {},
            id="F04-retrieval-arbitrary",
        ),
        pytest.param(lambda: _core(retrieved=()), {}, id="F05-zero-retrieval"),
        pytest.param(
            lambda: _core(builder_error=RuntimeError("pack fault")), {},
            id="F06-context-pack",
        ),
        pytest.param(
            lambda: _core(bridge=_Bridge(resolve_error=RuntimeError("qdrant unreachable"))),
            {}, id="F07-operational",
        ),
        pytest.param(
            lambda: _core(bridge=_Bridge(accepted=False, reasons=("R1",))), {},
            id="F08-governance-rejected",
        ),
        pytest.param(
            lambda: _core(gemini_error=RuntimeError("gemini 503")), {}, id="F10-gemini",
        ),
        pytest.param(
            lambda: _core(openai_error=RuntimeError("openai 503")), {}, id="F11-openai",
        ),
        pytest.param(
            lambda: _core(gemini_error=errors.NormalizationError("bad json")), {},
            id="F12-normalization",
        ),
        pytest.param(lambda: _core(mive_error=RuntimeError("mive fault")), {}, id="F13-mive"),
        pytest.param(
            lambda: _core(pricing_error=RuntimeError("pricing fault")), {},
            id="F14-telemetry",
        ),
        pytest.param(
            lambda: _core(renderer_error=RuntimeError("render fault")), {}, id="F15-renderer",
        ),
    ],
)
def test_t18_r16_every_ordinary_failure_closes_with_exactly_one_failed_record(
    monkeypatch, make, ask_kwargs
):
    """GAP-TURN-CLOSURE-01: every started ordinary turn now closes.

    Supersedes the TASK 18.2 expectation, which asserted no record at all.
    """
    core, _, _, _ = make()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    completed, failed = _spy_both(monkeypatch)

    kwargs = {"question": "Question", "top_k": 3}
    kwargs.update(ask_kwargs)

    with pytest.raises(Exception):
        core.ask(**kwargs)

    # exactly one record, and it is unambiguously a failure
    assert completed == [], "a failed turn must never be recorded as COMPLETED"
    assert len(failed) == 1
    record = failed[0]
    assert record.closure_state is TurnClosureState.FAILED
    assert record.failure is not None
    assert record.turn_id
    assert record.turn_started_at and record.turn_closed_at


def test_t18_r16b_the_f09_governed_gate_failure_also_closes(monkeypatch):
    """F09: the governed-evidence gate refuses, so no governed basis exists."""
    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    def refuse(source):
        raise GovernedEvidenceMaterializationError("native record carries no fingerprint")

    monkeypatch.setattr(orch, "materialize_governed_evidence_set", refuse)
    completed, failed = _spy_both(monkeypatch)

    with pytest.raises(errors.ContextPackError):
        core.ask("Question", top_k=3)

    assert completed == []
    assert len(failed) == 1
    record = failed[0]
    assert record.governed_evidence is None       # no basis was ever produced
    assert record.context_pack_id == "CP-001"     # but the pack truthfully existed
    assert record.model_executions == ()


# --------------------------------------------------------------------- #
# T18-R17  exception identity and the governance contracts are unchanged
# --------------------------------------------------------------------- #
def test_t18_r17_operational_failure_still_propagates_the_original_exception(monkeypatch):
    boom = RuntimeError("qdrant unreachable")
    core, _, _, _ = _core(bridge=_Bridge(resolve_error=boom))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_turn_record(monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=3)

    assert excinfo.value is boom  # identity, not merely the same type


def test_t18_r17b_both_governance_rejection_messages_are_unchanged(monkeypatch):
    core, _, _, _ = _core(bridge=_Bridge(accepted=False, reasons=("R1", "R2")))
    _spy_turn_record(monkeypatch)
    with pytest.raises(errors.ContextPackError) as excinfo:
        core.ask("Question", top_k=3)
    assert str(excinfo.value) == "Runtime evidence bridge rejected: R1|R2"

    core, _, _, _ = _core()

    def rejecting_gate(**kwargs):
        raise ValueError("blocked")

    monkeypatch.setattr(facade, "run_runtime_admission_gate", rejecting_gate)
    with pytest.raises(errors.ContextPackError) as excinfo:
        core.ask("Question", top_k=3)
    assert str(excinfo.value) == "Runtime admission gate rejected: blocked"


# --------------------------------------------------------------------- #
# T18-R18  a refused record does not become a silently successful turn
# --------------------------------------------------------------------- #
# --------------------------------------------------------------------- #
# T18-R19 .. T18-R26  stage truthfulness, masking, recursion, BaseException
# --------------------------------------------------------------------- #
def _close(monkeypatch, **core_kwargs):
    """Drive one failing turn and hand back the FAILED record it produced."""
    ask_kwargs = core_kwargs.pop("ask_kwargs", {})
    core, _, _, _ = _core(**core_kwargs)
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    completed, failed = _spy_both(monkeypatch)
    kwargs = {"question": "Question", "top_k": 3}
    kwargs.update(ask_kwargs)
    with pytest.raises(Exception) as excinfo:
        core.ask(**kwargs)
    assert completed == []
    assert len(failed) == 1
    return failed[0], excinfo.value


def test_t18_r19_f01_records_only_what_a_started_turn_is_guaranteed_to_hold(monkeypatch):
    record, exc = _close(monkeypatch, ask_kwargs={"question": "   "})

    assert record.question is None                      # never accepted
    assert record.configuration.effective_top_k is None
    assert record.retrieval_latency_ms is None
    assert record.comparison_latency_ms is None
    assert record.pipeline_latency_ms is None
    assert record.context_pack_id is None
    assert record.governed_evidence is None
    assert record.model_executions == ()
    assert record.mive_overall_status is None
    # the failure itself is a Product error, so its stage and controlled text stand
    assert record.failure.error_stage == errors.STAGE_CONFIGURATION
    assert record.failure.error_type == "IonError"
    assert record.failure.error_message == exc.message


def test_t18_r20_f02_rejects_top_k_so_none_was_ever_effective(monkeypatch):
    record, _ = _close(monkeypatch, ask_kwargs={"top_k": 0})

    assert record.question == "Question"                # accepted before top_k
    assert record.configuration.effective_top_k is None  # computed, then REJECTED
    assert record.failure.error_stage == errors.STAGE_CONFIGURATION


def test_t18_r21_f02b_non_numeric_top_k_has_no_stage_and_no_message(monkeypatch):
    record, exc = _close(monkeypatch, ask_kwargs={"top_k": "many"})

    assert isinstance(exc, (ValueError, TypeError))
    assert record.question == "Question"
    assert record.configuration.effective_top_k is None
    # not an IonError: no stage is invented, and its text is not disclosed
    assert record.failure.error_stage is None
    assert record.failure.error_type == type(exc).__name__
    assert record.failure.error_message is None


def test_t18_r22_f05_records_no_retrieval_span_that_was_never_measured(monkeypatch):
    record, _ = _close(monkeypatch, retrieved=())

    # the span is measured only AFTER a non-empty result, so it does not exist
    assert record.retrieval_latency_ms is None          # never 0.0
    assert record.configuration.effective_top_k == 3
    assert record.context_pack_id is None
    assert record.failure.error_stage == errors.STAGE_RETRIEVAL


@pytest.mark.parametrize(
    "core_kwargs,expect_stage",
    [
        ({"bridge": _Bridge(resolve_error=RuntimeError("qdrant unreachable"))}, None),
        ({"bridge": _Bridge(accepted=False, reasons=("R1",))}, errors.STAGE_CONTEXT_PACK),
    ],
    ids=["F07-operational", "F08-rejected"],
)
def test_t18_r23_f07_f08_have_a_context_pack_but_no_governed_basis(
    monkeypatch, core_kwargs, expect_stage
):
    record, _ = _close(monkeypatch, **core_kwargs)

    assert record.context_pack_id == "CP-001"   # the pack truthfully existed
    assert record.governed_evidence is None     # governance never completed
    assert record.model_executions == ()
    assert record.failure.error_stage == expect_stage


def test_t18_r24_f10_has_a_governed_basis_and_no_completed_execution(monkeypatch):
    record, _ = _close(monkeypatch, gemini_error=RuntimeError("gemini 503"))

    assert record.governed_evidence is not None
    assert record.governed_evidence.governed_count == 2
    assert record.model_executions == ()        # the failed attempt has no binding
    assert record.mive_overall_status is None
    assert record.failure.error_stage == errors.STAGE_GEMINI


def test_t18_r25_f11_binds_only_the_completed_gemini_without_pricing(monkeypatch):
    record, _ = _close(monkeypatch, openai_error=RuntimeError("openai 503"))

    assert record.governed_evidence is not None
    assert len(record.model_executions) == 1
    gemini = record.model_executions[0]
    assert gemini.engine_id == "gemini"
    assert gemini.provider == "gemini"
    assert gemini.requested_model == "gemini-3.1-flash-lite"
    # observed usage is recorded; cost was never computed and is NOT computed here
    assert gemini.input_tokens == 11
    assert gemini.output_tokens == 5
    assert gemini.latency_ms == 1.5
    assert gemini.estimated_cost is None
    # the engine that failed is named by the stage, never by a binding
    assert record.failure.error_stage == errors.STAGE_OPENAI
    assert [e.engine_id for e in record.model_executions] == ["gemini"]


def test_t18_r26_f13_f14_f15_record_progressively_more(monkeypatch):
    # F13 — MIVE failed: both engines completed, no comparison outcome
    record, _ = _close(monkeypatch, mive_error=RuntimeError("mive fault"))
    assert len(record.model_executions) == 2
    assert record.mive_overall_status is None
    assert record.comparison_latency_ms is None
    assert record.pipeline_latency_ms is None
    assert record.failure.error_stage == errors.STAGE_MIVE

    # F14 — telemetry failed: the comparison outcome is held, the span is not
    record, _ = _close(monkeypatch, pricing_error=RuntimeError("pricing fault"))
    assert record.mive_overall_status == "partial_agreement"
    assert record.comparison_latency_ms is not None
    assert record.pipeline_latency_ms is None     # measured after telemetry
    # both engines DID complete, so both are bound from their observed usage;
    # pricing never succeeded, so cost is absent rather than computed here
    assert len(record.model_executions) == 2
    assert all(e.estimated_cost is None for e in record.model_executions)
    assert all(e.input_tokens == 11 for e in record.model_executions)
    assert record.failure.error_stage is None     # unguarded: no stage to claim

    # F15 — renderer failed: everything up to rendering is held
    record, _ = _close(monkeypatch, renderer_error=RuntimeError("render fault"))
    assert len(record.model_executions) == 2
    assert record.mive_overall_status == "partial_agreement"
    assert record.pipeline_latency_ms is not None
    assert record.failure.error_stage is None     # no invented stage
    assert record.failure.error_type == "RuntimeError"
    assert record.failure.error_message is None


def test_t18_r27_a_secondary_recording_failure_never_masks_the_original(monkeypatch):
    """The backstop: M is suppressed, E propagates, and no retry happens."""
    # the operational path is where the runtime PINS object identity
    boom = RuntimeError("qdrant unreachable")
    core, _, _, _ = _core(bridge=_Bridge(resolve_error=boom))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)

    secondary = RuntimeError("the recorder itself is broken")

    def explode(**kwargs):
        raise secondary

    inputs, _ = _spy_failed_turn_record(monkeypatch, replacement=explode)

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=3)

    assert excinfo.value is boom            # the ORIGINAL failure, by identity
    assert excinfo.value is not secondary
    assert len(inputs) == 1                 # attempted once, never retried


def test_t18_r28_a_clock_that_refuses_during_closure_never_masks_the_original(monkeypatch):
    """The closing timestamp is inside the backstop (no synthetic timestamp)."""
    boom = RuntimeError("qdrant unreachable")
    clock = _Clock(iso_error=RuntimeError("clock unavailable"), iso_fails_from=1)
    core, _, _, _ = _core(bridge=_Bridge(resolve_error=boom), clock=clock)
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _, failed = _spy_both(monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=3)

    assert excinfo.value is boom
    assert failed == []                     # no record, and no fabricated time


def test_t18_r29_a_base_exception_bypasses_the_failure_closure(monkeypatch):
    """Process control is not an ordinary Product turn failure."""
    core, _, _, _ = _core(renderer_error=KeyboardInterrupt())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    completed, failed = _spy_both(monkeypatch)

    seen = []
    with pytest.raises(KeyboardInterrupt):
        core.ask("Question", top_k=3,
                 progress=lambda stage, status: seen.append((stage, status)))

    assert completed == []
    assert failed == []                     # not recorded as a failed turn
    assert ("answer", "ready") not in seen   # and no closure event was emitted


def test_t18_r30_a_failed_turn_emits_no_new_progress_event(monkeypatch):
    core, _, _, _ = _core(mive_error=RuntimeError("mive fault"))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)
    _spy_both(monkeypatch)

    seen = []
    with pytest.raises(errors.MiveError):
        core.ask("Question", top_k=3,
                 progress=lambda stage, status: seen.append((stage, status)))

    # the pre-existing failure stream, unchanged: no closure event, no answer
    assert seen == [
        ("retrieval", "started"), ("retrieval", "done"),
        ("context_pack", "started"), ("context_pack", "done"),
        (errors.STAGE_GEMINI, "started"), (errors.STAGE_GEMINI, "done"),
        (errors.STAGE_OPENAI, "started"), (errors.STAGE_OPENAI, "done"),
        ("mive", "started"),
    ]
    assert ("answer", "ready") not in seen


def test_t18_r18_a_refused_record_is_not_remapped_into_a_success(monkeypatch):
    from app.modules.turn_record import TurnRecordMaterializationError

    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)

    cause = TurnRecordMaterializationError("turn_id must be a non-empty string")

    def refuse(**kwargs):
        raise cause

    monkeypatch.setattr(orch, "materialize_turn_record", refuse)

    with pytest.raises(TurnRecordMaterializationError) as excinfo:
        core.ask("Question", top_k=3)

    # the refusal propagates untouched: not caught, not remapped onto a core
    # error stage, and never converted into an apparently successful AskResult
    assert excinfo.value is cause


def test_t18_r31_f16_does_not_recursively_record_its_own_failure(monkeypatch):
    """TURN_RECORD_SELF_FAILURE_BOUNDARY — intentional, not a missing branch."""
    from app.modules.turn_record import TurnRecordMaterializationError

    core, _, _, _ = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    _spy_governed(monkeypatch)

    cause = TurnRecordMaterializationError("turn_id must be a non-empty string")

    def refuse(**kwargs):
        raise cause

    monkeypatch.setattr(orch, "materialize_turn_record", refuse)
    failed_inputs, _ = _spy_failed_turn_record(monkeypatch)

    with pytest.raises(TurnRecordMaterializationError) as excinfo:
        core.ask("Question", top_k=3)

    assert excinfo.value is cause
    # the attempt guard was already spent by the success path, so the closure
    # handler makes NO second attempt: the mechanism never records itself
    assert failed_inputs == []
