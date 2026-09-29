"""Phase 2 tests: the SessionController's bounded, in-session context window.

Amendment OD22-08-A1 (docs/ION_PHASE2_CONVERSATION_CONTEXT_AMENDMENT_v1.md):
last 2 COMPLETED turns only, FAILED and CLARIFY never enter, no cross-session
memory, and Adaptive Dialogue still receives only the current normalized
question (OD23-05/06 unchanged). A REAL SessionController over a REAL Core
built from stand-in ports; no provider, no network.
"""

from __future__ import annotations

import importlib.util
import unittest

import pytest

from app.core import errors
from app.modules.adaptive_dialogue import AdaptiveDialogueEngine, DialogueTurnInput
from app.modules.session import SessionController
from tests.test_orchestrator_conversation_context_v0_1 import (
    RecordingRetrieval,
    ctx_core,
    ive_report,
)
from tests.test_session_controller_v0_1 import CLARIFY_Q


class SpyDialogueEngine(AdaptiveDialogueEngine):
    def __init__(self):
        super().__init__()
        self.inputs = []

    def evaluate(self, turn_input):
        self.inputs.append(turn_input)
        return super().evaluate(turn_input)


def controller_for(monkeypatch, reports, **kwargs):
    core, engine = ctx_core(monkeypatch, reports, **kwargs)
    spy = SpyDialogueEngine()
    return SessionController(core=core, dialogue_engine=spy), core, engine, spy


# --------------------------------------------------------------------- #
# same-session follow-up
# --------------------------------------------------------------------- #
def test_follow_up_turn_carries_the_prior_turn_context(monkeypatch):
    controller, core, engine, _ = controller_for(monkeypatch, [
        ive_report(abstract="ION is a monetary instrument.", uncertainty=("Scope unclear.",)),
        ive_report(abstract="In practice it works like this."),
    ])
    session = controller.create_session()
    controller.run_turn(session.session_id, "What is ION and how does it work?", top_k=3)
    controller.run_turn(session.session_id, "How does that work in practice?", top_k=3)

    first, second = engine.model_inputs
    assert first.conversation_memory is None
    [turn] = second.conversation_memory.turns
    assert turn.question == "What is ION and how does it work?"
    assert turn.interpretation == "ION is a monetary instrument."
    assert turn.uncertainty == ("Scope unclear.",)
    assert core._retrieval.queries == [
        "What is ION and how does it work?",
        "What is ION and how does it work?\nHow does that work in practice?",
    ]
    assert "PRIOR CONVERSATION (NOT EVIDENCE):" in engine.prompts[1]
    assert "PRIOR CONVERSATION" not in engine.prompts[0]


# --------------------------------------------------------------------- #
# RQ-A1-R1: root-anchored follow-up retrieval
# --------------------------------------------------------------------- #
Q1 = "What is ION and how does it work?"
Q2 = "Tell me more."
Q3 = "How does that work in practice?"
Q4 = "What are the risks?"


def test_four_turn_sequence_is_root_anchored(monkeypatch):
    reports = [ive_report(abstract=f"ASSISTANT-TEXT-T{i}", uncertainty=(f"ASSISTANT-UNC-T{i}",))
               for i in range(1, 5)]
    controller, core, engine, _ = controller_for(monkeypatch, reports)
    session = controller.create_session().session_id
    for question in (Q1, Q2, Q3, Q4):
        controller.run_turn(session, question, top_k=3)

    assert core._retrieval.queries == [
        Q1,                   # 1. T1 = Q1
        Q1 + "\n" + Q2,       # 2. T2 = Q1 + Q2
        Q1 + "\n" + Q3,       # 3. T3 = Q1 + Q3
        Q1 + "\n" + Q4,       # 4. T4 = Q1 + Q4 ...
    ]
    # ... even though Q1 has fallen out of the 2-turn context window at T4
    assert [t.question for t in engine.model_inputs[3].conversation_memory.turns] == [Q2, Q3]
    # 8. assistant/model text never enters retrieval
    for query in core._retrieval.queries:
        assert "ASSISTANT-" not in query
    # the exact retrieval query is recorded on every context turn
    records = [e.turn_record for e in controller.get_session(session).ordered_turns]
    assert records[0].conversation_context is None
    assert [r.conversation_context.retrieval_query for r in records[1:]] == \
        core._retrieval.queries[1:]
    assert controller._sessions[session].root_question == Q1


def test_root_is_isolated_per_session(monkeypatch):
    controller, core, _, _ = controller_for(monkeypatch, [ive_report() for _ in range(4)])
    a = controller.create_session().session_id
    b = controller.create_session().session_id
    controller.run_turn(a, "Root of A?", top_k=3)
    controller.run_turn(b, "Root of B?", top_k=3)
    controller.run_turn(a, "Follow-up A", top_k=3)
    controller.run_turn(b, "Follow-up B", top_k=3)
    assert core._retrieval.queries[2:] == ["Root of A?\nFollow-up A", "Root of B?\nFollow-up B"]


