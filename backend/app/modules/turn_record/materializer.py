"""Deterministic, fail-closed materialization of a TurnRecord (v0.1).

Pure: no I/O, no clock, no randomness, no persistence, no network, no
environment read, no provider call. It imports the standard library and this
package's own vocabulary, nothing else.

What it does NOT do, and must not be extended to do without a new
authorization: it does not govern, admit, retrieve, compare, render, judge
sufficiency, size a context, mint an identity, take a timestamp, or decide how
a turn ended. It records facts the caller already observed, and refuses
whenever those facts do not match what the contract expects.

The governed basis is read STRUCTURALLY, by attribute, so a real
`GovernedEvidenceSet` is consumed verbatim without this module importing the
module that defines it. Exactly the reference fields are read — identity,
binding and counts. The admitted, rejected and unknown entries, the native
records, validations and transitions, the fingerprints and the pack metadata
are never touched, so no governed evidence can be copied into a Turn Record
even by accident.

Only COMPLETED is produced here. `TurnClosureState.FAILED` exists in the
Product vocabulary because the runtime genuinely fails, but live failure
closure is a later, separately authorized step and has no entry point in this
module.

Every check below is fail-closed. A violated invariant raises
`TurnRecordMaterializationError`; none is ever downgraded into a partially
populated record, and none is ever converted into a governance verdict or an
evidence state.
"""

from __future__ import annotations

from typing import Any, NoReturn, Sequence

from .models import (
    QUESTION_NORMALIZATION_STRIP,
    GovernedEvidenceBinding,
    ModelExecutionBinding,
    TurnClosureState,
    TurnConfigurationBinding,
    TurnRecord,
    TurnRecordMaterializationError,
)

TURN_RECORD_MATERIALIZER_ID = "ION_TURN_RECORD_MATERIALIZER_V0_1"
TURN_RECORD_MATERIALIZER_VERSION = "0.1"

_WHAT_BASIS = "governed basis"
_MISSING = object()


# --------------------------------------------------------------------------- #
# fail-closed primitives
# --------------------------------------------------------------------------- #
def _fail(message: str) -> NoReturn:
    raise TurnRecordMaterializationError(message)


def _attr(obj: Any, name: str, what: str) -> Any:
    """Read one field, or refuse. A missing field is never defaulted."""
    value = getattr(obj, name, _MISSING)
    if value is _MISSING:
        _fail(f"{what} does not expose the required field: {name}")
    return value


def _text(value: Any, what: str) -> str:
    """Require a non-empty string, taken verbatim. Nothing is trimmed or cased."""
    if not isinstance(value, str) or not value:
        _fail(f"{what} must be a non-empty string, found {value!r}")
    return value


