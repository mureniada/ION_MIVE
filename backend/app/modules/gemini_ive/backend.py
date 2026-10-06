"""Real Gemini backend. Lazy-imports google-genai. Tests never make a real call.

SDK surface must be re-verified against official docs at live-prep (research-first,
docs/17). Structured output uses response_json_schema; usage from usage_metadata.
"""

from __future__ import annotations

import sys
import time

from ..ive_common import GenerationResult

# E2 (VOE-LATENCY): observational usage telemetry, one stderr line per call.
# google-genai 2.28.0 `GenerateContentResponseUsageMetadata` fields; any field
# the SDK leaves absent is logged as "na". Counts and latency only -- never
# prompt, evidence or response content.
_USAGE_FIELDS = (
    ("prompt_tokens", "prompt_token_count"),
    ("candidates_tokens", "candidates_token_count"),
    ("thoughts_tokens", "thoughts_token_count"),
    ("cached_tokens", "cached_content_token_count"),
    ("tool_use_prompt_tokens", "tool_use_prompt_token_count"),
    ("total_tokens", "total_token_count"),
)


def usage_telemetry_line(label: str, model: str, usage_metadata, latency_ms: float) -> str:
    parts = [f"[gemini-usage] call={label} model={model} latency_ms={latency_ms:.1f}"]
    for name, attr in _USAGE_FIELDS:
        value = getattr(usage_metadata, attr, None) if usage_metadata is not None else None
        parts.append(f"{name}={value if isinstance(value, int) else 'na'}")
    return " ".join(parts)


class GeminiBackend:
    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        telemetry_label: str = "gemini",
        thinking_budget: int | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._telemetry_label = telemetry_label
        # E3 (VOE-LATENCY): None sends no thinking config (provider default).
        self._thinking_budget = thinking_budget
        self._client = None

    def _ensure(self):
        if self._client is None:
            from google import genai  # lazy

            # Reads GEMINI_API_KEY / GOOGLE_API_KEY from env if api_key is None.
            self._client = genai.Client(api_key=self._api_key) if self._api_key else genai.Client()
        return self._client

    def generate(self, *, system: str, user: str, schema: dict) -> GenerationResult:
        client = self._ensure()
        from google.genai import types  # lazy

        config_kwargs = dict(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        if self._thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=self._thinking_budget
            )
        started = time.monotonic()
        resp = client.models.generate_content(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        latency_ms = (time.monotonic() - started) * 1000.0
        text = getattr(resp, "text", "") or ""
        um = getattr(resp, "usage_metadata", None)
        try:
            print(
                usage_telemetry_line(self._telemetry_label, self._model, um, latency_ms),
                file=sys.stderr,
                flush=True,
            )
        except Exception:  # telemetry must never fail a provider call
            pass
        in_tok = getattr(um, "prompt_token_count", None) if um else None
        out_tok = getattr(um, "candidates_token_count", None) if um else None
        return GenerationResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            usage_is_estimated=um is None,
        )
