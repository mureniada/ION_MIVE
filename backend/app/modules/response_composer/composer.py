"""VOE Response Composer (v0.1, Gate 3 + Gate 3B) — the one authorized
implementation of `ResponseComposerPort`.

Composes user-facing prose from an already-closed IVE interpretation under a
verified VOE Dialogue Profile. It is not an IVE, not a `ModelGateway` engine,
not a renderer, not an evidence interpreter, not a retrieval component, and
not an Adaptive Dialogue component — it restyles a decision that has already
been made, and makes none of its own about evidence, admission, or dialogue
state.

    PROFILE != KNOWLEDGE
    PROFILE != EVIDENCE
    PROFILE != ADAPTIVE DIALOGUE ENGINE
    MODEL OUTPUT != EVIDENCE
    METAPHOR != EVIDENCE
    METAPHOR != FACT
    INTERPRETATION != FACT
    COMPOSED CONTENT != EXECUTION PROVENANCE

Gate 3B: `compose()` returns a `ResponseComposerResult`, not a bare
`ComposedResponse` — the composed text plus the raw execution facts
(`provider`, `requested_model`, `input_tokens`, `output_tokens`,
`usage_is_estimated`, `latency_ms`) the provider call actually produced, so a
future caller can build truthful telemetry without this module inventing
anything on its behalf. `provider`/`requested_model` are supplied explicitly
at construction time (never inferred from `backend`, `ExecutionProfile`, or
`Settings` — this module imports neither of the latter two). `latency_ms` is
measured locally around the provider call, mirroring
`GeminiIVE`/`OpenAIIVE`'s own latency measurement. No cost is computed here:
this module imports neither `PricingPort` nor `PricingTable` — cost
estimation from these preserved facts is a later, `PricingPort`-holding
caller's job.

Provider execution is reused, not duplicated: `GeminiBackend`/`OpenAIBackend`
(`modules/gemini_ive/backend.py`, `modules/openai_ive/backend.py`) already
expose a provider-agnostic `generate(*, system, user, schema)` primitive that
knows nothing about `IVE_SYSTEM_PROMPT`, `IVE_RESPONSE_SCHEMA`, or
`ModelContextAssembly` — all of that IVE-specific meaning lives in
`ive_common.py` and the `GeminiIVE`/`OpenAIIVE` adapters, never in the raw
backend. This module reaches for that same raw primitive STRUCTURALLY, by
attribute (`backend.generate(...)`), and imports nothing from `ive_common`,
`gemini_ive`, `openai_ive`, `model_gateway`, or `core.ports.IVEPort` — so this
module cannot route through, depend on, or accidentally reproduce IVE
semantics, and no provider file needs to change for this reuse to be lawful.

This module imports the standard library and this package's own vocabulary
only. `VOEResponseComposer` satisfies `ResponseComposerPort`
(`app/core/ports.py`) structurally — by exposing a matching `compose()`
method — exactly as `GeminiIVE`/`OpenAIIVE` satisfy `IVEPort` without
inheriting from it; this module does not import that Protocol.
"""

from __future__ import annotations

import json
import time

from .models import (
    ComposedResponse,
    ComposerContractError,
    ComposerInput,
    ResponseComposerResult,
)

VOE_RESPONSE_COMPOSER_ID = "ION_VOE_RESPONSE_COMPOSER_V0_1"
VOE_RESPONSE_COMPOSER_VERSION = "0.1"


class ResponseComposerError(Exception):
    """Base of the composer's own local error hierarchy.

    Module-local on purpose, mirroring every other pure/adapter package in
    this codebase (`execution_profile`, `voe_profile`): this is not mapped
    onto `app.core.errors` here, and transport/HTTP status mapping is not
    this module's concern — that is later, separately authorized wiring.
    """


class ResponseComposerProviderError(ResponseComposerError):
    """The backend call itself failed (network, SDK, provider-side error).

    The original exception is chained (`from exc`) and never swallowed; this
    type exists only to give the composer boundary one recognizable error
    shape, exactly as `ProviderError` does for the IVE adapters — without
    reusing `ProviderError` itself, since that type belongs to the IVE error
    taxonomy this composer is deliberately not part of.
    """


class ResponseComposerOutputError(ResponseComposerError):
    """The backend returned output that does not satisfy the composer's own
    output contract: not text, not JSON, not an object, an unexpected key,
    or a missing/empty/wrong-typed `composed_text`.

    Every check is fail-closed: no partial or best-effort `ComposedResponse`
    is ever constructed from output that fails any one of these checks.
    """


