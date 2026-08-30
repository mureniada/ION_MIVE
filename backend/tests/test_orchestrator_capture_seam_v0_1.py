"""TASK 22.3B1 runtime test: the optional TurnRecord capture seam on Core.ask().

Scope is deliberately narrow: this covers the `on_turn_record` seam itself —
that it is invoked at most once, only once a real TurnRecord exists, that an
observer exception is suppressed (OD22-11), and that every existing Core.ask()
guarantee (AskResult shape, exception identity, pipeline order, TurnRecord
contract shape) is unaffected whether or not a caller supplies one.

It reuses the exact stand-in fixtures and construction pattern from
`test_orchestrator_turn_record_v0_1.py` (TASK 18) — only the seam is new here;
`ask()` itself is exercised genuinely, over fake seams, exactly as that file
already does. No Gemini/OpenAI/provider SDK is reachable from any test below.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from app.core.models import AskResult
import app.core.orchestrator as orch
import app.modules.core_adapter.facade as facade
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import STANDARD_GEMINI
from app.modules.model_gateway import ModelGateway
from app.modules.turn_record import TurnClosureState, TurnRecord

VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"

GEMINI_MODEL = "gemini-3.1-flash-lite"


# --------------------------------------------------------------------- #
# stand-ins — identical in shape to test_orchestrator_turn_record_v0_1.py
# --------------------------------------------------------------------- #
class _Clock:
    def __init__(self):
        self.monotonic_calls = 0
        self.iso_calls = 0

    def monotonic_ms(self):
        self.monotonic_calls += 1
        return float(self.monotonic_calls)

    def now_iso(self):
        value = f"ISO-{self.iso_calls}"
        self.iso_calls += 1
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
    def __init__(self, pack):
        self.pack = pack

    def build(self, question, evidence):
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
    def __init__(self, engine_id, provider, model, *, error=None):
        self._engine_id = engine_id
        self.provider = provider
        self.model = model
        self.error = error

    @property
    def engine_id(self):
        return self._engine_id

    def run(self, pack):
        if self.error is not None:
            raise self.error
        return _report(self._engine_id, self.provider, self.model)


class _Renderer:
    def __init__(self, *, error=None):
        self.error = error

    def render_single(self, **kwargs):
        if self.error is not None:
            raise self.error
        return {"primary_answer": "answer"}


class _Pricing:
    def estimate_cost(self, model, input_tokens, output_tokens):
        return 0.5


class _Mive:
    def compare(self, reports):  # pragma: no cover - unreachable under SINGLE
        raise AssertionError("MIVE must not be invoked under SINGLE")


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
    adapter = CoreAdapter.__new__(CoreAdapter)
    adapter._bridge = bridge
    return adapter


def _pack(document_ids):
    return SimpleNamespace(
        context_pack_id="CP-001",
        documents=[
            SimpleNamespace(
                document_id=did, content="body",
                title="Title-" + did, source="SRC-" + did,
                page=None, chunk_id=None,
            )
            for did in document_ids
        ],
        metadata={"included_documents": len(tuple(document_ids))},
    )


def _settings():
    return SimpleNamespace(
        default_top_k=1,
        context_char_budget=60000,
        qdrant_collection="ion_corpus_v1",
    )


def _core(
    *, retrieved=("EV-1", "EV-2", "EV-3"), submitted=("EV-1", "EV-2"),
    bridge=None, gemini_error=None, retrieval_error=None, renderer_error=None,
):
    """A real Core over stand-ins — identical construction to TASK 18's fixture."""
    pack = _pack(submitted)
    core = orch.Core.__new__(orch.Core)
    core._settings = _settings()
    core._clock = _Clock()
    core._retrieval = _Retrieval(retrieved, error=retrieval_error)
    core._build = _Builder(pack)
    core._core_adapter = _adapter(_Bridge() if bridge is None else bridge)
    core._execution_profile = STANDARD_GEMINI
    core._model_gateway = ModelGateway(
        {"gemini": _Engine("gemini", "gemini", GEMINI_MODEL, error=gemini_error)}
    )
    core._mive = _Mive()
    core._renderer = _Renderer(error=renderer_error)
    core._pricing = _Pricing()
    return core


def _patch_gate(monkeypatch, candidate_ids):
    native = _native_for(candidate_ids)

    def gate(**kwargs):
        return native

    monkeypatch.setattr(facade, "run_runtime_admission_gate", gate)


# --------------------------------------------------------------------- #
# 1. no observer: existing success behavior unchanged
# --------------------------------------------------------------------- #
def test_1_no_observer_success_behavior_unchanged(monkeypatch):
    core = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    result = core.ask("Question", top_k=3)

    assert isinstance(result, AskResult)
    assert result.status == "success"
    assert result.rendered == {"primary_answer": "answer"}


# --------------------------------------------------------------------- #
# 2. success + observer: receives the exact materialized COMPLETED record
# --------------------------------------------------------------------- #
def test_2_success_observer_receives_exact_completed_record_once(monkeypatch):
    core = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    captured = []

    result = core.ask("Question", top_k=3, on_turn_record=captured.append)

    assert len(captured) == 1
    record = captured[0]
    assert isinstance(record, TurnRecord)
    assert record.closure_state is TurnClosureState.COMPLETED
    assert record.turn_id == result.request_id
    assert record.failure is None


