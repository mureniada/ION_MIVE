"""TASK 22.3B2 test: the Session model layer (identity/status/history snapshot).

Scope is deliberately narrow: this proves ONLY the model layer in
`app/modules/session/models.py` — construction, immutability, and the
invariants `Session.__post_init__`/`SessionTurnEntry.__post_init__` enforce.
No `SessionController` exists yet, no lock, no runtime session management,
and `Core.ask()` is never called — real `TurnRecord` instances are built
directly through the frozen TASK 18 materializers, never through a live turn.

No Gemini/OpenAI/provider SDK is reachable from anything below.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from types import SimpleNamespace

import pytest

from app.modules.session import (
    ActiveTurnReservation,
    Session,
    SessionModelError,
    SessionStatus,
    SessionTurnEntry,
)
import app.modules.session.models as session_models
from app.modules.turn_record import (
    ModelExecutionBinding,
    TurnClosureState,
    TurnConfigurationBinding,
    TurnFailure,
    TurnRecord,
    materialize_failed_turn_record,
    materialize_turn_record,
)


# --------------------------------------------------------------------- #
# helpers — build real TurnRecord instances through the frozen TASK 18
# materializers, never a stand-in shape.
# --------------------------------------------------------------------- #
def _configuration() -> TurnConfigurationBinding:
    return TurnConfigurationBinding(
        effective_top_k=3,
        context_char_budget=60000,
        retrieval_collection="ion_corpus_v1",
        app_version="0.1.0",
        pricing_as_of="2026-01-01",
    )


def _failed_turn_record(turn_id: str) -> TurnRecord:
    return materialize_failed_turn_record(
        turn_id=turn_id,
        turn_started_at="ISO-0",
        turn_closed_at="ISO-1",
        failure=TurnFailure(error_type="RuntimeError"),
        configuration=_configuration(),
    )


def _governed_basis() -> SimpleNamespace:
    return SimpleNamespace(
        governed_evidence_set_id="GES-1",
        governed_evidence_set_version="0.1",
        question_id="Q-1",
        context_pack_id="CP-1",
        backend_id="TEST-BACKEND",
        mapping_profile_id="TEST-PROFILE",
        adapter_id="ADAPTER-1",
        adapter_version="0.1",
        accounting=SimpleNamespace(
            retrieved_count=2, submitted_ids=("EV-1", "EV-2"), governed_count=2
        ),
    )


def _completed_turn_record(turn_id: str) -> TurnRecord:
    return materialize_turn_record(
        turn_id=turn_id,
        question="Question",
        governed_basis=_governed_basis(),
        context_pack_id="CP-1",
        model_executions=(
            ModelExecutionBinding(
                engine_id="gemini",
                provider="gemini",
                requested_model="gemini-3.1-flash-lite",
                input_tokens=10,
                output_tokens=5,
                latency_ms=1.0,
                usage_is_estimated=False,
                estimated_cost=0.1,
            ),
        ),
        mive_overall_status="partial_agreement",
        configuration=_configuration(),
        turn_started_at="ISO-0",
        turn_closed_at="ISO-1",
        retrieval_latency_ms=1.0,
        comparison_latency_ms=1.0,
        pipeline_latency_ms=2.0,
    )


def _entry(session_id="S-1", turn_ordinal=1, turn_id="TURN-1", turn_record=None):
    if turn_record is None:
        turn_record = _failed_turn_record(turn_id)
    return SessionTurnEntry(
        session_id=session_id, turn_ordinal=turn_ordinal, turn_id=turn_id,
        turn_record=turn_record,
    )


# --------------------------------------------------------------------- #
# 1. SessionStatus has exactly ACTIVE and CLOSED
# --------------------------------------------------------------------- #
def test_1_session_status_has_exactly_active_and_closed():
    assert {s.value for s in SessionStatus} == {"ACTIVE", "CLOSED"}
    assert SessionStatus.ACTIVE.value == "ACTIVE"
    assert SessionStatus.CLOSED.value == "CLOSED"


# --------------------------------------------------------------------- #
# 2/3/4. frozen dataclasses
# --------------------------------------------------------------------- #
def test_2_active_turn_reservation_is_frozen():
    reservation = ActiveTurnReservation(reservation_id="R-1", turn_ordinal=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        reservation.turn_ordinal = 2


def test_3_session_turn_entry_is_frozen():
    entry = _entry()
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.turn_ordinal = 2


def test_4_session_is_frozen():
    session = Session(
        session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
        next_turn_ordinal=1,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        session.next_turn_ordinal = 2


# --------------------------------------------------------------------- #
# 5. valid empty ACTIVE session
# --------------------------------------------------------------------- #
def test_5_valid_empty_active_session_constructs():
    session = Session(
        session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
        next_turn_ordinal=1,
    )
    assert session.next_turn_ordinal == 1
    assert session.active_turn is None
    assert session.ordered_turns == ()


# --------------------------------------------------------------------- #
# 6. valid ACTIVE session with reservation
# --------------------------------------------------------------------- #
def test_6_valid_active_session_with_reservation():
    reservation = ActiveTurnReservation(reservation_id="R-1", turn_ordinal=1)
    session = Session(
        session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
        next_turn_ordinal=1, active_turn=reservation,
    )
    assert session.active_turn.turn_ordinal == session.next_turn_ordinal
    # the reservation is never the Core turn_id (OD22-13) — a distinct type
    assert not isinstance(session.active_turn, str)


# --------------------------------------------------------------------- #
# 7. CLOSED session with active_turn is rejected
# --------------------------------------------------------------------- #
def test_7_closed_session_with_active_turn_rejected():
    reservation = ActiveTurnReservation(reservation_id="R-1", turn_ordinal=1)
    with pytest.raises(SessionModelError):
        Session(
            session_id="S-1", created_at="ISO-0", status=SessionStatus.CLOSED,
            next_turn_ordinal=1, active_turn=reservation,
        )


# --------------------------------------------------------------------- #
# 8. SessionTurnEntry rejects mismatched turn_id
# --------------------------------------------------------------------- #
def test_8_session_turn_entry_rejects_mismatched_turn_id():
    record = _failed_turn_record(turn_id="TURN-REAL")
    with pytest.raises(SessionModelError):
        SessionTurnEntry(
            session_id="S-1", turn_ordinal=1, turn_id="TURN-WRONG",
            turn_record=record,
        )


# --------------------------------------------------------------------- #
# 9. SessionTurnEntry rejects empty session_id / turn_id / ordinal < 1
# --------------------------------------------------------------------- #
def test_9_session_turn_entry_rejects_invalid_fields():
    record = _failed_turn_record(turn_id="TURN-1")
    with pytest.raises(SessionModelError):
        SessionTurnEntry(session_id="", turn_ordinal=1, turn_id="TURN-1", turn_record=record)
    with pytest.raises(SessionModelError):
        SessionTurnEntry(session_id="S-1", turn_ordinal=1, turn_id="", turn_record=record)
    with pytest.raises(SessionModelError):
        SessionTurnEntry(session_id="S-1", turn_ordinal=0, turn_id="TURN-1", turn_record=record)


# --------------------------------------------------------------------- #
# 10. Session rejects entries belonging to another session
# --------------------------------------------------------------------- #
def test_10_session_rejects_entries_from_another_session():
    entry = _entry(session_id="OTHER-SESSION", turn_ordinal=1, turn_id="TURN-1")
    with pytest.raises(SessionModelError):
        Session(
            session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
            next_turn_ordinal=2, ordered_turns=(entry,),
        )


# --------------------------------------------------------------------- #
# 11. Session rejects non-contiguous turn ordinals
# --------------------------------------------------------------------- #
def test_11_session_rejects_non_contiguous_ordinals():
    e1 = _entry(turn_ordinal=1, turn_id="TURN-1")
    e3 = _entry(turn_ordinal=3, turn_id="TURN-3")  # gap: ordinal 2 missing
    with pytest.raises(SessionModelError):
        Session(
            session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
            next_turn_ordinal=3, ordered_turns=(e1, e3),
        )


# --------------------------------------------------------------------- #
# 12. Session rejects duplicate turn_ids
# --------------------------------------------------------------------- #
def test_12_session_rejects_duplicate_turn_ids():
    e1 = _entry(turn_ordinal=1, turn_id="TURN-1")
    e2 = _entry(turn_ordinal=2, turn_id="TURN-1")  # same turn_id as e1
    with pytest.raises(SessionModelError):
        Session(
            session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
            next_turn_ordinal=3, ordered_turns=(e1, e2),
        )


# --------------------------------------------------------------------- #
# 13. Session does NOT silently reorder entries
# --------------------------------------------------------------------- #
def test_13_session_does_not_silently_reorder_entries():
    e1 = _entry(turn_ordinal=1, turn_id="TURN-1")
    e2 = _entry(turn_ordinal=2, turn_id="TURN-2")
    # supplied out of order — must be rejected, never silently sorted
    with pytest.raises(SessionModelError):
        Session(
            session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
            next_turn_ordinal=3, ordered_turns=(e2, e1),
        )


# --------------------------------------------------------------------- #
# 14. Session next_turn_ordinal consistency is enforced
# --------------------------------------------------------------------- #
def test_14_session_next_turn_ordinal_consistency_enforced():
    e1 = _entry(turn_ordinal=1, turn_id="TURN-1")
    # one entry present, but next_turn_ordinal wrongly still claims 1
    with pytest.raises(SessionModelError):
        Session(
            session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
            next_turn_ordinal=1, ordered_turns=(e1,),
        )


# --------------------------------------------------------------------- #
# 15. ordered_turns is an immutable tuple; a list is rejected outright
# --------------------------------------------------------------------- #
def test_15_ordered_turns_is_immutable_tuple():
    session = Session(
        session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
        next_turn_ordinal=1,
    )
    assert isinstance(session.ordered_turns, tuple)

    with pytest.raises(SessionModelError):
        Session(
            session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
            next_turn_ordinal=1, ordered_turns=[],  # list, not tuple
        )


# --------------------------------------------------------------------- #
# 16. structural field test — no evidence/output/memory/dialogue content
# --------------------------------------------------------------------- #
def test_16_structural_fields_contain_no_forbidden_content():
    forbidden_substrings = (
        "evidence", "governed_evidence", "model_output", "rendered_response",
        "response", "history", "memory", "dialogue_instruction",
        "dialogue_profile",
    )
    for cls in (Session, SessionTurnEntry, ActiveTurnReservation):
        field_names = {f.name.lower() for f in dataclasses.fields(cls)}
        for name in field_names:
            for forbidden in forbidden_substrings:
                assert forbidden not in name, (
                    f"{cls.__name__}.{name} carries forbidden content ({forbidden})"
                )


# --------------------------------------------------------------------- #
# 17. existing TurnRecord dataclass fields are unchanged
# --------------------------------------------------------------------- #
def test_17_turn_record_fields_unchanged():
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
# 18. a FAILED TurnRecord is permitted exactly as a COMPLETED one is
# --------------------------------------------------------------------- #
def test_18_failed_and_completed_turn_records_both_permitted():
    failed = _failed_turn_record(turn_id="TURN-F")
    completed = _completed_turn_record(turn_id="TURN-C")

    entry_failed = SessionTurnEntry(
        session_id="S-1", turn_ordinal=1, turn_id="TURN-F", turn_record=failed,
    )
    entry_completed = SessionTurnEntry(
        session_id="S-1", turn_ordinal=1, turn_id="TURN-C", turn_record=completed,
    )

    assert entry_failed.turn_record.closure_state is TurnClosureState.FAILED
    assert entry_completed.turn_record.closure_state is TurnClosureState.COMPLETED

    # both entries also compose into a Session's ordered_turns without any
    # closure-state-dependent rejection
    session_failed = Session(
        session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
        next_turn_ordinal=2, ordered_turns=(entry_failed,),
    )
    session_completed = Session(
        session_id="S-1", created_at="ISO-0", status=SessionStatus.ACTIVE,
        next_turn_ordinal=2, ordered_turns=(entry_completed,),
    )
    assert session_failed.ordered_turns[0].turn_record.closure_state is TurnClosureState.FAILED
    assert session_completed.ordered_turns[0].turn_record.closure_state is TurnClosureState.COMPLETED


# --------------------------------------------------------------------- #
# 19. no model in this layer produces or derives evidence
# --------------------------------------------------------------------- #
def test_19_session_models_touches_no_evidence_or_governance_module():
    """Checks actual import statements only (not prose in comments/docstrings,
    which legitimately discusses what this module does NOT import)."""
    tree = ast.parse(inspect.getsource(session_models))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    for forbidden in (
        "governed_evidence", "retrieval", "core_adapter", "model_gateway",
        "model_context", "renderer",
    ):
        assert not any(forbidden in module for module in imported_modules), (
            f"session/models.py must not import {forbidden}"
        )


# --------------------------------------------------------------------- #
# 20. no provider is executed anywhere in this layer
# --------------------------------------------------------------------- #
def test_20_session_models_touches_no_provider():
    source = inspect.getsource(session_models).lower()
    for forbidden in ("gemini", "openai", "genai"):
        assert forbidden not in source, f"session/models.py must not reference {forbidden}"


# --------------------------------------------------------------------- #
# additional: package exports are closed to the approved public surface
#
# TASK 22.3B3 authoritatively expanded this package's public surface from
# the five frozen model symbols (TASK 22.3B2) to those PLUS the approved
# Controller API and its exception hierarchy (OD22-16/OD22-17). The exact
# approved set is stated below rather than weakened into a subset check:
# an unreviewed addition must fail this test, in either direction.
# --------------------------------------------------------------------- #
FROZEN_MODEL_EXPORTS = frozenset({
    "ActiveTurnReservation", "Session", "SessionModelError",
    "SessionStatus", "SessionTurnEntry",
})

APPROVED_CONTROLLER_EXPORTS = frozenset({
    "SessionController", "SessionControllerError", "UnknownSessionError",
    "SessionClosedError", "ConcurrentTurnError", "TurnRecordCaptureError",
})


def test_package_exports_only_the_approved_public_surface():
    import app.modules.session as session_pkg

    exported = set(session_pkg.__all__)

    # exact approved surface — no unrelated export is admitted, and none of
    # the approved ones may quietly disappear
    assert exported == set(FROZEN_MODEL_EXPORTS | APPROVED_CONTROLLER_EXPORTS)

    # every frozen TASK 22.3B2 model export survives the B3 expansion
    assert FROZEN_MODEL_EXPORTS <= exported

    # the approved Controller public API is present
    assert APPROVED_CONTROLLER_EXPORTS <= exported

    # every exported name actually resolves on the package
    for name in exported:
        assert hasattr(session_pkg, name), f"{name} is exported but not present"

    # no private runtime-state type is exported: _SessionState is internal
    # to controller.py and must never reach the package surface
    assert not any(name.startswith("_") for name in exported)
    assert "_SessionState" not in exported
    assert not hasattr(session_pkg, "_SessionState")


def test_session_model_error_is_a_value_error():
    assert issubclass(SessionModelError, ValueError)
