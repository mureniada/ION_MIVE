"""E2 (VOE-LATENCY): observational Gemini usage telemetry.

No real provider call: the SDK client is replaced by a fake, and the request
the backend sends is asserted unchanged. The telemetry line carries counts and
latency only, never prompt, evidence or response content.
"""

from __future__ import annotations

import sys
import types

from app.container import _build_engines, build_voe_composer
from app.core.config import Settings
from app.modules.execution_profile import STANDARD_GEMINI
from app.modules.gemini_ive import backend as gb
from tests.voe_pack import COMMITTED_VOE_PACK_DIR

FULL_USAGE = types.SimpleNamespace(
    prompt_token_count=814,
    candidates_token_count=310,
    thoughts_token_count=2150,
    cached_content_token_count=0,
    tool_use_prompt_token_count=None,
    total_token_count=3274,
)


def test_line_reports_every_usage_field():
    line = gb.usage_telemetry_line("ive", "gemini-2.5-pro", FULL_USAGE, 22275.04)
    assert line == (
        "[gemini-usage] call=ive model=gemini-2.5-pro latency_ms=22275.0 "
        "prompt_tokens=814 candidates_tokens=310 thoughts_tokens=2150 "
        "cached_tokens=0 tool_use_prompt_tokens=na total_tokens=3274"
    )


def test_absent_fields_and_absent_metadata_are_na():
    partial = types.SimpleNamespace(prompt_token_count=5, candidates_token_count=7)
    line = gb.usage_telemetry_line("composer", "m", partial, 1.0)
    assert "prompt_tokens=5 candidates_tokens=7 thoughts_tokens=na cached_tokens=na" in line
    assert line.endswith("tool_use_prompt_tokens=na total_tokens=na")
    none_line = gb.usage_telemetry_line("composer", "m", None, 1.0)
    assert none_line.count("=na") == 6


class _FakeModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _backend_with_fake_client(response, label="ive"):
    backend = gb.GeminiBackend("gemini-2.5-pro", telemetry_label=label)
    backend._client = types.SimpleNamespace(models=_FakeModels(response))
    return backend


def _ensure_sdk_types(monkeypatch):
    """Use the real google-genai types when installed; otherwise a stand-in
    GenerateContentConfig, so the test never needs the SDK or a network."""
    try:
        from google.genai import types as _real  # noqa: F401
    except ImportError:
        fake_types = types.ModuleType("google.genai.types")
        fake_types.GenerateContentConfig = lambda **kw: types.SimpleNamespace(**kw)
        fake_genai = types.ModuleType("google.genai")
        fake_genai.types = fake_types
        fake_google = sys.modules.get("google") or types.ModuleType("google")
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setattr(fake_google, "genai", fake_genai, raising=False)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)


def test_generate_logs_once_and_leaves_request_and_result_unchanged(monkeypatch, capsys):
    _ensure_sdk_types(monkeypatch)
    response = types.SimpleNamespace(text='{"answer": "secret evidence"}', usage_metadata=FULL_USAGE)
    backend = _backend_with_fake_client(response)
    schema = {"type": "object"}

    result = backend.generate(system="SYSTEM PROMPT TEXT", user="USER PROMPT TEXT", schema=schema)

    # Result contract unchanged: input/output stay prompt/candidates counts.
    assert result.text == '{"answer": "secret evidence"}'
    assert (result.input_tokens, result.output_tokens) == (814, 310)
    assert result.usage_is_estimated is False

    # Request unchanged: same model, contents and config fields as before E2.
    (call,) = backend._client.models.calls
    assert call["model"] == "gemini-2.5-pro"
    assert call["contents"] == "USER PROMPT TEXT"
    config = call["config"]
    assert config.system_instruction == "SYSTEM PROMPT TEXT"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema
    assert getattr(config, "thinking_config", None) is None
    assert getattr(config, "max_output_tokens", None) is None

    err = capsys.readouterr().err
    lines = [l for l in err.splitlines() if l.startswith("[gemini-usage]")]
    assert len(lines) == 1
    assert lines[0].startswith("[gemini-usage] call=ive model=gemini-2.5-pro latency_ms=")
    assert "thoughts_tokens=2150 cached_tokens=0" in lines[0]
    for content in ("SYSTEM PROMPT TEXT", "USER PROMPT TEXT", "secret evidence"):
        assert content not in err


def test_missing_usage_metadata_keeps_estimated_flag(monkeypatch, capsys):
    _ensure_sdk_types(monkeypatch)
    backend = _backend_with_fake_client(types.SimpleNamespace(text="{}", usage_metadata=None))
    result = backend.generate(system="s", user="u", schema={})
    assert (result.input_tokens, result.output_tokens, result.usage_is_estimated) == (None, None, True)
    assert "prompt_tokens=na" in capsys.readouterr().err


def test_telemetry_failure_never_fails_the_call(monkeypatch):
    _ensure_sdk_types(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("telemetry broke")

    monkeypatch.setattr(gb, "usage_telemetry_line", boom)
    backend = _backend_with_fake_client(types.SimpleNamespace(text="{}", usage_metadata=FULL_USAGE))
    assert backend.generate(system="s", user="u", schema={}).input_tokens == 814


def test_container_labels_the_ive_and_composer_backends():
    settings = Settings.load({
        "GEMINI_MODEL": "gemini-2.5-pro",
        "VOE_PROFILE_ENABLED": "true",
        "VOE_PROFILE_BUNDLE_DIR": str(COMMITTED_VOE_PACK_DIR),
    })
    engines = _build_engines(STANDARD_GEMINI, settings)
    composer, _ = build_voe_composer(STANDARD_GEMINI, settings)
    assert engines["gemini"]._backend._telemetry_label == "ive"
    assert composer._backend._telemetry_label == "composer"
    assert gb.GeminiBackend("m")._telemetry_label == "gemini"
