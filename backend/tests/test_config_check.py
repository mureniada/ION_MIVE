"""TASK 20: readiness is POLICY-DRIVEN. `require_ready` requires exactly the
provider configuration the ACTIVE, already-resolved `ExecutionProfile` names
— never a fixed pair, and never silently skipped for an engine a profile
does name.

Gate 4: `require_ready` also independently re-verifies the VOE Dialogue
Profile bundle whenever `VOE_PROFILE_ENABLED=true` — turning "the loader is
fail-closed when invoked" into "a bad or missing bundle prevents request
execution" via the SAME readiness gate, not a parallel one.
"""

from __future__ import annotations

import dataclasses

from app.config_check import require_ready
from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.modules.execution_profile import ExecutionMode, ExecutionProfile, STANDARD_GEMINI
from app.modules.voe_profile.loader import RUNTIME_BEHAVIORAL_FILES, load_voe_runtime_profile
from tests.util import raises
from tests.voe_pack import COMMITTED_VOE_PACK_DIR

REAL_VOE_PACK_DIR = COMMITTED_VOE_PACK_DIR


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


# --------------------------------------------------------------------- #
# Gate 4: VOE profile readiness — independent of, and additive to, the
# engine-credential checks above.
# --------------------------------------------------------------------- #
def _ready_env():
    return {"GEMINI_API_KEY": "gk-abc123", "OPENAI_API_KEY": "sk-abc123"}


def test_voe_disabled_skips_the_voe_check_entirely():
    """VOE_PROFILE_ENABLED=false (the default): readiness behaves exactly as
    it did before Gate 4 — a nonexistent bundle_dir is never even inspected."""
    settings = Settings.load({
        "GEMINI_MODEL": "gemini-3.1-flash-lite",
        "VOE_PROFILE_ENABLED": "false",
        "VOE_PROFILE_BUNDLE_DIR": "C:/definitely/does/not/exist",
    })
    require_ready(settings, STANDARD_GEMINI, env={"GEMINI_API_KEY": "gk-abc123"})  # must not raise


def test_voe_enabled_with_valid_bundle_succeeds():
    settings = Settings.load({
        "GEMINI_MODEL": "gemini-3.1-flash-lite",
        "OPENAI_MODEL": "gpt-5.4-mini",
        "VOE_PROFILE_ENABLED": "true",
        "VOE_PROFILE_BUNDLE_DIR": str(REAL_VOE_PACK_DIR),
    })
    require_ready(
        settings, STANDARD_GEMINI, env=_ready_env(),
        core_voe_runtime_profile=load_voe_runtime_profile(REAL_VOE_PACK_DIR),
    )  # must not raise


def test_voe_enabled_with_missing_bundle_dir_fails_closed():
    settings = Settings.load({
        "GEMINI_MODEL": "gemini-3.1-flash-lite",
        "VOE_PROFILE_ENABLED": "true",
        "VOE_PROFILE_BUNDLE_DIR": "C:/definitely/does/not/exist",
    })
    with raises(ConfigurationError):
        require_ready(settings, STANDARD_GEMINI, env=_ready_env())


def test_voe_enabled_with_hash_mismatch_fails_closed(tmp_path):
    for filename, _, _ in RUNTIME_BEHAVIORAL_FILES:
        (tmp_path / filename).write_bytes((REAL_VOE_PACK_DIR / filename).read_bytes())
    # Corrupt one file's content without changing its byte count.
    target = tmp_path / RUNTIME_BEHAVIORAL_FILES[0][0]
    original = target.read_bytes()
    mutated_byte = (original[0] + 1) % 256
    target.write_bytes(bytes([mutated_byte]) + original[1:])

    settings = Settings.load({
        "GEMINI_MODEL": "gemini-3.1-flash-lite",
        "VOE_PROFILE_ENABLED": "true",
        "VOE_PROFILE_BUNDLE_DIR": str(tmp_path),
    })
    with raises(ConfigurationError):
        require_ready(settings, STANDARD_GEMINI, env=_ready_env())