def test_clarify_before_first_completed_turn_does_not_establish_a_root(monkeypatch):
    controller, core, _, _ = controller_for(monkeypatch, [ive_report(), ive_report()])
    session = controller.create_session().session_id
    controller.run_turn(session, CLARIFY_Q, top_k=3)          # CLARIFY: no Core.ask
    assert controller._sessions[session].root_question is None
    controller.run_turn(session, "Actual first question", top_k=3)
    controller.run_turn(session, "Tell me more", top_k=3)
    assert core._retrieval.queries == [
        "Actual first question", "Actual first question\nTell me more",
    ]


def test_failed_turn_before_first_completed_turn_does_not_establish_a_root(monkeypatch):
    from app.core import errors as core_errors

    class _FailingThenOk:
        def __init__(self):
            self.calls = 0

        def retrieve(self, question, top_k):
            from types import SimpleNamespace

            self.calls += 1
            self.queries.append(question)
            if self.calls == 1:
                raise core_errors.RetrievalError("controlled retrieval failure")
            return [SimpleNamespace(document_id=c, content="body") for c in ("EV-1", "EV-2", "EV-3")]

    retrieval = _FailingThenOk()
    retrieval.queries = []
    controller, core, _, _ = controller_for(
        monkeypatch, [ive_report(), ive_report()], retrieval=retrieval,
    )
    session = controller.create_session().session_id
    with pytest.raises(errors.IonError):
        controller.run_turn(session, "Failed first question", top_k=3)
    assert controller._sessions[session].root_question is None
    controller.run_turn(session, "Completed first question", top_k=3)
    controller.run_turn(session, "Tell me more", top_k=3)
    assert retrieval.queries[-1] == "Completed first question\nTell me more"
    assert controller._sessions[session].root_question == "Completed first question"


def test_new_session_gets_a_new_root(monkeypatch):
    controller, core, _, _ = controller_for(monkeypatch, [ive_report() for _ in range(4)])
    first = controller.create_session().session_id
    controller.run_turn(first, "Old root?", top_k=3)
    controller.run_turn(first, "Old follow-up", top_k=3)
    controller.close_session(first)
    second = controller.create_session().session_id
    controller.run_turn(second, "New root?", top_k=3)
    controller.run_turn(second, "New follow-up", top_k=3)
    assert core._retrieval.queries == [
        "Old root?", "Old root?\nOld follow-up", "New root?", "New root?\nNew follow-up",
    ]


def test_root_is_capped_with_the_question_cap(monkeypatch):
    controller, core, _, _ = controller_for(monkeypatch, [ive_report(), ive_report()])
    session = controller.create_session().session_id
    long_root = "r" * 900
    controller.run_turn(session, long_root, top_k=3)
    controller.run_turn(session, "Tell me more", top_k=3)
    assert core._retrieval.queries[1] == "r" * 499 + "…" + "\nTell me more"


def test_dialogue_engine_still_receives_only_the_current_question(monkeypatch):
    controller, _, _, spy = controller_for(monkeypatch, [ive_report(), ive_report()])
    session = controller.create_session()
    controller.run_turn(session.session_id, "  First question  ", top_k=3)
    controller.run_turn(session.session_id, "Tell me more", top_k=3)
    assert spy.inputs == [
        DialogueTurnInput(question="First question"),
        DialogueTurnInput(question="Tell me more"),
    ]


# --------------------------------------------------------------------- #
# cross-session isolation
# --------------------------------------------------------------------- #
def test_interleaved_sessions_never_share_context(monkeypatch):
    controller, _, engine, _ = controller_for(monkeypatch, [
        ive_report(abstract="A-1"), ive_report(abstract="B-1"),
        ive_report(abstract="A-2"), ive_report(abstract="B-2"),
    ])
    a = controller.create_session().session_id
    b = controller.create_session().session_id
    controller.run_turn(a, "Session A first", top_k=3)
    controller.run_turn(b, "Session B first", top_k=3)
    controller.run_turn(a, "Session A second", top_k=3)
    controller.run_turn(b, "Session B second", top_k=3)

    a2, b2 = engine.model_inputs[2], engine.model_inputs[3]
    assert [t.question for t in a2.conversation_memory.turns] == ["Session A first"]
    assert [t.interpretation for t in a2.conversation_memory.turns] == ["A-1"]
    assert [t.question for t in b2.conversation_memory.turns] == ["Session B first"]
    assert [t.interpretation for t in b2.conversation_memory.turns] == ["B-1"]


