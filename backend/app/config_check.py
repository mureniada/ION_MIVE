"""Runtime readiness checks that must pass BEFORE any external call (docs/04, /11).

Never returns or logs secret values — only presence booleans and safety checks.

Readiness is POLICY-DRIVEN (TASK 20): the active, already-resolved Model
Execution Profile names which engines this turn may use, and only those
engines' configuration is required. An engine the active profile does not
name is never checked — the historical "always require both providers" rule
is retired — and an engine it DOES name is always checked, whatever that
engine happens to be, so a future profile that names "openai" still gets
OpenAI's configuration verified. Missing provider configuration is never
globally ignored; it is required exactly where the active policy asks for it.
"""

from __future__ import annotations

import os
import re

from .core.config import Settings, secret_presence
from .core.errors import ConfigurationError
from .modules.execution_profile import ExecutionProfile
from .modules.voe_profile import VOEProfileLoadError, VOERuntimeProfile, resolve_voe_profile

# header-safe: no control chars / whitespace that would corrupt an auth header
_HEADER_SAFE = re.compile(r"^[\x21-\x7E]+$")

# The credential/model pair each currently RECOGNIZED engine identity
# requires. This is composition-time knowledge only — not a registry, not
# discovery, and not a default: an engine id an active profile names but
# this mapping does not recognize fails closed (see `require_ready` below)
# rather than being treated as requiring nothing.
_ENGINE_REQUIREMENTS: dict[str, tuple[str, str]] = {
    "gemini": ("GEMINI_API_KEY", "gemini_model"),
    "openai": ("OPENAI_API_KEY", "openai_model"),
}


def _key_is_header_safe(name: str, env: dict[str, str]) -> bool:
    val = env.get(name, "")
    return bool(val) and bool(_HEADER_SAFE.match(val.strip()))


def require_ready(
    settings: Settings,
    execution_profile: ExecutionProfile,
    env: dict[str, str] | None = None,
    *,
    core_voe_runtime_profile: VOERuntimeProfile | None = None,
) -> None:
    """Require exactly the provider configuration `execution_profile` names,
    and — independently — a valid VOE Dialogue Profile bundle whenever
    `VOE_PROFILE_ENABLED=true` (Gate 4).

    An engine id the profile names that this module does not recognize is a
    composition error, not a missing-credential one, and fails closed
    immediately — no engine's configuration is silently skipped because it
    was unrecognized.

    The VOE check is a genuine second gate, deliberately independent of
    whatever `app.container.build_voe_composer` already resolved at
    composition-root time (which degrades to "no composer" on a bad bundle
    rather than raising, mirroring how this module's own engine checks are
    independent of `_build_engines`): re-resolving here, per call, is what
    turns "the loader is fail-closed when invoked" into "a bad or missing
    bundle prevents request execution" — exactly the same shape this
    function already gives provider credentials, applied to the VOE bundle
    instead. `VOE_PROFILE_ENABLED=false` (the default) skips this check
    entirely, so this function's behavior for every existing caller with the
    profile disabled is unchanged.

    G5 consistency check: with VOE enabled, a valid fresh resolution is not
    enough — the running Core (`core_voe_runtime_profile`, from
    `Core.voe_runtime_profile`) must also hold a bound profile whose binding
    equals the freshly resolved one. A Core cached without a profile (bundle
    became valid only after composition) or with a different one fails
    closed until the process restarts; the Core is never rebuilt or mutated
    here. The argument defaults to None, so a caller that omits it fails
    closed rather than silently skipping the check. Ignored when disabled.
    """
    e = env if env is not None else os.environ
    missing: list[str] = []
    required_keys: list[str] = []

    presence = secret_presence(e)
    for engine_id in execution_profile.engine_ids:
        requirement = _ENGINE_REQUIREMENTS.get(engine_id)
        if requirement is None:
            raise ConfigurationError(
                f"execution profile names an unrecognized engine id: {engine_id!r}"
            )
        key_name, model_field = requirement
        required_keys.append(key_name)
        if not presence.get(key_name, False):
            missing.append(key_name)
        if not getattr(settings, model_field):
            missing.append(key_name.replace("_API_KEY", "_MODEL"))

    if missing:
        raise ConfigurationError(
            "Missing required configuration (values never shown): " + ", ".join(missing)
        )

    for key_name in required_keys:
        if not _key_is_header_safe(key_name, e):
            raise ConfigurationError(
                f"{key_name} contains characters that are not header-safe."
            )

    if settings.voe_profile_enabled:
        try:
            resolved = resolve_voe_profile(
                enabled=True, bundle_dir=settings.voe_profile_bundle_dir
            )
        except VOEProfileLoadError as exc:
            raise ConfigurationError(
                f"VOE profile is enabled but failed to load: {exc}"
            ) from exc
        if core_voe_runtime_profile is None:
            raise ConfigurationError(
                "VOE profile is enabled but the running Core was composed "
                "without it; a process restart is required."
            )
        if core_voe_runtime_profile.binding != resolved.binding:
            raise ConfigurationError(
                "VOE profile is enabled but the running Core is bound to a "
                "different VOE profile than the one now configured; a process "
                "restart is required."
            )
