from __future__ import annotations

from app.core.config import Settings, secret_presence


def test_debug_parsing_and_defaults():
    s = Settings.load({"DEBUG": "true", "OPENAI_MODEL": "gpt-5.4-mini"})
    assert s.debug is True
    assert s.openai_model == "gpt-5.4-mini"
    assert s.default_top_k == 5
    assert Settings.load({"DEBUG": "0"}).debug is False
    assert Settings.load({}).debug is False


def test_secret_presence_is_boolean_only():
    p = secret_presence({"OPENAI_API_KEY": "sk-xxx", "GEMINI_API_KEY": ""})
    assert p == {"OPENAI_API_KEY": True, "GEMINI_API_KEY": False}
    assert all(isinstance(v, bool) for v in p.values())