def _count(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{what} must be a non-negative integer, found {value!r}")
    return value


def _duration(value: Any, what: str) -> float:
    """Require a non-negative real measurement, carried verbatim — never rounded."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{what} must be a real number of milliseconds, found {value!r}")
    if value < 0:
        _fail(f"{what} must not be negative, found {value!r}")
    return value


def _sequence(value: Any, what: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        _fail(f"{what} must be supplied as a tuple or list, found {type(value).__name__}")
    return tuple(value)


# --------------------------------------------------------------------------- #
# governed basis: bound by reference, never copied
# --------------------------------------------------------------------------- #
def _bind_governed_evidence(governed_basis: Any) -> GovernedEvidenceBinding:
    """Bind the governed basis by identity and counts. Nothing else is read.

    `submitted_count` is derived deterministically from the accounting's own
    submitted identities, because the upstream contract exposes those
    identities rather than a dedicated count. It is a length, not a judgement.
    """
    accounting = _attr(governed_basis, "accounting", _WHAT_BASIS)
    what_accounting = f"{_WHAT_BASIS} accounting"

    submitted_ids = _sequence(
        _attr(accounting, "submitted_ids", what_accounting),
        f"{what_accounting} submitted identities",
    )

    return GovernedEvidenceBinding(
        governed_evidence_set_id=_text(
            _attr(governed_basis, "governed_evidence_set_id", _WHAT_BASIS),
            f"{_WHAT_BASIS} governed_evidence_set_id",
        ),
        governed_evidence_set_version=_text(
            _attr(governed_basis, "governed_evidence_set_version", _WHAT_BASIS),
            f"{_WHAT_BASIS} governed_evidence_set_version",
        ),
        question_id=_text(
            _attr(governed_basis, "question_id", _WHAT_BASIS),
            f"{_WHAT_BASIS} question_id",
        ),
        context_pack_id=_text(
            _attr(governed_basis, "context_pack_id", _WHAT_BASIS),
            f"{_WHAT_BASIS} context_pack_id",
        ),
        backend_id=_text(
            _attr(governed_basis, "backend_id", _WHAT_BASIS),
            f"{_WHAT_BASIS} backend_id",
        ),
        mapping_profile_id=_text(
            _attr(governed_basis, "mapping_profile_id", _WHAT_BASIS),
            f"{_WHAT_BASIS} mapping_profile_id",
        ),
        adapter_id=_text(
            _attr(governed_basis, "adapter_id", _WHAT_BASIS),
            f"{_WHAT_BASIS} adapter_id",
        ),
        adapter_version=_text(
            _attr(governed_basis, "adapter_version", _WHAT_BASIS),
            f"{_WHAT_BASIS} adapter_version",
        ),
        retrieved_count=_count(
            _attr(accounting, "retrieved_count", what_accounting),
            f"{what_accounting} retrieved_count",
        ),
        submitted_count=len(submitted_ids),
        governed_count=_count(
            _attr(accounting, "governed_count", what_accounting),
            f"{what_accounting} governed_count",
        ),
    )


# --------------------------------------------------------------------------- #
# materialization
# --------------------------------------------------------------------------- #
def materialize_turn_record(
    *,
    turn_id: str,
    question: str,
    governed_basis: Any,
    context_pack_id: str,
    model_executions: Sequence[ModelExecutionBinding],
    mive_overall_status: str,
    configuration: TurnConfigurationBinding,
    turn_started_at: str,
    turn_closed_at: str,
    retrieval_latency_ms: float,
    comparison_latency_ms: float,
    pipeline_latency_ms: float,
) -> TurnRecord:
    """Materialize the record of one COMPLETED turn.

    `turn_id` is the runtime's own turn identity, supplied by the caller. This
    module never mints one.

    `question` is the already-normalized question the turn actually used. The
    declared normalization is VERIFIED here; it is never applied, and no
    rewriting, expansion or reformulation of any kind happens.

    `governed_basis` is read structurally and must expose `question_id`,
    `context_pack_id`, `backend_id`, `mapping_profile_id`, `adapter_id`,
    `adapter_version`, the two contract-identity fields, and an `accounting`
    exposing `retrieved_count`, `submitted_ids` and `governed_count`. A real
    `GovernedEvidenceSet` satisfies this without any adaptation.

    `turn_started_at` and `turn_closed_at` are timestamps the CALLER took from
    its own injected clock. This module has no clock of its own.

    Raises `TurnRecordMaterializationError` on every contract violation.
    """
    # --- the turn's own identity and input, carried verbatim -------------- #
    turn_id = _text(turn_id, "turn_id")

    question = _text(question, "question")
    # Verify the declared normalization already holds. This checks the caller's
    # contract; it does not APPLY a normalization.
    if question != question.strip():
        _fail(
            "question is not normalized as contracted "
            f"({QUESTION_NORMALIZATION_STRIP}); this contract never normalizes"
        )

    context_pack_id = _text(context_pack_id, "context_pack_id")

    # --- the governed basis, by reference --------------------------------- #
    governed_evidence = _bind_governed_evidence(governed_basis)

    # One turn names one Context Pack. A disagreement here means the record
    # would bind a governed basis built for a different pack, so it fails
    # closed rather than silently preferring either value.
    if context_pack_id != governed_evidence.context_pack_id:
        _fail(
            f"context_pack_id {context_pack_id!r} does not match the governed "
            f"basis {governed_evidence.context_pack_id!r}; the turn and its "
            "governed basis must name one Context Pack"
        )

    # --- the executions that actually ran --------------------------------- #
    executions = _sequence(model_executions, "model executions")
    if executions == ():
        _fail(
            "a completed turn ran at least one model execution; an empty "
            "execution binding would record a turn that never reasoned"
        )
    seen_engines: set[str] = set()
    for execution in executions:
        if not isinstance(execution, ModelExecutionBinding):
            _fail(
                "each model execution must be a ModelExecutionBinding, "
                f"found {type(execution).__name__}"
            )
        # A repeated engine identity makes the record ambiguous: two different
        # executions would answer to one name.
        if execution.engine_id in seen_engines:
            _fail(f"duplicate model execution engine identity: {execution.engine_id}")
        seen_engines.add(execution.engine_id)

    # --- the comparison outcome, carried verbatim ------------------------- #
    # Read as an opaque value. This module owns no comparison vocabulary and
    # never interprets, ranks or re-derives what the comparison concluded.
    mive_overall_status = _text(mive_overall_status, "mive_overall_status")

    if not isinstance(configuration, TurnConfigurationBinding):
        _fail(
            "configuration must be a TurnConfigurationBinding, "
            f"found {type(configuration).__name__}"
        )

    return TurnRecord(
        turn_id=turn_id,
        question=question,
        # v0.1 materializes COMPLETED only. Live failure closure is deferred,
        # so this module has no path that can produce a FAILED record.
        closure_state=TurnClosureState.COMPLETED,
        turn_started_at=_text(turn_started_at, "turn_started_at"),
        turn_closed_at=_text(turn_closed_at, "turn_closed_at"),
        retrieval_latency_ms=_duration(retrieval_latency_ms, "retrieval_latency_ms"),
        comparison_latency_ms=_duration(comparison_latency_ms, "comparison_latency_ms"),
        pipeline_latency_ms=_duration(pipeline_latency_ms, "pipeline_latency_ms"),
        context_pack_id=context_pack_id,
        governed_evidence=governed_evidence,
        model_executions=executions,
        mive_overall_status=mive_overall_status,
        configuration=configuration,
        failure=None,
    )