def test_a_new_session_after_close_starts_without_context(monkeypatch):
    controller, _, engine, _ = controller_for(monkeypatch, [ive_report(), ive_report()])
    first = controller.create_session().session_id
    controller.run_turn(first, "Earlier topic", top_k=3)
    controller.close_session(first)
    second = controller.create_session().session_id
    controller.run_turn(second, "Fresh start", top_k=3)
    assert engine.model_inputs[1].conversation_memory is None


# --------------------------------------------------------------------- #
# bounded history
# --------------------------------------------------------------------- #
def test_window_holds_only_the_last_two_completed_turns(monkeypatch):
    reports = [ive_report(abstract=f"Interpretation {i}") for i in range(1, 6)]
    controller, _, engine, _ = controller_for(monkeypatch, reports)
    session = controller.create_session().session_id
    for i in range(1, 6):
        controller.run_turn(session, f"Question {i}", top_k=3)

    fifth = engine.model_inputs[4]
    assert [t.question for t in fifth.conversation_memory.turns] == ["Question 3", "Question 4"]
    state = controller._sessions[session]
    assert [p.question for p in state.context_window] == ["Question 4", "Question 5"]


def test_oversized_fields_are_capped_in_the_window(monkeypatch):
    controller, _, engine, _ = controller_for(monkeypatch, [
        ive_report(abstract="a" * 5000, uncertainty=("u" * 900,) * 5),
        ive_report(),
    ])
    session = controller.create_session().session_id
    controller.run_turn(session, "q" * 900, top_k=3)
    controller.run_turn(session, "Tell me more", top_k=3)
    [turn] = engine.model_inputs[1].conversation_memory.turns
    assert len(turn.question) == 500
    assert len(turn.interpretation) == 1200
    assert len(turn.uncertainty) == 3 and all(len(u) == 300 for u in turn.uncertainty)
    total = len(turn.question) + len(turn.interpretation) + sum(map(len, turn.uncertainty))
    assert total <= 4000


# --------------------------------------------------------------------- #
# CLARIFY / FAILED never enter the window
# --------------------------------------------------------------------- #
def test_clarify_adds_nothing_and_does_not_clear_the_window(monkeypatch):
    controller, _, engine, _ = controller_for(monkeypatch, [ive_report(), ive_report()])
    session = controller.create_session().session_id
    controller.run_turn(session, "Real question", top_k=3)
    controller.run_turn(session, CLARIFY_Q, top_k=3)      # CLARIFY: no Core.ask
    controller.run_turn(session, "Tell me more", top_k=3)
    assert len(engine.model_inputs) == 2
    assert [t.question for t in engine.model_inputs[1].conversation_memory.turns] == [
        "Real question"
    ]


def test_failed_turn_does_not_enter_the_window(monkeypatch):
    controller, _, engine, _ = controller_for(monkeypatch, [
        ive_report(abstract="Good first"),
        ive_report(claim_ids=("NOT-ADMITTED",)),   # context turn -> guard fails it
        ive_report(),
    ])
    session = controller.create_session().session_id
    controller.run_turn(session, "First", top_k=3)
    with pytest.raises(errors.IonError):
        controller.run_turn(session, "Second", top_k=3)
    controller.run_turn(session, "Third", top_k=3)
    third = engine.model_inputs[2]
    assert [t.question for t in third.conversation_memory.turns] == ["First"]
    # the FAILED turn is still preserved in the session's own history
    snapshot = controller.get_session(session)
    assert len(snapshot.ordered_turns) == 3


# --------------------------------------------------------------------- #
# transport: a guard failure is a 422 on /pilot/.../turn
# --------------------------------------------------------------------- #
def test_pilot_turn_returns_422_when_a_context_turn_cites_non_admitted_evidence(monkeypatch):
    if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx") is None:
        raise unittest.SkipTest("fastapi/httpx not installed")
    from fastapi.testclient import TestClient

    import app.main as main
    from app.core.config import Settings

    controller, core, _, _ = controller_for(monkeypatch, [
        ive_report(), ive_report(claim_ids=("NOT-ADMITTED",)),
    ])
    settings = Settings.load({"GEMINI_MODEL": "gemini-test"})
    monkeypatch.setattr(main, "_get_core", lambda: (settings, core))
    monkeypatch.setattr(main, "_get_session_controller", lambda: controller)
    monkeypatch.setattr(main, "require_ready", lambda *a, **k: None)
    client = TestClient(main.app)

    session_id = client.post("/pilot/sessions").json()["session_id"]
    first = client.post(f"/pilot/sessions/{session_id}/turn", json={"question": "What is ION?"})
    assert first.status_code == 200 and first.json()["kind"] == "answer"
    second = client.post(f"/pilot/sessions/{session_id}/turn", json={"question": "Tell me more"})
    assert second.status_code == 422
    assert second.json()["error_stage"] == "normalization"
