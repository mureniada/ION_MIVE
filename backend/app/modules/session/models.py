"""Session model vocabulary (TASK 22 v0.1).

These types state WHAT a session's identity and turn history ARE, as an
immutable snapshot — never how a session's runtime state is mutated over
time. That responsibility belongs entirely to a later, separately authorized
`SessionController` (TASK 22.3B3+), which will own private mutable runtime
state and materialize a `Session` snapshot from it. Nothing in this module
runs a turn, calls `Core.ask()`, or manages any lock.

Session identity and turn ordering live OUTSIDE `TurnRecord` (OD22-02):
`TurnRecord` itself is imported here, by reference, and is never modified,
subclassed, or reinterpreted. A `SessionTurnEntry` binds a `TurnRecord` to
its session and ordinal; it does not re-derive or duplicate anything the
`TurnRecord` already states, and it does not care whether that record is
COMPLETED or FAILED — a successfully captured FAILED `TurnRecord` is a real,
ordinal-consuming entry exactly like a COMPLETED one (OD22-12). Session
models never inspect or branch on `closure_state`.

Structural absence (OD22-08). Session state may contain lifecycle/identity
metadata and immutable `TurnRecord` references ONLY. There is deliberately
no field anywhere in this module for evidence content, a `GovernedEvidenceSet`
value, model-output text, a rendered answer, conversation memory, or a
dialogue instruction — not nullable, not optional, simply absent. Whatever a
`TurnRecord` itself does not carry (evidence content, rendered output — see
`turn_record/models.py`) cannot enter a session's state through this module
either, since a `TurnRecord` is referenced by identity only.

`ActiveTurnReservation.reservation_id` is a CONTROLLER-OWNED identity
(OD22-13): it is never the Core/TurnRecord `turn_id`, and this module holds
no mechanism that could make it one — `Core.ask()` mints `turn_id`
internally and does not expose it until a turn closes, so a reservation
identity necessarily predates and is independent of it.

Every public type here is frozen (OD22-17): a `Session` is a snapshot, not a
mutable store. `ordered_turns` is a plain `tuple`, never a list, and nothing
in this module ever reorders, sorts, or otherwise "helps" a caller who
supplies entries out of order or with gaps — such input fails closed with
`SessionModelError` instead.

This module imports the standard library and `TurnRecord` only. No Core,
orchestrator, container, controller, transport, retrieval, governance, or
provider module is reachable from here, and nothing here can call any of
them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..turn_record import TurnRecord


class SessionModelError(ValueError):
    """Raised when a Session-model invariant is violated at construction.

    Local to the Session model layer, exactly like `TurnRecordMaterializationError`
    is local to the Turn Record layer: no new transport stage or core error
    mapping is introduced here, and none is decided by this module.
    """


class SessionStatus(str, Enum):
    """A session's lifecycle state. Exactly two values exist at v0.1.

    There is deliberately no PAUSED, SUSPENDED, or other intermediate value:
    nothing in TASK 22 v0.1 can produce one, and declaring one would state a
    session state the system cannot reach.
    """

    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


def _require_non_empty_str(value: object, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise SessionModelError(f"{what} must be a non-empty string, found {value!r}")
    return value


def _require_ordinal(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SessionModelError(f"{what} must be an integer >= 1, found {value!r}")
    return value


@dataclass(frozen=True, kw_only=True)
class ActiveTurnReservation:
    """An opaque, Controller-owned claim on the next turn ordinal (OD22-13).

    `reservation_id` identifies the in-flight attempt itself, minted by the
    Controller BEFORE a turn runs — `Core.ask()` mints its own `turn_id`
    internally and does not expose it until the turn closes, so a
    reservation cannot be, and must never be presented as, that `turn_id`.
    Once a turn closes, the reservation is discarded; only the resulting
    `SessionTurnEntry.turn_id` (if any) carries the real Core identity.
    """

    reservation_id: str
    turn_ordinal: int

    def __post_init__(self) -> None:
        _require_non_empty_str(self.reservation_id, "reservation_id")
        _require_ordinal(self.turn_ordinal, "turn_ordinal")


@dataclass(frozen=True, kw_only=True)
class SessionTurnEntry:
    """One captured turn's place in a session's ordered history.

    Deliberately closed to exactly these four fields: a session identity, an
    ordinal, a turn identity, and a reference to the `TurnRecord` `Core.ask()`
    already produced. There is no field for evidence, model-output text, a
    rendered answer, or anything else `TurnRecord` itself does not carry.

    Whether `turn_record.closure_state` is COMPLETED or FAILED is never
    inspected here (OD22-12): a captured FAILED record is exactly as valid an
    entry as a COMPLETED one, and this type does not reinterpret either.
    """

    session_id: str
    turn_ordinal: int
    turn_id: str
    turn_record: TurnRecord

    def __post_init__(self) -> None:
        _require_non_empty_str(self.session_id, "session_id")
        _require_non_empty_str(self.turn_id, "turn_id")
        _require_ordinal(self.turn_ordinal, "turn_ordinal")
        if not isinstance(self.turn_record, TurnRecord):
            raise SessionModelError(
                f"turn_record must be a TurnRecord, found {type(self.turn_record).__name__}"
            )
        if self.turn_id != self.turn_record.turn_id:
            raise SessionModelError(
                f"turn_id {self.turn_id!r} does not match turn_record.turn_id "
                f"{self.turn_record.turn_id!r}"
            )


@dataclass(frozen=True, kw_only=True)
class Session:
    """An immutable snapshot of one session's identity, status, and history.

    This is a SNAPSHOT, not a store: there is no mutable list or dict field
    here, and none is added later by any caller — a later `SessionController`
    owns private mutable runtime state and materializes a new `Session`
    instance each time its observable state changes. `ordered_turns` is a
    plain, already-ordered `tuple`; nothing in this type reorders, sorts, or
    deduplicates what it is given. Invalid input fails closed with
    `SessionModelError` rather than being silently corrected.

    Invariants enforced structurally, not by convention:

    - every `SessionTurnEntry` in `ordered_turns` names THIS session
      (`entry.session_id == session_id`);
    - `ordered_turns` ordinals are exactly `1, 2, ..., N`, in that supplied
      order — no gaps, no reordering, no duplicates;
    - no two entries share a `turn_id`;
    - `next_turn_ordinal` always equals `len(ordered_turns) + 1` — the
      ordinal a turn reservation or a newly appended entry would take next,
      whether or not one is currently reserved;
    - `active_turn`, when present, requires `status is ACTIVE` and
      `active_turn.turn_ordinal == next_turn_ordinal`;
    - `status is CLOSED` requires `active_turn is None`.
    """

    session_id: str
    created_at: str
    status: SessionStatus
    next_turn_ordinal: int
    active_turn: ActiveTurnReservation | None = None
    ordered_turns: tuple[SessionTurnEntry, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_str(self.session_id, "session_id")
        _require_non_empty_str(self.created_at, "created_at")
        if not isinstance(self.status, SessionStatus):
            raise SessionModelError(
                f"status must be a SessionStatus, found {self.status!r}"
            )
        _require_ordinal(self.next_turn_ordinal, "next_turn_ordinal")

        if not isinstance(self.ordered_turns, tuple):
            raise SessionModelError(
                "ordered_turns must be supplied as a tuple, found "
                f"{type(self.ordered_turns).__name__}"
            )
        for entry in self.ordered_turns:
            if not isinstance(entry, SessionTurnEntry):
                raise SessionModelError(
                    "ordered_turns must contain only SessionTurnEntry values, "
                    f"found {type(entry).__name__}"
                )
            if entry.session_id != self.session_id:
                raise SessionModelError(
                    f"entry belongs to session {entry.session_id!r}, not this "
                    f"session {self.session_id!r}"
                )

        # Contiguous, already-ordered, no gaps: this rejects out-of-order,
        # non-contiguous, or duplicate-ordinal input rather than reordering
        # or otherwise "helping" the caller.
        expected_ordinals = list(range(1, len(self.ordered_turns) + 1))
        actual_ordinals = [entry.turn_ordinal for entry in self.ordered_turns]
        if actual_ordinals != expected_ordinals:
            raise SessionModelError(
                "ordered_turns must be contiguous, gap-free, and already in "
                f"ordinal order 1..N; found ordinals {actual_ordinals!r}"
            )

        turn_ids = [entry.turn_id for entry in self.ordered_turns]
        if len(set(turn_ids)) != len(turn_ids):
            raise SessionModelError("ordered_turns must not contain duplicate turn_ids")

        if self.active_turn is not None and not isinstance(
            self.active_turn, ActiveTurnReservation
        ):
            raise SessionModelError(
                "active_turn must be an ActiveTurnReservation or None, found "
                f"{type(self.active_turn).__name__}"
            )

        if self.status is SessionStatus.CLOSED and self.active_turn is not None:
            raise SessionModelError("a CLOSED session must not carry an active_turn")

        # The ordinal a turn would take next is always len(ordered_turns) + 1,
        # whether or not one is currently reserved — a reservation claims
        # that same next ordinal; it does not advance past it.
        if self.next_turn_ordinal != len(self.ordered_turns) + 1:
            raise SessionModelError(
                "next_turn_ordinal must equal len(ordered_turns) + 1 "
                f"({self.next_turn_ordinal!r} != {len(self.ordered_turns) + 1!r})"
            )

        if self.active_turn is not None:
            if self.status is not SessionStatus.ACTIVE:
                raise SessionModelError("active_turn requires status ACTIVE")
            if self.active_turn.turn_ordinal != self.next_turn_ordinal:
                raise SessionModelError(
                    "active_turn.turn_ordinal must equal next_turn_ordinal "
                    f"({self.active_turn.turn_ordinal!r} != "
                    f"{self.next_turn_ordinal!r})"
                )
