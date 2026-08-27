"""Deterministic, fail-closed materialization of a GovernedEvidenceSet (v0.1).

Pure: no I/O, no clock, no randomness, no persistence, no provider call. It
imports the standard library and this package's own vocabulary, nothing else.

What it does NOT do, and must not be extended to do without a new authorization:
it does not govern, admit, promote, validate, resolve provenance, recompute a
fingerprint, retrieve, size a context, judge sufficiency, or build a Model
Context. It re-labels a governance result Core already produced, and refuses
whenever that result does not match what the contract expects.

Every check below is fail-closed. A violated invariant raises
`GovernedEvidenceMaterializationError`; none is ever downgraded to a Product
UNKNOWN, which would invent a per-candidate verdict the runtime never returned.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, NoReturn

from .models import (
    ACCOUNTING_STATE_NOT_SUBMITTED,
    GOVERNANCE_COMPLETE,
    NATIVE_STATUS_PENDING,
    NATIVE_STATUS_VERIFIED,
    NATIVE_VALIDATION_PASS,
    CandidateAccounting,
    CandidateAccountingEntry,
    GovernanceDisposition,
    GovernedEvidenceEntry,
    GovernedEvidenceMaterializationError,
    GovernedEvidenceSet,
    MaterializationInput,
)

MATERIALIZER_ID = "ION_GOVERNED_EVIDENCE_MATERIALIZER_V0_1"
MATERIALIZER_VERSION = "0.1"

_MISSING = object()


# --------------------------------------------------------------------------- #
# fail-closed primitives
# --------------------------------------------------------------------------- #
def _fail(message: str) -> NoReturn:
    raise GovernedEvidenceMaterializationError(message)


def _attr(obj: Any, name: str, what: str) -> Any:
    """Read one native field, or refuse. A missing field is never defaulted."""
    value = getattr(obj, name, _MISSING)
    if value is _MISSING:
        _fail(f"{what} does not expose the required native field: {name}")
    return value


def _required_text(value: Any, what: str) -> str:
    """Require a non-empty string, taken verbatim. Nothing is trimmed or cased."""
    if not isinstance(value, str) or not value:
        _fail(f"{what} must be a non-empty string, found {value!r}")
    return value


def _require_native_value(value: Any, expected: str, what: str) -> Any:
    """Compare a native value by its own string value, and return it unchanged.

    The native governance enums subclass `str`, so equality reads the native
    value without importing the vocabulary that defines it. The value is
    returned as received so callers carry the native object, not a copy.
    """
    if not isinstance(value, str) or value != expected:
        _fail(f"{what}: expected native {expected}, found {value!r}")
    return value


def _require_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{what} must be a non-negative integer, found {value!r}")
    return value


def _sequence(value: Any, what: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        _fail(f"{what} must be supplied as a tuple or list, found {type(value).__name__}")
    return tuple(value)


def _identities(value: Any, what: str) -> tuple[str, ...]:
    ids = tuple(
        _required_text(item, f"{what} identity") for item in _sequence(value, f"{what} identities")
    )
    if len(set(ids)) != len(ids):
        _fail(f"duplicate {what} identity in {list(ids)}")
    return ids


def _index_by_evidence_id(items: tuple[Any, ...], what: str) -> dict[str, Any]:
    """Index native objects by their OWN evidence_id — never by list position."""
    index: dict[str, Any] = {}
    for item in items:
        candidate_id = _required_text(
            _attr(item, "evidence_id", what), f"{what} evidence_id"
        )
        if candidate_id in index:
            _fail(f"duplicate {what} for candidate {candidate_id}")
        index[candidate_id] = item
    return index


def _context_pack_metadata(value: Any) -> Mapping[str, Any]:
    """Carry Product-owned pack metadata verbatim, as a read-only view."""
    if not isinstance(value, Mapping):
        _fail(
            "context_pack_metadata must be a mapping carried verbatim, "
            f"found {type(value).__name__}"
        )
    return MappingProxyType(dict(value))


# --------------------------------------------------------------------------- #
# materialization
# --------------------------------------------------------------------------- #
def materialize_governed_evidence_set(
    source: MaterializationInput,
) -> GovernedEvidenceSet:
    """Materialize the governed basis of one COMPLETED governance run.

    Raises `GovernedEvidenceMaterializationError` on any other outcome state and
    on every contract violation.
    """
    if not isinstance(source, MaterializationInput):
        _fail(
            "materialization requires a MaterializationInput, "
            f"found {type(source).__name__}"
        )

    # --- governance-state gate: GOVERNANCE_COMPLETE is the only entry ------ #
    # GOVERNANCE_REJECTED is set-level and destructive (a rejected run returns
    # no per-candidate basis at all, not even for candidates already verified
    # before the failure), and OPERATIONAL_FAILURE is not a governance verdict.
    # Neither can be materialized, and neither is parsed for per-item meaning.
    state = source.outcome_state
    if not isinstance(state, str) or state != GOVERNANCE_COMPLETE:
        _fail(
            f"a GovernedEvidenceSet exists only for {GOVERNANCE_COMPLETE}; "
            f"refused outcome state: {state!r}"
        )

    native_result = source.native_result
    if native_result is None:
        _fail(f"{GOVERNANCE_COMPLETE} requires a native governance result")

    what_native = "native governance result"
    records = _sequence(_attr(native_result, "records", what_native), "native records")
    validations = _sequence(
        _attr(native_result, "validations", what_native), "native validations"
    )
    transitions = _sequence(
        _attr(native_result, "transitions", what_native), "native transitions"
    )

    # --- cardinality ------------------------------------------------------- #
    if not len(records) == len(validations) == len(transitions):
        _fail(
            "native records / validations / transitions cardinality mismatch: "
            f"{len(records)} / {len(validations)} / {len(transitions)}"
        )

    governed_count = _require_int(source.governed_count, "governed_count")
    if len(records) != governed_count:
        _fail(
            f"governed_count {governed_count} does not match "
            f"{len(records)} returned native records"
        )

    candidate_count = _require_int(source.candidate_count, "candidate_count")
    retrieved_ids = _identities(source.retrieved_candidate_ids, "retrieved candidate")
    if len(retrieved_ids) != candidate_count:
        _fail(
            f"candidate_count {candidate_count} does not match "
            f"{len(retrieved_ids)} retrieved candidates"
        )

    submitted_ids = _identities(source.submitted_candidate_ids, "submitted candidate")

    # --- identity, by value ------------------------------------------------ #
    governed_ids = tuple(
        _required_text(_attr(record, "evidence_id", "native record"), "native record evidence_id")
        for record in records
    )
    if len(set(governed_ids)) != len(governed_ids):
        _fail(f"duplicate native record evidence_id in {list(governed_ids)}")

    retrieved_set = set(retrieved_ids)
    submitted_set = set(submitted_ids)
    governed_set = set(governed_ids)

    if not submitted_set <= retrieved_set:
        _fail(
            "submitted candidates are not a subset of retrieved candidates: "
            f"{sorted(submitted_set - retrieved_set)}"
        )
    if governed_set != submitted_set:
        _fail(
            "governed identities do not equal submitted identities; "
            f"governed-only {sorted(governed_set - submitted_set)}, "
            f"submitted-only {sorted(submitted_set - governed_set)}"
        )

    # Accounting only: excluded before governance, therefore never disposed.
    not_submitted_ids = tuple(cid for cid in retrieved_ids if cid not in submitted_set)
    if governed_set & set(not_submitted_ids):
        _fail(
            "governed and NOT_SUBMITTED axes overlap: "
            f"{sorted(governed_set & set(not_submitted_ids))}"
        )

    validation_by_id = _index_by_evidence_id(validations, "native validation")
    transition_by_id = _index_by_evidence_id(transitions, "native transition")

    if set(validation_by_id) != governed_set:
        _fail(
            "native validation identities do not match native record identities: "
            f"{sorted(set(validation_by_id) ^ governed_set)}"
        )
    if set(transition_by_id) != governed_set:
        _fail(
            "native transition identities do not match native record identities: "
            f"{sorted(set(transition_by_id) ^ governed_set)}"
        )

    # --- per-candidate governance basis ------------------------------------ #
    admitted: list[GovernedEvidenceEntry] = []
    for record in records:
        # Re-read the record's own identity and join the other two native
        # objects by that value. List position is never the identity contract.
        candidate_id = _required_text(
            _attr(record, "evidence_id", "native record"), "native record evidence_id"
        )
        validation = validation_by_id[candidate_id]
        transition = transition_by_id[candidate_id]

        # Only native VERIFIED admits. Any other returned status — PENDING,
        # PROMOTED, REJECTED, UNKNOWN or anything else — fails closed here and
        # is never re-labelled as a Product UNKNOWN.
        native_status = _require_native_value(
            _attr(record, "status", "native record"),
            NATIVE_STATUS_VERIFIED,
            f"native record {candidate_id} status",
        )

        _require_native_value(
            _attr(validation, "result", "native validation"),
            NATIVE_VALIDATION_PASS,
            f"native validation {candidate_id} result",
        )
        blocking_reasons = _sequence(
            _attr(validation, "blocking_reasons", "native validation"),
            f"native validation {candidate_id} blocking_reasons",
        )
        if blocking_reasons != ():
            _fail(
                f"native validation {candidate_id} carries blocking reasons: "
                f"{list(blocking_reasons)}"
            )

        record_validation_id = _required_text(
            _attr(record, "validation_id", "native record"),
            f"native record {candidate_id} validation_id",
        )
        validation_id = _required_text(
            _attr(validation, "validation_id", "native validation"),
            f"native validation {candidate_id} validation_id",
        )
        transition_validation_id = _required_text(
            _attr(transition, "validation_id", "native transition"),
            f"native transition {candidate_id} validation_id",
        )
        if record_validation_id != validation_id:
            _fail(
                f"native record {candidate_id} validation_id {record_validation_id!r} "
                f"does not match native validation {validation_id!r}"
            )
        if validation_id != transition_validation_id:
            _fail(
                f"native validation {candidate_id} validation_id {validation_id!r} "
                f"does not match native transition {transition_validation_id!r}"
            )

        _require_native_value(
            _attr(transition, "from_status", "native transition"),
            NATIVE_STATUS_PENDING,
            f"native transition {candidate_id} from_status",
        )
        _require_native_value(
            _attr(transition, "to_status", "native transition"),
            NATIVE_STATUS_VERIFIED,
            f"native transition {candidate_id} to_status",
        )

        fingerprint = _attr(record, "fingerprint", "native record")
        if fingerprint is None:
            _fail(f"native record {candidate_id} carries no fingerprint")
        fingerprint_hash = _required_text(
            _attr(fingerprint, "hash", "native record fingerprint"),
            f"native record {candidate_id} fingerprint hash",
        )
        validated_hash = _required_text(
            _attr(validation, "evidence_fingerprint_hash", "native validation"),
            f"native validation {candidate_id} evidence_fingerprint_hash",
        )
        if fingerprint_hash != validated_hash:
            _fail(
                f"native record {candidate_id} fingerprint hash {fingerprint_hash!r} "
                f"does not match validated hash {validated_hash!r}"
            )

        admitted.append(
            GovernedEvidenceEntry(
                candidate_id=candidate_id,
                # An ADDITIONAL Product label over an unchanged native status.
                disposition=GovernanceDisposition.ADMITTED,
                native_status=native_status,
                native_record=record,
                native_validation=validation,
                native_transition=transition,
            )
        )

    accounting = CandidateAccounting(
        retrieved_ids=retrieved_ids,
        submitted_ids=submitted_ids,
        governed_ids=governed_ids,
        not_submitted=tuple(
            CandidateAccountingEntry(
                candidate_id=candidate_id,
                accounting_state=ACCOUNTING_STATE_NOT_SUBMITTED,
            )
            for candidate_id in not_submitted_ids
        ),
        retrieved_count=len(retrieved_ids),
        governed_count=len(governed_ids),
        context_pack_metadata=_context_pack_metadata(source.context_pack_metadata),
    )

    return GovernedEvidenceSet(
        admitted=tuple(admitted),
        rejected=(),
        unknown=(),
        accounting=accounting,
        backend_id=_required_text(source.backend_id, "backend_id"),
        mapping_profile_id=_required_text(source.mapping_profile_id, "mapping_profile_id"),
        adapter_id=_required_text(source.adapter_id, "adapter_id"),
        adapter_version=_required_text(source.adapter_version, "adapter_version"),
        context_pack_id=_required_text(source.context_pack_id, "context_pack_id"),
        question_id=_required_text(source.question_id, "question_id"),
    )
