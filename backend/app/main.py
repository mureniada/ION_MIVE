"""FastAPI transport for the frozen ION MIVE core (M8).

Thin by design: routes validate input, gate on readiness, then delegate to the
existing `core.ask()` via `app.api.service`. No orchestration, retrieval, provider,
MIVE, or renderer logic lives here. Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from .api import service
from .config_check import require_ready
from .container import build_core
from .core.config import Settings
from .core.errors import ConfigurationError, IonError

app = FastAPI(title="ION MIVE Transport", version="0.1.0")

# Built once and reused (the local embedding model loads lazily on first use).
_STATE: dict = {}


def _get_core():
    if "core" not in _STATE:
        settings = Settings.load()
        _STATE["settings"] = settings
        _STATE["core"] = build_core(settings)
    return _STATE["settings"], _STATE["core"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
async def ask(payload: dict | None = None):
    payload = payload or {}
    question = payload.get("question")
    top_k = payload.get("top_k")

    invalid = service.validate_request(question, top_k)
    if invalid:
        return JSONResponse(status_code=invalid[0], content=invalid[1])

    settings, core = _get_core()
    try:
        # The SAME resolved profile Core itself executes under — never a
        # second, independent resolution of `settings.execution_profile_id`
        # (TASK 20 / D20-03).
        require_ready(settings, core.execution_profile)
    except ConfigurationError as exc:
        code, body = service.not_ready_payload(exc)
        return JSONResponse(status_code=code, content=body)

    try:
        result = await run_in_threadpool(service.run_ask, core, question, top_k)
    except IonError as exc:
        code, body = service.core_error_payload(exc)
        return JSONResponse(status_code=code, content=body)

    # Existing renderer result: question, primary_answer, mive_assessment,
    # uncertainty, evidence, operational_metrics, disclaimer.
    return result.rendered


@app.get("/ask/stream")
def ask_stream(question: str, top_k: int | None = None):
    # Gate first, on a fresh config read only — before validation, readiness,
    # core construction, or any provider work (docs/15, ADR-003).
    if not Settings.load().debug:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    invalid = service.validate_request(question, top_k)
    if invalid:
        return JSONResponse(status_code=invalid[0], content=invalid[1])

    settings, core = _get_core()
    try:
        require_ready(settings, core.execution_profile)
    except ConfigurationError as exc:
        code, body = service.not_ready_payload(exc)
        return JSONResponse(status_code=code, content=body)

    def event_stream():
        for event, data in service.sse_events(core, question, top_k):
            yield service.format_sse(event, data)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
