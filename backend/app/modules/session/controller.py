"""Session / Turn Controller (TASK 22.3B3, v0.1).

The Controller sits STRICTLY ABOVE `Core.ask()` (L22-07). It owns session
identity, lifecycle, and ordered turn membership; it never re-implements,
re-derives, or duplicates anything `Core.ask()` already does. Every turn that
runs is run by calling `Core.ask()` exactly once, through the frozen
`on_turn_record` capture seam (TASK 22.3B1) — the Controller never touches
retrieval, governance, the Model Gateway, or the renderer directly, and never
reorders or reruns any stage of the governed pipeline underneath Core.

Adaptive Dialogue seam (E1). Between admission and `Core.ask()`, `run_turn()`
evaluates `AdaptiveDialogueEngine` exactly once per eligible interaction. On
PROCEED the governed path below runs completely unchanged. On CLARIFY no turn
runs at all: `Core.ask()` is never called, so there is no Core `request_id`,
no Core-minted `turn_id`, no `TurnRecord`, and no `SessionTurnEntry` — the
reserved ordinal is released WITHOUT being committed and is taken again by the
next eligible interaction, and the session stays ACTIVE. The two outcomes are
distinguishable by TYPE at the public boundary (`AskResult` versus
`SessionClarificationOutcome`), never by a flag on a fabricated result. The
engine decides only; every session-level consequence is this Controller's,
and the Controller passes it nothing but a `DialogueTurnInput`.

Because Core suppresses any exception the observer itself raises (OD22-11),
the Controller cannot rely on the observer's own control flow to signal
success or failure. Instead, after `Core.ask()` returns or raises, the
Controller inspects what was ACTUALLY captured — zero records, one COMPLETED
record, or one FAILED record — and only ever preserves a `SessionTurnEntry`
from a record it actually received. A missing or malformed capture is never
papered over: it either fails closed with `TurnRecordCaptureError` (on the
success path, where the caller must be told nothing usable happened) or is
silently skipped while the ORIGINAL Core exception still wins (on the
failure path, where OD22-11's guarantee — an observer fault must never
replace the real failure — extends to this Controller's own bookkeeping).

Two lock roles exist per session, both released before returning control to
whichever caller is waiting on them, and NEITHER is ever held across the
`Core.ask()` call itself except the first:

- `turn_lock` — held for the FULL duration of one `run_turn()` call,
  including the `Core.ask()` call inside it. A non-blocking acquire is how
  "at most one active turn per session" (OD22-19, L22-11) is enforced, and
  the SAME lock is how `close_session()` detects an in-flight turn: if it
  cannot acquire `turn_lock` without blocking, a turn is running.
- `guard` — held only for the brief instant it takes to read or write the
  small mutable fields (`status`, `next_turn_ordinal`, `active_reservation`,
  `entries`) as one atomic unit, so `get_session()` can safely build a
  consistent `Session` snapshot — including observing `active_turn` while a
  turn is genuinely in flight (L22-11's "active turn" is meant to be
  observable, not merely inferred) — without ever blocking on `turn_lock`
  and therefore without ever blocking for the duration of `Core.ask()`.
  `turn_lock` alone already serializes every WRITE to these fields (both
  `run_turn` and `close_session` require it first); `guard` exists solely so
  concurrent READS stay consistent, exactly the same "short, never held
  across Core.ask()" discipline OD22-14 already states for the registry
  lock, applied at the per-session field level.

A third, short-lived lock (`_registry_lock`) protects only the Controller's
`session_id -> _SessionState` dictionary itself (creation and lookup), and
is released before this method returns — never held anywhere near
`Core.ask()` (OD22-14). Different sessions' turns run under entirely
different `turn_lock` objects, so they are never globally serialized.

Private runtime state (`_SessionState`) carries lifecycle/identity metadata
and `SessionTurnEntry` REFERENCES only — the exact same closed shape
`Session` itself enforces (OD22-08): no evidence content, no model-output
text, no rendered answer, no conversation memory, no dialogue instruction.
Every value returned to a caller is a fresh, immutable `Session` snapshot
built from the already-frozen models in `session/models.py` — there is no
second public Session representation.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from ..adaptive_dialogue import (
    AdaptiveDialogueEngine,
    DialogueDecisionType,
    DialogueReasonCode,
    DialogueTurnInput,
)
from ..turn_record import TurnClosureState, TurnRecord
from .models import (
    ActiveTurnReservation,
    Session,
    SessionStatus,
    SessionTurnEntry,
)

# Imported only for the constructor's type hint and this method's return
# type — read-only references, never called except via `core.ask()` itself,
# and never a path back into retrieval, governance, the Model Gateway, or
# the renderer (L22-07: Controller owns lifecycle, Core owns one turn).
from ...core.models import AskResult
from ...core.orchestrator import Core


class SessionControllerError(Exception):
    """Base of the Controller's own exception hierarchy (OD22-16).

    Distinct from `SessionModelError`, which stays in the model layer for
    invariant violations at `Session`/`SessionTurnEntry` construction time.
    """


class UnknownSessionError(SessionControllerError):
    """Raised for any operation naming a `session_id` this Controller never issued."""


class SessionClosedError(SessionControllerError):
    """Raised when `run_turn()` is requested against a CLOSED session."""


class ConcurrentTurnError(SessionControllerError):
    """Raised when a session already has one turn in flight.

    Covers both directions: a second `run_turn()` on the same session while
    one is running, and a `close_session()` attempted while one is running
    (OD22-19) — both are detected through the same non-blocking acquire of
    that session's `turn_lock`.
    """


class TurnRecordCaptureError(SessionControllerError):
    """Raised only on the SUCCESS path, when Core.ask() returns normally but
    what the capture seam actually received does not match a usable,
    COMPLETED TurnRecord (none captured, more than one, or a malformed one).

    Never raised in place of an original Core exception on the failure path
    (OD22-11): there, an unusable or missing capture is silently skipped and
    the real failure still propagates unchanged.
    """


@dataclass(frozen=True, kw_only=True)
class SessionClarificationOutcome:
    """What `run_turn()` returns when the dialogue layer answered CLARIFY.

    A DISTINCT type, deliberately not an `AskResult` and deliberately not an
    exception: a clarification is neither a governed answer nor a failure. It
    is also not a `TurnRecord` and not a `SessionTurnEntry` — no Core turn was
    started, so there is no turn identity to carry and none is invented here.

    Exactly three fields. `turn_ordinal` is the ordinal that was RESERVED and
    then released WITHOUT being committed (OD22-13's reserved/committed
    distinction): the very next eligible interaction on this session takes
    that same ordinal. `reason_code` names the deterministic rule that
    actually fired. There is deliberately no field for clarification text, a
    prompt, a confidence, a score, evidence, a turn id, or any minted
    identifier — this type states that a turn did NOT run, and why, nothing
    more.
    """

    session_id: str
    turn_ordinal: int
    reason_code: DialogueReasonCode


class _SessionState:
    """Private mutable runtime state for one session. Never exposed publicly.

    Holds exactly: identity, lifecycle status, the next ordinal, the current
    reservation (if any), and an append-only list of `SessionTurnEntry`
    REFERENCES. Nothing else — no evidence, no model output, no rendered
    text, no memory, no dialogue instruction; `SessionTurnEntry` itself
    already carries none of that (see `session/models.py`), and this class
    adds nothing beyond binding entries to their session.
    """

    def __init__(self, session_id: str, created_at: str) -> None:
        self.session_id = session_id
        self.created_at = created_at
        self.status = SessionStatus.ACTIVE
        self.next_turn_ordinal = 1
        self.active_reservation: ActiveTurnReservation | None = None
        self.entries: list[SessionTurnEntry] = []
        # Held for the full duration of one run_turn() call, Core.ask()
        # included — see the module docstring for why two lock roles exist.
        self.turn_lock = threading.Lock()
        # Held only to read/write the fields above as one atomic unit.
        self.guard = threading.Lock()

    def _build_snapshot_locked(self) -> Session:
        """Build a Session snapshot. Caller must already hold `guard`."""
        return Session(
            session_id=self.session_id,
            created_at=self.created_at,
            status=self.status,
            next_turn_ordinal=self.next_turn_ordinal,
            active_turn=self.active_reservation,
            ordered_turns=tuple(self.entries),
        )

    def snapshot(self) -> Session:
        with self.guard:
            return self._build_snapshot_locked()


class SessionController:
    """TASK 22 v0.1 in-memory Session / Turn Controller.

    Public surface only: `create_session`, `get_session`, `run_turn`,
    `close_session`. All four return, or raise over, the already-frozen
    `Session`/`SessionTurnEntry` model types — never a second representation.
    """

    def __init__(
        self, core: Core, dialogue_engine: AdaptiveDialogueEngine | None = None
    ) -> None:
        self._core = core
        # Injected so a test can substitute a spy/stub engine; defaulted so
        # every existing construction site keeps working unchanged. The
        # engine is stateless and carries no constructor argument of its own,
        # so a default instance is not shared mutable state.
        self._dialogue_engine = (
            AdaptiveDialogueEngine() if dialogue_engine is None else dialogue_engine
        )
        self._sessions: dict[str, _SessionState] = {}
        self._registry_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def _get_state(self, session_id: str) -> _SessionState:
        with self._registry_lock:
            state = self._sessions.get(session_id)
        if state is None:
            raise UnknownSessionError(f"unknown session_id: {session_id!r}")
        return state

    # ------------------------------------------------------------------ #
    def create_session(self) -> Session:
        session_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        state = _SessionState(session_id=session_id, created_at=created_at)
        with self._registry_lock:
            self._sessions[session_id] = state
        return state.snapshot()

    # ------------------------------------------------------------------ #
    def get_session(self, session_id: str) -> Session:
        state = self._get_state(session_id)
        return state.snapshot()

    # ------------------------------------------------------------------ #
    def close_session(self, session_id: str) -> Session:
        state = self._get_state(session_id)

        # The SAME lock run_turn() holds for its whole duration: unable to
        # acquire it without blocking means a turn is genuinely in flight
        # (OD22-19), never inferred from any separate flag.
        if not state.turn_lock.acquire(blocking=False):
            raise ConcurrentTurnError(
                f"session {session_id!r} has an active turn in flight"
            )
        try:
            with state.guard:
                if state.status is SessionStatus.ACTIVE:
                    state.status = SessionStatus.CLOSED
                # Already CLOSED: OD22-20 — idempotent, no further mutation,
                # same snapshot-building path either way.
                return state._build_snapshot_locked()
        finally:
            state.turn_lock.release()

    # ------------------------------------------------------------------ #
    def run_turn(
        self, session_id: str, question: str, top_k: int | None = None
    ) -> AskResult | SessionClarificationOutcome:
        state = self._get_state(session_id)

        if not state.turn_lock.acquire(blocking=False):
            raise ConcurrentTurnError(
                f"session {session_id!r} already has a turn in flight"
            )

        try:
            with state.guard:
                if state.status is SessionStatus.CLOSED:
                    raise SessionClosedError(f"session {session_id!r} is CLOSED")
                turn_ordinal = state.next_turn_ordinal
                reservation = ActiveTurnReservation(
                    reservation_id=uuid.uuid4().hex, turn_ordinal=turn_ordinal,
                )
                state.active_reservation = reservation

            # --- dialogue evaluation seam --------------------------------- #
            # Strictly AFTER admission (CLOSED check, ordinal read, and the
            # reservation above) and strictly BEFORE Core.ask(). Evaluated
            # exactly once per eligible interaction — an interaction refused
            # earlier by admission never reaches this point at all.
            #
            # The engine is handed a DialogueTurnInput and nothing else: no
            # session identity, no ordinal, no history, no retrieval, no
            # evidence, no governance, no model or provider handle, no
            # renderer, and no persistence. It returns a decision; it does not
            # act on one. Everything the CLARIFY branch below does is done by
            # this Controller, not by the engine.
            decision = self._dialogue_engine.evaluate(
                DialogueTurnInput(question=question)
            )

            if decision.decision_type is DialogueDecisionType.CLARIFY:
                # No Core.ask(). Therefore: no Core request_id, no Core-minted
                # turn_id, no TurnRecord, no SessionTurnEntry, and no ordinal
                # advancement — `turn_ordinal` stays RESERVED-but-uncommitted
                # and is taken again by the next eligible interaction. The
                # shared `finally` below releases the reservation and the
                # turn lock on this path exactly as it does on every other,
                # leaving the session ACTIVE. Nothing is fabricated here: a
                # clarification did not produce a turn, and no history is
                # written to claim otherwise.
                return SessionClarificationOutcome(
                    session_id=session_id,
                    turn_ordinal=turn_ordinal,
                    reason_code=decision.reason_code,
                )

            # PROCEED falls through to the pre-existing governed path below,
            # unchanged: exactly one Core.ask(), the same capture seam, the
            # same preservation rules.

            # At most one captured TurnRecord is ever expected. This list is
            # the Controller's own observation of what Core actually did —
            # never authoritative on its own until validated below.
            captured: list[TurnRecord] = []

            try:
                # Exactly one Core.ask() call. The capture callback only
                # ever appends the exact object Core hands it: it does not
                # modify the TurnRecord and submits nothing back into Core.
                result = self._core.ask(
                    question, top_k, on_turn_record=captured.append,
                )
            except Exception:
                # Best-effort preservation only. OD22-11's guarantee — an
                # observer/bookkeeping fault must never replace the real
                # failure — extends here: whatever happens while preserving
                # a captured FAILED record, the ORIGINAL Core exception is
                # what propagates, unchanged, from this method.
                try:
                    self._preserve_failed_capture(
                        state, session_id, turn_ordinal, captured
                    )
                except Exception:
                    pass
                raise
            else:
                self._preserve_completed_capture(
                    state, session_id, turn_ordinal, captured
                )
                return result
        finally:
            with state.guard:
                state.active_reservation = None
            state.turn_lock.release()

    # ------------------------------------------------------------------ #
    def _preserve_completed_capture(
        self, state: _SessionState, session_id: str, turn_ordinal: int,
        captured: list[TurnRecord],
    ) -> None:
        """Success path only. Fails closed with TurnRecordCaptureError on
        anything but exactly one valid, COMPLETED capture — never fabricates
        a record, and never advances the ordinal when it refuses."""
        if len(captured) != 1:
            raise TurnRecordCaptureError(
                f"expected exactly one captured TurnRecord for session "
                f"{session_id!r}, found {len(captured)}"
            )
        record = captured[0]
        if (
            not isinstance(record, TurnRecord)
            or record.closure_state is not TurnClosureState.COMPLETED
            or not record.turn_id
        ):
            raise TurnRecordCaptureError(
                f"captured value for session {session_id!r} is not a valid "
                "COMPLETED TurnRecord"
            )

        entry = SessionTurnEntry(
            session_id=session_id, turn_ordinal=turn_ordinal,
            turn_id=record.turn_id, turn_record=record,
        )
        with state.guard:
            state.entries.append(entry)
            state.next_turn_ordinal = turn_ordinal + 1

    # ------------------------------------------------------------------ #
    def _preserve_failed_capture(
        self, state: _SessionState, session_id: str, turn_ordinal: int,
        captured: list[TurnRecord],
    ) -> None:
        """Failure path only. Never raises to its caller (see run_turn's own
        try/except around this call) and never fabricates a record: a
        missing or malformed capture is silently skipped, leaving the
        ordinal unconsumed and prior history untouched."""
        if len(captured) != 1:
            return
        record = captured[0]
        if (
            not isinstance(record, TurnRecord)
            or record.closure_state is not TurnClosureState.FAILED
            or not record.turn_id
        ):
            return

        entry = SessionTurnEntry(
            session_id=session_id, turn_ordinal=turn_ordinal,
            turn_id=record.turn_id, turn_record=record,
        )
        with state.guard:
            state.entries.append(entry)
            state.next_turn_ordinal = turn_ordinal + 1
