"""LIVE-1 OpenAI request-construction bridge (v0.1).

Maps a frozen LiveRunConfig onto the real OpenAIBackend.generate() call, so
that requested_model / reasoning.mode / reasoning.effort / max_output_tokens /
tools_policy are actually consumed by the request -- not merely recorded on
the config object. Reuses the existing prompt/schema/normalization building
blocks (ive_common) and the existing OpenAIBackend provider implementation;
does not reimplement the Responses API call.

NOT wired into container.py/Core.ask(). No provider call happens by
importing or unit-testing this module -- callers supply an already-
constructed backend (production OpenAIBackend or a test double).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ...core.errors import NormalizationError, ProviderError
from ...core.models import ContextPack, IVEReport, LiveRunConfig, Usage
from .. import ive_common as ic
from .generation_control import PROVIDER_OPENAI, validate_generation_parameters

TOOLS_POLICY_NONE = "NONE"


class LiveOpenAIPolicyError(Exception):
    """A LiveRunConfig requests something the LIVE-1 OpenAI path does not
    support (a provider mismatch or a non-NONE tools policy)."""


@dataclass(frozen=True)
class LiveOpenAIResult:
    report: IVEReport
    reported_model: str | None
    request_kwargs: dict[str, Any]


def build_openai_request_kwargs(config: LiveRunConfig) -> dict[str, Any]:
    """Pure mapping: LiveRunConfig -> the kwargs OpenAIBackend.generate()
    will forward to the OpenAI Responses API's request constructor. Raises
    before any call is made."""
    if config.provider != PROVIDER_OPENAI:
        raise LiveOpenAIPolicyError(f"not an OpenAI run config: provider={config.provider!r}")
    validate_generation_parameters(PROVIDER_OPENAI, config.generation)
    if config.tools_policy != TOOLS_POLICY_NONE:
        raise LiveOpenAIPolicyError(
            f"unsupported LIVE-1 tools_policy {config.tools_policy!r}; "
            f"only {TOOLS_POLICY_NONE!r} is implemented"
        )
    kwargs: dict[str, Any] = {"model": config.requested_model}
    reasoning = config.generation.provider_specific.get("reasoning")
    if reasoning is not None:
        kwargs["reasoning"] = dict(reasoning)
    if config.max_output_tokens is not None:
        kwargs["max_output_tokens"] = config.max_output_tokens
    # No "tools" key is ever added here: TOOLS_POLICY_NONE means structurally
    # absent, not conditionally omitted.
    return kwargs


def run_live_openai(config: LiveRunConfig, context_pack: ContextPack, backend: Any) -> LiveOpenAIResult:
    """Executes exactly one LIVE-1 OpenAI call through the real OpenAIBackend
    (or a test double with the same `.generate()` shape), with every frozen
    generation control mechanically enforced. Raises before backend.generate()
    is called if the configuration cannot be honored."""
    request_kwargs = build_openai_request_kwargs(config)
    prompt = ic.build_user_prompt(context_pack)
    t0 = time.monotonic()
    try:
        result: ic.GenerationResult = backend.generate(
            system=ic.IVE_SYSTEM_PROMPT, user=prompt, schema=ic.IVE_RESPONSE_SCHEMA,
            **request_kwargs,
        )
    except Exception as exc:
        raise ProviderError(f"openai call failed: {exc}", stage="openai") from exc
    latency_ms = (time.monotonic() - t0) * 1000.0

    usage = Usage(
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
        usage_is_estimated=result.usage_is_estimated,
    )
    try:
        raw = ic.parse_json(result.text)
        report = ic.normalize(
            raw,
            engine_id="openai",
            provider=PROVIDER_OPENAI,
            model=config.requested_model,
            question=context_pack.question,
            raw_text=result.text,
            usage=usage,
        )
    except NormalizationError as exc:
        raise ProviderError(f"openai produced invalid output: {exc}", stage="openai") from exc

    return LiveOpenAIResult(
        report=report,
        reported_model=result.reported_model,
        request_kwargs=request_kwargs,
    )
