"""Model Execution Profile contract (v0.1) — public package surface.

Pure policy-shape contract only. See `models.py` for the full law and
`profiles.py` for the one canonical profile this phase defines. This package
must never import the Model Gateway, a provider adapter, MIVE, the Model
Context builder, governed evidence, Core, the container, Settings, telemetry,
the renderer, or the Turn Record — it states execution policy shape only, and
knows nothing about how that policy is later carried out (TASK 20.3, not yet
authorized).
"""

from __future__ import annotations

from .models import (
    EXECUTION_PROFILE_CONTRACT_ID,
    EXECUTION_PROFILE_CONTRACT_VERSION,
    ExecutionMode,
    ExecutionProfile,
    ExecutionProfileError,
)
from .profiles import STANDARD_GEMINI

__all__ = [
    "EXECUTION_PROFILE_CONTRACT_ID",
    "EXECUTION_PROFILE_CONTRACT_VERSION",
    "ExecutionMode",
    "ExecutionProfile",
    "ExecutionProfileError",
    "STANDARD_GEMINI",
]
