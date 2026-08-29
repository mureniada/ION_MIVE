"""The core orchestrator: the single hub that owns the pipeline order.

It depends only on ports. It calls the two IVE engines independently (each sees
ONLY the Context Pack), then MIVE, then the renderer, then telemetry. A single
provider failure yields an incomplete MIVE state — never a success (docs/06).

Progress is reported through an optional callback so the API layer can drive the
DEBUG-gated SSE stream without the core knowing anything about transport.
"""

from __future__ import annotations

import uuid
from typing import Callable

from . import errors
from .config import Settings
from .. import __version__ as APP_VERSION
from ..modules.core_adapter import (
    CoreAdapter,
    CoreAdapterOutcomeState,
    CoreAdapterRequest,
    CoreInvocationMode,
)
from ..modules.governed_evidence import (
    GovernedEvidenceMaterializationError,
    GovernedEvidenceSet,
    MaterializationInput,
    materialize_governed_evidence_set,
)
from ..modules.telemetry.pricing import PRICING_AS_OF
from ..modules.turn_record import (
    ModelExecutionBinding,
    TurnConfigurationBinding,
    TurnFailure,
    TurnRecord,
    materialize_failed_turn_record,
    materialize_turn_record,
)
from .models import (
    AskResult,
    Evidence,
    IVEReport,
    Metrics,
    ProviderMetrics,
)
from .ports import (
    ClockPort,
    ContextPackBuilderPort,
    IVEPort,
    MIVEPort,
    PricingPort,
    RendererPort,
    RetrievalPort,
)

# stage lifecycle event = (stage, status) e.g. ("retrieval", "started")
ProgressCallback = Callable[[str, str], None]


def _turn_failure_for(exc: Exception) -> TurnFailure:
    """Bind why a turn failed, without widening what the system discloses.

    A Product `IonError` already names its stage, and its `message` is the exact
    controlled text the transport layer returns to callers today, so recording
    both adds no disclosure surface.

    Any other exception contributes its TYPE NAME ONLY. Its stage is genuinely
    absent — the runtime has failure paths that carry none, and inventing one
    would misstate where the turn failed — and its text is deliberately dropped:
    provider SDK, vector-store and HTTP errors are exactly the ones whose
    `str()` may embed an endpoint, a payload fragment or a credential, and that
    text is not surfaced by the current transport at all.

    No traceback, no repr, no provider or store payload, no settings value.
    """
    if isinstance(exc, errors.IonError):
        return TurnFailure(
            error_type=type(exc).__name__,
            error_stage=exc.stage,
            error_message=exc.message,
        )
    return TurnFailure(error_type=type(exc).__name__)


def _completed_execution_bindings(
    reports: tuple[IVEReport, ...], metrics: tuple[ProviderMetrics, ...]
) -> tuple[ModelExecutionBinding, ...]:
    """Bind the model executions that COMPLETED before a turn failed.

    An engine that raised has no binding at all: it produced no usage, latency
    or cost, so a binding for it would be indistinguishable from one that
    completed while reporting nothing. The engine that failed is named by the
    turn's failure stage instead.

    Telemetry is computed for both engines at once, only after both complete, so
    a turn that fails at the second engine holds a completed first report with
    NO metrics for it. Such a report is bound from its own observed usage and
    its `estimated_cost` is left ABSENT — pricing that never ran is not run here
    to fill the gap.
    """
    bindings = []
    for index, report in enumerate(reports):
        reported = metrics[index] if index < len(metrics) else None
        usage = report.usage
        bindings.append(
            ModelExecutionBinding(
                engine_id=report.engine_id,
                provider=report.provider,
                requested_model=report.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=usage.latency_ms,
                usage_is_estimated=usage.usage_is_estimated,
                estimated_cost=None if reported is None else reported.estimated_cost,
            )
        )
    return tuple(bindings)


