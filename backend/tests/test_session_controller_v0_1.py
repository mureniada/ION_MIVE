"""TASK 22.3B3 test: the in-memory Session / Turn Controller.

The Controller wraps a REAL `Core` (over stand-in ports, exactly like
`test_orchestrator_capture_seam_v0_1.py` and `test_orchestrator_turn_record_v0_1.py`
already do) for every scenario `Core.ask()` can genuinely produce, and a
deliberately CONTRACT-VIOLATING fake `core` object only for the one
scenario a real, correct `Core` can never produce (a success with nothing
captured) — proving the Controller's own defensive check exists
independently of Core's guarantees, per the task's own instruction that
Controller correctness must be verified by inspecting what was actually
captured, never trusted blindly.

No Gemini/OpenAI/provider SDK is reachable from anything below.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import threading
from types import SimpleNamespace

import pytest

from app.core.models import AskResult
import app.core.orchestrator as orch
import app.modules.core_adapter.facade as facade
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import STANDARD_GEMINI
from app.modules.model_gateway import ModelGateway
from app.modules.session import (
    ConcurrentTurnError,
    Session,
    SessionClosedError,
    SessionController,
    SessionStatus,
    SessionTurnEntry,
    TurnRecordCaptureError,
    UnknownSessionError,
)
import app.modules.session.controller as session_controller_module
from app.modules.turn_record import TurnClosureState, TurnRecord

VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"
GEMINI_MODEL = "gemini-3.1-flash-lite"


# --------------------------------------------------------------------- #
# stand-ins — same shapes as test_orchestrator_capture_seam_v0_1.py
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
    """Default renderer: returns immediately."""

    def render_single(self, **kwargs):
        return {"primary_answer": "answer"}


class _BlockingRenderer:
    """Blocks inside render_single until released — lets a test observe a
    turn genuinely in flight, and confirm concurrent entry across sessions."""

    def __init__(self):
        self.lock = threading.Lock()
        self.concurrent_count = 0
        self.max_concurrent = 0
        self.enter_event = threading.Event()
        self.release_event = threading.Event()

    def render_single(self, **kwargs):
        with self.lock:
            self.concurrent_count += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent_count)
        self.enter_event.set()
        self.release_event.wait(timeout=5)
        with self.lock:
            self.concurrent_count -= 1
        return {"primary_answer": "answer"}


class _RaisingRenderer:
    def __init__(self, exc):
        self._exc = exc

    def render_single(self, **kwargs):
        raise self._exc


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
                evidence_id=cid, status=VERIFIED, validation_id="VAL-" + cid,
                fingerprint=SimpleNamespace(algorithm="SHA256", hash="FP-" + cid, content_id=cid),
            )
            for cid in candidate_ids
        ),
        validations=tuple(
            SimpleNamespace(
                validation_id="VAL-" + cid, evidence_id=cid, result=PASS,
                blocking_reasons=(), evidence_fingerprint_hash="FP-" + cid,
            )
            for cid in candidate_ids
        ),
        transitions=tuple(
            SimpleNamespace(
                transition_id="TR-" + cid, evidence_id=cid, from_status=PENDING,
                to_status=VERIFIED, validation_id="VAL-" + cid,
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
                document_id=did, content="body", title="Title-" + did,
                source="SRC-" + did, page=None, chunk_id=None,
            )
            for did in document_ids
        ],
        metadata={"included_documents": len(tuple(document_ids))},
    )


def _settings():
    return SimpleNamespace(
        default_top_k=1, context_char_budget=60000, qdrant_collection="ion_corpus_v1",
    )


def _core(
    *, retrieved=("EV-1", "EV-2", "EV-3"), submitted=("EV-1", "EV-2"),
    bridge=None, gemini_error=None, renderer=None,
):
    """A real Core over stand-ins — same construction as TASK 18/22.3B1."""
    pack = _pack(submitted)
    core = orch.Core.__new__(orch.Core)
    core._settings = _settings()
    core._clock = _Clock()
    core._retrieval = _Retrieval(retrieved)
    core._build = _Builder(pack)
    core._core_adapter = _adapter(_Bridge() if bridge is None else bridge)
    core._execution_profile = STANDARD_GEMINI
    core._model_gateway = ModelGateway(
        {"gemini": _Engine("gemini", "gemini", GEMINI_MODEL, error=gemini_error)}
    )
    core._mive = _Mive()
    core._renderer = renderer if renderer is not None else _Renderer()
    core._pricing = _Pricing()
    return core


def _patch_gate(monkeypatch, candidate_ids):
    native = _native_for(candidate_ids)

    def gate(**kwargs):
        return native

    monkeypatch.setattr(facade, "run_runtime_admission_gate", gate)


class _FakeCoreNoCapture:
    """Deliberately violates Core's own contract: succeeds but never calls
    the observer. Used ONLY to prove the Controller's own defensive check
    (a real, correct Core can never produce this — see test_12)."""

    def ask(self, question, top_k=None, *, progress=None, on_turn_record=None):
        return AskResult(
            request_id="FAKE-REQUEST-1", question=question, status="success",
            rendered={"primary_answer": "fake"}, mive_result=None,
            ive_reports=[], metrics={},
        )


class _SpyCore:
    """Records every call's kwargs, delegates to a real Core underneath."""

    def __init__(self, real_core):
        self._real = real_core
        self.calls: list[dict] = []

    def ask(self, question, top_k=None, *, progress=None, on_turn_record=None):
        self.calls.append({"question": question, "top_k": top_k})
        return self._real.ask(question, top_k, progress=progress, on_turn_record=on_turn_record)


