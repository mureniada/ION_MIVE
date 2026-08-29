"""TASK 20: readiness is POLICY-DRIVEN. `require_ready` requires exactly the
provider configuration the ACTIVE, already-resolved `ExecutionProfile` names
— never a fixed pair, and never silently skipped for an engine a profile
does name."""

from __future__ import annotations

from app.config_check import require_ready
from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.modules.execution_profile import ExecutionMode, ExecutionProfile, STANDARD_GEMINI
from tests.util import raises


def _settings(**overrides):
    values = {"OPENAI_MODEL": "gpt-5.4-mini", "GEMINI_MODEL": "gemini-3.1-flash-lite"}
    values.update(overrides)
    return Settings.load(values)


def _profile(**overrides):
    kwargs = dict(
        profile_id="TEST", profile_version="0.1", mode=ExecutionMode.SINGLE,
        engine_ids=("gemini",),
    )
    kwargs.update(overrides)
    return ExecutionProfile(**kwargs)


# A. STANDARD_GEMINI is ready with ONLY Gemini configured — no OpenAI
# credential or model is required (D20-10). --------------------------------
def test_standard_gemini_ready_with_only_gemini_configured():
    settings = Settings.load({"GEMINI_MODEL": "gemini-3.1-flash-lite"})  # no OPENAI_MODEL at all
    env = {"GEMINI_API_KEY": "gk-abc123"}  # no OPENAI_API_KEY at all
    require_ready(settings, STANDARD_GEMINI, env=env)  # should not raise


# B. STANDARD_GEMINI still requires ITS OWN engine's credential. -----------
def test_standard_gemini_missing_gemini_api_key_fails():
    settings = Settings.load({"GEMINI_MODEL": "gemini-3.1-flash-lite"})
    with raises(ConfigurationError):
        require_ready(settings, STANDARD_GEMINI, env={})


# C. STANDARD_GEMINI still requires ITS OWN engine's model. ----------------
def test_standard_gemini_missing_gemini_model_fails():
    settings = Settings.load({})  # gemini_model == ""
    env = {"GEMINI_API_KEY": "gk-abc123"}
    with raises(ConfigurationError):
        require_ready(settings, STANDARD_GEMINI, env=env)


# D. Readiness is policy-driven, not "OpenAI checks removed globally": a
# profile that explicitly names "openai" still requires OpenAI's own
# configuration, exactly as STANDARD_GEMINI requires Gemini's. -------------
def test_profile_naming_openai_still_requires_openai_configuration():
    profile = _profile(engine_ids=("openai",))

    with raises(ConfigurationError):
        require_ready(Settings.load({}), profile, env={})  # no OPENAI_MODEL, no key

    settings = _settings()  # OPENAI_MODEL present
    with raises(ConfigurationError):
        require_ready(settings, profile, env={})  # still no OPENAI_API_KEY

    require_ready(settings, profile, env={"OPENAI_API_KEY": "sk-abc123"})  # now ready


# E. An engine id a profile names that this composition does not recognize
# fails closed — never silently treated as requiring nothing. --------------
def test_unrecognized_engine_id_in_profile_fails_closed():
    profile = _profile(engine_ids=("unknown-engine",))
    with raises(ConfigurationError):
        require_ready(
            _settings(), profile, env={"GEMINI_API_KEY": "x", "OPENAI_API_KEY": "y"}
        )


def test_ready_when_present_and_header_safe():
    env = {"OPENAI_API_KEY": "sk-abc123", "GEMINI_API_KEY": "gk-abc123"}
    require_ready(_settings(), STANDARD_GEMINI, env=env)  # should not raise


def test_rejects_non_header_safe_key():
    env = {"GEMINI_API_KEY": "gk abc"}
    with raises(ConfigurationError):
        require_ready(_settings(), STANDARD_GEMINI, env=env)
