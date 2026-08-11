"""LIVE-1 generation-parameter control surface (v0.1).

Read-only SDK introspection (no provider call, no network) established which
generation parameters each installed backend's request-construction object
actually accepts:

  Gemini (google.genai.types.GenerateContentConfig) includes, among others:
    temperature, top_p, top_k, seed, max_output_tokens, candidate_count,
    stop_sequences, frequency_penalty, presence_penalty, tools, safety_settings.

  OpenAI (the Responses API's request-construction surface) includes:
    temperature, top_p, max_output_tokens, tools, tool_choice, reasoning,
    parallel_tool_calls, truncation.
    It does NOT expose `seed` at all (unlike the older Chat Completions API) --
    an asymmetry recorded here honestly, not hidden.

This module chooses no values. It only lets a caller assert "this provider
can honor this provider_specific parameter name" before freezing a
LiveRunConfig, and rejects anything not on the allow-list explicitly rather
than silently ignoring it.
"""

from __future__ import annotations

from ...core.models import GenerationControlSurface

PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai"

# Parameters representable via the common GenerationControlSurface fields
# (temperature, top_p, max_output_tokens) are supported by both providers and
# are not listed again here -- this allow-list is for `provider_specific` only.
PROVIDER_SPECIFIC_ALLOWLIST: dict[str, frozenset[str]] = {
    PROVIDER_GEMINI: frozenset({
        "top_k", "seed", "candidate_count", "stop_sequences",
        "frequency_penalty", "presence_penalty", "safety_settings",
    }),
    PROVIDER_OPENAI: frozenset({
        "tool_choice", "reasoning", "parallel_tool_calls", "truncation",
    }),
}


class UnsupportedGenerationParameterError(Exception):
    """A provider_specific generation parameter is not honored by this backend."""


def validate_generation_parameters(provider: str, surface: GenerationControlSurface) -> None:
    """Reject any provider_specific key the named backend cannot actually
    accept. Raises explicitly; never silently drops an unsupported key."""
    if provider not in PROVIDER_SPECIFIC_ALLOWLIST:
        raise UnsupportedGenerationParameterError(f"unknown provider: {provider!r}")
    allowed = PROVIDER_SPECIFIC_ALLOWLIST[provider]
    unsupported = set(surface.provider_specific) - allowed
    if unsupported:
        raise UnsupportedGenerationParameterError(
            f"{provider}: unsupported provider_specific parameter(s) {sorted(unsupported)}; "
            f"allowed: {sorted(allowed)}. Note: 'seed' is not exposed by OpenAI's Responses "
            "API in the installed SDK -- a real, structural limitation, not an oversight."
        )
