"""Gemini IVE adapter (IVEPort).

Provider-agnostic normalization lives in `ive_common`. The adapter only knows its
identity and a `backend` object exposing `.generate(system, user, schema)`.
Tests inject a fake backend; the real one is `backend.GeminiBackend` (lazy SDK).
"""

from __future__ import annotations

import time

from ...core.errors import NormalizationError, ProviderError
from ...core.models import ContextPack, IVEReport, Usage
from .. import ive_common as ic


class GeminiIVE:
    provider = "gemini"

    def __init__(self, backend, *, model: str, engine_id: str = "gemini") -> None:
        self._backend = backend
        self._model = model
        self._engine_id = engine_id

    # IVEPort surface -------------------------------------------------- #
    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def model(self) -> str:
        return self._model

    def run(self, context_pack: ContextPack) -> IVEReport:
        prompt = ic.build_user_prompt(context_pack)
        t0 = time.monotonic()
        try:
            result: ic.GenerationResult = self._backend.generate(
                system=ic.IVE_SYSTEM_PROMPT, user=prompt, schema=ic.IVE_RESPONSE_SCHEMA
            )
        except Exception as exc:  # SDK/network failure
            raise ProviderError(f"gemini call failed: {exc}", stage="gemini") from exc
        latency_ms = (time.monotonic() - t0) * 1000.0

        usage = Usage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            usage_is_estimated=result.usage_is_estimated,
        )
        try:
            raw = ic.parse_json(result.text)
            return ic.normalize(
                raw,
                engine_id=self._engine_id,
                provider=self.provider,
                model=self._model,
                question=context_pack.question,
                raw_text=result.text,
                usage=usage,
            )
        except NormalizationError as exc:
            raise ProviderError(
                f"gemini produced invalid output: {exc}", stage="gemini"
            ) from exc
