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
from .container import build_core, build_session_controller
from .core.config import Settings
from .core.errors import ConfigurationError, IonError
from .modules.session import (
    ConcurrentTurnError,
    SessionClarificationOutcome,
    SessionClosedError,
    TurnRecordCaptureError,
    UnknownSessionError,
)

app = FastAPI(title="ION MIVE Transport", version="0.1.0")

# Built once and reused (the local embedding model loads lazily on first use).
_STATE: dict = {}


def _get_core():
    if "core" not in _STATE:
        settings = Settings.load()
        _STATE["settings"] = settings
        _STATE["core"] = build_core(settings)
    return _STATE["settings"], _STATE["core"]


def _get_session_controller():
    # ONE process -> ONE shared Core -> ONE SessionController wrapping that
    # exact same Core instance (E4C composition root). `_get_core()` itself
    # already caches the Core, so this never builds a second one.
    if "session_controller" not in _STATE:
        _, core = _get_core()
        _STATE["session_controller"] = build_session_controller(core)
    return _STATE["session_controller"]


def _session_summary(session) -> dict:
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "status": session.status.value,
        "next_turn_ordinal": session.next_turn_ordinal,
    }


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


# --------------------------------------------------------------------------- #
# Pilot transport (TASK E4C). Additive only: legacy /ask and /ask/stream above
# are untouched, and neither route above is rerouted through SessionController.
# Every pilot route below delegates to the existing SessionController public
# API exactly once; none of them reaches Core.ask() directly.
# --------------------------------------------------------------------------- #
@app.post("/pilot/sessions")
def create_pilot_session():
    controller = _get_session_controller()
    session = controller.create_session()
    return _session_summary(session)


@app.post("/pilot/sessions/{session_id}/turn")
async def run_pilot_turn(session_id: str, payload: dict | None = None):
    payload = payload or {}
    question = payload.get("question")
    top_k = payload.get("top_k")

    invalid = service.validate_request(question, top_k)
    if invalid:
        return JSONResponse(status_code=invalid[0], content=invalid[1])

    settings, core = _get_core()
    try:
        # The SAME readiness gate /ask uses, ahead of the same governed
        # Core.ask() this turn may reach on PROCEED (D20-03).
        require_ready(settings, core.execution_profile)
    except ConfigurationError as exc:
        code, body = service.not_ready_payload(exc)
        return JSONResponse(status_code=code, content=body)

    controller = _get_session_controller()
    try:
        result = await run_in_threadpool(controller.run_turn, session_id, question, top_k)
    except UnknownSessionError as exc:
        return JSONResponse(status_code=404, content={
            "status": "error", "error_stage": "not_found", "message": str(exc),
        })
    except SessionClosedError as exc:
        return JSONResponse(status_code=409, content={
            "status": "error", "error_stage": "session_closed", "message": str(exc),
        })
    except ConcurrentTurnError as exc:
        return JSONResponse(status_code=409, content={
            "status": "error", "error_stage": "concurrent_turn", "message": str(exc),
        })
    except TurnRecordCaptureError as exc:
        return JSONResponse(status_code=500, content={
            "status": "error", "error_stage": "internal", "message": str(exc),
        })
    except IonError as exc:
        code, body = service.core_error_payload(exc)
        return JSONResponse(status_code=code, content=body)

    if isinstance(result, SessionClarificationOutcome):
        return {
            "kind": "clarify",
            "session_id": result.session_id,
            "turn_ordinal": result.turn_ordinal,
            "reason_code": result.reason_code.value,
        }

    # AskResult: same rendered shape /ask returns, tagged so a pilot client
    # can distinguish it from the clarify shape above without guessing.
    return {"kind": "answer", **result.rendered}


@app.post("/pilot/sessions/{session_id}/close")
def close_pilot_session(session_id: str):
    controller = _get_session_controller()
    try:
        session = controller.close_session(session_id)
    except UnknownSessionError as exc:
        return JSONResponse(status_code=404, content={
            "status": "error", "error_stage": "not_found", "message": str(exc),
        })
    except ConcurrentTurnError as exc:
        return JSONResponse(status_code=409, content={
            "status": "error", "error_stage": "concurrent_turn", "message": str(exc),
        })
    return _session_summary(session)