# --------------------------------------------------------------------- #
# 1. create_session returns valid ACTIVE immutable snapshot
# --------------------------------------------------------------------- #
def test_1_create_session_returns_valid_active_snapshot():
    controller = SessionController(core=_core())
    session = controller.create_session()

    assert isinstance(session, Session)
    assert session.status is SessionStatus.ACTIVE
    assert session.next_turn_ordinal == 1
    assert session.active_turn is None
    assert session.ordered_turns == ()
    assert session.session_id


# --------------------------------------------------------------------- #
# 2. session_id remains stable across get_session()
# --------------------------------------------------------------------- #
def test_2_session_id_stable_across_get_session():
    controller = SessionController(core=_core())
    created = controller.create_session()
    fetched = controller.get_session(created.session_id)

    assert fetched.session_id == created.session_id
    assert fetched.created_at == created.created_at
    assert fetched.status is SessionStatus.ACTIVE


# --------------------------------------------------------------------- #
# 3. unknown session -> UnknownSessionError
# --------------------------------------------------------------------- #
def test_3_unknown_session_raises():
    controller = SessionController(core=_core())
    with pytest.raises(UnknownSessionError):
        controller.get_session("no-such-session")
    with pytest.raises(UnknownSessionError):
        controller.close_session("no-such-session")
    with pytest.raises(UnknownSessionError):
        controller.run_turn("no-such-session", "Question")


# --------------------------------------------------------------------- #
# 4. close_session produces CLOSED snapshot
# --------------------------------------------------------------------- #
def test_4_close_session_produces_closed_snapshot():
    controller = SessionController(core=_core())
    session = controller.create_session()

    closed = controller.close_session(session.session_id)

    assert closed.status is SessionStatus.CLOSED
    assert closed.active_turn is None
    assert closed.session_id == session.session_id


# --------------------------------------------------------------------- #
# 5. repeated close is idempotent
# --------------------------------------------------------------------- #
def test_5_repeated_close_is_idempotent():
    controller = SessionController(core=_core())
    session = controller.create_session()

    first = controller.close_session(session.session_id)
    second = controller.close_session(session.session_id)

    assert first.status is SessionStatus.CLOSED
    assert second.status is SessionStatus.CLOSED
    assert second.ordered_turns == first.ordered_turns == ()


# --------------------------------------------------------------------- #
# 6. close during active turn -> ConcurrentTurnError, no mutation
# --------------------------------------------------------------------- #
def test_6_close_during_active_turn_rejected_no_mutation(monkeypatch):
    renderer = _BlockingRenderer()
    controller = SessionController(core=_core(renderer=renderer))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    result_holder = {}

    def run():
        result_holder["result"] = controller.run_turn(session.session_id, "Question", top_k=3)

    thread = threading.Thread(target=run)
    thread.start()
    assert renderer.enter_event.wait(timeout=5), "turn never entered the renderer"

    with pytest.raises(ConcurrentTurnError):
        controller.close_session(session.session_id)

    # no mutation: still ACTIVE, still no entries
    mid_flight = controller.get_session(session.session_id)
    assert mid_flight.status is SessionStatus.ACTIVE
    assert mid_flight.ordered_turns == ()

    renderer.release_event.set()
    thread.join(timeout=5)
    assert "result" in result_holder


# --------------------------------------------------------------------- #
# 7. run_turn on CLOSED -> SessionClosedError
# --------------------------------------------------------------------- #
def test_7_run_turn_on_closed_session_raises(monkeypatch):
    controller = SessionController(core=_core())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()
    controller.close_session(session.session_id)

    with pytest.raises(SessionClosedError):
        controller.run_turn(session.session_id, "Question", top_k=3)


# --------------------------------------------------------------------- #
# 8. successful first turn
# --------------------------------------------------------------------- #
def test_8_successful_first_turn(monkeypatch):
    real_core = _core()
    spy = _SpyCore(real_core)
    controller = SessionController(core=spy)
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    result = controller.run_turn(session.session_id, "Question", top_k=3)

    assert len(spy.calls) == 1
    assert isinstance(result, AskResult)
    assert result.status == "success"

    after = controller.get_session(session.session_id)
    assert len(after.ordered_turns) == 1
    entry = after.ordered_turns[0]
    assert entry.turn_ordinal == 1
    assert entry.turn_record.closure_state is TurnClosureState.COMPLETED
    assert entry.turn_id == entry.turn_record.turn_id
    assert after.next_turn_ordinal == 2
    assert after.active_turn is None


# --------------------------------------------------------------------- #
# 9. successful second turn
# --------------------------------------------------------------------- #
def test_9_successful_second_turn(monkeypatch):
    controller = SessionController(core=_core())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    controller.run_turn(session.session_id, "Question 1", top_k=3)
    first_snapshot = controller.get_session(session.session_id)
    first_entry = first_snapshot.ordered_turns[0]

    controller.run_turn(session.session_id, "Question 2", top_k=3)
    second_snapshot = controller.get_session(session.session_id)

    assert [e.turn_ordinal for e in second_snapshot.ordered_turns] == [1, 2]
    assert second_snapshot.next_turn_ordinal == 3
    # the first entry is unchanged (identical values) after the second turn
    assert second_snapshot.ordered_turns[0] == first_entry


