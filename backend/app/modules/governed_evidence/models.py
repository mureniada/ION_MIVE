"""Product-level Governed Evidence Output vocabulary (v0.1).

A `GovernedEvidenceSet` is a PRODUCT object. It is materialized only from
information a completed Core governance run already returned through the Core
Adapter boundary, plus Product-owned request accounting. It owns no admission,
provenance or fingerprint semantics and never re-derives a governance
conclusion: native governance objects are carried by reference, verbatim.

Two axes are kept strictly apart and are never substituted for one another:

    CANDIDATE ACCOUNTING     RETRIEVED / SUBMITTED / NOT_SUBMITTED / GOVERNED
    GOVERNANCE DISPOSITION   ADMITTED / REJECTED / UNKNOWN

`CandidateAccountingEntry` therefore carries no disposition field at all — not
even a nullable one — so no reader can mistake an accounting state for a
verdict, and a NOT_SUBMITTED candidate can never be read as governed evidence.

This module imports the standard library only. No Core, Core Adapter, admission,
runtime-evidence-bridge, provenance-resolver or retrieval entry point is
reachable from here, so no mutation authority and no governance vocabulary can
be reached through Product code by way of this package. Native status values are
compared through their own string value (the native enums subclass `str`), which
reads them without importing the vocabulary that defines them.

v0.1 production rules, enforced in `materializer.py` and pinned structurally by
`GovernedEvidenceSet` below:

    ADMITTED   may be produced, and only from a native VERIFIED record.
    REJECTED   must never be produced — no current runtime path returns a
               candidate-specific rejection basis.
    UNKNOWN    must never be produced — no current runtime path returns a
               candidate-specific unknown basis.

Both members are declared so the Product vocabulary is complete; neither is
reachable at v0.1. No value in this module is derived from a wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

GOVERNED_EVIDENCE_SET_ID = "ION_GOVERNED_EVIDENCE_SET_V0_1"
GOVERNED_EVIDENCE_SET_VERSION = "0.1"

# Core Adapter outcome state that alone permits materialization. Held as a plain
# string so this module never imports the adapter that defines it.
GOVERNANCE_COMPLETE = "GOVERNANCE_COMPLETE"

# Native governance values this module reads, held as plain strings for the same
# reason. These are read, never assigned to a native object.
NATIVE_STATUS_PENDING = "PENDING"
NATIVE_STATUS_VERIFIED = "VERIFIED"
NATIVE_VALIDATION_PASS = "PASS"

# The single accounting literal for a candidate excluded before governance.
ACCOUNTING_STATE_NOT_SUBMITTED = "NOT_SUBMITTED"


class GovernedEvidenceMaterializationError(ValueError):
    """Raised whenever governed evidence cannot be materialized as contracted.

    Every failure is closed: a violated invariant, an unexpected native status
    or a non-complete governance outcome raises. None of them is ever mapped to
    a Product UNKNOWN, which would invent a per-candidate verdict the runtime
    did not return.
    """


class GovernanceDisposition(str, Enum):
    """Product governance dispositions. Only ADMITTED is producible at v0.1."""

    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, kw_only=True)
class GovernedEvidenceEntry:
    """One candidate's Product disposition over its native governance basis.

    `disposition` is an ADDITIONAL Product label. It never replaces
    `native_status`, which carries the native value verbatim, and the three
    native objects are held by reference exactly as Core returned them.
    """

    candidate_id: str
    disposition: GovernanceDisposition
    native_status: str
    native_record: Any
    native_validation: Any
    native_transition: Any


@dataclass(frozen=True, kw_only=True)
class CandidateAccountingEntry:
    """A candidate excluded before governance. Accounting state, never a verdict.

    This type deliberately has no disposition field, so a NOT_SUBMITTED
    candidate cannot be read as ADMITTED, REJECTED or UNKNOWN, and is never
    eligible for Model Context evidence.
    """

    candidate_id: str
    accounting_state: str = ACCOUNTING_STATE_NOT_SUBMITTED


@dataclass(frozen=True, kw_only=True)
class CandidateAccounting:
    """The accounting axis: which candidates reached which stage, by identity.

    `context_pack_metadata` is Product-owned accounting context carried verbatim.
    It is never parsed into a governance reason: exclusion before governance has
    no governance meaning at all.
    """

    retrieved_ids: tuple[str, ...]
    submitted_ids: tuple[str, ...]
    governed_ids: tuple[str, ...]
    not_submitted: tuple[CandidateAccountingEntry, ...]
    retrieved_count: int
    governed_count: int
    context_pack_metadata: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class GovernedEvidenceSet:
    """The full governed basis returned by one completed governance run.

    This is the basis BEFORE any later context sizing. It performs no
    sufficiency judgement and no Model Context selection.

    `rejected` and `unknown` exist to state the complete Product vocabulary and
    are pinned empty: producing either would require a candidate-specific basis
    that no current runtime path returns.
    """

    admitted: tuple[GovernedEvidenceEntry, ...]
    rejected: tuple[GovernedEvidenceEntry, ...] = ()
    unknown: tuple[GovernedEvidenceEntry, ...] = ()
    accounting: CandidateAccounting
    backend_id: str
    mapping_profile_id: str
    adapter_id: str
    adapter_version: str
    context_pack_id: str
    question_id: str
    governed_evidence_set_id: str = GOVERNED_EVIDENCE_SET_ID
    governed_evidence_set_version: str = GOVERNED_EVIDENCE_SET_VERSION

    def __post_init__(self) -> None:
        # v0.1 production law, enforced structurally rather than by convention:
        # no construction path — materializer or caller — can populate a
        # per-candidate REJECTED or UNKNOWN verdict.
        if self.rejected != ():
            raise GovernedEvidenceMaterializationError(
                "v0.1 produces ADMITTED only: `rejected` must stay empty — no "
                "current runtime path returns a candidate-specific rejection basis"
            )
        if self.unknown != ():
            raise GovernedEvidenceMaterializationError(
                "v0.1 produces ADMITTED only: `unknown` must stay empty — no "
                "current runtime path returns a candidate-specific unknown basis"
            )


@dataclass(frozen=True, kw_only=True)
class MaterializationInput:
    """Product-side input to materialization. Carries no Core Adapter type.

    The Product caller already holds every value here: the governance outcome it
    invoked, the candidates it submitted, and the Context Pack it built. Passing
    identities rather than objects keeps raw retrieval metadata out of this
    module entirely, so governance data can never be recovered by re-reading it.

    Deliberately absent: any field for `native_gate_error` or bridge rejection
    reasons. Those are set-level, free-form, and are never parsed into
    per-candidate verdicts — so this contract gives them nowhere to enter.
    """

    outcome_state: str
    native_result: Any
    retrieved_candidate_ids: Sequence[str]
    submitted_candidate_ids: Sequence[str]
    candidate_count: int
    governed_count: int
    backend_id: str
    mapping_profile_id: str
    adapter_id: str
    adapter_version: str
    context_pack_id: str
    question_id: str
    context_pack_metadata: Mapping[str, Any]
