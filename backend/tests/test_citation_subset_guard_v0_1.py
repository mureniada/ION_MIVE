"""Phase 2 tests: the CG-A1 citation-subset guard.

Scoped by operator decision (2026-09-29): the guard runs ONLY on a turn that
carries a non-empty conversation context. There, every cited
`evidence_document_id` in claims and relations must be an evidence item of
this turn's model context; a violation fails the turn closed, with nothing
stripped or repaired. Without context the pre-Phase-2 behaviour is unchanged:
the renderer silently excludes a stray citation (D20-20).
docs/ION_PHASE2_CONVERSATION_CONTEXT_AMENDMENT_v1.md.
"""

from __future__ import annotations

import pytest

from app.core import errors
from app.modules.turn_record import TurnClosureState
from tests.test_orchestrator_conversation_context_v0_1 import (
    PRIOR,
    context_of,
    ctx_core,
    ive_report,
)


def test_context_turn_with_stray_claim_citation_fails_closed(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report(claim_ids=("EV-1", "NOT-ADMITTED"))])
    captured = []
    with pytest.raises(errors.IonError) as info:
        core.ask("Tell me more", 3, conversation_context=context_of(PRIOR),
                 on_turn_record=captured.append)
    assert info.value.stage == errors.STAGE_NORMALIZATION
    assert "NOT-ADMITTED" in info.value.message
    [record] = captured
    assert record.closure_state is TurnClosureState.FAILED
    assert record.failure.error_stage == errors.STAGE_NORMALIZATION
    assert record.conversation_context is not None
    assert record.conversation_context.retrieval_query == "What is ION?\nTell me more"
    assert len(record.model_executions) == 1     # the execution that ran is recorded


def test_context_turn_with_stray_relation_citation_fails_closed(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report(relation_ids=("EV-9",))])
    with pytest.raises(errors.IonError) as info:
        core.ask("Tell me more", 3, conversation_context=context_of(PRIOR))
    assert info.value.stage == errors.STAGE_NORMALIZATION
    assert "EV-9" in info.value.message


def test_context_turn_with_admitted_citations_passes(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report(claim_ids=("EV-1", "EV-2"),
                                                relation_ids=("EV-2",))])
    result = core.ask("Tell me more", 3, conversation_context=context_of(PRIOR))
    assert result.status == "success"


def test_context_turn_failure_is_not_repaired(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report(claim_ids=("EV-1", "NOT-ADMITTED"))])
    with pytest.raises(errors.IonError):
        core.ask("Tell me more", 3, conversation_context=context_of(PRIOR))
    # no answer is produced at all: nothing was stripped and rendered instead


def test_no_context_stray_citation_keeps_pre_phase2_behaviour(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report(claim_ids=("EV-1", "NOT-ADMITTED"),
                                                relation_ids=("EV-9",))])
    calls = []
    original = core._enforce_citation_subset
    monkeypatch.setattr(core, "_enforce_citation_subset",
                        lambda *a, **k: calls.append(1) or original(*a, **k))
    captured = []
    result = core.ask("Question", 3, on_turn_record=captured.append)
    assert result.status == "success"
    assert calls == []                                   # guard never invoked
    # the renderer silently excludes the stray id, exactly as before (D20-20)
    assert [row["document_id"] for row in result.rendered["evidence"]] == ["EV-1"]
    assert captured[0].closure_state is TurnClosureState.COMPLETED
    assert captured[0].conversation_context is None


def test_first_session_turn_is_a_no_context_turn(monkeypatch):
    from app.modules.session import SessionController

    core, _ = ctx_core(monkeypatch, [ive_report(claim_ids=("EV-1", "NOT-ADMITTED"))])
    controller = SessionController(core=core)
    session = controller.create_session().session_id
    result = controller.run_turn(session, "First question", top_k=3)
    assert result.status == "success"                    # unchanged behaviour on turn 1
