"""Gate 4: container-level VOE composer construction.

Scope: `app.container.build_voe_composer` only — that it degrades to
(None, None) when disabled or when the bundle is invalid (never raising, so
`build_core()` itself never crashes on a bad bundle — the fail-closed gate is
`config_check.require_ready`, tested separately), that it reuses the active
SINGLE IVE engine's own provider/model as the minimum first-release rule, and
that it always constructs a SECOND, independent raw backend instance rather
than reaching into a private IVE adapter attribute. No real provider call is
made anywhere in this file — backend objects are only constructed and
introspected, never `.generate()`-invoked.
"""

from __future__ import annotations

from app.container import _build_engines, build_voe_composer
from app.core.config import Settings
from app.modules.execution_profile import STANDARD_GEMINI
from app.modules.response_composer import VOEResponseComposer
from app.modules.voe_profile import VOERuntimeProfile
from tests.voe_pack import COMMITTED_VOE_PACK_DIR

REAL_VOE_PACK_DIR = COMMITTED_VOE_PACK_DIR


def _settings(**overrides):
    values = {"GEMINI_MODEL": "gemini-3.1-flash-lite"}
    values.update(overrides)
    return Settings.load(values)


def _enabled_settings():
    return _settings(
        VOE_PROFILE_ENABLED="true",
        VOE_PROFILE_BUNDLE_DIR=str(REAL_VOE_PACK_DIR),
    )


# --------------------------------------------------------------------- #
# 3: disabled -> no composer constructed
# --------------------------------------------------------------------- #
def test_disabled_returns_none_none():
    composer, profile = build_voe_composer(STANDARD_GEMINI, _settings(VOE_PROFILE_ENABLED="false"))
    assert composer is None
    assert profile is None


def test_enabled_but_invalid_bundle_degrades_to_none_none_never_raises():
    """build_voe_composer must never crash build_core(): a bad bundle here
    degrades exactly like "no composer configured" — the actual fail-closed
    gate is config_check.require_ready, tested separately."""
    settings = _settings(
        VOE_PROFILE_ENABLED="true",
        VOE_PROFILE_BUNDLE_DIR="C:/definitely/does/not/exist",
    )
    composer, profile = build_voe_composer(STANDARD_GEMINI, settings)
    assert composer is None
    assert profile is None


# --------------------------------------------------------------------- #
# 9: enabled + valid -> composer constructed from a separate raw backend
# --------------------------------------------------------------------- #
def test_enabled_with_valid_bundle_constructs_composer_and_profile():
    composer, profile = build_voe_composer(STANDARD_GEMINI, _enabled_settings())
    assert isinstance(composer, VOEResponseComposer)
    assert isinstance(profile, VOERuntimeProfile)


def test_composer_profile_matches_the_verified_runtime_profile():
    _, profile = build_voe_composer(STANDARD_GEMINI, _enabled_settings())
    assert profile.binding.profile_id == "VOE-DIALOGUE-PROFILE"
    # VOE profile v0.3 (operator-approved 2026-09-29); v0.2 was 432dd52a…70f5.
    assert profile.binding.profile_version == "0.3"
    assert (
        profile.binding.runtime_behavioral_fingerprint_sha256
        == "e9966bd07fe723b68e6d10112ffa8651983649c255859fd95d55abd9a90fbbee"
    )


# --------------------------------------------------------------------- #
# 10: composer provider/model equals the active SINGLE IVE provider/model
# --------------------------------------------------------------------- #
def test_composer_provider_and_model_match_the_active_ive_engine():
    settings = _enabled_settings()
    composer, _ = build_voe_composer(STANDARD_GEMINI, settings)
    # Introspection only — never a real .generate() call.
    assert composer._provider == STANDARD_GEMINI.engine_ids[0] == "gemini"
    assert composer._requested_model == settings.gemini_model


def test_composer_backend_is_the_correct_provider_class():
    composer, _ = build_voe_composer(STANDARD_GEMINI, _enabled_settings())
    assert type(composer._backend).__name__ == "GeminiBackend"


# --------------------------------------------------------------------- #
# 11: no private IVE adapter backend is reused
# --------------------------------------------------------------------- #
def test_composer_backend_is_not_shared_with_the_ive_engines_backend():
    settings = _enabled_settings()
    engines = _build_engines(STANDARD_GEMINI, settings)
    composer, _ = build_voe_composer(STANDARD_GEMINI, settings)

    ive_backend = engines["gemini"]._backend  # introspection only, matching this
    composer_backend = composer._backend      # file's own stated scope (docstring above)

    assert composer_backend is not ive_backend
    assert type(composer_backend) is type(ive_backend)  # same class, independent instance


def test_two_calls_construct_two_independent_composer_backends():
    """Each build_voe_composer call constructs its own fresh backend — no
    hidden module-level caching/sharing across calls."""
    settings = _enabled_settings()
    composer_a, _ = build_voe_composer(STANDARD_GEMINI, settings)
    composer_b, _ = build_voe_composer(STANDARD_GEMINI, settings)
    assert composer_a._backend is not composer_b._backend
