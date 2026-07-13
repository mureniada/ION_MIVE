"""Clock adapter (kept tiny; injected so tests can use a deterministic clock)."""

from __future__ import annotations

import time
from datetime import datetime, timezone


class SystemClock:
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def monotonic_ms(self) -> float:
        return time.monotonic() * 1000.0
