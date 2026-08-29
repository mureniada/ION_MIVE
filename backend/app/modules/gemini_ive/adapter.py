"""Gemini IVE adapter (IVEPort).

Provider-agnostic normalization lives in `ive_common`. The adapter only knows its
identity and a `backend` object exposing `.generate(system, user, schema)`.
Tests inject a fake backend; the real one is `backend.GeminiBackend` (lazy SDK).

Receives ONLY the already-governed `ModelContextAssembly` for this turn (TASK
19.3) — never the upstream `ContextPack`, and never another engine's output.
It imports no governance, admission, retrieval, Core Adapter, Turn Record or
Response Evidence type: the input it is given here is already authorized
before it ever reaches this adapter.
"""

from __future__ import annotations

import time

from ...core.errors import NormalizationError, ProviderError
from ...core.models import IVEReport, Usage
from .. import ive_common as ic

# `ModelContextAssembly` is named only as a quoted forward reference below,
# with NO import anywhere in this module: this adapter never inspects the
# payload beyond handing it to `ive_common`, so it stays closed against the
# Product package that defines the type.


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

    def run(self, model_input: "ModelContextAssembly") -> IVEReport:
        prompt = ic.build_model_input_prompt(model_input)
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
                question=model_input.question,
                raw_text=result.text,
                usage=usage,
            )
        except NormalizationError as exc:
            raise ProviderError(
                f"gemini produced invalid output: {exc}", stage="gemini"
            ) from exc
