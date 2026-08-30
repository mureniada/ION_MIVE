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
def test_30_no_adaptive_dialogue_reference():
    """Checks actual code constructs (defs, classes, imports, identifiers
    used in expressions) — not prose in comments/docstrings, which
    legitimately documents that no dialogue instruction is stored."""
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

    assert not any("dialogue" in name.lower() for name in identifiers)


def test_package_exports_full_public_surface():
    import app.modules.session as session_pkg

    assert set(session_pkg.__all__) == {
        "ActiveTurnReservation", "ConcurrentTurnError", "Session",
        "SessionClosedError", "SessionController", "SessionControllerError",
        "SessionModelError", "SessionStatus", "SessionTurnEntry",
        "TurnRecordCaptureError", "UnknownSessionError",
    }
    assert not any(name.startswith("_SessionState") for name in session_pkg.__all__)
