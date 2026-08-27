"""Boundary vocabulary for the Product-facing Core Adapter facade (v0.1).

These types describe ONLY the boundary between Product orchestration and the
frozen B0 governance stack. They deliberately carry no evidence-set vocabulary:
per-candidate ADMITTED / REJECTED / UNKNOWN semantics and GovernedEvidenceSet
belong to a later task and are not modelled here.

Native governance results are preserved by reference, never reinterpreted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

ADAPTER_ID = "ION_CORE_ADAPTER_FACADE_V0_1"
ADAPTER_VERSION = "0.1"


class CoreInvocationMode(str, Enum):
    """Pilot v1 chat governance is READ-ONLY. This enum has exactly one member."""

    READ_ONLY = "READ_ONLY"


class CoreAdapterOutcomeState(str, Enum):
    """Whole-invocation states, NOT per-candidate verdicts.

    B0 admission is all-or-nothing (claim_adjudication.run_runtime_admission_gate
    raises rather than recording a per-item status), so the adapter reports only
    the distinctions B0 actually makes.
    """

    GOVERNANCE_COMPLETE = "GOVERNANCE_COMPLETE"
    GOVERNANCE_REJECTED = "GOVERNANCE_REJECTED"
    OPERATIONAL_FAILURE = "OPERATIONAL_FAILURE"


@dataclass(frozen=True)
class CoreAdapterRequest:
    """Product-side candidate submission.

    `adapter_created_at` is supplied by the caller rather than generated here so
    that the timestamp value and its capture point stay exactly as B0 had them.
    """

    candidate_set_id: str
    question_id: str
    candidates: Sequence[Any]
    context_pack: Any
    adapter_created_at: str
    mode: CoreInvocationMode = CoreInvocationMode.READ_ONLY


@dataclass(frozen=True)
class CoreAdapterOutcome:
    """Product-side intermediate result. Native Core values are held verbatim."""

    outcome: CoreAdapterOutcomeState
    native_result: Any = None
    native_bridge_reasons: tuple[str, ...] = ()
    native_gate_error: str | None = None
    operational_error: str | None = None
    operational_exception: Exception | None = None
    candidate_count: int = 0
    governed_count: int = 0
    backend_id: str = ""
    mapping_profile_id: str = ""
    adapter_id: str = ADAPTER_ID
    adapter_version: str = ADAPTER_VERSION

    @property
    def is_complete(self) -> bool:
        return self.outcome is CoreAdapterOutcomeState.GOVERNANCE_COMPLETE