# --------------------------------------------------------------------- #
# 10. FAILED Core turn with captured FAILED TurnRecord
# --------------------------------------------------------------------- #
def test_10_failed_turn_with_captured_failed_record_preserved(monkeypatch):
    boom = RuntimeError("qdrant unreachable")
    controller = SessionController(core=_core(bridge=_Bridge(resolve_error=boom)))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    with pytest.raises(RuntimeError) as excinfo:
        controller.run_turn(session.session_id, "Question", top_k=3)

    assert excinfo.value is boom  # original exception identity preserved

    after = controller.get_session(session.session_id)
    assert len(after.ordered_turns) == 1
    entry = after.ordered_turns[0]
    assert entry.turn_ordinal == 1
    assert entry.turn_record.closure_state is TurnClosureState.FAILED
    assert after.next_turn_ordinal == 2  # ordinal consumed
    assert after.active_turn is None
    assert after.status is SessionStatus.ACTIVE


# --------------------------------------------------------------------- #
# 11. failure without captured TurnRecord
# --------------------------------------------------------------------- #
def test_11_failure_without_captured_record_not_fabricated(monkeypatch):
    boom = KeyboardInterrupt()  # bypasses Core's own closure handler entirely
    controller = SessionController(core=_core(renderer=_RaisingRenderer(boom)))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    with pytest.raises(KeyboardInterrupt) as excinfo:
        controller.run_turn(session.session_id, "Question", top_k=3)

    assert excinfo.value is boom

    after = controller.get_session(session.session_id)
    assert after.ordered_turns == ()          # nothing fabricated
    assert after.next_turn_ordinal == 1        # ordinal not consumed
    assert after.active_turn is None


# --------------------------------------------------------------------- #
# 12. success without captured TurnRecord (Controller's own defense)
# --------------------------------------------------------------------- #
def test_12_success_without_captured_record_raises_capture_error():
    controller = SessionController(core=_FakeCoreNoCapture())
    session = controller.create_session()

    with pytest.raises(TurnRecordCaptureError):
        controller.run_turn(session.session_id, "Question", top_k=3)

    after = controller.get_session(session.session_id)
    assert after.ordered_turns == ()
    assert after.next_turn_ordinal == 1
    assert after.active_turn is None


# --------------------------------------------------------------------- #
# 13. active_turn reservation
# --------------------------------------------------------------------- #
def test_13_active_turn_reservation_lifecycle(monkeypatch):
    renderer = _BlockingRenderer()
    controller = SessionController(core=_core(renderer=renderer))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    result_holder = {}

    def run():
        result_holder["result"] = controller.run_turn(session.session_id, "Question", top_k=3)

    thread = threading.Thread(target=run)
    thread.start()
    assert renderer.enter_event.wait(timeout=5)

    mid_flight = controller.get_session(session.session_id)
    assert mid_flight.active_turn is not None
    assert mid_flight.active_turn.turn_ordinal == mid_flight.next_turn_ordinal == 1
    reservation_id = mid_flight.active_turn.reservation_id

    renderer.release_event.set()
    thread.join(timeout=5)

    after = controller.get_session(session.session_id)
    assert after.active_turn is None  # cleared after closure
    real_turn_id = after.ordered_turns[0].turn_id
    assert reservation_id != real_turn_id  # OD22-13: never the Core turn_id


# --------------------------------------------------------------------- #
# 14. same-session concurrent second turn -> immediate ConcurrentTurnError
# --------------------------------------------------------------------- #
def test_14_same_session_concurrent_turn_rejected_immediately(monkeypatch):
    renderer = _BlockingRenderer()
    controller = SessionController(core=_core(renderer=renderer))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    result_holder = {}

    def run():
        result_holder["result"] = controller.run_turn(session.session_id, "Question", top_k=3)

    thread = threading.Thread(target=run)
    thread.start()
    assert renderer.enter_event.wait(timeout=5)

    with pytest.raises(ConcurrentTurnError):
        controller.run_turn(session.session_id, "Second question", top_k=3)

    renderer.release_event.set()
    thread.join(timeout=5)
    assert result_holder["result"].status == "success"

    after = controller.get_session(session.session_id)
    assert len(after.ordered_turns) == 1  # the rejected attempt left no trace


# --------------------------------------------------------------------- #
# 15. different-session concurrent turns: both enter Core.ask(), no global lock
# --------------------------------------------------------------------- #
def test_15_different_session_turns_not_globally_serialized(monkeypatch):
    renderer = _BlockingRenderer()
    controller = SessionController(core=_core(renderer=renderer))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session_a = controller.create_session()
    session_b = controller.create_session()

    results = {}

    def run(session_id, key):
        results[key] = controller.run_turn(session_id, "Question", top_k=3)

    thread_a = threading.Thread(target=run, args=(session_a.session_id, "a"))
    thread_a.start()
    assert renderer.enter_event.wait(timeout=5)
    renderer.enter_event.clear()

    thread_b = threading.Thread(target=run, args=(session_b.session_id, "b"))
    thread_b.start()
    assert renderer.enter_event.wait(timeout=5), (
        "second session's turn never entered Core.ask() — appears globally serialized"
    )

    assert renderer.max_concurrent == 2  # both genuinely inside at once

    renderer.release_event.set()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert results["a"].status == "success"
    assert results["b"].status == "success"


# --------------------------------------------------------------------- #
# 16/17. public snapshots remain frozen
# --------------------------------------------------------------------- #
def test_16_session_snapshot_is_frozen(monkeypatch):
    controller = SessionController(core=_core())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()
    controller.run_turn(session.session_id, "Question", top_k=3)
    snapshot = controller.get_session(session.session_id)

    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.next_turn_ordinal = 99


