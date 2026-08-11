"""Real OpenAI backend. Lazy-imports the OpenAI SDK. Never imported by tests.

Uses the Responses API with strict structured outputs via `text.format`
(JSON mode is legacy). Re-verify the SDK surface at live-prep (docs/17).
"""

from __future__ import annotations

from ..ive_common import GenerationResult


class OpenAIBackend:
    def __init__(self, model: str, *, api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key
        self._client = None

    def _ensure(self):
        if self._client is None:
            from openai import OpenAI  # lazy

            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def generate(
        self, *, system: str, user: str, schema: dict,
        model: str | None = None,
        reasoning: dict | None = None,
        max_output_tokens: int | None = None,
        tools: list | None = None,
    ) -> GenerationResult:
        """The four optional keyword parameters are additive: omitting all of
        them reproduces exactly today's call (same three keys). A caller that
        supplies `model` overrides the constructor-time model rather than
        falling back to it -- this is how the LIVE-1 bridge (modules/live1/
        openai_execution.py) guarantees a frozen requested_model is actually
        used instead of silently defaulting to settings.openai_model."""
        client = self._ensure()
        kwargs: dict = {
            "model": model if model is not None else self._model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "ive_report",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        if reasoning is not None:
            kwargs["reasoning"] = reasoning
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = max_output_tokens
        if tools is not None:
            kwargs["tools"] = tools
        resp = client.responses.create(**kwargs)
        text = getattr(resp, "output_text", "") or ""
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "input_tokens", None) if usage else None
        out_tok = getattr(usage, "output_tokens", None) if usage else None
        return GenerationResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            usage_is_estimated=usage is None,
            reported_model=getattr(resp, "model", None),
        )
