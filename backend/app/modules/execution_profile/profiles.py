"""The one canonical Model Execution Profile v0.1 defines: STANDARD_GEMINI.

This module states, and states only, that STANDARD_GEMINI is a SINGLE
execution profile whose requested engine identity is "gemini". It does NOT
claim that Core uses it, that Gemini actually executes, that OpenAI is
skipped at runtime, that MIVE is bypassed, that the renderer supports SINGLE,
that Turn Record supports SINGLE, that configuration selects it, or that a
pilot deployment can run without OpenAI credentials. Every one of those is a
runtime-wiring claim that belongs to a later, separately authorized phase
(TASK 20.3B) — none of them is true merely because this module exists.

`STANDARD_GEMINI` is a plain, pre-constructed `ExecutionProfile` instance: no
factory, no environment lookup, no registry, and no hidden behaviour. TASK
20.2 defines exactly this one profile; a general profile registry is
explicitly out of scope.

`resolve_execution_profile` (TASK 20.3A) maps an explicit, exactly-matching
profile identity string to the one canonical profile above, by identity —
nothing more. It reads no environment variable, no file, no clock, no UUID,
no random source, and inspects no Gateway, provider or credential: it is a
pure mapping from a string a caller already holds to policy data this module
already defines. It does not normalize, default, or near-match its input,
because doing any of those would let a caller silently receive a different
policy than the one it asked for.
"""

from __future__ import annotations

from .models import ExecutionMode, ExecutionProfile

STANDARD_GEMINI = ExecutionProfile(
    profile_id="STANDARD_GEMINI",
    profile_version="0.1",
    mode=ExecutionMode.SINGLE,
    engine_ids=("gemini",),
)


class ExecutionProfileResolutionError(ValueError):
    """Raised whenever a requested profile identity cannot be resolved.

    This is a package-local error, deliberately not `app.core.errors.
    ConfigurationError`: this package stays closed against Core's error
    taxonomy, exactly as it stays closed against Core itself. Mapping this
    onto the existing `ConfigurationError` boundary is a later, separately
    authorized composition-time concern (TASK 20.3B), not this pure
    resolver's business.
    """


def resolve_execution_profile(profile_id: object) -> ExecutionProfile:
    """Resolve an explicit profile identity to its canonical policy, by identity.

    The ONLY currently resolvable identity is the exact string
    `"STANDARD_GEMINI"`. Every other input is refused, including `None`, a
    non-string value, an empty string, a whitespace-only string, a string
    carrying leading/trailing whitespace, an unknown identity, a case
    variant, and a near match. Nothing here is normalized, stripped, cased,
    or defaulted: a caller either names an existing canonical profile
    exactly, or is refused.

    The returned object is `STANDARD_GEMINI` itself, not a copy — resolution
    performs no reconstruction of profile data.
    """
    if not isinstance(profile_id, str) or not profile_id:
        raise ExecutionProfileResolutionError(
            f"execution profile id must be a non-empty string, found {profile_id!r}"
        )
    if profile_id == STANDARD_GEMINI.profile_id:
        return STANDARD_GEMINI
    raise ExecutionProfileResolutionError(
        f"unknown execution profile id: {profile_id!r}"
    )
