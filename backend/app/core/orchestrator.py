"""The core orchestrator: the single hub that owns the pipeline order.

It depends on ports and on ONE provider-neutral model execution boundary, the
Model Gateway. It names no concrete engine implementation and holds no
provider-named execution dependency: it asks the Gateway for one explicitly
identified target at a time. WHICH targets a turn asks for, and in what order,
is CALLER POLICY — stated not as a literal here but as the immutable
`ExecutionProfile` this Core was constructed with (TASK 20). The Gateway
still executes only the target it is handed; Core still decides which
target(s) to hand it, and now reads that decision from policy data instead
of a literal.

Each engine execution sees ONLY the governed `ModelContextAssembly`
materialized for this turn (TASK 19.3) — never the upstream `ContextPack`
directly, and never another engine's output. TASK 20 v0.1 implements exactly
one execution mode, SINGLE: one engine, one `IVEReport`, and MIVE comparison
is NOT APPLICABLE — never invoked, never simulated, never represented as a
successful comparison of one report with itself. MIVE remains implemented
and frozen as a genuine two-report comparison mechanism for a future profile
that explicitly requests it; this Core simply does not call it under the one
profile that exists today. A single provider failure still yields no
success, single-engine or otherwise (docs/06).

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
from ..modules.conversation_context import ConversationContext, retrieval_query_for
from ..modules.execution_profile import ExecutionMode, ExecutionProfile
from ..modules.governed_evidence import (
    GovernedEvidenceMaterializationError,
    GovernedEvidenceSet,
    MaterializationInput,
    materialize_governed_evidence_set,
)
from ..modules.model_context import (
    CandidateContentProjection,
    ModelContextAssembly,
    ModelContextBuildError,
    build_model_context,
)
from ..modules.model_gateway import ModelGateway
from ..modules.response_composer import (
    ComposerClaimView,
    ComposerInput,
    ResponseComposerOutputError,
    ResponseComposerProviderError,
    ResponseComposerResult,
)
from ..modules.telemetry.pricing import PRICING_AS_OF
from ..modules.turn_record import (
    ExecutionProfileBinding,
    ModelExecutionBinding,
    TurnConfigurationBinding,
    TurnFailure,
    TurnRecord,
    materialize_failed_turn_record,
    materialize_turn_record,
)
from ..modules.voe_profile import VOERuntimeProfile
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
    MIVEPort,
    PricingPort,
    RendererPort,
    ResponseComposerPort,
    RetrievalPort,
)

# stage lifecycle event = (stage, status) e.g. ("retrieval", "started")
ProgressCallback = Callable[[str, str], None]

# TASK 22.3B1: an optional, best-effort capture seam for the TurnRecord a
# turn already materializes. Invoked at most once per `ask()` call, only
# once a real TurnRecord exists (never on a turn that produced none — see
# `ask()`'s two invocation sites). An observer that raises is suppressed
# (OD22-11): it may not alter AskResult return semantics, the original Core
# exception, the governed-turn pipeline order, or TurnRecord materialization
# itself. Nothing here places TurnRecord on AskResult, the rendered output,
# or any transport payload — the observer is the only way out (OD22-01).
TurnRecordObserver = Callable[[TurnRecord], None]

# A2-009A: the closed set of presentation-depth values `ask()` accepts
# besides None. `response_depth` is presentation metadata only — validated
# before retrieval and carried, unchanged, onto `ComposerInput`. It never
# reaches top_k, retrieval, governance, the governed evidence set, the model
# context, primary engine input, the ExecutionProfile, or the TurnRecord.
_RESPONSE_DEPTHS = ("BRIEF", "STANDARD", "DEEP")

# G7: the disclaimer a COMPOSED turn ships instead of the renderer's
# single-execution one. The displayed text was restyled by a separate
# presentation call, so the single-execution wording alone would be untrue.
# "was instructed not to" — not "does not": composer output is not verified.
_COMPOSED_DISCLAIMER_TEMPLATE = (
    "The interpretation in this response was produced by a single configured "
    "model execution ({engine_id}). A separate presentation step, run under "
    "the VOE Dialogue Profile {version}, then restyled its wording and was "
    "instructed not to add claims or evidence. No second, independent model "
    "interpretation was run for this turn, so no cross-model agreement, "
    "disagreement, or consensus claim applies."
)


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


def _context_binding_kwargs(
    conversation_context: ConversationContext | None, retrieval_query: str | None
) -> dict:
    """TR-A1 arguments for a Turn Record materializer — or none at all.

    A turn without conversation context calls the materializer with exactly
    the pre-Phase-2 arguments, so the no-context closure is unchanged.
    """
    if conversation_context is None:
        return {}
    return {"conversation_context": conversation_context, "retrieval_query": retrieval_query}


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
        model_gateway: ModelGateway,
        mive: MIVEPort,
        renderer: RendererPort,
        pricing: PricingPort,
        clock: ClockPort,
        settings: Settings,
        execution_profile: ExecutionProfile,
        composer: ResponseComposerPort | None = None,
        voe_runtime_profile: VOERuntimeProfile | None = None,
    ) -> None:
        self._retrieval = retrieval
        self._build = context_pack_builder
        self._model_gateway = model_gateway
        self._mive = mive
        self._renderer = renderer
        self._pricing = pricing
        self._clock = clock
        self._settings = settings
        self._execution_profile = execution_profile
        self._core_adapter = CoreAdapter()
        # Gate 4: both None unless VOE_PROFILE_ENABLED=true resolved a
        # verified bundle at composition-root time (app/container.py).
        # Every existing construction site that supplies neither argument
        # keeps working unchanged — the exact pre-profile path.
        self._composer = composer
        self._voe_runtime_profile = voe_runtime_profile

    @property
    def execution_profile(self) -> ExecutionProfile:
        """The immutable Model Execution Profile this Core was composed with.

        Read-only composition surface, for the readiness gate to check the
        SAME resolved profile Core itself executes under (no independent
        re-resolution) — never exposed on `AskResult` or any transport
        payload (D20-12).
        """
        return self._execution_profile

    @property
    def voe_runtime_profile(self) -> VOERuntimeProfile | None:
        """The VOE runtime profile this Core was composed with, or None.

        Read-only composition surface (G5), mirroring `execution_profile`:
        the readiness gate compares it against a fresh resolution so a Core
        cached without — or with a different — profile fails closed instead
        of silently answering uncomposed. Never exposed on any payload.
        """
        return self._voe_runtime_profile

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        *,
        progress: ProgressCallback | None = None,
        on_turn_record: TurnRecordObserver | None = None,
        response_depth: str | None = None,
        conversation_context: ConversationContext | None = None,
    ) -> AskResult:
        # Phase 2 (docs/ION_PHASE2_CONVERSATION_CONTEXT_AMENDMENT_v1.md):
        # `conversation_context` is the bounded prior-turn context of the same
        # session, supplied only by the SessionController for a follow-up turn.
        # `None` — the first turn of a session, and every legacy /ask call — is
        # the exact pre-Phase-2 path: same retrieval query object, same model
        # context shape, same prompt bytes, no citation-subset guard.
        emit = progress or (lambda *_: None)
        capture = on_turn_record or (lambda _: None)
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
        # Bound only once the supplied context has been validated below, so a
        # rejected context is never recorded as one the turn ran with.
        bound_context: ConversationContext | None = None
        bound_retrieval_query: str | None = None

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
            # A2-009A: exact membership only — no case folding, no stripping,
            # no coercion. Checked here, before retrieval and any engine call,
            # whether or not a composer is configured.
            if response_depth is not None and not (
                isinstance(response_depth, str) and response_depth in _RESPONSE_DEPTHS
            ):
                raise errors.IonError(
                    "response_depth must be None or one of 'BRIEF', 'STANDARD', 'DEEP'.",
                    stage=errors.STAGE_CONFIGURATION,
                )
            if conversation_context is not None and not isinstance(
                conversation_context, ConversationContext
            ):
                raise errors.IonError(
                    "conversation_context must be None or a ConversationContext.",
                    stage=errors.STAGE_CONFIGURATION,
                )
            # RQ-A1 (revised RQ-A1-R1): with context, the session's ROOT user
            # question (first COMPLETED turn, capped), a newline, then this
            # question; without context, `q` itself — the
            # identical object retrieval has always received. Prior model text
            # never reaches retrieval. The Context Pack, governance, the model
            # context question and the Turn Record question all stay `q`.
            retrieval_query = retrieval_query_for(q, conversation_context)
            if conversation_context is not None:
                bound_context = conversation_context
                bound_retrieval_query = retrieval_query

            # --- retrieval ---
            emit("retrieval", "started")
            t = self._clock.monotonic_ms()
            try:
                evidence: list[Evidence] = self._retrieval.retrieve(retrieval_query, k)
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
            # bind the governed basis BY REFERENCE when the turn closes. Beyond that
            # binding, it is now also the basis the Model Context Builder joins
            # against immediately below — its ADMITTED identities are what determine
            # which content the engines may see. It is still not consumed by MIVE,
            # the renderer or `AskResult`.
            governed_evidence = self._materialize_governed_evidence(
                governance, evidence, pack, request_id
            )

            # --- model context: the ONLY object that crosses into model execution ---
            # Built strictly after the governed-evidence gate and strictly before the
            # first engine call (TASK 19.3), from values already held: the governed
            # basis just materialized, and the submitted Context Pack's own document
            # content. This is what makes "only admitted governed evidence may enter
            # model input" a property of CONSTRUCTION rather than an upstream equality
            # assertion — a non-admitted candidate is never looked up by the frozen
            # Builder, so it has no path into the object the engines receive.
            if bound_context is None:
                model_input = self._materialize_model_context(governed_evidence, pack, q)
            else:
                model_input = self._materialize_model_context(
                    governed_evidence, pack, q, bound_context
                )

            # --- engine execution, from POLICY, not a literal (TASK 20) ---
            # WHICH engine(s) run, and in what order, is the active
            # `ExecutionProfile`'s decision, stated as data this Core was
            # constructed with — never a literal engine name written here, and
            # never a loop over a collection Core invented on its own. v0.1
            # implements exactly one mode: SINGLE runs exactly the one engine
            # the profile names. The branch below fails closed for any other
            # mode; no such mode exists yet for any profile this Product
            # resolves, so it is unreachable today and stays that way until a
            # later, separately authorized phase actually implements one.
            profile = self._execution_profile
            if profile.mode is not ExecutionMode.SINGLE:
                raise errors.ConfigurationError(
                    f"unsupported execution mode: {profile.mode!r}"
                )
            engine_id = profile.engine_ids[0]
            # The engine's own identity IS the existing stage value for every
            # engine this Product currently resolves ("gemini"): no new stage
            # vocabulary is introduced, and no mapping table stands between
            # policy and the progress/error stage it produces.
            report = self._run_engine(engine_id, model_input, engine_id, emit)
            completed_reports = (report,)

            # --- CG-A1: citation-subset guard, context turns ONLY ---
            # The compensating boundary for the PRIOR CONVERSATION block: on a
            # turn that carried one, every cited id must be an evidence item
            # this turn's model context actually contained. A violation fails
            # the turn closed — nothing is stripped or repaired. Without
            # context this is never called, so the pre-Phase-2 behaviour (the
            # renderer silently excluding a stray citation, D20-20) is unchanged.
            if bound_context is not None:
                self._enforce_citation_subset(report, model_input)

            # --- comparison: NOT APPLICABLE under SINGLE (TASK 20 / D20-01) ---
            # SINGLE authorizes exactly one engine. MIVE compares two
            # independent reports and is never invoked here: no call, no
            # timer, no synthetic result, no fabricated agreement. `mive_dict`
            # and `mive_status` stay at their ABSENT initial value (None) —
            # comparison not applicable is recorded as absence, never as a
            # zero-duration measurement of a comparison that did not run.
            mive_dict = None

            # --- telemetry ---
            provider_metrics = [self._provider_metrics(report)]
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
                comparison_latency_ms=None,
                total_latency_ms=round(total_ms, 3),
                providers=provider_metrics,
                total_estimated_cost=total_cost,
                status="success",
            )

            # --- render (deterministic, SINGLE path) ---
            # `model_input.evidence` — the SAME Model Context evidence the
            # executed engine itself received — is the ONLY evidence basis the
            # renderer may resolve this report's citations against (D20-20):
            # never the broader `evidence` list retrieval returned, which may
            # include candidates governance never admitted into model input.
            base_rendered = self._renderer.render_single(
                question=q,
                report=report,
                authorized_evidence_basis=model_input.evidence,
                metrics_dict=metrics.to_dict(),
            )

            # --- VOE composition (Gate 4): additive, disabled by default ---
            # Reached only after the deterministic base answer above already
            # exists in full. `self._composer` is None unless
            # VOE_PROFILE_ENABLED=true resolved a verified VOERuntimeProfile
            # at composition-root time (app/container.py) — RendererPort and
            # `base_rendered` itself are never touched by this block;
            # `final_rendered` is a fresh shallow copy when composition runs,
            # and is `base_rendered` BY REFERENCE, untouched, when it does
            # not — the exact pre-profile object.
            #
            # A composer failure never fails the turn (TRUTH > STYLE): the
            # already-correct, already evidence-grounded `base_rendered`
            # answer is what ships, and the failure is disclosed — never
            # hidden — in operational_metrics["composition"]. Only the two
            # composer-local error types are caught; any other exception is
            # a genuine defect and propagates as a real turn failure, exactly
            # like every other unexpected exception in this method.
            composition_metrics: dict | None = None
            final_answer = base_rendered["primary_answer"]

            if self._composer is not None:
                composer_input = self._build_composer_input(
                    q, report, response_depth=response_depth
                )
                # G3: Core's own span around the whole compose() attempt, on
                # the injected clock — measured on success AND fallback alike,
                # distinct from the composer-reported provider-call latency.
                composition_result: ResponseComposerResult | None = None
                composition_started = self._clock.monotonic_ms()
                try:
                    composition_result = self._composer.compose(composer_input)
                except ResponseComposerProviderError:
                    composition_status = "FALLBACK_PROVIDER_ERROR"
                except ResponseComposerOutputError:
                    composition_status = "FALLBACK_MALFORMED_OUTPUT"
                else:
                    composition_status = "COMPOSED"
                attempt_latency_ms = self._clock.monotonic_ms() - composition_started

                if composition_result is None:
                    composition_metrics = self._composition_fallback_metrics(
                        composition_status, attempt_latency_ms
                    )
                else:
                    final_answer = composition_result.response.composed_text
                    composition_metrics = self._composition_success_metrics(
                        composition_result, attempt_latency_ms
                    )

            if composition_metrics is None:
                # Disabled, or no composer configured: the exact pre-profile
                # object, untouched — never even shallow-copied, and no
                # "composition" or "presentation" key anywhere in it.
                final_rendered = base_rendered
                final_metrics_dict = metrics.to_dict()
            else:
                # One final metrics snapshot, built once, used for both
                # `final_rendered["operational_metrics"]` and
                # `AskResult.metrics` below — never two independently
                # constructed representations of the same turn.
                #
                # G3: on a turn that attempted composition, the turn totals
                # cover it: total_latency_ms adds the attempt span to the
                # pipeline span (which, like the Turn Record's
                # pipeline_latency_ms, still ends before rendering), and
                # total_estimated_cost adds the composition cost — or is None
                # whenever that cost is unknown, including every fallback.
                # `providers` stays IVE-only.
                final_metrics_dict = {
                    **metrics.to_dict(),
                    "total_latency_ms": round(total_ms + attempt_latency_ms, 3),
                    "total_estimated_cost": self._total_cost_with_composition(
                        total_cost, composition_metrics["estimated_cost"]
                    ),
                    "composition": composition_metrics,
                }
                composed = composition_status == "COMPOSED"
                final_rendered = dict(base_rendered)
                final_rendered["primary_answer"] = final_answer
                final_rendered["operational_metrics"] = final_metrics_dict
                # G7: explicit public presentation disclosure, present only
                # when composition was attempted. A fallback keeps the
                # renderer's disclaimer: the text shown IS the single
                # execution's own answer.
                # Composer v0.2: the already-filtered suggested next questions
                # ride here and ONLY here — presentation/navigation, never
                # primary_answer, uncertainty, evidence, the Turn Record, the
                # Model Context or conversation memory. FALLBACK exposes none.
                final_rendered["presentation"] = {
                    "composition_status": "COMPOSED" if composed else "FALLBACK",
                    "suggested_questions": (
                        list(composition_result.response.suggested_questions)
                        if composed else []
                    ),
                }
                if composed:
                    final_rendered["disclaimer"] = _COMPOSED_DISCLAIMER_TEMPLATE.format(
                        engine_id=report.engine_id,
                        version=self._voe_runtime_profile.binding.profile_version,
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
            # It is deliberately not placed in AskResult, not rendered, not
            # emitted, not logged and not persisted. The only exposure path is
            # the optional `on_turn_record` capture seam immediately below
            # (TASK 22.3B1 / OD22-01) — never a return value, never transport.
            #
            # Deliberately unaware of composition (Gate 4): this record binds
            # the ONE IVE model execution this turn ran, exactly as it always
            # has. A VOE composition attempt is not an IVE execution and is
            # never represented here — durable composition provenance
            # (a `composition_execution` binding or equivalent) remains
            # deferred, separately authorized work.
            turn_closed_at = self._clock.now_iso()
            turn_record_attempted = True
            turn_record = self._materialize_turn_record(
                turn_id=request_id,
                question=q,
                governed_basis=governed_evidence,
                pack=pack,
                reports=(report,),
                provider_metrics=provider_metrics,
                mive_overall_status=None,
                effective_top_k=k,
                turn_started_at=adapter_created_at,
                turn_closed_at=turn_closed_at,
                retrieval_latency_ms=retrieval_ms,
                comparison_latency_ms=None,
                pipeline_latency_ms=total_ms,
                **_context_binding_kwargs(bound_context, bound_retrieval_query),
            )

            # Best-effort capture (OD22-11): an observer exception is
            # suppressed here and never allowed to reach the caller, so it
            # can neither change this successful AskResult nor be mistaken
            # for a turn failure. Invoked exactly once, only now that a real
            # COMPLETED TurnRecord exists.
            try:
                capture(turn_record)
            except Exception:
                pass

            emit("answer", "ready")

            return AskResult(
                request_id=request_id,
                question=q,
                status="success",
                rendered=final_rendered,
                mive_result=mive_dict,
                ive_reports=[report.to_contract_dict()],
                metrics=final_metrics_dict,
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
                    failed_record = self._materialize_failed_turn_record(
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
                        **_context_binding_kwargs(bound_context, bound_retrieval_query),
                    )
                    # Best-effort capture (OD22-11), same guarantee as the
                    # success path: invoked exactly once, only now that a real
                    # FAILED TurnRecord exists, and its own exception is
                    # suppressed here rather than masking `original_exc` below.
                    try:
                        capture(failed_record)
                    except Exception:
                        pass
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

    def _materialize_model_context(
        self,
        governed_basis: GovernedEvidenceSet,
        pack,
        question: str,
        conversation_context: ConversationContext | None = None,
    ) -> ModelContextAssembly:
        """Materialize the ONLY object that may cross into model execution.

        Every value below is one the caller already holds at this point: the
        governed basis governance just produced, and the Context Pack Product
        already built. Building the projections is a pure one-pass copy of
        each document's model-facing fields — no governance logic, no
        metadata, no score, no ranking and no defaulting happens here. The
        frozen Builder performs the one substantive decision itself: which of
        these projections may actually be exposed, by joining on the governed
        basis's own ADMITTED identities and excluding everything else.

        Only `ModelContextBuildError` is caught. An operational fault must
        still propagate untouched, so no broad `Exception` handler wraps this
        call. The mapping onto `ContextPackError` is a transport / error-model
        COMPATIBILITY mapping, exactly like the governed-evidence mapping
        above; it does NOT assert that Context Pack construction failed.
        """
        projections = [
            CandidateContentProjection(
                document_id=d.document_id,
                content=d.content,
                title=d.title,
                source_identity=d.source,
                page=d.page,
                chunk_id=d.chunk_id,
            )
            for d in pack.documents
        ]
        # MC-A1: the bounded prior-turn context enters ONLY the separate
        # CONVERSATION_MEMORY segment; without one the call is exactly v0.1's.
        extra = {} if conversation_context is None else {
            "conversation_context": conversation_context
        }
        try:
            return build_model_context(
                governed_basis=governed_basis,
                candidate_projections=projections,
                question=question,
                **extra,
            )
        except ModelContextBuildError as exc:
            raise errors.ContextPackError(
                "Model context materialization failed: " + str(exc)
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
        conversation_context: ConversationContext | None = None,
        retrieval_query: str | None = None,
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
            execution_profile=self._execution_profile_binding(),
            **_context_binding_kwargs(conversation_context, retrieval_query),
        )

    def _enforce_citation_subset(self, report: IVEReport, model_input) -> None:
        """CG-A1: fail closed on a citation outside this turn's model context.

        Called ONLY for a turn that carried a non-empty conversation context.
        `allowed` is exactly the evidence the executed engine received — the
        same basis the renderer resolves citations against (D20-20). Claims
        and relations are both checked. Nothing is stripped or repaired: the
        turn fails with a normalization-stage error (HTTP 422 through the
        existing stage map), and its FAILED Turn Record keeps the context.
        """
        allowed = {item.candidate_id for item in model_input.evidence}
        cited: set[str] = set()
        for claim in report.claims:
            cited.update(claim.evidence_document_ids)
        for relation in report.relations:
            cited.update(relation.evidence_document_ids)
        stray = sorted(cited - allowed)
        if stray:
            raise errors.IonError(
                "IVE report cites evidence not in this turn's admitted model "
                "context: " + ", ".join(stray),
                stage=errors.STAGE_NORMALIZATION,
            )

    def _execution_profile_binding(self) -> ExecutionProfileBinding:
        """Bind this Core's own active policy identity, for provenance only.

        The active `ExecutionProfile` is known from construction, before any
        turn starts, so it is available for EVERY closure this Core produces
        — COMPLETED or FAILED alike, however early a turn fails. Turn Record
        never imports `execution_profile`; this method reads Core's own
        already-resolved profile and hands the materializer only the plain
        string values its local binding type accepts.
        """
        profile = self._execution_profile
        return ExecutionProfileBinding(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            mode=profile.mode.value,
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
        conversation_context: ConversationContext | None = None,
        retrieval_query: str | None = None,
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
            # The active profile is known from Core construction, before any
            # turn starts, so it is bound even on the earliest possible
            # failure (§26): failure of the sole configured engine still
            # truthfully records WHICH policy authorized that one attempt.
            execution_profile=self._execution_profile_binding(),
            **_context_binding_kwargs(conversation_context, retrieval_query),
        )

    def _run_engine(
        self, engine_id: str, model_input, stage: str, emit: ProgressCallback
    ) -> IVEReport:
        """Run ONE explicitly identified engine through the Model Gateway.

        `model_input` is the `ModelContextAssembly` materialized once, before
        either call (TASK 19.3) — never the upstream `ContextPack`.

        This method remains the progress authority: the Gateway emits nothing,
        so the stage lifecycle vocabulary and its order are unchanged. It also
        remains the layer that maps a non-Product exception escaping an engine
        onto the existing provider stage — the Gateway does not reinterpret
        provider semantics, and this fallback is exactly the behaviour it had
        before the boundary moved.
        """
        emit(stage, "started")
        try:
            report = self._model_gateway.execute(engine_id, model_input)
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

    # ----------------------------------------------------------------- #
    # Gate 4: VOE composition helpers
    # ----------------------------------------------------------------- #
    def _build_composer_input(
        self,
        question: str,
        report: IVEReport,
        *,
        response_depth: str | None = None,
    ) -> ComposerInput:
        """Project one closed IVEReport into the composer's narrow input
        contract. Reads only fields `ComposerInput`/`ComposerClaimView`
        already accept — no evidence content, no `ModelContextAssembly`, no
        `GovernedEvidenceSet`, no retrieval result, no session state, no
        governance object — and never mutates `report` itself. Called only
        when `self._composer is not None`, which is only ever true together
        with `self._voe_runtime_profile is not None` (both are set, or
        neither is, at composition-root time).

        `response_depth` (A2-009A) is the value `ask()` already validated,
        carried through unchanged: presentation metadata only, never read
        from or derived from `report`.
        """
        claims = tuple(
            ComposerClaimView(statement=c.statement, confidence=c.confidence)
            for c in report.claims
        )
        return ComposerInput(
            question=question,
            report_abstract=report.abstract,
            report_highlights=tuple(report.highlights),
            report_claims=claims,
            report_uncertainty=tuple(report.uncertainty),
            report_confidence=report.confidence,
            voe_profile=self._voe_runtime_profile,
            response_depth=response_depth,
        )

    def _composition_fallback_metrics(self, status: str, attempt_latency_ms: float) -> dict:
        """Truthful disclosure of a failed composition attempt: no usage,
        cost, or latency fact the runtime did not actually observe is ever
        fabricated. Each stays `None`/`False`, exactly as a stage that did
        not complete produces no fact for that field elsewhere in this
        module (see `_materialize_failed_turn_record`'s own discipline).
        `attempt_latency_ms` IS observed — Core timed the attempt itself —
        so it is recorded; the composer-reported `latency_ms` is not."""
        binding = self._voe_runtime_profile.binding
        return {
            "status": status,
            "provider": None,
            "model": None,
            "input_tokens": None,
            "output_tokens": None,
            "usage_is_estimated": False,
            "latency_ms": None,
            "attempt_latency_ms": round(attempt_latency_ms, 3),
            "estimated_cost": None,
            "voe_profile_id": binding.profile_id,
            "voe_profile_version": binding.profile_version,
            "voe_runtime_behavioral_fingerprint_sha256": (
                binding.runtime_behavioral_fingerprint_sha256
            ),
        }

    def _composition_success_metrics(
        self, result: ResponseComposerResult, attempt_latency_ms: float
    ) -> dict:
        """Truthful disclosure of a completed composition: every usage fact
        is carried verbatim from what the composer itself already preserved
        (never recomputed here). `estimated_cost` is computed through the
        existing `PricingPort`, exactly mirroring how `_provider_metrics`
        already prices the IVE side — no pricing logic is duplicated inside
        `response_composer`. `latency_ms` is the composer-measured provider
        call; `attempt_latency_ms` is Core's span around the whole attempt."""
        binding = self._voe_runtime_profile.binding
        return {
            "status": "COMPOSED",
            "provider": result.provider,
            "model": result.requested_model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "usage_is_estimated": result.usage_is_estimated,
            "latency_ms": round(result.latency_ms, 3),
            "attempt_latency_ms": round(attempt_latency_ms, 3),
            "estimated_cost": self._pricing.estimate_cost(
                result.requested_model, result.input_tokens, result.output_tokens
            ),
            "voe_profile_id": binding.profile_id,
            "voe_profile_version": binding.profile_version,
            "voe_runtime_behavioral_fingerprint_sha256": (
                binding.runtime_behavioral_fingerprint_sha256
            ),
        }

    @staticmethod
    def _total_cost_with_composition(
        ive_total_cost: float | None, composition_cost: float | None
    ) -> float | None:
        """G3: the turn's total estimated cost once composition was attempted.

        The same rule `ask()` already applies to provider costs: any unknown
        part makes the total unknown — never a partial sum presented as the
        whole. A fallback always has an unknown composition cost (the provider
        may still have billed the attempt), so its total is always None.
        """
        if ive_total_cost is None or composition_cost is None:
            return None
        return round(ive_total_cost + composition_cost, 8)
