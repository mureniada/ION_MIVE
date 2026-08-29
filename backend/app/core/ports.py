"""Ports: the interface contracts the core depends on (hexagonal / ports & adapters).

Modules provide adapters implementing these Protocols. The core is wired with
concrete adapters at startup (see app/container.py) and never imports them
directly. This is how "modules talk to the core" (docs/14).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .models import BlindedAnswer, ContextPack, EvaluationRecord, Evidence, IVEReport, MIVEResult

if TYPE_CHECKING:
    # Type-only: Core is wired to concrete engines exclusively through the
    # Model Gateway (itself wired by app/container.py), so this module never
    # runtime-imports the Product module that defines its payload type.
    from ..modules.model_context import EvidenceContextItem, ModelContextAssembly


@runtime_checkable
class EmbeddingPort(Protocol):
    """Turns text into vectors. Real backends: local model or provider API."""

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class RetrievalPort(Protocol):
    """Stores and returns evidence. Does not interpret it (docs/04).

    The only product implementation is Qdrant; tests use an in-memory double.
    """

    def retrieve(self, question: str, top_k: int) -> list[Evidence]: ...


@runtime_checkable
class ContextPackBuilderPort(Protocol):
    """Builds the canonical Context Pack. Performs no reasoning (docs/04)."""

    def build(self, question: str, evidence: list[Evidence]) -> ContextPack: ...


@runtime_checkable
class IVEPort(Protocol):
    """One independent model interpretation of one authorized Model Context
    for a turn (docs/05).

    Implementations receive ONLY the already-governed `ModelContextAssembly`
    for this turn — never another engine's output, and never the upstream
    `ContextPack` directly (TASK 19.3): only admitted governed content may
    reach a provider. The payload is a forward reference so this module,
    which Core depends on directly, never runtime-imports the Product module
    that defines it.
    """

    @property
    def engine_id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def run(self, model_input: "ModelContextAssembly") -> IVEReport: ...


@runtime_checkable
class MIVEPort(Protocol):
    """Compares independent IVE reports (docs/06). Never produces a third answer."""

    def compare(self, reports: list[IVEReport]) -> MIVEResult: ...


@runtime_checkable
class RendererPort(Protocol):
    """Deterministically renders the user output contract (docs/07). No LLM calls."""

    def render(
        self,
        *,
        question: str,
        mive_result: MIVEResult,
        reports: list[IVEReport],
        evidence: list[Evidence],
        metrics_dict: dict,
    ) -> dict: ...

    def render_single(
        self,
        *,
        question: str,
        report: IVEReport,
        authorized_evidence_basis: "tuple[EvidenceContextItem, ...]",
        metrics_dict: dict,
    ) -> dict:
        """Render one engine's report under a comparison-not-applicable policy.

        `authorized_evidence_basis` is the SAME evidence tuple the executed
        engine itself received — Model Context evidence, never the broader
        retrieved-candidate list — so an implementation can resolve a report's
        own citations without ever reaching for a wider evidence authority
        than the one that actually reasoned over it (TASK 17 remains
        unwired; this is not a substitute for it).
        """
        ...


@runtime_checkable
class ClockPort(Protocol):
    def now_iso(self) -> str: ...

    def monotonic_ms(self) -> float: ...


@runtime_checkable
class EvaluationPort(Protocol):
    """LIVE-1 semantic evaluation (v0.1: HUMAN_BLIND only).

    Implementations receive a blinded answer pair and produce one
    EvaluationRecord. FUTURE / NOT IMPLEMENTED: LLM_JUDGE, HYBRID,
    DUAL_JUDGE — this Protocol exists so they *could* be added later
    without changing the interface, but no such implementation exists in
    this codebase.
    """

    def evaluate(
        self,
        pair: tuple[BlindedAnswer, BlindedAnswer],
        *,
        rubric_version: str,
        evaluation_profile: str,
        evidence: list[Evidence] | None = None,
    ) -> EvaluationRecord: ...


@runtime_checkable
class PricingPort(Protocol):
    """Estimates cost from usage. Unknown pricing returns None (docs/08)."""

    def estimate_cost(
        self, model: str, input_tokens: int | None, output_tokens: int | None
    ) -> float | None: ...
