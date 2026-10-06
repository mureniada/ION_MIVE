"""E3 (VOE-LATENCY): composer-only Gemini thinking budget.

No real provider call: the SDK client is replaced by a fake and the request the
backend sends is inspected. Unset keeps the request exactly as before E3; a set
budget reaches the composer call only, never the IVE call.
"""

from __future__ import annotations

import types

import pytest

from app.container import _build_engines, build_voe_composer
from app.core.config import Settings, SettingsError
from app.modules.execution_profile import STANDARD_GEMINI
from app.modules.gemini_ive import backend as gb
from tests.voe_pack import COMMITTED_VOE_PACK_DIR

genai_types = pytest.importorskip("google.genai.types")

BASE_ENV = {
    "GEMINI_MODEL": "gemini-2.5-pro",
    "VOE_PROFILE_ENABLED": "true",
    "VOE_PROFILE_BUNDLE_DIR": str(COMMITTED_VOE_PACK_DIR),
}


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_unset_or_empty_budget_is_none(raw):
    env = dict(BASE_ENV)
    if raw is not None:
        env["VOE_COMPOSER_THINKING_BUDGET"] = raw
    assert Settings.load(env).voe_composer_thinking_budget is None


@pytest.mark.parametrize("raw,expected", [("512", 512), (" 128 ", 128), ("32768", 32768)])
def test_valid_budget_is_parsed(raw, expected):
    env = {**BASE_ENV, "VOE_COMPOSER_THINKING_BUDGET": raw}
    assert Settings.load(env).voe_composer_thinking_budget == expected


@pytest.mark.parametrize("raw", ["abc", "512.0", "0", "-1", "127", "32769"])
def test_malformed_or_out_of_range_budget_fails_loud(raw):
    with pytest.raises(SettingsError, match="VOE_COMPOSER_THINKING_BUDGET"):
        Settings.load({**BASE_ENV, "VOE_COMPOSER_THINKING_BUDGET": raw})


class _FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(text="{}", usage_metadata=None)


def _sent_config(backend):
    backend._client = types.SimpleNamespace(models=_FakeModels())
    backend.generate(system="SYSTEM", user="USER", schema={"type": "object"})
    (call,) = backend._client.models.calls
    return call["config"]


def _pre_e3_config():
    # The exact config construction at 7cec12f, before E3.
    return genai_types.GenerateContentConfig(
        system_instruction="SYSTEM",
        response_mime_type="application/json",
        response_json_schema={"type": "object"},
    )


def test_default_request_is_identical_to_pre_e3():
    sent = _sent_config(gb.GeminiBackend("gemini-2.5-pro"))
    assert sent.model_dump() == _pre_e3_config().model_dump()
    assert sent.thinking_config is None


def test_budget_adds_only_the_thinking_config():
    sent = _sent_config(gb.GeminiBackend("gemini-2.5-pro", thinking_budget=512))
    assert sent.thinking_config.thinking_budget == 512
    assert sent.thinking_config.include_thoughts is None
    assert sent.thinking_config.thinking_level is None
    without = sent.model_dump()
    without["thinking_config"] = None
    assert without == _pre_e3_config().model_dump()


def test_container_unset_leaves_both_backends_at_default():
    settings = Settings.load(BASE_ENV)
    ive = _build_engines(STANDARD_GEMINI, settings)["gemini"]._backend
    composer, _ = build_voe_composer(STANDARD_GEMINI, settings)
    assert ive._thinking_budget is None
    assert composer._backend._thinking_budget is None


def test_container_budget_reaches_the_composer_only():
    settings = Settings.load({**BASE_ENV, "VOE_COMPOSER_THINKING_BUDGET": "512"})
    ive = _build_engines(STANDARD_GEMINI, settings)["gemini"]._backend
    composer, _ = build_voe_composer(STANDARD_GEMINI, settings)
    assert composer._backend._thinking_budget == 512
    assert ive._thinking_budget is None
    assert _sent_config(composer._backend).thinking_config.thinking_budget == 512
    assert _sent_config(ive).model_dump() == _pre_e3_config().model_dump()
