from __future__ import annotations

from app.core.models import ContextDocument, ContextPack, GenerationControlSurface, LiveRunConfig
from app.modules.live1 import (
    LiveOpenAIPolicyError,
    UnsupportedGenerationParameterError,
    build_openai_request_kwargs,
    run_live_openai,
)
from app.modules.openai_ive.backend import OpenAIBackend
from tests.netguard import guarded
from tests.util import raises


class _FakeResponse:
    """Mimics the subset of openai.types.responses.response.Response that
    OpenAIBackend.generate() reads. No SDK import, no network."""

    def __init__(self, *, output_text: str, model: str | None, input_tokens=1000, output_tokens=300):
        self.output_text = output_text
        self.model = model

        class _Usage:
            pass

        u = _Usage()
        u.input_tokens = input_tokens
        u.output_tokens = output_tokens
        self.usage = u


class _FakeResponses:
    """Records the exact kwargs OpenAIBackend.generate() forwards to
    client.responses.create(), and returns a canned _FakeResponse."""

    def __init__(self, *, echoed_model: str | None):
        self.calls: list[dict] = []
        self._echoed_model = echoed_model

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = (
            '{"abstract": "a", "highlights": [], "claims": [], "concepts": [], '
            '"relations": [], "uncertainty": [], "confidence": 0.5}'
        )
        model = self._echoed_model if self._echoed_model is not None else kwargs.get("model")
        return _FakeResponse(output_text=text, model=model)


class _FakeClient:
    def __init__(self, *, echoed_model: str | None = None):
        self.responses = _FakeResponses(echoed_model=echoed_model)


def _fake_backend(*, settings_model: str, echoed_model: str | None = None) -> tuple[OpenAIBackend, _FakeClient]:
    """A real OpenAIBackend, constructed as container.py would (with a
    settings-sourced model), but with its lazily-created client pre-set to a
    recorder double -- so `_ensure()` never imports the real `openai` SDK."""
    backend = OpenAIBackend(settings_model)
    client = _FakeClient(echoed_model=echoed_model)
    backend._client = client
    return backend, client


def _pack() -> ContextPack:
    return ContextPack(
        context_pack_id="cp_live1_test",
        question="is money credit or debt?",
        documents=[
            ContextDocument(
                document_id="d0", title="Broken Money", content="money is credit and debt",
                source="broken_money", page=None, chunk_id="broken_money::pall::c0",
            ),
        ],
    )


def _config(**overrides) -> LiveRunConfig:
    fields = dict(
        experiment_id="live1-exp-0001",
        run_id="L-B1",
        arm="baseline",
        provider="openai",
        requested_model="gpt-5.6-terra",
        context_snapshot_ref="context_a_baseline.json",
        context_snapshot_sha256="8fdbf3a0" + "0" * 56,
        prompt_version="ive-system-prompt-v1",
        generation=GenerationControlSurface(
            max_output_tokens=2000,
            provider_specific={"reasoning": {"mode": "standard", "effort": "medium"}},
        ),
        tools_policy="NONE",
        evaluation_profile="LIVE1-HUMAN-BLIND-v1",
        rubric_version="live1-semantic-rubric-v0.1",
        max_output_tokens=2000,
    )
    fields.update(overrides)
    return LiveRunConfig(**fields)


# 1. requested_model furnishes the LIVE-1 request model
@guarded
def test_requested_model_furnishes_the_request_model():
    kwargs = build_openai_request_kwargs(_config())
    assert kwargs["model"] == "gpt-5.6-terra"


# 2. environment/settings model cannot silently replace requested_model
@guarded
def test_settings_model_cannot_silently_replace_requested_model():
    backend, client = _fake_backend(settings_model="settings-model-should-be-ignored")
    result = run_live_openai(_config(requested_model="gpt-5.6-terra"), _pack(), backend)
    assert client.responses.calls[0]["model"] == "gpt-5.6-terra"
    assert result.request_kwargs["model"] == "gpt-5.6-terra"


# 3. reasoning.mode reaches request construction
@guarded
def test_reasoning_mode_reaches_request_construction():
    backend, client = _fake_backend(settings_model="irrelevant")
    run_live_openai(_config(), _pack(), backend)
    assert client.responses.calls[0]["reasoning"]["mode"] == "standard"


# 4. reasoning.effort reaches request construction
@guarded
def test_reasoning_effort_reaches_request_construction():
    backend, client = _fake_backend(settings_model="irrelevant")
    run_live_openai(_config(), _pack(), backend)
    assert client.responses.calls[0]["reasoning"]["effort"] == "medium"


# 5. max_output_tokens reaches request construction
@guarded
def test_max_output_tokens_reaches_request_construction():
    backend, client = _fake_backend(settings_model="irrelevant")
    run_live_openai(_config(), _pack(), backend)
    assert client.responses.calls[0]["max_output_tokens"] == 2000


# 6. tools_policy NONE produces a no-tools request
@guarded
def test_tools_policy_none_produces_no_tools_key():
    backend, client = _fake_backend(settings_model="irrelevant")
    run_live_openai(_config(tools_policy="NONE"), _pack(), backend)
    assert "tools" not in client.responses.calls[0]


# 7. unsupported/non-NONE LIVE-1 tool policy is rejected before any call
@guarded
def test_unsupported_tools_policy_is_rejected_before_any_call():
    backend, client = _fake_backend(settings_model="irrelevant")
    with raises(LiveOpenAIPolicyError):
        run_live_openai(_config(tools_policy="WEB_SEARCH"), _pack(), backend)
    assert client.responses.calls == []


# 8. unsupported generation parameters remain rejected, not silently dropped
@guarded
def test_unsupported_generation_parameter_remains_rejected():
    backend, client = _fake_backend(settings_model="irrelevant")
    bad = _config(generation=GenerationControlSurface(provider_specific={"nonexistent_param": 1}))
    with raises(UnsupportedGenerationParameterError):
        run_live_openai(bad, _pack(), backend)
    assert client.responses.calls == []


# 9. requested_model and reported_model remain distinct -- no auto-copy
@guarded
def test_reported_model_is_independently_plumbed_not_copied():
    backend, client = _fake_backend(
        settings_model="irrelevant", echoed_model="gpt-5.6-terra-2026-01-01"
    )
    result = run_live_openai(_config(requested_model="gpt-5.6-terra"), _pack(), backend)
    assert result.reported_model == "gpt-5.6-terra-2026-01-01"
    assert result.report.model == "gpt-5.6-terra"
    assert result.reported_model != result.report.model


# 10. none of the above requires or performs a provider call
@guarded
def test_no_test_above_requires_a_real_provider_call():
    """Every test in this file injects backend._client directly, so
    OpenAIBackend._ensure() never imports the real `openai` package. Proven
    here by confirming _ensure() is a no-op once _client is pre-set."""
    backend, client = _fake_backend(settings_model="irrelevant")
    assert backend._ensure() is client
