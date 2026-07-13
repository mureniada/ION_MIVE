from __future__ import annotations

from app.config_check import require_ready
from app.core.config import Settings
from app.core.errors import ConfigurationError
from tests.util import raises


def _settings():
    return Settings.load({"OPENAI_MODEL": "gpt-5.4-mini", "GEMINI_MODEL": "gemini-3.1-flash-lite"})


def test_missing_keys_fail_clearly_before_calls():
    with raises(ConfigurationError):
        require_ready(_settings(), env={"OPENAI_MODEL": "x", "GEMINI_MODEL": "y"})


def test_ready_when_present_and_header_safe():
    env = {"OPENAI_API_KEY": "sk-abc123", "GEMINI_API_KEY": "gk-abc123"}
    require_ready(_settings(), env=env)  # should not raise


def test_rejects_non_header_safe_key():
    env = {"OPENAI_API_KEY": "sk abc", "GEMINI_API_KEY": "gk-abc"}
    with raises(ConfigurationError):
        require_ready(_settings(), env=env)
