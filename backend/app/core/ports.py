"""Ports: the interface contracts the core depends on (hexagonal / ports & adapters).

Modules provide adapters implementing these Protocols. The core is wired with
concrete adapters at startup (see app/container.py) and never imports them
directly. This is how "modules talk to the core" (docs/14).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .models import (
    BlindedAnswer,
    ContextPack,
    EvaluationRecord,
    Evidence,
    IVEReport,
    LexicalRetrievalOutcome,
    MIVEResult,
)

if TYPE_CHECKING:
    # Type-only: Core is wired to concrete engines exclusively through the
    # Model Gateway (itself wired by app/container.py), so this module never
    # runtime-imports the Product module that defines its payload type.
    from ..modules.model_context import EvidenceContextItem, ModelContextAssembly

    # Type-only, same discipline: this module never runtime-imports the
    # response_composer package that defines these payload types (see
    # ResponseComposerPort below). No composer is wired to Core yet.
    from ..modules.response_composer import ComposerInput, ResponseComposerResult


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
class LexicalRetrievalPort(Protocol):
    """OPTIONAL entity lexical branch (OP-DEC-20261004-TW2-51).

    Separate from `retrieve()`, which stays the unchanged dense contract.
    `question` is the CURRENT user question only — never the warm-session
    retrieval query, prior model output or prior evidence. The branch only
    NOMINATES candidates: each added one is materialized by point id from the
    active collection and then passes the same governance and admission as a
    dense candidate. It never raises for an unavailable lexical structure; it
    reports `UNAVAILABLE` instead.
    """

    def lexical_candidates(
        self, question: str, *, exclude_document_ids: tuple[str, ...], limit: int
    ) -> LexicalRetrievalOutcome: ...


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
class ResponseComposerPort(Protocol):
    """Composes user-facing text from an already-closed IVE interpretation,
    under a versioned VOE Dialogue Profile (Gate 1 contract only).

    A distinct responsibility from every other port here, and never a
    substitute for one: `IVEPort` interprets an authorized Model Context into
    evidence-grounded findings; `RendererPort` deterministically packages
    those findings with no model call at all. This port RESTYLES an
    already-produced `IVEReport` projection for presentation — it never
    re-interprets evidence, never runs before an `IVEReport` exists, and
    never runs in place of either of those ports. It does not inherit from,
    extend, or weaken `IVEPort`, `RendererPort`, or the Model Gateway's
    execution contract; none of those changes because this Protocol exists.

    Implementations receive only a `ComposerInput`: the normalized question,
    a read-only projection of one `IVEReport` (abstract, highlights,
    per-claim statement/confidence — Gate 3B removed the third field this
    claim projection used to carry, `evidence_document_ids`: v0.1
    composition has no functional use for any evidence-identity value, so
    none crosses this boundary — uncertainty, confidence), and a verified
    `VOERuntimeProfile` — the VOE profile's identity plus the actual
    behavioral text a composer needs. No evidence content or
    evidence-identity value of any kind (title, content, source_identity,
    page, chunk_id, or a document/candidate id), no `ModelContextAssembly`,
    no `GovernedEvidenceSet`, no raw retrieved `Evidence`, no governance
    object, no session or conversation state, no `Settings`, and no provider
    credential is reachable through this port's signature — see
    `modules/response_composer/models.py`.

    Returns a `ResponseComposerResult` (Gate 3B) — the composed content plus
    the raw execution facts (`provider`, `requested_model`, `input_tokens`,
    `output_tokens`, `usage_is_estimated`, `latency_ms`) the provider call
    actually produced, kept structurally separate from the composed content
    itself (`COMPOSED CONTENT != EXECUTION PROVENANCE`). Never a cost, a
    fallback/success status, or a `TurnRecord`/transport field — those
    belong to a later, separately authorized caller.

    Gate 1 defined this Protocol and its data shapes; Gate 3 added the one
    authorized implementation, `VOEResponseComposer`
    (`modules/response_composer/composer.py`), whose `provider`/
    `requested_model` identity is supplied explicitly at construction time
    by whichever future composition root builds it — never inferred from
    `ExecutionProfile`, `Settings`, or the backend object itself. Neither
    this Protocol nor its implementation is constructed or called anywhere
    in Core, `app.container`, or any runtime entry point at this stage.
    """

    def compose(self, composer_input: "ComposerInput") -> "ResponseComposerResult": ...


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
