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

Two entry points, one per closure state, and neither can produce the other's:
`materialize_turn_record` records a COMPLETED turn and requires every stage
fact; `materialize_failed_turn_record` records a FAILED turn and requires only
the facts every started turn is guaranteed to hold — its identity, when it
started, when it closed, why it failed, and the configuration it ran under.
Everything else is accepted where it exists and left absent where the stage
that produces it did not complete. That makes the failure entry point TOTAL
over the observed failure paths without ever inventing a fact.

Every check below is fail-closed. A violated invariant raises
`TurnRecordMaterializationError`; none is ever downgraded into a partially
populated record, and none is ever converted into a governance verdict or an
evidence state.
"""

from __future__ import annotations

from typing import Any, NoReturn, Sequence

from .models import (
    QUESTION_NORMALIZATION_STRIP,
    ExecutionProfileBinding,
    GovernedEvidenceBinding,
    ModelExecutionBinding,
    TurnClosureState,
    TurnConfigurationBinding,
    TurnFailure,
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


def _optional_text(value: Any, what: str) -> str | None:
    """A stage-dependent identity: absent, or a non-empty string carried verbatim.

    `None` is the ONLY way to say "not produced". An empty string is refused
    rather than treated as absence, so a blank value can never stand in for a
    fact the runtime did not produce.
    """
    return None if value is None else _text(value, what)


def _optional_duration(value: Any, what: str) -> float | None:
    """A stage-dependent measurement: absent, or a real, non-negative one.

    NO MEASUREMENT IS NOT ZERO DURATION. `None` means the span was never
    measured; 0.0 would assert that it was measured and took no time.
    """
    return None if value is None else _duration(value, what)


def _executions(value: Any) -> tuple[ModelExecutionBinding, ...]:
    """Validate completed model executions. Emptiness is judged by the caller.

    `model_executions` holds COMPLETED executions only. An execution that
    failed produced no measurement at all, so a binding for it would be
    indistinguishable from one that completed without reporting usage; the
    failing engine is named by the turn's failure stage instead.
    """
    executions = _sequence(value, "model executions")
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
    return executions


def _execution_profile(value: Any) -> ExecutionProfileBinding | None:
    """Accept the caller's own policy-identity binding, or its absence.

    `None` means the caller did not know, or did not supply, a profile
    identity — the comparison-applicable shape this contract has always
    accepted. A supplied value must already be a real `ExecutionProfileBinding`
    (itself already shape-validated by its own `__post_init__`): this module
    never constructs one from an opaque object, and never reads a Product
    `ExecutionProfile` structurally, so it stays closed against that
    package's types exactly as it stays closed against every other runtime
    module.
    """
    if value is None:
        return None
    if not isinstance(value, ExecutionProfileBinding):
        _fail(
            "execution_profile must be an ExecutionProfileBinding or None, "
            f"found {type(value).__name__}"
        )
    return value


def _normalized_question(value: Any) -> str:
    """Verify the declared normalization already holds. Never apply it."""
    question = _text(value, "question")
    if question != question.strip():
        _fail(
            "question is not normalized as contracted "
            f"({QUESTION_NORMALIZATION_STRIP}); this contract never normalizes"
        )
    return question


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
    mive_overall_status: str | None = None,
    configuration: TurnConfigurationBinding,
    turn_started_at: str,
    turn_closed_at: str,
    retrieval_latency_ms: float,
    comparison_latency_ms: float | None = None,
    pipeline_latency_ms: float,
    execution_profile: ExecutionProfileBinding | None = None,
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

    `mive_overall_status` and `comparison_latency_ms` (TASK 20) are optional:
    `None` on either means the comparison stage did not run for this turn.
    Whether that is legal — and what `model_executions` cardinality it
    requires — is enforced by `TurnRecord.__post_init__` itself, keyed on
    `execution_profile`, so no construction path (this function or any
    other) can bypass that law. `execution_profile` is likewise optional:
    `None` means the caller did not supply a policy-identity binding, the
    same comparison-applicable shape this function has always produced.

    Raises `TurnRecordMaterializationError` on every contract violation.
    """
    # --- the turn's own identity and input, carried verbatim -------------- #
    turn_id = _text(turn_id, "turn_id")
    question = _normalized_question(question)
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
    executions = _executions(model_executions)
    if executions == ():
        _fail(
            "a completed turn ran at least one model execution; an empty "
            "execution binding would record a turn that never reasoned"
        )

    # --- the comparison outcome, carried verbatim ------------------------- #
    # Read as an opaque value where present. This module owns no comparison
    # vocabulary and never interprets, ranks or re-derives what a comparison
    # concluded — nor whether the ABSENCE of one here is legal, which is a
    # law `TurnRecord` itself enforces against `execution_profile`.
    mive_overall_status = _optional_text(mive_overall_status, "mive_overall_status")
    comparison_latency_ms = _optional_duration(
        comparison_latency_ms, "comparison_latency_ms"
    )
    execution_profile = _execution_profile(execution_profile)

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
        comparison_latency_ms=comparison_latency_ms,
        pipeline_latency_ms=_duration(pipeline_latency_ms, "pipeline_latency_ms"),
        context_pack_id=context_pack_id,
        governed_evidence=governed_evidence,
        model_executions=executions,
        mive_overall_status=mive_overall_status,
        execution_profile=execution_profile,
        configuration=configuration,
        failure=None,
    )


