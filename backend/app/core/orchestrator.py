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

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        *,
        progress: ProgressCallback | None = None,
    ) -> AskResult:
        emit = progress or (lambda *_: None)
        request_id = uuid.uuid4().hex
        started = self._clock.monotonic_ms()

        # --- input validation happens before any external call (docs/15) ---
        q = (question or "").strip()
        if not q:
            raise errors.IonError("Question must be a non-empty string.",
                                  stage=errors.STAGE_CONFIGURATION)
        k = self._settings.default_top_k if top_k is None else int(top_k)
        if k < 1:
            raise errors.IonError("top_k must be >= 1.", stage=errors.STAGE_CONFIGURATION)

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

        # --- independent IVE runs (neither sees the other) ---
        gemini_report = self._run_engine(self._gemini, pack, errors.STAGE_GEMINI, emit)
        openai_report = self._run_engine(self._openai, pack, errors.STAGE_OPENAI, emit)

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

        # --- telemetry ---
        provider_metrics = [
            self._provider_metrics(r) for r in (gemini_report, openai_report)
        ]
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
        emit("answer", "ready")

        return AskResult(
            request_id=request_id,
            question=q,
            status="success",
            rendered=rendered,
            mive_result=mive_result.to_dict(),
            ive_reports=[gemini_report.to_contract_dict(), openai_report.to_contract_dict()],
            metrics=metrics.to_dict(),
        )

    # ----------------------------------------------------------------- #
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
