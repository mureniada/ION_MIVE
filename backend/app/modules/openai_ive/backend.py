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

    def generate(self, *, system: str, user: str, schema: dict) -> GenerationResult:
        client = self._ensure()
        resp = client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ive_report",
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        text = getattr(resp, "output_text", "") or ""
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "input_tokens", None) if usage else None
        out_tok = getattr(usage, "output_tokens", None) if usage else None
        return GenerationResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            usage_is_estimated=usage is None,
        )