def test_17_session_turn_entry_is_frozen(monkeypatch):
    controller = SessionController(core=_core())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()
    controller.run_turn(session.session_id, "Question", top_k=3)
    entry = controller.get_session(session.session_id).ordered_turns[0]

    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.turn_ordinal = 99


# --------------------------------------------------------------------- #
# 18. history is append-only
# --------------------------------------------------------------------- #
def test_18_history_is_append_only(monkeypatch):
    controller = SessionController(core=_core())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    controller.run_turn(session.session_id, "Question 1", top_k=3)
    snap1 = controller.get_session(session.session_id)

    controller.run_turn(session.session_id, "Question 2", top_k=3)
    snap2 = controller.get_session(session.session_id)

    # snap1's tuple is untouched by the later mutation (a fresh tuple was
    # built for snap2, never the same underlying list)
    assert len(snap1.ordered_turns) == 1
    assert len(snap2.ordered_turns) == 2
    assert snap2.ordered_turns[0] == snap1.ordered_turns[0]
    assert snap2.ordered_turns[:1] == snap1.ordered_turns


# --------------------------------------------------------------------- #
# 19-22. no evidence/model-output/rendered-response/memory/dialogue in
# private Controller runtime state
# --------------------------------------------------------------------- #
def test_19_to_22_private_state_carries_no_forbidden_content(monkeypatch):
    controller = SessionController(core=_core())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()
    controller.run_turn(session.session_id, "Question", top_k=3)

    state = controller._sessions[session.session_id]
    forbidden = (
        "evidence", "governed_evidence", "model_output", "rendered_response",
        "response", "history", "memory", "dialogue_instruction", "dialogue_profile",
    )
    state_attr_names = {name.lower() for name in vars(state) if not name.startswith("_")}
    # 'entries' is the append-only SessionTurnEntry list — not "history" by
    # name, and only ever holds TurnRecord references (proven separately).
    for name in state_attr_names:
        for word in forbidden:
            assert word not in name, f"_SessionState.{name} looks forbidden ({word})"

    # and the TurnRecord references it holds carry no such content either —
    # already proven structurally by TurnRecord's own closed field set.
    entry = state.entries[0]
    assert isinstance(entry, SessionTurnEntry)
    assert isinstance(entry.turn_record, TurnRecord)


# --------------------------------------------------------------------- #
# 23/24. prior TurnRecord never passed into the next Core.ask(); no
# cross-turn evidence reuse
# --------------------------------------------------------------------- #
def test_23_24_no_prior_turn_data_passed_into_next_core_ask(monkeypatch):
    real_core = _core()
    spy = _SpyCore(real_core)
    controller = SessionController(core=spy)
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    controller.run_turn(session.session_id, "Question 1", top_k=3)
    controller.run_turn(session.session_id, "Question 2", top_k=3)

    assert len(spy.calls) == 2
    for call in spy.calls:
        assert set(call.keys()) == {"question", "top_k"}
        assert isinstance(call["question"], str)
        # no TurnRecord, SessionTurnEntry, or evidence object is ever passed
        for value in call.values():
            assert not isinstance(value, (TurnRecord, SessionTurnEntry))


# --------------------------------------------------------------------- #
# 25. Controller imports/calls Core.ask only
# --------------------------------------------------------------------- #
def test_25_controller_touches_no_pipeline_module_directly():
    tree = ast.parse(inspect.getsource(session_controller_module))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    forbidden = (
        "governed_evidence", "retrieval", "core_adapter", "model_gateway",
        "model_context", "renderer", "execution_profile",
    )
    for word in forbidden:
        assert not any(word in module for module in imported_modules), (
            f"controller.py must not import {word}"
        )
    # the only Core surface referenced is the class itself (for the
    # constructor's type hint) and its .ask() method, called exactly once
    # per run_turn
    source = inspect.getsource(session_controller_module)
    assert source.count("self._core.ask(") == 1


# --------------------------------------------------------------------- #
# 26. TurnRecord model fields remain unchanged
# --------------------------------------------------------------------- #
def test_26_turn_record_fields_unchanged():
    assert {f.name for f in dataclasses.fields(TurnRecord)} == {
        "turn_id", "closure_state", "turn_started_at", "turn_closed_at",
        "configuration", "question", "retrieval_latency_ms",
        "comparison_latency_ms", "pipeline_latency_ms", "context_pack_id",
        "governed_evidence", "model_executions", "mive_overall_status",
        "execution_profile", "failure", "turn_identity_basis",
        "question_normalization", "turn_record_contract_id",
        "turn_record_version",
    }


# --------------------------------------------------------------------- #
# 27. AskResult shape remains unchanged
# --------------------------------------------------------------------- #
def test_27_ask_result_shape_unchanged(monkeypatch):
    controller = SessionController(core=_core())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    result = controller.run_turn(session.session_id, "Question", top_k=3)

    assert {f.name for f in dataclasses.fields(AskResult)} == {
        "request_id", "question", "status", "rendered", "mive_result",
        "ive_reports", "metrics", "error_stage", "message",
    }
    body = result.to_dict()
    for value in body.values():
        assert not isinstance(value, TurnRecord)


