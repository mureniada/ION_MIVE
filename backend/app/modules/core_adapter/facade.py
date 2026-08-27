"""Product-facing Core Adapter facade (v0.1).

This is a BOUNDARY, not a second governance engine. It owns no admission,
provenance, or fingerprint semantics: it marshals a Product-side candidate
submission into the existing B0 governance mechanisms, then hands the native
results back without reinterpreting them.

Deliberately narrow. It imports exactly two governance entry points and
re-exports nothing else, so the promotion / authority / receipt vocabulary
carried by `app.modules.admission` never reaches Product code through here.

Pilot v1 chat governance is READ-ONLY: no promotion, no state persistence, and
no autonomous Core-state transition call is reachable from this facade.
"""

from __future__ import annotations

from ..admission.claim_adjudication import run_runtime_admission_gate
from ..runtime_evidence_bridge import build_qdrant_runtime_bridge
from .models import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    CoreAdapterOutcome,
    CoreAdapterOutcomeState,
    CoreAdapterRequest,
    CoreInvocationMode,
)


class CoreAdapter:
    """The single boundary between Product orchestration and B0 governance."""

    def __init__(self) -> None:
        # Same factory, same hardcoded backend/profile binding as B0
        # (bridge.py:248-252). The facade adds no profile selection.
        self._bridge = build_qdrant_runtime_bridge()

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    @property
    def adapter_version(self) -> str:
        return ADAPTER_VERSION

    def govern(self, request: CoreAdapterRequest) -> CoreAdapterOutcome:
        """Run the existing B0 governance sequence for one candidate set.

        Ordering is the B0 ordering: resolve -> build_request -> acceptance
        check -> admission gate. Only the ownership of those calls moves here;
        each call, its arguments, and its semantics are unchanged.

        Governance rejection is returned as an outcome. Operational failure is
        classified as an outcome that carries the original exception, which the
        caller re-raises so that B0 propagation behaviour is preserved.
        """
        # --- read-only authority gate, before any governance call ---
        if request.mode is not CoreInvocationMode.READ_ONLY:
            raise ValueError(
                "Core Adapter permits READ_ONLY invocation only; "
                f"refused mode: {request.mode!r}"
            )

        candidate_count = len(request.candidates)

        try:
            resolutions = self._bridge.resolve(request.candidates)

            bridge_result = self._bridge.build_request(
                request.context_pack,
                resolutions,
                question_id=request.question_id,
                adapter_created_at=request.adapter_created_at,
            )
            if not bridge_result.accepted:
                return self._rejected(
                    candidate_count=candidate_count,
                    bridge_reasons=tuple(bridge_result.reasons),
                )

            try:
                native_result = run_runtime_admission_gate(
                    evidence=request.candidates,
                    pack=request.context_pack,
                    question_id=request.question_id,
                    request=bridge_result.request,
                )
            except ValueError as exc:
                return self._rejected(
                    candidate_count=candidate_count,
                    gate_error=str(exc),
                )
        except Exception as exc:  # noqa: BLE001 - operational, not governance
            return CoreAdapterOutcome(
                outcome=CoreAdapterOutcomeState.OPERATIONAL_FAILURE,
                operational_error=f"{type(exc).__name__}: {exc}",
                operational_exception=exc,
                candidate_count=candidate_count,
                backend_id=self._bridge.backend_id,
                mapping_profile_id=self._bridge.mapping_profile_id,
            )

        return CoreAdapterOutcome(
            outcome=CoreAdapterOutcomeState.GOVERNANCE_COMPLETE,
            native_result=native_result,
            candidate_count=candidate_count,
            governed_count=len(native_result.records),
            backend_id=self._bridge.backend_id,
            mapping_profile_id=self._bridge.mapping_profile_id,
        )

    # ----------------------------------------------------------------- #
    def _rejected(
        self,
        *,
        candidate_count: int,
        bridge_reasons: tuple[str, ...] = (),
        gate_error: str | None = None,
    ) -> CoreAdapterOutcome:
        return CoreAdapterOutcome(
            outcome=CoreAdapterOutcomeState.GOVERNANCE_REJECTED,
            native_bridge_reasons=bridge_reasons,
            native_gate_error=gate_error,
            candidate_count=candidate_count,
            backend_id=self._bridge.backend_id,
            mapping_profile_id=self._bridge.mapping_profile_id,
        )
