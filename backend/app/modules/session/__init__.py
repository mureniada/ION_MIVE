"""Session model vocabulary (TASK 22 v0.1) — identity, status, turn history.

The export list is deliberately closed to the approved model surface only.
No `SessionController` type is exported here: it does not exist yet, and
this package must not be extended to imply otherwise before it is
separately authorized and implemented.
"""

from .models import (
    ActiveTurnReservation,
    Session,
    SessionModelError,
    SessionStatus,
    SessionTurnEntry,
)

__all__ = [
    "ActiveTurnReservation",
    "Session",
    "SessionModelError",
    "SessionStatus",
    "SessionTurnEntry",
]