# --------------------------------------------------------------------- #
# TASK 22.3B3-R2 — repeated FAILED-turn preservation and ordinal continuity
#
# Standing regression cover for OD22-12 / L22-04 across a SEQUENCE of
# failing turns, not just one. The Core here is real (over stand-in seams),
# so each FAILED TurnRecord is genuinely materialized by Core's own closure
# handler — nothing about the record is stubbed. The operational-failure
# path is used deliberately: it propagates the ORIGINAL exception untouched,
# so exception identity stays provable on every iteration.
# --------------------------------------------------------------------- #
def test_r2_repeated_failed_turns_preserve_contiguous_history(monkeypatch):
    boom = RuntimeError("qdrant unreachable")
    controller = SessionController(core=_core(bridge=_Bridge(resolve_error=boom)))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    session = controller.create_session()

    snapshots = []
    for expected_ordinal in (1, 2, 3):
        before = controller.get_session(session.session_id)
        assert before.next_turn_ordinal == expected_ordinal

        with pytest.raises(RuntimeError) as excinfo:
            controller.run_turn(
                session.session_id, f"Question {expected_ordinal}", top_k=3
            )

        # the ORIGINAL Core exception, by identity, on every turn
        assert excinfo.value is boom

        after = controller.get_session(session.session_id)

        # exactly one new entry per failing turn — never zero, never two
        assert len(after.ordered_turns) == len(before.ordered_turns) + 1
        newest = after.ordered_turns[-1]
        assert newest.turn_ordinal == expected_ordinal
        assert newest.turn_record.closure_state is TurnClosureState.FAILED

        # every prior entry survives this turn completely unchanged
        assert after.ordered_turns[:-1] == before.ordered_turns

        snapshots.append(after)

    final = controller.get_session(session.session_id)

    # ordinals exactly 1, 2, 3 — no gap, and nothing fabricated to fill one
    assert [e.turn_ordinal for e in final.ordered_turns] == [1, 2, 3]
    assert len(final.ordered_turns) == 3
    assert final.next_turn_ordinal == 4

    for entry in final.ordered_turns:
        # a genuine, materialized FAILED record — not a fabricated placeholder
        assert isinstance(entry.turn_record, TurnRecord)
        assert entry.turn_record.closure_state is TurnClosureState.FAILED
        assert entry.turn_record.failure is not None
        assert entry.turn_record.turn_id
        assert entry.turn_id == entry.turn_record.turn_id

    # no duplicate turn_ids across the whole history
    turn_ids = [e.turn_id for e in final.ordered_turns]
    assert len(set(turn_ids)) == 3

    # prior entries are identical in the final snapshot to when they were
    # first observed — append-only across the entire sequence
    assert final.ordered_turns[:1] == snapshots[0].ordered_turns
    assert final.ordered_turns[:2] == snapshots[1].ordered_turns

    assert final.active_turn is None
    assert final.status is SessionStatus.ACTIVE

    # the final snapshot satisfies every frozen model invariant: rebuilding
    # a Session from its own parts must be ACCEPTED by Session.__post_init__
    # (contiguity, session-ownership, uniqueness, next_turn_ordinal, and the
    # active_turn rules are all re-checked there, fail-closed)
    rebuilt = Session(
        session_id=final.session_id,
        created_at=final.created_at,
        status=final.status,
        next_turn_ordinal=final.next_turn_ordinal,
        active_turn=final.active_turn,
        ordered_turns=final.ordered_turns,
    )
    assert rebuilt == final


# --------------------------------------------------------------------- #
# 29. no provider execution
# --------------------------------------------------------------------- #
def test_29_no_provider_referenced_in_controller():
    source = inspect.getsource(session_controller_module).lower()
    for forbidden in ("gemini", "openai", "genai"):
        assert forbidden not in source


# --------------------------------------------------------------------- #
# 30. no Adaptive Dialogue implementation
# --------------------------------------------------------------------- #
def test_30_dialogue_reference_is_confined_to_the_authorized_seam():
    """E1 wires the Controller to the Adaptive Dialogue engine, so a blanket
    "no dialogue identifier anywhere" assertion is no longer the law. What
    survives unchanged is the REASON that assertion existed (OD22-08): the
    Controller may CONSULT the dialogue layer, but no dialogue content may
    enter session state. This checks the narrower, still-true invariant —
    the only dialogue names the Controller uses are the decision vocabulary
    and the engine itself, and no dialogue STATE/memory/history/profile type
    is referenced at all."""
    tree = ast.parse(inspect.getsource(session_controller_module))
    identifiers = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identifiers.add(node.name)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module:
            identifiers.add(node.module)
        elif isinstance(node, ast.Import):
            identifiers.update(alias.name for alias in node.names)

    dialogue_names = {n for n in identifiers if "dialogue" in n.lower()}
    assert dialogue_names == {
        "adaptive_dialogue",
        "AdaptiveDialogueEngine",
        "DialogueDecisionType",
        "DialogueReasonCode",
        "DialogueTurnInput",
        "_dialogue_engine",
        "dialogue_engine",
    }
    # the forbidden shapes stay forbidden, structurally
    for forbidden in ("DialogueState", "DialogueProfile", "DialogueMemory",
                      "DialogueHistory", "ClarificationHistory"):
        assert forbidden not in identifiers


def test_package_exports_full_public_surface():
    import app.modules.session as session_pkg

    assert set(session_pkg.__all__) == {
        "ActiveTurnReservation", "ConcurrentTurnError", "Session",
        "SessionClarificationOutcome",
        "SessionClosedError", "SessionController", "SessionControllerError",
        "SessionModelError", "SessionStatus", "SessionTurnEntry",
        "TurnRecordCaptureError", "UnknownSessionError",
    }
    assert not any(name.startswith("_SessionState") for name in session_pkg.__all__)