def test_voe_readiness_failure_message_never_exposes_a_secret_value():
    settings = Settings.load({
        "GEMINI_MODEL": "gemini-3.1-flash-lite",
        "VOE_PROFILE_ENABLED": "true",
        "VOE_PROFILE_BUNDLE_DIR": "C:/definitely/does/not/exist",
    })
    try:
        require_ready(settings, STANDARD_GEMINI, env=_ready_env())
        assert False, "expected ConfigurationError"
    except ConfigurationError as exc:
        for secret in _ready_env().values():
            assert secret not in exc.message


# --------------------------------------------------------------------- #
# G5: with VOE enabled, the running Core's bound profile must be present and
# match the freshly resolved binding — otherwise fail closed until restart.
# --------------------------------------------------------------------- #
def _voe_settings(bundle_dir):
    return Settings.load({
        "GEMINI_MODEL": "gemini-3.1-flash-lite",
        "VOE_PROFILE_ENABLED": "true",
        "VOE_PROFILE_BUNDLE_DIR": str(bundle_dir),
    })


def _mismatched_profile():
    real = load_voe_runtime_profile(REAL_VOE_PACK_DIR)
    other_binding = dataclasses.replace(
        real.binding, runtime_behavioral_fingerprint_sha256="0" * 64
    )
    return dataclasses.replace(real, binding=other_binding)


def test_g5_voe_enabled_core_without_profile_fails_closed():
    try:
        require_ready(
            _voe_settings(REAL_VOE_PACK_DIR), STANDARD_GEMINI, env=_ready_env(),
            core_voe_runtime_profile=None,
        )
        assert False, "expected ConfigurationError"
    except ConfigurationError as exc:
        assert "composed without it" in exc.message
        assert "restart" in exc.message


def test_g5_voe_enabled_omitted_core_profile_fails_closed():
    """A caller that forgets the argument gets 503, never a silent skip."""
    with raises(ConfigurationError):
        require_ready(_voe_settings(REAL_VOE_PACK_DIR), STANDARD_GEMINI, env=_ready_env())


def test_g5_voe_enabled_core_bound_to_different_profile_fails_closed():
    try:
        require_ready(
            _voe_settings(REAL_VOE_PACK_DIR), STANDARD_GEMINI, env=_ready_env(),
            core_voe_runtime_profile=_mismatched_profile(),
        )
        assert False, "expected ConfigurationError"
    except ConfigurationError as exc:
        assert "different VOE profile" in exc.message
        assert "restart" in exc.message


def test_g5_voe_enabled_invalid_bundle_fails_even_with_valid_core_profile():
    """The fresh resolution must itself pass; a valid cached profile is not
    a substitute for a valid currently-configured bundle."""
    try:
        require_ready(
            _voe_settings("C:/definitely/does/not/exist"), STANDARD_GEMINI,
            env=_ready_env(),
            core_voe_runtime_profile=load_voe_runtime_profile(REAL_VOE_PACK_DIR),
        )
        assert False, "expected ConfigurationError"
    except ConfigurationError as exc:
        assert "failed to load" in exc.message


def test_g5_voe_disabled_ignores_core_profile_argument():
    settings = Settings.load({
        "GEMINI_MODEL": "gemini-3.1-flash-lite",
        "VOE_PROFILE_ENABLED": "false",
    })
    env = {"GEMINI_API_KEY": "gk-abc123"}
    require_ready(settings, STANDARD_GEMINI, env=env)  # must not raise
    require_ready(settings, STANDARD_GEMINI, env=env, core_voe_runtime_profile=None)
    require_ready(
        settings, STANDARD_GEMINI, env=env,
        core_voe_runtime_profile=_mismatched_profile(),
    )


def test_g5_consistency_failure_messages_never_expose_a_secret_value():
    for core_profile in (None, _mismatched_profile()):
        try:
            require_ready(
                _voe_settings(REAL_VOE_PACK_DIR), STANDARD_GEMINI, env=_ready_env(),
                core_voe_runtime_profile=core_profile,
            )
            assert False, "expected ConfigurationError"
        except ConfigurationError as exc:
            for secret in _ready_env().values():
                assert secret not in exc.message
