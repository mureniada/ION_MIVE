"""Response Composer boundary vocabulary (v0.1, Gate 1).

A `ComposerInput` is the complete, narrow input a `ResponseComposerPort`
implementation may read for one turn. A `ComposedResponse` is the minimum
output shape Gate 1 defines. Together they state the composer's whole lawful
surface — nothing about how composition is actually carried out.

    PROFILE != KNOWLEDGE
    PROFILE != EVIDENCE
    MODEL OUTPUT != EVIDENCE
    TRUTH > STYLE
    ETHICS > STYLE

A composer RESTYLES an already-closed `IVEReport` interpretation; it never
re-interprets evidence. That law is enforced STRUCTURALLY here, not by
convention: `ComposerInput` carries a read-only PROJECTION of an `IVEReport`
— `ComposerClaimView` exposes only `statement` and `confidence` from each
claim (Gate 3B: `evidence_document_ids` was removed — v0.1 composition has no
functional use for any evidence-identity value, and least-authority reasoning
says data not required for lawful composition should not cross this
boundary; see the Gate 3A audit) — and has no field anywhere for evidence
content, title, source_identity, page, chunk_id, or ANY evidence-identity
value of any kind, no field for `ModelContextAssembly` or
`GovernedEvidenceSet`, no field for the raw retrieved `Evidence` list, no
field for a governance object, no field for session or conversation state,
no field for `Settings` or a provider credential, and no field that is a
mutable reference to the `IVEReport` object itself. A value no field exists
for cannot be passed through this module by accident, however the caller is
constructed.

`ResponseComposerResult` (Gate 3B) is a SEPARATE object from `ComposedResponse`
on purpose:

    COMPOSED CONTENT != EXECUTION PROVENANCE

`ComposedResponse` stays exactly what Gate 1 defined — user-content-shaped
only, no provider, no usage, no latency, no cost, no status field, ever.
`ResponseComposerResult` wraps one `ComposedResponse` together with the raw
execution facts a real provider call actually produced (`provider`,
`requested_model`, `input_tokens`, `output_tokens`, `usage_is_estimated`,
`latency_ms`) — never `estimated_cost` (that belongs to a later,
`PricingPort`-holding caller, mirroring how `Core._provider_metrics()` prices
`IVEReport.usage` after the fact rather than the IVE adapter pricing itself),
never a fallback/success status, and never a `TurnRecord` or transport field.

This module imports the standard library and this package's own vocabulary,
plus `VOERuntimeProfile`'s verified identity-and-text shape, only. No Core, Core Adapter,
governed-evidence, model-context, admission, provenance, retrieval, provider,
MIVE, IVE, renderer, evidence-citation projection, container, config or
transport entry point is reachable from here.

Gate 1 scope only: this module defines data shapes. It contains no loading,
no prompt construction, no provider execution, and is not imported by
`Core.ask()`, `app.container`, or any runtime entry point at this stage.

No value in this module is derived from a wall clock, a UUID or a random
source, and no instance identifier is minted: the identity fields are fixed
contract literals, and every other value is carried verbatim from an input
the caller already holds.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..voe_profile import VOERuntimeProfile

RESPONSE_COMPOSER_CONTRACT_ID = "ION_RESPONSE_COMPOSER_V0_1"
RESPONSE_COMPOSER_VERSION = "0.1"


class ComposerContractError(ValueError):
    """Raised whenever a composer boundary object cannot be constructed as
    contracted.

    A missing runtime fact, an out-of-range confidence, or a malformed
    identity raises here; none is ever downgraded into a partially populated
    object.

    This is a module-local error on purpose. This module is inert at Gate 1:
    it introduces no transport stage and no mapping onto the core error
    taxonomy; how a caller responds to a construction failure is a later,
    separately authorized wiring decision, not this contract's business.
    """


def _confidence(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComposerContractError(f"{what} must be a number, found {value!r}")
    v = float(value)
    if not (0.0 <= v <= 1.0):
        raise ComposerContractError(f"{what} must be in [0, 1], found {v!r}")
    return v


@dataclass(frozen=True, kw_only=True)
class ComposerClaimView:
    """One IVE claim, projected into the composer's read-only view.

    Carries exactly the two fields a composer may see from an `IVEReport`
    claim: `statement` and `confidence`. Gate 3B removed the third field this
    type used to carry, `evidence_document_ids`: v0.1 composition never
    reads any evidence-identity value (no citation wiring exists, no
    evidence-citation projection is reached), so per least-authority
    reasoning that value must not cross this boundary at all. This type has
    no field for `evidence_document_ids`, `candidate_id`, `document_id`,
    `source_id`, or any other evidence-identity value — none can be added
    back without a new, separately authorized decision, and none can be
    passed through this type by accident, however the caller is constructed.
    """

    statement: str
    confidence: float

    def __post_init__(self) -> None:
        if not isinstance(self.statement, str) or not self.statement:
            raise ComposerContractError(
                f"statement must be a non-empty string, found {self.statement!r}"
            )
        _confidence(self.confidence, "confidence")


@dataclass(frozen=True, kw_only=True)
class ComposerInput:
    """The complete, narrow input a Response Composer may read for one turn.

    Every field is a plain, already-closed value: the normalized question,
    a read-only projection of one `IVEReport` (`report_abstract`,
    `report_highlights`, `report_claims`, `report_uncertainty`,
    `report_confidence`), and a verified `VOERuntimeProfile` — the VOE
    profile's identity plus the actual behavioral text a composer needs to
    construct a system instruction (Gate 2A: `VOEProfileBinding` alone
    carries identity only and has no field a composer could read to
    determine what the profile actually says).

    Deliberately absent, with no field to carry them: evidence content
    (title, content, source_identity, page, chunk_id), `ModelContextAssembly`,
    `GovernedEvidenceSet`, the raw retrieved `Evidence` list, a rejected or
    non-admitted candidate, a governance decision object, session state,
    conversation memory, `Settings`, a provider credential, and a mutable
    reference to the `IVEReport` object itself — none of them has anywhere to
    enter, however this object is constructed. `VOERuntimeProfile` itself
    carries none of these either (see `voe_profile/models.py`), so nesting
    it here introduces no new evidence-shaped surface.
    """

    question: str
    report_abstract: str
    report_highlights: tuple[str, ...]
    report_claims: tuple[ComposerClaimView, ...]
    report_uncertainty: tuple[str, ...]
    report_confidence: float
    voe_profile: VOERuntimeProfile

    def __post_init__(self) -> None:
        if not isinstance(self.question, str) or not self.question.strip():
            raise ComposerContractError(
                f"question must be a non-empty string, found {self.question!r}"
            )
        if not isinstance(self.report_abstract, str):
            raise ComposerContractError(
                "report_abstract must be a string, found "
                f"{type(self.report_abstract).__name__}"
            )
        for name in ("report_highlights", "report_uncertainty"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or not all(isinstance(x, str) for x in value):
                raise ComposerContractError(f"{name} must be a tuple of strings")
        if not isinstance(self.report_claims, tuple) or not all(
            isinstance(c, ComposerClaimView) for c in self.report_claims
        ):
            raise ComposerContractError(
                "report_claims must be a tuple of ComposerClaimView"
            )
        _confidence(self.report_confidence, "report_confidence")
        if not isinstance(self.voe_profile, VOERuntimeProfile):
            raise ComposerContractError(
                "voe_profile must be a VOERuntimeProfile, found "
                f"{type(self.voe_profile).__name__}"
            )


@dataclass(frozen=True, kw_only=True)
class ComposedResponse:
    """The minimum Gate 1 output shape a Response Composer produces.

    Exactly one substantive field: `composed_text`, the composer's restyled,
    user-facing rendering of `ComposerInput.report_abstract` under the bound
    VOE profile. Deliberately absent, with no field to carry them at Gate 1:
    a citation or evidence-reference list (evidence-citation projection
    wiring is explicitly deferred), a provider or model identity, token counts,
    latency, cost, or any execution-telemetry value (deferred to a later
    gate), and a status/fallback flag (that classification belongs to the
    calling orchestrator once this type is actually wired, not to this inert
    Gate 1 contract).
    """

    composed_text: str
    response_composer_contract_id: str = RESPONSE_COMPOSER_CONTRACT_ID
    response_composer_version: str = RESPONSE_COMPOSER_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.composed_text, str) or not self.composed_text.strip():
            raise ComposerContractError(
                f"composed_text must be a non-empty string, found {self.composed_text!r}"
            )


def _non_empty_str(value: object, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise ComposerContractError(f"{what} must be a non-empty string, found {value!r}")
    return value


def _optional_nonneg_int(value: object, what: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ComposerContractError(f"{what} must be an int or None, found {value!r}")
    if value < 0:
        raise ComposerContractError(f"{what} must be >= 0, found {value!r}")
    return value


@dataclass(frozen=True, kw_only=True)
class ResponseComposerResult:
    """One composer execution's complete, truthful record: the composed
    content, plus the raw execution facts the provider call actually
    produced. A separate object from `ComposedResponse` on purpose:

        COMPOSED CONTENT != EXECUTION PROVENANCE

    `response` is the exact `ComposedResponse` this execution produced —
    never duplicated, never re-derived, carried by reference.

    `provider` and `requested_model` are execution facts supplied by the
    caller that constructed the `VOEResponseComposer` (see
    `composer.py::VOEResponseComposer.__init__`), never inferred here or
    anywhere in this package from a backend's type or private state — this
    module has no way to guess them and does not try to.

    `input_tokens`, `output_tokens`, and `usage_is_estimated` are carried
    verbatim from the raw provider response, exactly as reported (or
    `None`/`False` when the provider did not report them) — never
    recomputed, never estimated further, never defaulted to a fabricated
    number. `latency_ms` is the measured wall-clock duration of the provider
    call itself (`compose()`'s own measurement, mirroring how
    `GeminiIVE`/`OpenAIIVE` measure their own provider call), always present
    because it is always measured locally rather than reported by a
    provider.

    Deliberately absent, with no field to carry them: `estimated_cost` (a
    later, `PricingPort`-holding caller's job — this object states raw
    facts, never a derived price), a fallback/success status (this object
    represents only a successful execution; a failed one is represented by
    this package's own exception types, never by a partially populated
    result), any `TurnRecord` field, any transport field, a citation or
    evidence-reference list, and an open-ended metadata dict.
    """

    response: ComposedResponse
    provider: str
    requested_model: str
    input_tokens: int | None
    output_tokens: int | None
    usage_is_estimated: bool
    latency_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.response, ComposedResponse):
            raise ComposerContractError(
                "response must be a ComposedResponse, found "
                f"{type(self.response).__name__}"
            )
        _non_empty_str(self.provider, "provider")
        _non_empty_str(self.requested_model, "requested_model")
        _optional_nonneg_int(self.input_tokens, "input_tokens")
        _optional_nonneg_int(self.output_tokens, "output_tokens")
        if not isinstance(self.usage_is_estimated, bool):
            raise ComposerContractError(
                "usage_is_estimated must be a bool, found "
                f"{type(self.usage_is_estimated).__name__}"
            )
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float)):
            raise ComposerContractError(
                f"latency_ms must be a number, found {self.latency_ms!r}"
            )
        if self.latency_ms < 0:
            raise ComposerContractError(
                f"latency_ms must be >= 0, found {self.latency_ms!r}"
            )