# --------------------------------------------------------------------- #
# TASK 22.5B — cross-session mutation isolation
#
# L22.5-07/08/09: a Controller-owned session's lifecycle/history state must
# be unaffected by an operation performed on a DIFFERENT session, whether
# that operation is a close or a genuine Core failure. Both tests below use
# the same real-SessionController/real-Core-over-stand-ins composition as
# every other test in this file — no provider, no network, no Qdrant.
# --------------------------------------------------------------------- #
def test_31_closing_session_a_does_not_mutate_session_b(monkeypatch):
    controller = SessionController(core=_core())
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    session_a = controller.create_session()
    session_b = controller.create_session()

    controller.run_turn(session_b.session_id, "Question", top_k=3)
    b_before = controller.get_session(session_b.session_id)

    assert b_before.status is SessionStatus.ACTIVE
    assert len(b_before.ordered_turns) == 1
    assert [e.turn_ordinal for e in b_before.ordered_turns] == [1]
    assert b_before.next_turn_ordinal == 2
    assert b_before.active_turn is None

    controller.close_session(session_a.session_id)

    b_after = controller.get_session(session_b.session_id)

    assert b_after == b_before
    assert b_after.status == SessionStatus.ACTIVE
    assert b_after.ordered_turns == b_before.ordered_turns
    assert b_after.next_turn_ordinal == 2
    assert b_after.active_turn is None

    # closing A only ever affected A, never B
    a_after = controller.get_session(session_a.session_id)
    assert a_after.status is SessionStatus.CLOSED
    assert a_after.session_id != b_after.session_id


class _FailFromSecondCallBridge(_Bridge):
    """The same `_Bridge` stand-in already used across this file, extended
    only to succeed on its first `resolve()` call and fail from the second
    call onward. One `Core` instance is shared by the Controller across all
    sessions (matches production wiring), so a session-A failure that must
    leave a session-B success in place needs a bridge whose failure is
    ORDERED, not global — B's turn (called first) succeeds, A's turn
    (called second) genuinely fails through the same governance seam every
    other failure test in this file already uses.
    """

    def __init__(self, error):
        super().__init__()
        self._error = error
        self._calls = 0

    def resolve(self, evidence):
        self._calls += 1
        if self._calls >= 2:
            raise self._error
        return super().resolve(evidence)


def test_32_failure_in_session_a_does_not_mutate_session_b_history(monkeypatch):
    boom = RuntimeError("qdrant unreachable")
    controller = SessionController(core=_core(bridge=_FailFromSecondCallBridge(boom)))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    session_a = controller.create_session()
    session_b = controller.create_session()

    controller.run_turn(session_b.session_id, "Question", top_k=3)
    b_before = controller.get_session(session_b.session_id)

    assert b_before.status is SessionStatus.ACTIVE
    assert [e.turn_ordinal for e in b_before.ordered_turns] == [1]
    assert b_before.next_turn_ordinal == 2
    assert b_before.active_turn is None

    with pytest.raises(RuntimeError) as excinfo:
        controller.run_turn(session_a.session_id, "Question", top_k=3)
    assert excinfo.value is boom  # the genuine Core failure path was exercised

    b_after = controller.get_session(session_b.session_id)

    assert b_after == b_before
    assert b_after.status == SessionStatus.ACTIVE
    assert b_after.ordered_turns == b_before.ordered_turns
    assert b_after.next_turn_ordinal == 2
    assert b_after.active_turn is None

    # confirm A actually took the intended failure path: one captured
    # FAILED TurnRecord, distinct from B's own (unrelated) history
    a_after = controller.get_session(session_a.session_id)
    assert len(a_after.ordered_turns) == 1
    assert a_after.ordered_turns[0].turn_record.closure_state is TurnClosureState.FAILED
    assert a_after.session_id != b_after.session_id


# ===================================================================== #
# E1 — SessionController <-> AdaptiveDialogueEngine wiring
#
# Proves the seam sits AFTER session admission and the ActiveTurnReservation
# and BEFORE Core.ask(); that PROCEED preserves the TASK 22 governed path
# exactly; and that CLARIFY starts no Core turn, writes no history, consumes
# no ordinal, releases the reservation, and is distinguishable by TYPE.
# ===================================================================== #
from app.modules.adaptive_dialogue import (  # noqa: E402
    AdaptiveDialogueEngine,
    DialogueDecision,
    DialogueDecisionType,
    DialogueReasonCode,
    DialogueTurnInput,
)
from app.modules.session import SessionClarificationOutcome  # noqa: E402

CLARIFY_Q = "???"          # no alphanumeric content -> the authorized rule
PROCEED_Q = "Question"     # ordinary question -> PROCEED


class _SpyEngine:
    """Records every evaluate() call and what it was handed."""

    def __init__(self, decision=None):
        self.calls = []
        self._decision = decision
        self._real = AdaptiveDialogueEngine()

    def evaluate(self, turn_input):
        self.calls.append(turn_input)
        if self._decision is not None:
            return self._decision
        return self._real.evaluate(turn_input)


class _OrderRecordingCore:
    """Delegates to a real Core but records WHEN ask() happened relative to
    the dialogue evaluation, via a shared event log."""

    def __init__(self, real_core, log):
        self._real = real_core
        self._log = log
        self.calls = 0

    def ask(self, question, top_k=None, *, progress=None, on_turn_record=None):
        self.calls += 1
        self._log.append("core.ask")
        return self._real.ask(
            question, top_k, progress=progress, on_turn_record=on_turn_record
        )


class _LoggingEngine:
    def __init__(self, log, controller_probe):
        self._log = log
        self._probe = controller_probe
        self._real = AdaptiveDialogueEngine()

    def evaluate(self, turn_input):
        self._log.append("dialogue.evaluate")
        self._probe()
        return self._real.evaluate(turn_input)


