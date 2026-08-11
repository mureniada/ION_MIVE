from __future__ import annotations

from app.core.models import GenerationControlSurface, LiveRunConfig
from app.modules.live1 import (
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    UnsupportedGenerationParameterError,
    validate_generation_parameters,
)
from tests.netguard import guarded
from tests.util import raises


def _config(**overrides) -> LiveRunConfig:
    fields = dict(
        experiment_id="live1-exp-0001",
        run_id="run-0001",
        arm="baseline",
        provider="gemini",
        requested_model="gemini-2.5-pro",
        context_snapshot_ref="context_a_baseline.json",
        context_snapshot_sha256="8fdbf3a0" + "0" * 56,
        prompt_version="ive-system-prompt-v1",
        generation=GenerationControlSurface(),
        tools_policy="NONE",
        evaluation_profile="LIVE1-HUMAN-BLIND-v1",
        rubric_version="live1-semantic-rubric-v0.1",
    )
    fields.update(overrides)
    return LiveRunConfig(**fields)


@guarded
def test_live_run_config_is_frozen():
    cfg = _config()
    try:
        cfg.requested_model = "different"  # type: ignore[misc]
        assert False, "LiveRunConfig must be immutable"
    except Exception as exc:
        assert type(exc).__name__ in {"FrozenInstanceError", "AttributeError"}


@guarded
def test_requested_model_and_reported_model_are_distinct():
    cfg = _config(requested_model="gemini-2.5-pro")
    assert cfg.requested_model == "gemini-2.5-pro"
    assert cfg.reported_model is None  # never auto-set equal to requested_model


@guarded
def test_reported_model_can_honestly_be_unknown():
    cfg = _config(reported_model=None)
    d = cfg.to_dict()
    assert d["reported_model"] is None
    # And it can later be filled in with an actual provider-reported value,
    # as a *distinct* field, without ever assuming it equals requested_model.
    cfg2 = _config(requested_model="gemini-2.5-pro", reported_model="gemini-2.5-pro-002")
    assert cfg2.requested_model != cfg2.reported_model


@guarded
def test_generation_control_surface_common_fields_round_trip():
    surface = GenerationControlSurface(temperature=0.0, top_p=1.0, max_output_tokens=2048)
    d = surface.to_dict()
    assert d == {
        "temperature": 0.0, "top_p": 1.0, "max_output_tokens": 2048, "provider_specific": {},
    }


@guarded
def test_gemini_allows_seed_and_top_k():
    surface = GenerationControlSurface(provider_specific={"seed": 42, "top_k": 40})
    validate_generation_parameters(PROVIDER_GEMINI, surface)  # must not raise


@guarded
def test_openai_unsupported_parameter_is_rejected_not_silently_dropped():
    surface = GenerationControlSurface(provider_specific={"nonexistent_param": 1})
    with raises(UnsupportedGenerationParameterError):
        validate_generation_parameters(PROVIDER_OPENAI, surface)


@guarded
def test_openai_seed_is_rejected_as_structurally_unsupported():
    """OpenAI's Responses API does not expose `seed` at all -- this must be
    rejected explicitly, not silently accepted or silently ignored."""
    surface = GenerationControlSurface(provider_specific={"seed": 42})
    with raises(UnsupportedGenerationParameterError):
        validate_generation_parameters(PROVIDER_OPENAI, surface)


@guarded
def test_openai_allows_its_own_supported_provider_specific_params():
    surface = GenerationControlSurface(provider_specific={"tool_choice": "none", "truncation": "auto"})
    validate_generation_parameters(PROVIDER_OPENAI, surface)  # must not raise
