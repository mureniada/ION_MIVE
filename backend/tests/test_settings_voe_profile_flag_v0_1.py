"""Bounded contract test for the strict VOE_PROFILE_ENABLED parser (Gate 2A).

Scope: this covers only `Settings.load()`'s parsing of `VOE_PROFILE_ENABLED`
and proves that change is isolated from the shared, still-permissive
`_as_bool` helper other flags (e.g. `DEBUG`) continue to use. It does not
exercise the loader, the composer, or any runtime wiring.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings, SettingsError


# --------------------------------------------------------------------- #
# 13: unset -> False
# --------------------------------------------------------------------- #
def test_unset_voe_profile_enabled_is_false():
    settings = Settings.load({})
    assert settings.voe_profile_enabled is False


def test_empty_string_voe_profile_enabled_is_false():
    """Present-but-empty is treated as absence of operator intent, not as a
    malformed value — the same boundary `_as_bool` already draws for other
    flags."""
    settings = Settings.load({"VOE_PROFILE_ENABLED": ""})
    assert settings.voe_profile_enabled is False


# --------------------------------------------------------------------- #
# 14: accepted explicit false spellings -> False
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["0", "false", "False", "FALSE", "no", "No", "off", "Off"])
def test_accepted_false_spellings_are_false(value):
    settings = Settings.load({"VOE_PROFILE_ENABLED": value})
    assert settings.voe_profile_enabled is False


# --------------------------------------------------------------------- #
# 15: accepted explicit true spellings -> True
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "Yes", "on", "On"])
def test_accepted_true_spellings_are_true(value):
    settings = Settings.load({"VOE_PROFILE_ENABLED": value})
    assert settings.voe_profile_enabled is True


def test_accepted_spellings_tolerate_surrounding_whitespace():
    settings = Settings.load({"VOE_PROFILE_ENABLED": "  true  "})
    assert settings.voe_profile_enabled is True


# --------------------------------------------------------------------- #
# 16: malformed non-empty values fail loudly, never silently False
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["treu", "enabled", "maybe", "2", "TRVE", "yesplease", "disable"])
def test_malformed_non_empty_values_raise_instead_of_silently_disabling(value):
    with pytest.raises(SettingsError, match="VOE_PROFILE_ENABLED"):
        Settings.load({"VOE_PROFILE_ENABLED": value})


def test_malformed_value_error_names_the_offending_value():
    with pytest.raises(SettingsError, match="treu"):
        Settings.load({"VOE_PROFILE_ENABLED": "treu"})


# --------------------------------------------------------------------- #
# 17: DEBUG and other existing boolean settings are unaffected
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["treu", "enabled", "maybe", "2"])
def test_debug_flag_keeps_permissive_semantics_unchanged(value):
    """The exact malformed values that now raise for VOE_PROFILE_ENABLED
    must still silently resolve to False for DEBUG — proving the strict
    parser is isolated to the one governed flag, not a change to the shared
    `_as_bool` helper."""
    settings = Settings.load({"DEBUG": value})
    assert settings.debug is False


def test_debug_flag_true_spellings_still_work():
    settings = Settings.load({"DEBUG": "true"})
    assert settings.debug is True


def test_a_malformed_voe_flag_does_not_prevent_other_settings_from_being_read_first_class():
    """The raise happens inside Settings.load(); a caller gets a clear,
    named failure rather than a partially-constructed Settings object."""
    with pytest.raises(SettingsError):
        Settings.load({"DEBUG": "true", "VOE_PROFILE_ENABLED": "maybe"})