# --------------------------------------------------------------------- #
# T01/T02/T03 — ordering: admission -> reservation -> dialogue -> Core.ask
# --------------------------------------------------------------------- #
def test_e1_t01_t02_t03_dialogue_runs_after_reservation_and_before_core(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    log = []
    spy_core = _OrderRecordingCore(_core(), log)

    observed = {}
    holder = {}

    def probe():
        # observed from INSIDE dialogue evaluation: the reservation already
        # exists (T02) and the session is still ACTIVE (admission passed, T01)
        snapshot = holder["controller"].get_session(holder["session_id"])
        observed["active_turn"] = snapshot.active_turn
        observed["status"] = snapshot.status
        observed["core_calls_so_far"] = spy_core.calls

    controller = SessionController(
        core=spy_core, dialogue_engine=_LoggingEngine(log, probe)
    )
    session = controller.create_session()
    holder["controller"] = controller
    holder["session_id"] = session.session_id

    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)

    assert log == ["dialogue.evaluate", "core.ask"]           # T03
    assert observed["active_turn"] is not None                # T02
    assert observed["active_turn"].turn_ordinal == 1
    assert observed["status"] is SessionStatus.ACTIVE         # T01
    assert observed["core_calls_so_far"] == 0                 # T03


def test_e1_t01_admission_refusal_precedes_dialogue_entirely(monkeypatch):
    """A CLOSED session and an unknown session are both refused BEFORE the
    dialogue layer is consulted: admission is upstream of dialogue."""
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    spy = _SpyEngine()
    controller = SessionController(core=_core(), dialogue_engine=spy)

    session = controller.create_session()
    controller.close_session(session.session_id)

    with pytest.raises(SessionClosedError):
        controller.run_turn(session.session_id, PROCEED_Q, top_k=3)
    with pytest.raises(UnknownSessionError):
        controller.run_turn("no-such-session", PROCEED_Q, top_k=3)

    assert spy.calls == []


# --------------------------------------------------------------------- #
# T04 — exactly one dialogue evaluation per eligible interaction
# --------------------------------------------------------------------- #
def test_e1_t04_one_dialogue_evaluation_per_interaction(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    spy = _SpyEngine()
    controller = SessionController(core=_core(), dialogue_engine=spy)
    session = controller.create_session()

    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)
    assert len(spy.calls) == 1

    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)
    assert len(spy.calls) == 2