# --------------------------------------------------------------------- #
# composer-owned system instruction
# --------------------------------------------------------------------- #
_SYSTEM_INSTRUCTION_PREAMBLE = """You are the Voice of Emergence Response Composer.

1. An Intelligence Validation Engine has already produced a closed, evidence-grounded interpretation for this turn. That interpretation is final: you do not re-interpret, re-verify, extend, or second-guess it.
2. You may change expression, structure, emphasis, warmth, directness, framing, and illustrative presentation.
3. You may NOT introduce new factual authority: no claim, fact, figure, or assertion beyond what the supplied interpretation already states.
4. You have no source authority. You may NOT claim access to source material beyond the supplied interpretation, you have not read any underlying document, and you must never invent, describe, or imply a citation, a source, or a document you were not given.
5. Preserve the uncertainty and confidence boundaries the interpretation already states. Do not manufacture confidence the interpretation does not have, and do not discard uncertainty it does state.
6. Metaphor, analogy, and example are explanatory devices only. They are never evidence and never proof of a claim.
7. When you reframe or interpret beyond the literal claim text, make clear that this is interpretation, not fact, whenever that distinction matters to the reader.
8. The person you are writing to remains the author of their own life. Do not act as an oracle, do not claim privileged access to their purpose or destiny, and do not prescribe what they must do.
9. Depth is conditional, not compulsory: match depth to what the question actually needs.
10. An insightful closing is optional. Do not manufacture one.
11. Do not manufacture profundity. If a plain answer is complete, give a plain answer.

The following four documents are your complete behavioral instruction. Follow them in the voice and manner they describe."""

_SYSTEM_INSTRUCTION_CLOSING = (
    "Return a single JSON object matching the requested schema and nothing else."
)


