"""Session / Turn Controller vocabulary (TASK 22 v0.1) — identity, status,
turn history, and the in-memory Controller that runs turns over them.

The export list is deliberately closed to the approved public surface only:
the frozen model types (TASK 22.3B2) plus the Controller and its exception
hierarchy (TASK 22.3B3). No private runtime-state type is exported — in
particular `_SessionState` stays internal to `controller.py`.
"""

from .controller import (
    ConcurrentTurnError,
    SessionClosedError,
    SessionController,
    SessionControllerError,
    TurnRecordCaptureError,
    UnknownSessionError,
)
from .models import (
    ActiveTurnReservation,
    Session,
    SessionModelError,
    SessionStatus,
    SessionTurnEntry,
)

__all__ = [
    "ActiveTurnReservation",
    "ConcurrentTurnError",
    "Session",
    "SessionClosedError",
    "SessionController",
    "SessionControllerError",
    "SessionModelError",
    "SessionStatus",
    "SessionTurnEntry",
    "TurnRecordCaptureError",
    "UnknownSessionError",
]