# --------------------------------------------------------------------- #
# T05 — PROCEED causes exactly one Core.ask()
# --------------------------------------------------------------------- #
def test_e1_t05_proceed_calls_core_exactly_once(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    spy_core = _SpyCore(_core())
    controller = SessionController(core=spy_core)
    session = controller.create_session()

    result = controller.run_turn(session.session_id, PROCEED_Q, top_k=3)

    assert len(spy_core.calls) == 1
    assert isinstance(result, AskResult)


# --------------------------------------------------------------------- #
# T06/T07/T08/T09 — CLARIFY starts no Core turn and writes no history
# --------------------------------------------------------------------- #
def test_e1_t06_t07_t08_t09_clarify_starts_no_core_turn(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    spy_core = _SpyCore(_core())
    controller = SessionController(core=spy_core)
    session = controller.create_session()

    outcome = controller.run_turn(session.session_id, CLARIFY_Q, top_k=3)

    assert spy_core.calls == []                                     # T06
    assert isinstance(outcome, SessionClarificationOutcome)
    assert not hasattr(outcome, "turn_id")                          # T07
    assert not hasattr(outcome, "request_id")                       # T07

    after = controller.get_session(session.session_id)
    assert after.ordered_turns == ()                                # T08/T09


# --------------------------------------------------------------------- #
# T10/T13 — CLARIFY leaves next_turn_ordinal unchanged, and the very next
#           eligible interaction takes that same ordinal
# --------------------------------------------------------------------- #
def test_e1_t10_t13_clarify_preserves_and_releases_the_ordinal(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    controller = SessionController(core=_core())
    session = controller.create_session()

    before = controller.get_session(session.session_id)
    assert before.next_turn_ordinal == 1

    outcome = controller.run_turn(session.session_id, CLARIFY_Q, top_k=3)
    assert outcome.turn_ordinal == 1

    mid = controller.get_session(session.session_id)
    assert mid.next_turn_ordinal == 1                                # T10

    # T13: the same ordinal is genuinely reusable by a real turn
    result = controller.run_turn(session.session_id, PROCEED_Q, top_k=3)
    assert isinstance(result, AskResult)

    after = controller.get_session(session.session_id)
    assert [e.turn_ordinal for e in after.ordered_turns] == [1]
    assert after.next_turn_ordinal == 2


# --------------------------------------------------------------------- #
# T11/T12 — reservation released, session still ACTIVE, lock not leaked
# --------------------------------------------------------------------- #
def test_e1_t11_t12_clarify_releases_reservation_and_keeps_session_active(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    controller = SessionController(core=_core())
    session = controller.create_session()

    controller.run_turn(session.session_id, CLARIFY_Q, top_k=3)

    after = controller.get_session(session.session_id)
    assert after.active_turn is None                                 # T11
    assert after.status is SessionStatus.ACTIVE                      # T12

    # the turn lock was genuinely released: a further turn is admitted,
    # and close_session() does not see a turn in flight
    controller.run_turn(session.session_id, CLARIFY_Q, top_k=3)
    closed = controller.close_session(session.session_id)
    assert closed.status is SessionStatus.CLOSED


# --------------------------------------------------------------------- #
# T14 — PROCEED preserves TASK 22 TurnRecord -> SessionTurnEntry behavior
# --------------------------------------------------------------------- #
def test_e1_t14_proceed_preserves_task22_history_behavior(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    controller = SessionController(core=_core())
    session = controller.create_session()

    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)
    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)

    after = controller.get_session(session.session_id)
    assert [e.turn_ordinal for e in after.ordered_turns] == [1, 2]
    assert after.next_turn_ordinal == 3
    for entry in after.ordered_turns:
        assert isinstance(entry, SessionTurnEntry)
        assert entry.session_id == session.session_id
        assert entry.turn_id == entry.turn_record.turn_id
        assert entry.turn_record.closure_state is TurnClosureState.COMPLETED
    assert len({e.turn_id for e in after.ordered_turns}) == 2


def test_e1_t14_clarify_between_two_turns_leaves_history_contiguous(monkeypatch):
    """The strongest ordinal-integrity case: a CLARIFY sandwiched between two
    real turns must leave NO gap and NO fabricated entry."""
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    controller = SessionController(core=_core())
    session = controller.create_session()

    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)
    controller.run_turn(session.session_id, CLARIFY_Q, top_k=3)
    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)

    after = controller.get_session(session.session_id)
    assert [e.turn_ordinal for e in after.ordered_turns] == [1, 2]
    assert after.next_turn_ordinal == 3
    assert after.active_turn is None
    assert after.status is SessionStatus.ACTIVE


# --------------------------------------------------------------------- #
# T15 — CLARIFY outcome is distinguishable from AskResult (and is not a
#       failure, not a TurnRecord, not a SessionTurnEntry)
# --------------------------------------------------------------------- #
def test_e1_t15_clarify_outcome_is_a_distinct_type(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    controller = SessionController(core=_core())
    session = controller.create_session()

    outcome = controller.run_turn(session.session_id, CLARIFY_Q, top_k=3)
    result = controller.run_turn(session.session_id, PROCEED_Q, top_k=3)

    assert isinstance(outcome, SessionClarificationOutcome)
    assert not isinstance(outcome, AskResult)
    assert not isinstance(outcome, (TurnRecord, SessionTurnEntry))
    assert not isinstance(outcome, BaseException)
    assert isinstance(result, AskResult)
    assert type(outcome) is not type(result)

    assert outcome.session_id == session.session_id
    assert outcome.reason_code is DialogueReasonCode.QUESTION_HAS_NO_ANSWERABLE_CONTENT
    assert dataclasses.is_dataclass(outcome)
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.turn_ordinal = 99  # type: ignore[misc]


def test_e1_t15_clarify_outcome_carries_no_forbidden_content(monkeypatch):
    """OD22-08 applied to the new type: it states that a turn did NOT run,
    and why — never evidence, model output, rendered text, or a turn id."""
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    controller = SessionController(core=_core())
    session = controller.create_session()

    outcome = controller.run_turn(session.session_id, CLARIFY_Q, top_k=3)

    field_names = {f.name for f in dataclasses.fields(outcome)}
    assert field_names == {"session_id", "turn_ordinal", "reason_code"}
    for forbidden in (
        "turn_id", "request_id", "turn_record", "evidence", "rendered",
        "clarification_prompt", "prompt", "text", "answer", "memory",
        "history", "confidence", "score", "ive_reports", "mive_result",
    ):
        assert forbidden not in field_names


# --------------------------------------------------------------------- #
# T20 — the engine receives a DialogueTurnInput and NOTHING else: no
#       retrieval, evidence, governance, model, provider, session, or
#       persistence authority is handed to it.
# --------------------------------------------------------------------- #
def test_e1_t20_engine_receives_only_dialogue_turn_input(monkeypatch):
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    spy = _SpyEngine()
    controller = SessionController(core=_core(), dialogue_engine=spy)
    session = controller.create_session()

    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)

    assert len(spy.calls) == 1
    handed = spy.calls[0]
    assert isinstance(handed, DialogueTurnInput)
    assert handed.question == PROCEED_Q

    field_names = {f.name for f in dataclasses.fields(handed)}
    assert field_names == {"question"}
    for forbidden in (
        "session_id", "turn_ordinal", "top_k", "evidence", "candidates",
        "governed_evidence", "model_context", "core", "controller",
        "history", "ordered_turns", "turn_record", "provider", "engine",
    ):
        assert forbidden not in field_names


def test_e1_t20_engine_is_called_with_exactly_one_positional_argument(monkeypatch):
    """Nothing extra is smuggled in as a second argument or a kwarg."""
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))
    seen = {}

    class _StrictEngine:
        def evaluate(self, turn_input, *args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            return DialogueDecision(
                decision_type=DialogueDecisionType.PROCEED,
                reason_code=DialogueReasonCode.NO_RULE_TRIGGERED,
            )

    controller = SessionController(core=_core(), dialogue_engine=_StrictEngine())
    session = controller.create_session()
    controller.run_turn(session.session_id, PROCEED_Q, top_k=3)

    assert seen["args"] == ()
    assert seen["kwargs"] == {}


# --------------------------------------------------------------------- #
# default construction still wires a real engine (no silent no-op seam)
# --------------------------------------------------------------------- #
def test_e1_default_controller_wires_a_real_engine():
    controller = SessionController(core=_core())
    assert isinstance(controller._dialogue_engine, AdaptiveDialogueEngine)
