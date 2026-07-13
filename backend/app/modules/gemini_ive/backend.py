"""Real Gemini backend. Lazy-imports google-genai. Never imported by tests.

SDK surface must be re-verified against official docs at live-prep (research-first,
docs/17). Structured output uses response_json_schema; usage from usage_metadata.
"""

from __future__ import annotations

from ..ive_common import GenerationResult


class GeminiBackend:
    def __init__(self, model: str, *, api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key
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

        resp = client.models.generate_content(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
        text = getattr(resp, "text", "") or ""
        um = getattr(resp, "usage_metadata", None)
        in_tok = getattr(um, "prompt_token_count", None) if um else None
        out_tok = getattr(um, "candidates_token_count", None) if um else None
        return GenerationResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            usage_is_estimated=um is None,
        )