class Core:
    def __init__(
        self,
        *,
        retrieval: RetrievalPort,
        context_pack_builder: ContextPackBuilderPort,
        gemini_ive: IVEPort,
        openai_ive: IVEPort,
        mive: MIVEPort,
        renderer: RendererPort,
        pricing: PricingPort,
        clock: ClockPort,
        settings: Settings,
    ) -> None:
        self._retrieval = retrieval
        self._build = context_pack_builder
        self._gemini = gemini_ive
        self._openai = openai_ive
        self._mive = mive
        self._renderer = renderer
        self._pricing = pricing
        self._clock = clock
        self._settings = settings
        self._core_adapter = CoreAdapter()

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        *,
        progress: ProgressCallback | None = None,
    ) -> AskResult:
        emit = progress or (lambda *_: None)
        request_id = uuid.uuid4().hex
        adapter_created_at = self._clock.now_iso()
        started = self._clock.monotonic_ms()

        # --- partial-turn facts, for closure ---
        # The turn is STARTED from here on: its identity and start timestamp
        # exist, so it must eventually close with one record however it ends —
        # input validation below included.
        #
        # Each local begins ABSENT and is populated only once the existing stage
        # that produces it has completed. That is the whole mechanism: no stage
        # objects, no status enum, no workflow engine. Absence is therefore an
        # observed fact ("this stage did not complete"), never a default.
        normalized_question: str | None = None
        effective_top_k: int | None = None
        retrieval_ms: float | None = None
        context_pack_id: str | None = None
        governed_evidence: GovernedEvidenceSet | None = None
        completed_reports: tuple[IVEReport, ...] = ()
        completed_metrics: tuple[ProviderMetrics, ...] = ()
        comparison_ms: float | None = None
        mive_status: str | None = None
        total_ms: float | None = None

        # At most ONE Turn Record materialization per turn, success or failure.
        # This is what makes the mechanism non-recursive by construction: it is
        # set immediately before any attempt, so a failure of the attempt itself
        # can never provoke a second one.
        turn_record_attempted = False

        try:
            # --- input validation happens before any external call (docs/15) ---
            q = (question or "").strip()
            if not q:
                raise errors.IonError("Question must be a non-empty string.",
                                      stage=errors.STAGE_CONFIGURATION)
            normalized_question = q
            k = self._settings.default_top_k if top_k is None else int(top_k)
            if k < 1:
                raise errors.IonError("top_k must be >= 1.", stage=errors.STAGE_CONFIGURATION)
            # Only now is a top_k EFFECTIVE. A value that was computed and then
            # rejected never governed anything, so it is not recorded as one.
            effective_top_k = k

            # --- retrieval ---
            emit("retrieval", "started")
            t = self._clock.monotonic_ms()
            try:
                evidence: list[Evidence] = self._retrieval.retrieve(q, k)
            except errors.IonError:
                raise
            except Exception as exc:  # adapter-level failure
                raise errors.RetrievalError(f"Retrieval failed: {exc}") from exc
            if not evidence:
                raise errors.RetrievalError("Retrieval returned no evidence (no silent empty success).")
            retrieval_ms = self._clock.monotonic_ms() - t
            emit("retrieval", "done")

            # --- context pack (identical for both providers) ---
            emit("context_pack", "started")
            try:
                pack = self._build.build(q, evidence)
            except errors.IonError:
                raise
            except Exception as exc:
                raise errors.ContextPackError(f"Context Pack build failed: {exc}") from exc
            emit("context_pack", "done")
            context_pack_id = pack.context_pack_id

            # --- governance, through the Core Adapter boundary (read-only) ---
            governance = self._core_adapter.govern(
                CoreAdapterRequest(
                    candidate_set_id=request_id,
                    question_id=request_id,
                    candidates=evidence,
                    context_pack=pack,
                    adapter_created_at=adapter_created_at,
                    mode=CoreInvocationMode.READ_ONLY,
                )
            )

            # Operational failure is not a governance verdict. B0 let such an
            # exception propagate untouched, so the captured original is re-raised
            # as-is; the wrapper below exists only for the unreachable case where an
            # OPERATIONAL_FAILURE outcome carries no exception to re-raise.
            if governance.outcome is CoreAdapterOutcomeState.OPERATIONAL_FAILURE:
                if governance.operational_exception is not None:
                    raise governance.operational_exception
                raise errors.ContextPackError(
                    "Core Adapter operational failure: "
                    + (governance.operational_error or "")
                )

            # Governance rejection. Both B0 message contracts are reproduced
            # verbatim — same prefixes, same "|" join over the bridge reasons — so
            # the boundary move is invisible to every caller of ask().
            if governance.outcome is CoreAdapterOutcomeState.GOVERNANCE_REJECTED:
                if governance.native_gate_error is not None:
                    raise errors.ContextPackError(
                        "Runtime admission gate rejected: " + governance.native_gate_error
                    )
                raise errors.ContextPackError(
                    "Runtime evidence bridge rejected: "
                    + "|".join(governance.native_bridge_reasons)
                )

            # --- governed evidence gate (fail-closed, before any engine) ---
            # Reachable ONLY on the GOVERNANCE_COMPLETE fall-through: both branches
            # above raise first, so no rejected or operationally failed run is ever
            # materialized. Materializing IS the gate at v0.1 — the set re-establishes
            # the governed basis of this run from values the Product already holds.
            # The gate itself is unchanged: same call, same position, same exceptions.
            # Its result is CAPTURED rather than discarded, so the Turn Record can
            # bind the governed basis BY REFERENCE when the turn closes. It is still
            # not consumed by any engine, by MIVE, by the renderer or by AskResult.
            governed_evidence = self._materialize_governed_evidence(
                governance, evidence, pack, request_id
            )

            # --- independent IVE runs (neither sees the other) ---
            gemini_report = self._run_engine(self._gemini, pack, errors.STAGE_GEMINI, emit)
            completed_reports = (gemini_report,)
            openai_report = self._run_engine(self._openai, pack, errors.STAGE_OPENAI, emit)
            completed_reports = (gemini_report, openai_report)

            # --- MIVE ---
            emit("mive", "started")
            t = self._clock.monotonic_ms()
            try:
                mive_result = self._mive.compare([gemini_report, openai_report])
            except errors.IonError:
                raise
            except Exception as exc:
                raise errors.MiveError(f"MIVE comparison failed: {exc}") from exc
            comparison_ms = self._clock.monotonic_ms() - t
            emit("mive", "done")
            # Serialized once here and reused below, so the comparison outcome is
            # a held fact from the moment MIVE completes — a turn that fails
            # afterwards can still record what the comparison concluded.
            mive_dict = mive_result.to_dict()
            mive_status = mive_dict["overall_status"]

            # --- telemetry ---
            provider_metrics = [
                self._provider_metrics(r) for r in (gemini_report, openai_report)
            ]
            completed_metrics = tuple(provider_metrics)
            costs = [p.estimated_cost for p in provider_metrics]
            total_cost = None if any(c is None for c in costs) else round(sum(costs), 8)
            total_ms = self._clock.monotonic_ms() - started
            context_chars = sum(len(d.content) for d in pack.documents)

            metrics = Metrics(
                request_id=request_id,
                timestamp=self._clock.now_iso(),
                question=q,
                retrieved_chunks=len(evidence),
                context_characters=context_chars,
                context_documents=len(pack.documents),
                retrieval_latency_ms=round(retrieval_ms, 3),
                comparison_latency_ms=round(comparison_ms, 3),
                total_latency_ms=round(total_ms, 3),
                providers=provider_metrics,
                total_estimated_cost=total_cost,
                status="success",
            )

            # --- render (deterministic) ---
            rendered = self._renderer.render(
                question=q,
                mive_result=mive_result,
                reports=[gemini_report, openai_report],
                evidence=evidence,
                metrics_dict=metrics.to_dict(),
            )

            # --- turn closure: exactly one immutable Turn Record ---
            # Reached only after the renderer completed, so the record states a turn
            # that genuinely produced an answer. The closing timestamp comes from the
            # already-injected clock — the Turn Record contract owns none.
            #
            # It is materialized BEFORE the final progress event so that a refusal
            # here cannot leave a stream that announced a ready answer and then
            # failed. The emitted success sequence is unchanged either way.
            #
            # The record is EPHEMERAL at v0.1 (D18-06): held as a local value only.
            # It is deliberately not returned, not placed in AskResult, not rendered,
            # not emitted, not logged and not persisted. Exposing it anywhere is a
            # later, separately authorized task.
            turn_closed_at = self._clock.now_iso()
            turn_record_attempted = True
            turn_record = self._materialize_turn_record(  # noqa: F841 - see above
                turn_id=request_id,
                question=q,
                governed_basis=governed_evidence,
                pack=pack,
                reports=(gemini_report, openai_report),
                provider_metrics=provider_metrics,
                mive_overall_status=mive_status,
                effective_top_k=k,
                turn_started_at=adapter_created_at,
                turn_closed_at=turn_closed_at,
                retrieval_latency_ms=retrieval_ms,
                comparison_latency_ms=comparison_ms,
                pipeline_latency_ms=total_ms,
            )

            emit("answer", "ready")

            return AskResult(
                request_id=request_id,
                question=q,
                status="success",
                rendered=rendered,
                mive_result=mive_dict,
                ive_reports=[gemini_report.to_contract_dict(), openai_report.to_contract_dict()],
                metrics=metrics.to_dict(),
            )

        except Exception as original_exc:
            # THE ORIGINAL RUNTIME FAILURE ALWAYS WINS.
            #
            # `Exception`, deliberately not `BaseException`: KeyboardInterrupt,
            # SystemExit and GeneratorExit are process control, not Product turn
            # outcomes, and must not be recorded as failed turns or delayed here.
            #
            # If a record was already attempted for this turn, none is attempted
            # again — that is what keeps a failure of the Turn Record mechanism
            # from recursively recording itself (D18-10).
            if not turn_record_attempted:
                turn_record_attempted = True
                try:
                    self._materialize_failed_turn_record(
                        turn_id=request_id,
                        exc=original_exc,
                        turn_started_at=adapter_created_at,
                        question=normalized_question,
                        effective_top_k=effective_top_k,
                        context_pack_id=context_pack_id,
                        governed_basis=governed_evidence,
                        completed_reports=completed_reports,
                        completed_metrics=completed_metrics,
                        mive_overall_status=mive_status,
                        retrieval_latency_ms=retrieval_ms,
                        comparison_latency_ms=comparison_ms,
                        pipeline_latency_ms=total_ms,
                    )
                except Exception:
                    # Best-effort backstop. A secondary failure of the recording
                    # mechanism — including a clock that refuses to give a closing
                    # timestamp — is suppressed and never retried, because it must
                    # not replace, wrap or obscure the failure it was describing.
                    pass
            # Bare: the SAME exception object, with its own stage, cause and
            # traceback. Nothing here converts, wraps or re-stages it.
            raise

    # ----------------------------------------------------------------- #
    def _materialize_governed_evidence(
        self, governance, evidence: list[Evidence], pack, question_id: str
    ) -> GovernedEvidenceSet:
        """Materialize the governed basis of one COMPLETED governance run.

        Every value below is one the caller already holds at this point: the
        outcome the Core Adapter returned, the candidates Product retrieved, and
        the Context Pack Product built. Nothing is retrieved, recomputed,
        re-governed or timestamped here, and no Core Adapter or governance
        internal is reached — the frozen materializer is called exactly as
        implemented.

        Only `GovernedEvidenceMaterializationError` is caught. An operational
        fault must still propagate untouched, so no broad `Exception` handler
        wraps this call. The mapping onto `ContextPackError` is a transport /
        error-model COMPATIBILITY mapping so the stage vocabulary in docs/15 is
        unchanged; it does NOT assert that Context Pack construction failed.
        """
        try:
            return materialize_governed_evidence_set(
                MaterializationInput(
                    outcome_state=governance.outcome.value,
                    native_result=governance.native_result,
                    retrieved_candidate_ids=tuple(e.document_id for e in evidence),
                    submitted_candidate_ids=tuple(d.document_id for d in pack.documents),
                    candidate_count=governance.candidate_count,
                    governed_count=governance.governed_count,
                    backend_id=governance.backend_id,
                    mapping_profile_id=governance.mapping_profile_id,
                    adapter_id=governance.adapter_id,
                    adapter_version=governance.adapter_version,
                    context_pack_id=pack.context_pack_id,
                    question_id=question_id,
                    context_pack_metadata=pack.metadata,
                )
            )
        except GovernedEvidenceMaterializationError as exc:
            raise errors.ContextPackError(
                "Governed evidence materialization failed: " + str(exc)
            ) from exc

    def _materialize_turn_record(
        self,
        *,
        turn_id: str,
        question: str,
        governed_basis: GovernedEvidenceSet,
        pack,
        reports: tuple[IVEReport, ...],
        provider_metrics: list[ProviderMetrics],
        mive_overall_status: str,
        effective_top_k: int,
        turn_started_at: str,
        turn_closed_at: str,
        retrieval_latency_ms: float,
        comparison_latency_ms: float,
        pipeline_latency_ms: float,
    ) -> TurnRecord:
        """Record the closure of one COMPLETED turn.

        Every value below is one the caller already holds at this point. Nothing
        is retrieved, recomputed, re-governed, re-compared or timestamped here:
        the closing timestamp arrives as an argument, and the frozen Turn Record
        materializer is called exactly as implemented.

        The governed basis is passed through so the record can bind it BY
        REFERENCE. The materializer reads only its identity, binding and counts;
        no admitted entry, native object or evidence content is reachable from
        the record it returns.

        Model execution figures are taken from the ProviderMetrics this turn
        already produced, so the record cannot disagree with the Product's own
        telemetry for the same turn. `engine_id` comes from the report, which is
        the only object carrying it. `report.model` is the model the Product
        REQUESTED; the provider-reported identity is discarded upstream and is
        therefore never claimed.

        No exception is caught here. A refusal must not be remapped into an
        apparently successful turn, and turning one into a recorded failure is a
        later, separately authorized step.
        """
        executions = tuple(
            ModelExecutionBinding(
                engine_id=report.engine_id,
                provider=metrics.provider,
                requested_model=metrics.model,
                input_tokens=metrics.input_tokens,
                output_tokens=metrics.output_tokens,
                latency_ms=metrics.latency_ms,
                usage_is_estimated=metrics.usage_is_estimated,
                estimated_cost=metrics.estimated_cost,
            )
            for report, metrics in zip(reports, provider_metrics, strict=True)
        )

        return materialize_turn_record(
            turn_id=turn_id,
            question=question,
            governed_basis=governed_basis,
            context_pack_id=pack.context_pack_id,
            model_executions=executions,
            mive_overall_status=mive_overall_status,
            configuration=TurnConfigurationBinding(
                effective_top_k=effective_top_k,
                context_char_budget=self._settings.context_char_budget,
                retrieval_collection=self._settings.qdrant_collection,
                app_version=APP_VERSION,
                pricing_as_of=PRICING_AS_OF,
            ),
            turn_started_at=turn_started_at,
            turn_closed_at=turn_closed_at,
            retrieval_latency_ms=retrieval_latency_ms,
            comparison_latency_ms=comparison_latency_ms,
            pipeline_latency_ms=pipeline_latency_ms,
        )

    def _materialize_failed_turn_record(
        self,
        *,
        turn_id: str,
        exc: Exception,
        turn_started_at: str,
        question: str | None,
        effective_top_k: int | None,
        context_pack_id: str | None,
        governed_basis: GovernedEvidenceSet | None,
        completed_reports: tuple[IVEReport, ...],
        completed_metrics: tuple[ProviderMetrics, ...],
        mive_overall_status: str | None,
        retrieval_latency_ms: float | None,
        comparison_latency_ms: float | None,
        pipeline_latency_ms: float | None,
    ) -> TurnRecord:
        """Record the closure of one FAILED turn, from facts already observed.

        Called only from the closure handler, and only when no record has been
        attempted for this turn. It performs NO retrieval, governance, provider,
        MIVE, renderer or pricing call: re-running any stage while closing a
        failed turn would invent facts the turn never produced, and could fail
        again inside the handler.

        The closing timestamp is read here rather than passed in, so that a
        clock which refuses is caught by the caller's backstop like any other
        secondary fault — never masking the original failure.

        Absent arguments are absent facts. Each one means the stage that would
        have produced it did not complete, and none is defaulted into a value.
        """
        turn_closed_at = self._clock.now_iso()
        return materialize_failed_turn_record(
            turn_id=turn_id,
            turn_started_at=turn_started_at,
            turn_closed_at=turn_closed_at,
            failure=_turn_failure_for(exc),
            configuration=TurnConfigurationBinding(
                effective_top_k=effective_top_k,
                context_char_budget=self._settings.context_char_budget,
                retrieval_collection=self._settings.qdrant_collection,
                app_version=APP_VERSION,
                pricing_as_of=PRICING_AS_OF,
            ),
            question=question,
            context_pack_id=context_pack_id,
            governed_basis=governed_basis,
            model_executions=_completed_execution_bindings(
                completed_reports, completed_metrics
            ),
            mive_overall_status=mive_overall_status,
            retrieval_latency_ms=retrieval_latency_ms,
            comparison_latency_ms=comparison_latency_ms,
            pipeline_latency_ms=pipeline_latency_ms,
        )

    def _run_engine(
        self, engine: IVEPort, pack, stage: str, emit: ProgressCallback
    ) -> IVEReport:
        emit(stage, "started")
        try:
            report = engine.run(pack)
        except errors.IonError as exc:
            # keep a specific stage the adapter set; only fill an unknown one.
            if exc.stage == "unknown":
                exc.stage = stage
            emit(stage, "failed")
            raise
        except Exception as exc:
            emit(stage, "failed")
            raise errors.ProviderError(f"{stage} provider failed: {exc}", stage=stage) from exc
        emit(stage, "done")
        return report

    def _provider_metrics(self, report: IVEReport) -> ProviderMetrics:
        u = report.usage
        return ProviderMetrics(
            provider=report.provider,
            model=report.model,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            latency_ms=None if u.latency_ms is None else round(u.latency_ms, 3),
            estimated_cost=self._pricing.estimate_cost(
                report.model, u.input_tokens, u.output_tokens
            ),
            usage_is_estimated=u.usage_is_estimated,
        )