def build_composer_system_instruction(voe_profile) -> str:
    """Build the composer's system instruction, deterministically, from the
    already-verified `VOERuntimeProfile` supplied on `ComposerInput`.

    `voe_profile` is read STRUCTURALLY, by attribute (`dialogue_profile_text`,
    `style_parameters_text`, `ethical_policy_text`,
    `illustrative_reasoning_policy_text`) — this module imports nothing from
    `voe_profile` and never calls a loader, never reads a file, and never
    accepts a `bundle_dir`/path argument anywhere in this module. The four
    texts are included VERBATIM, in the fixed order 01 -> 02 -> 03 -> 04, with
    no normalization, rewriting, summarization, or regeneration: same
    `voe_profile` in, byte-identical instruction out, every time.
    """
    parts = [
        _SYSTEM_INSTRUCTION_PREAMBLE,
        "",
        "=== 01 DIALOGUE PROFILE ===",
        voe_profile.dialogue_profile_text,
        "",
        "=== 02 STYLE PARAMETERS ===",
        voe_profile.style_parameters_text,
        "",
        "=== 03 ETHICAL POLICY ===",
        voe_profile.ethical_policy_text,
        "",
        "=== 04 ILLUSTRATIVE REASONING POLICY ===",
        voe_profile.illustrative_reasoning_policy_text,
        "",
        _SYSTEM_INSTRUCTION_CLOSING,
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------- #
# composer-owned user payload
# --------------------------------------------------------------------- #
def build_composer_user_payload(composer_input: ComposerInput) -> str:
    """Build the composer's user payload, deterministically, from
    `ComposerInput` alone.

    Contains exactly the approved IVE projection fields — question, abstract,
    highlights, claims (statement/confidence only — Gate 3B removed
    `evidence_document_ids`; v0.1 composition has no functional use for any
    evidence-identity value, so none crosses this boundary), uncertainty,
    confidence — and nothing else: no evidence content, no title, no
    source_identity, no page, no chunk_id, no evidence-identity value of any
    kind, because `ComposerInput` and `ComposerClaimView` have no field to
    read any of those from in the first place. Serialization is
    deterministic (`sort_keys=True`): the same `ComposerInput` always
    produces the same payload string, byte for byte.
    """
    claims = [
        {
            "statement": claim.statement,
            "confidence": claim.confidence,
        }
        for claim in composer_input.report_claims
    ]
    payload = {
        "question": composer_input.question,
        "abstract": composer_input.report_abstract,
        "highlights": list(composer_input.report_highlights),
        "claims": claims,
        "uncertainty": list(composer_input.report_uncertainty),
        "confidence": composer_input.report_confidence,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------- #
# composer-owned output schema
# --------------------------------------------------------------------- #
# Deliberately NOT `IVE_RESPONSE_SCHEMA` — a distinct, minimal schema owned
# by this module, naming nothing this Gate defers: no citation/reference
# list, no evidence list, no telemetry, no provider provenance field.
COMPOSER_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["composed_text"],
    "properties": {
        "composed_text": {"type": "string"},
    },
}

_ALLOWED_OUTPUT_KEYS = frozenset({"composed_text"})


# --------------------------------------------------------------------- #
# the composer
# --------------------------------------------------------------------- #
class VOEResponseComposer:
    """The one authorized `ResponseComposerPort` implementation for the VOE
    Dialogue Profile.

    `backend` is any object exposing a callable
    `generate(*, system: str, user: str, schema: dict)` returning a value
    with `.text` (and, when the provider reports them, `.input_tokens`,
    `.output_tokens`, `.usage_is_estimated`) attributes — read
    STRUCTURALLY, by attribute, so a real `GeminiBackend`/`OpenAIBackend`
    instance satisfies this without any adaptation, and without this module
    importing either concrete backend class or `ive_common.GenerationResult`.

    `provider` and `requested_model` are execution-identity facts supplied
    explicitly by the caller that constructs this composer — never inferred
    from `backend`'s type, its private attributes, `ExecutionProfile`, or
    `Settings`, none of which this module imports or inspects. Gate 3B
    establishes this constructor contract; which concrete values a future
    composition root passes is that later, separately authorized gate's
    decision, not this module's.

    No retry policy exists here: a backend failure or a malformed output
    raises once and propagates.
    """

    def __init__(self, backend, *, provider: str, requested_model: str) -> None:
        if not callable(getattr(backend, "generate", None)):
            raise ResponseComposerError(
                "backend must expose a callable generate(system=..., user=..., "
                "schema=...)"
            )
        if not isinstance(provider, str) or not provider:
            raise ResponseComposerError(
                f"provider must be a non-empty string, found {provider!r}"
            )
        if not isinstance(requested_model, str) or not requested_model:
            raise ResponseComposerError(
                f"requested_model must be a non-empty string, found {requested_model!r}"
            )
        self._backend = backend
        self._provider = provider
        self._requested_model = requested_model

    def compose(self, composer_input: ComposerInput) -> ResponseComposerResult:
        if not isinstance(composer_input, ComposerInput):
            raise ResponseComposerError(
                "compose() requires a ComposerInput, found "
                f"{type(composer_input).__name__}"
            )

        system = build_composer_system_instruction(composer_input.voe_profile)
        user = build_composer_user_payload(composer_input)

        # Measures the provider execution boundary only — started
        # immediately before, stopped immediately after, the one backend
        # call. Never covers profile text assembly above, output
        # validation below, or anything else.
        started = time.monotonic()
        try:
            result = self._backend.generate(
                system=system, user=user, schema=COMPOSER_RESPONSE_SCHEMA
            )
        except Exception as exc:  # backend/SDK/network failure
            raise ResponseComposerProviderError(
                f"composer backend call failed: {exc}"
            ) from exc
        latency_ms = (time.monotonic() - started) * 1000.0

        text = getattr(result, "text", None)
        if not isinstance(text, str) or not text:
            raise ResponseComposerOutputError(
                "composer backend returned no text output"
            )

        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResponseComposerOutputError(
                f"composer output is not valid JSON: {exc}"
            ) from None

        if not isinstance(raw, dict):
            raise ResponseComposerOutputError(
                f"composer output must be a JSON object, found {type(raw).__name__}"
            )

        extra_keys = set(raw.keys()) - _ALLOWED_OUTPUT_KEYS
        if extra_keys:
            raise ResponseComposerOutputError(
                f"composer output has unexpected key(s): {sorted(extra_keys)}"
            )

        if "composed_text" not in raw:
            raise ResponseComposerOutputError(
                "composer output missing required key 'composed_text'"
            )

        composed_text = raw["composed_text"]
        if not isinstance(composed_text, str) or not composed_text.strip():
            raise ResponseComposerOutputError(
                "composer output 'composed_text' must be a non-empty string, "
                f"found {composed_text!r}"
            )

        try:
            response = ComposedResponse(composed_text=composed_text)
        except ComposerContractError as exc:
            raise ResponseComposerOutputError(str(exc)) from exc

        # Truthful preservation only: whatever the raw provider response
        # reported, verbatim — never recomputed, never estimated further,
        # never defaulted to a fabricated number. A provider that reports
        # nothing yields None/False here, exactly as GenerationResult itself
        # already represents "not reported."
        try:
            return ResponseComposerResult(
                response=response,
                provider=self._provider,
                requested_model=self._requested_model,
                input_tokens=getattr(result, "input_tokens", None),
                output_tokens=getattr(result, "output_tokens", None),
                usage_is_estimated=bool(getattr(result, "usage_is_estimated", False)),
                latency_ms=latency_ms,
            )
        except ComposerContractError as exc:
            raise ResponseComposerOutputError(str(exc)) from exc