def materialize_failed_turn_record(
    *,
    turn_id: str,
    turn_started_at: str,
    turn_closed_at: str,
    failure: TurnFailure,
    configuration: TurnConfigurationBinding,
    question: str | None = None,
    context_pack_id: str | None = None,
    governed_basis: Any | None = None,
    model_executions: Sequence[ModelExecutionBinding] = (),
    mive_overall_status: str | None = None,
    retrieval_latency_ms: float | None = None,
    comparison_latency_ms: float | None = None,
    pipeline_latency_ms: float | None = None,
    execution_profile: ExecutionProfileBinding | None = None,
) -> TurnRecord:
    """Materialize the record of one FAILED turn.

    TOTAL over the observed failure paths. The five required arguments are the
    only facts every started turn is guaranteed to hold: its identity, when it
    started, when it closed, why it failed, and the configuration it ran under.
    A turn that fails on its very first validation step has all five, so no
    observed failure is unrecordable.

    Every other argument is a STAGE-DEPENDENT fact. Each is accepted where the
    stage that produces it completed, and left absent where it did not. Nothing
    here substitutes a default for a missing fact: a measurement that was never
    taken stays `None` rather than becoming `0.0`, an identity that was never
    produced stays `None` rather than becoming `""`, and a governed basis that
    never existed stays absent rather than being fabricated.

    `model_executions` carries COMPLETED executions only and may be empty — a
    turn whose first engine failed completed none. The engine that failed is
    named by `failure.error_stage` where the runtime truthfully has one; it is
    never given a binding of its own, because a failed attempt produced no
    measurement and would be indistinguishable from a completed one.

    `execution_profile` (TASK 20) is likewise optional and NOT stage-dependent
    in the usual sense: a resolved policy identity is normally known from the
    very start of a turn, before retrieval or anything else is attempted, so a
    caller MAY supply it even for the earliest possible failure. It is not
    REQUIRED here, because a failure during profile resolution itself — before
    any turn-like object exists to close — has no binding to supply and is
    outside this function's contract entirely.

    This function neither takes a timestamp nor decides what failed: like its
    COMPLETED counterpart it records facts the caller already observed, and it
    raises `TurnRecordMaterializationError` on every contract violation.
    """
    if not isinstance(failure, TurnFailure):
        _fail(f"failure must be a TurnFailure, found {type(failure).__name__}")
    if not isinstance(configuration, TurnConfigurationBinding):
        _fail(
            "configuration must be a TurnConfigurationBinding, "
            f"found {type(configuration).__name__}"
        )

    # --- stage-dependent facts, each accepted only where it exists -------- #
    context_pack_id = _optional_text(context_pack_id, "context_pack_id")

    governed_evidence = (
        None if governed_basis is None else _bind_governed_evidence(governed_basis)
    )
    if governed_evidence is not None:
        if context_pack_id is None:
            _fail(
                "a governed basis was supplied without a context_pack_id; a "
                "governed basis always names the Context Pack it governs"
            )
        if context_pack_id != governed_evidence.context_pack_id:
            _fail(
                f"context_pack_id {context_pack_id!r} does not match the governed "
                f"basis {governed_evidence.context_pack_id!r}; the turn and its "
                "governed basis must name one Context Pack"
            )

    return TurnRecord(
        turn_id=_text(turn_id, "turn_id"),
        # This entry point produces FAILED only. It has no parameter through
        # which a caller could ask for COMPLETED, so a failed turn can never be
        # recorded as a successful one.
        closure_state=TurnClosureState.FAILED,
        turn_started_at=_text(turn_started_at, "turn_started_at"),
        turn_closed_at=_text(turn_closed_at, "turn_closed_at"),
        question=None if question is None else _normalized_question(question),
        retrieval_latency_ms=_optional_duration(
            retrieval_latency_ms, "retrieval_latency_ms"
        ),
        comparison_latency_ms=_optional_duration(
            comparison_latency_ms, "comparison_latency_ms"
        ),
        pipeline_latency_ms=_optional_duration(
            pipeline_latency_ms, "pipeline_latency_ms"
        ),
        context_pack_id=context_pack_id,
        governed_evidence=governed_evidence,
        model_executions=_executions(model_executions),
        mive_overall_status=_optional_text(mive_overall_status, "mive_overall_status"),
        execution_profile=_execution_profile(execution_profile),
        configuration=configuration,
        failure=failure,
    )
