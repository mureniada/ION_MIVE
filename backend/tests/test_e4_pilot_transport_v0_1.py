"""TASK E4C tests: the pilot transport seam (REAL TRANSPORT -> SessionController
-> Adaptive Dialogue -> existing Core.ask() -> existing governed SINGLE spine).

This file proves ONLY the transport integration added in E4C. It does not
re-verify `SessionController`'s own internal guarantees (capture/preservation,
locking, ordinal bookkeeping) — those are `test_session_controller_v0_1.py`'s
job, and that file's own stand-ins are reused here unmodified so this file
does not duplicate ~150 lines of orchestrator scaffolding.

Skipped where FastAPI/httpx are absent (the thin sandbox); runs in the built
Docker image, exactly like `test_transport_api.py`. No live provider calls.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import os
import unittest
from unittest import mock

from tests.test_session_controller_v0_1 import CLARIFY_Q, _core, _patch_gate, _SpyCore


def _client():
    if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx") is None:
        raise unittest.SkipTest("fastapi/httpx not installed (present in the Docker image)")
    from fastapi.testclient import TestClient

    import app.main as main
    return TestClient(main.app)


def _wire(monkeypatch, *, retrieved=("EV-1", "EV-2", "EV-3"), submitted=("EV-1", "EV-2")):
    """Wire the pilot transport onto a REAL SessionController over a REAL Core
    built from `test_session_controller_v0_1.py`'s own stand-in ports — the
    same construction TASK 22.3B3 already uses. `require_ready` is stubbed
    exactly like the existing `/ask` transport tests stub it: readiness is not
    what this file is proving.
    """
    import app.main as main
    from app.core.config import Settings
    from app.modules.session import SessionController

    real_core = _core(retrieved=retrieved, submitted=submitted)
    _patch_gate(monkeypatch, submitted)
    spy_core = _SpyCore(real_core)
    controller = SessionController(core=spy_core)
    settings = Settings.load({"GEMINI_MODEL": "gemini-test"})

    monkeypatch.setattr(main, "_get_core", lambda: (settings, real_core))
    monkeypatch.setattr(main, "_get_session_controller", lambda: controller)
    monkeypatch.setattr(main, "require_ready", lambda *a, **k: None)
    return controller, spy_core


# --------------------------------------------------------------------- #
# E4C-T01 / E4C-T02 — POST /pilot/sessions creates a real Session, held in
# the existing in-memory SessionController state.
# --------------------------------------------------------------------- #
def test_e4c_t01_t02_create_session_is_real_and_in_memory(monkeypatch):
    client = _client()
    controller, _ = _wire(monkeypatch)

    resp = client.post("/pilot/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["next_turn_ordinal"] == 1
    assert body["session_id"]

    # T02: fetchable back out of the SAME controller's own registry, not
    # merely echoed by the HTTP response.
    from app.modules.session import Session

    session = controller.get_session(body["session_id"])
    assert isinstance(session, Session)
    assert session.session_id == body["session_id"]


# --------------------------------------------------------------------- #
# E4C-T03..T07 — a PROCEED turn: exactly one run_turn call, exactly one
# Core.ask, an answer transport distinguishable from clarify, exactly one
# TurnRecord, exactly one SessionTurnEntry.
# --------------------------------------------------------------------- #
def test_e4c_t03_to_t07_proceed_turn_reaches_core_exactly_once(monkeypatch):
    from app.modules.turn_record import TurnClosureState

    client = _client()
    controller, spy_core = _wire(monkeypatch)
    session_id = client.post("/pilot/sessions").json()["session_id"]

    with mock.patch.object(controller, "run_turn", wraps=controller.run_turn) as spy_run_turn:
        resp = client.post(
            f"/pilot/sessions/{session_id}/turn",
            json={"question": "What is money?", "top_k": 3},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "answer"  # T05: distinguishable from clarify

    assert spy_run_turn.call_count == 1  # T03
    assert spy_core.calls == [{"question": "What is money?", "top_k": 3}]  # T04

    snapshot = controller.get_session(session_id)
    assert len(snapshot.ordered_turns) == 1  # T06 + T07
    entry = snapshot.ordered_turns[0]
    assert entry.turn_record.closure_state is TurnClosureState.COMPLETED


# --------------------------------------------------------------------- #
# E4C-T08..T14 — a CLARIFY turn: reaches the existing CLARIFY branch, calls
# no Core.ask, creates no TurnRecord/SessionTurnEntry, does not advance the
# ordinal, releases the reservation, and leaves the session ACTIVE.
# --------------------------------------------------------------------- #
def test_e4c_t08_to_t14_clarify_turn_never_reaches_core(monkeypatch):
    from app.modules.session import SessionStatus

    client = _client()
    controller, spy_core = _wire(monkeypatch)
    session_id = client.post("/pilot/sessions").json()["session_id"]

    resp = client.post(
        f"/pilot/sessions/{session_id}/turn",
        json={"question": CLARIFY_Q, "top_k": 3},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "clarify"  # T08
    assert body["turn_ordinal"] == 1
    assert body["session_id"] == session_id

    assert spy_core.calls == []  # T09: zero Core.ask

    snapshot = controller.get_session(session_id)
    assert snapshot.ordered_turns == ()  # T10 + T11: zero TurnRecord/SessionTurnEntry
    assert snapshot.next_turn_ordinal == 1  # T12: ordinal not advanced
    assert snapshot.active_turn is None  # T13: reservation released
    assert snapshot.status is SessionStatus.ACTIVE  # T14: still ACTIVE


# --------------------------------------------------------------------- #
# E4C-T15 — close route delegates to the existing close_session behavior.
# --------------------------------------------------------------------- #
def test_e4c_t15_close_route_delegates_to_close_session(monkeypatch):
    from app.modules.session import SessionStatus

    client = _client()
    controller, _ = _wire(monkeypatch)
    session_id = client.post("/pilot/sessions").json()["session_id"]

    resp = client.post(f"/pilot/sessions/{session_id}/close")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CLOSED"

    snapshot = controller.get_session(session_id)
    assert snapshot.status is SessionStatus.CLOSED


# --------------------------------------------------------------------- #
# E4C-T16 / E4C-T17 — legacy /ask and /ask/stream remain unchanged.
# Same assertions as the existing `test_transport_api.py` proofs, kept here
# only as a same-file regression tripwire for this E4C change.
# --------------------------------------------------------------------- #
def test_e4c_t16_legacy_ask_unchanged():
    client = _client()
    resp = client.post("/ask", json={"question": "   "})
    assert resp.status_code == 400
    assert resp.json()["error_stage"] == "invalid_request"


def test_e4c_t17_legacy_ask_stream_unchanged():
    client = _client()
    old = os.environ.pop("DEBUG", None)
    try:
        resp = client.get("/ask/stream", params={"question": "what is money?"})
        assert resp.status_code == 404
    finally:
        if old is not None:
            os.environ["DEBUG"] = old


# --------------------------------------------------------------------- #
# E4C-T18 — no pilot route bypasses SessionController to call Core.ask
# directly. Proven structurally (source inspection), not just behaviorally:
# the turn route's only path to a turn is `controller.run_turn`.
# --------------------------------------------------------------------- #
def test_e4c_t18_pilot_turn_route_never_calls_core_ask_directly():
    _client()  # skip early if fastapi/httpx are absent, same gate as above
    import app.main as main

    tree = ast.parse(inspect.getsource(main.run_pilot_turn))

    # No `<anything>.ask(...)` call exists anywhere in the route. Checked over
    # the AST, not the source text, so a prose mention of Core.ask() in a
    # comment can neither satisfy nor break this proof.
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "ask" not in called_attributes

    # The route's only path to a turn is the Controller's own public method.
    referenced_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "run_turn" in referenced_attributes
