"""Ports: the interface contracts the core depends on (hexagonal / ports & adapters).

Modules provide adapters implementing these Protocols. The core is wired with
concrete adapters at startup (see app/container.py) and never imports them
directly. This is how "modules talk to the core" (docs/14).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import ContextPack, Evidence, IVEReport, MIVEResult


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
    """One independent model interpretation of one Context Pack (docs/05).

    Implementations receive ONLY the Context Pack — never another engine's output.
    """

    @property
    def engine_id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def run(self, context_pack: ContextPack) -> IVEReport: ...


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


@runtime_checkable
class ClockPort(Protocol):
    def now_iso(self) -> str: ...

    def monotonic_ms(self) -> float: ...


@runtime_checkable
class PricingPort(Protocol):
    """Estimates cost from usage. Unknown pricing returns None (docs/08)."""

    def estimate_cost(
        self, model: str, input_tokens: int | None, output_tokens: int | None
    ) -> float | None: ...