# --------------------------------------------------------------------- #
# 3. failure + observer: exact FAILED record once, original exception re-raised
# --------------------------------------------------------------------- #
def test_3_failure_observer_receives_exact_failed_record_and_reraises(monkeypatch):
    # An operational failure (bridge.resolve raises) propagates the ORIGINAL
    # exception untouched (unlike a provider failure, which _run_engine wraps
    # into errors.ProviderError) — the sharpest test of exception identity.
    boom = RuntimeError("qdrant unreachable")
    core = _core(bridge=_Bridge(resolve_error=boom))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    captured = []

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=3, on_turn_record=captured.append)

    assert excinfo.value is boom  # original exception identity preserved
    assert len(captured) == 1
    record = captured[0]
    assert isinstance(record, TurnRecord)
    assert record.closure_state is TurnClosureState.FAILED
    assert record.failure is not None
    assert record.failure.error_type == "RuntimeError"


# --------------------------------------------------------------------- #
# 4. observer raises on success: ask() still returns the normal AskResult
# --------------------------------------------------------------------- #
def test_4_observer_raises_on_success_ask_still_returns_normally(monkeypatch):
    core = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    def exploding_observer(record):
        raise RuntimeError("observer bug")

    result = core.ask("Question", top_k=3, on_turn_record=exploding_observer)

    assert isinstance(result, AskResult)
    assert result.status == "success"
    assert result.rendered == {"primary_answer": "answer"}


# --------------------------------------------------------------------- #
# 5. observer raises on failure: original Core exception still re-raised
# --------------------------------------------------------------------- #
def test_5_observer_raises_on_failure_original_exception_still_reraised(monkeypatch):
    boom = RuntimeError("qdrant unreachable")
    core = _core(bridge=_Bridge(resolve_error=boom))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    def exploding_observer(record):
        raise RuntimeError("observer bug")

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=3, on_turn_record=exploding_observer)

    assert excinfo.value is boom
    assert str(excinfo.value) == "qdrant unreachable"


# --------------------------------------------------------------------- #
# 6. no double observer invocation (success and failure paths)
# --------------------------------------------------------------------- #
def test_6a_no_double_invocation_on_success(monkeypatch):
    core = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    calls = []

    core.ask("Question", top_k=3, on_turn_record=lambda r: calls.append(r))

    assert len(calls) == 1


def test_6b_no_double_invocation_on_failure(monkeypatch):
    boom = RuntimeError("qdrant unreachable")
    core = _core(bridge=_Bridge(resolve_error=boom))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    calls = []

    with pytest.raises(RuntimeError):
        core.ask("Question", top_k=3, on_turn_record=lambda r: calls.append(r))

    assert len(calls) == 1


def test_6c_no_invocation_when_no_turn_record_is_ever_captured(monkeypatch):
    """A BaseException bypasses the closure handler entirely (T18-R29):
    no TurnRecord exists, so the observer must not be called at all."""
    core = _core(renderer_error=KeyboardInterrupt())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    calls = []

    with pytest.raises(KeyboardInterrupt):
        core.ask("Question", top_k=3, on_turn_record=lambda r: calls.append(r))

    assert calls == []


# --------------------------------------------------------------------- #
# 7. existing governed-turn pipeline order remains unchanged
# --------------------------------------------------------------------- #
def test_7_pipeline_order_unchanged_with_observer_present(monkeypatch):
    core = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    seen = []
    core.ask(
        "Question", top_k=3,
        progress=lambda stage, status: seen.append((stage, status)),
        on_turn_record=lambda r: None,
    )

    assert seen == [
        ("retrieval", "started"),
        ("retrieval", "done"),
        ("context_pack", "started"),
        ("context_pack", "done"),
        ("gemini", "started"),
        ("gemini", "done"),
        ("answer", "ready"),
    ]


# --------------------------------------------------------------------- #
# 8. AskResult schema/shape remains unchanged
# --------------------------------------------------------------------- #
def test_8_ask_result_schema_unchanged(monkeypatch):
    core = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    result = core.ask("Question", top_k=3, on_turn_record=lambda r: None)

    assert {f.name for f in dataclasses.fields(AskResult)} == {
        "request_id", "question", "status", "rendered", "mive_result",
        "ive_reports", "metrics", "error_stage", "message",
    }
    body = result.to_dict()
    assert "ION_TURN_RECORD_V0_1" not in repr(body)
    for value in body.values():
        assert not isinstance(value, TurnRecord)


# --------------------------------------------------------------------- #
# 9. TurnRecord dataclass fields remain unchanged
# --------------------------------------------------------------------- #
def test_9_turn_record_fields_unchanged(monkeypatch):
    core = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    captured = []

    core.ask("Question", top_k=3, on_turn_record=captured.append)

    assert {f.name for f in dataclasses.fields(TurnRecord)} == {
        "turn_id", "closure_state", "turn_started_at", "turn_closed_at",
        "configuration", "question", "retrieval_latency_ms",
        "comparison_latency_ms", "pipeline_latency_ms", "context_pack_id",
        "governed_evidence", "model_executions", "mive_overall_status",
        "execution_profile", "failure", "turn_identity_basis",
        "question_normalization", "turn_record_contract_id",
        "turn_record_version",
    }
    assert isinstance(captured[0], TurnRecord)
