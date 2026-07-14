"""Transport-agnostic helpers for the FastAPI layer (M8).

No web framework is imported here, so this module is fully unit-testable without a
running server. It does NOT orchestrate anything — it calls the existing
`core.ask()` and maps results/errors to transport-shaped payloads. Secrets never
appear in any payload (messages come from IonError.message / controlled text).
"""

from __future__ import annotations

import json
import queue
import threading

from ..core.errors import IonError

# HTTP status per core error stage (transport concern only).
_STAGE_STATUS = {
    "retrieval": 502,
    "context_pack": 500,
    "gemini": 502,
    "openai": 502,
    "normalization": 422,
    "mive": 500,
    "configuration": 500,
}


def validate_request(question, top_k):
    """Return None if valid, else a (status_code, error_body) tuple."""
    if not isinstance(question, str) or not question.strip():
        return (400, {
            "status": "error",
            "error_stage": "invalid_request",
            "message": "'question' must be a non-empty string.",
        })
    if top_k is not None:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            return (400, {
                "status": "error",
                "error_stage": "invalid_request",
                "message": "'top_k' must be an integer >= 1.",
            })
    return None


def not_ready_payload(exc: IonError):
    """Missing/invalid runtime configuration (secrets absent) -> 503 not_ready."""
    return (503, {
        "status": "error",
        "error_stage": "not_ready",
        "message": exc.message,
    })


def core_error_payload(exc: IonError):
    """Map a core-stage failure to (status_code, error_body). Never a success."""
    stage = getattr(exc, "stage", "internal")
    code = _STAGE_STATUS.get(stage, 500)
    return (code, {
        "status": "error",
        "error_stage": stage,
        "message": exc.message,
    })


def run_ask(core, question, top_k=None):
    """Call the intelligence core exactly once. No orchestration lives here."""
    return core.ask(question, top_k=top_k)


def sse_events(core, question, top_k=None):
    """Yield (event_name, data) tuples, preserving the core's progress order.

    `progress` events mirror the core lifecycle exactly (no invented percentages,
    no provider tokens). The stream terminates with exactly one ("result", …) or
    ("error", …) event.
    """
    q: "queue.Queue" = queue.Queue()
    sentinel = object()

    def progress(stage, status):
        q.put(("progress", {"stage": stage, "status": status}))

    def worker():
        try:
            result = core.ask(question, top_k=top_k, progress=progress)
            q.put(("result", result.rendered))
        except IonError as exc:
            q.put(("error", {"status": "error", "error_stage": exc.stage,
                             "message": exc.message}))
        except Exception as exc:  # never swallow; surface as internal
            q.put(("error", {"status": "error", "error_stage": "internal",
                             "message": str(exc)}))
        finally:
            q.put(sentinel)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    while True:
        item = q.get()
        if item is sentinel:
            break
        yield item
    t.join(timeout=2)


def format_sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def parse_sse_stream(lines):
    """Inverse of `format_sse`: parse SSE lines into (event, data) tuples.

    Canonical parser used by the round-trip test; the Streamlit client mirrors it.
    `data` is JSON-decoded (None if empty/undecodable).
    """
    event = None
    data_lines: list[str] = []

    def flush():
        nonlocal event, data_lines
        if event is None and not data_lines:
            return None
        raw = "\n".join(data_lines)
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = None
        out = (event or "message", payload)
        event, data_lines = None, []
        return out

    for raw in lines:
        line = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
        line = (line or "").rstrip("\r\n")
        if line == "":
            frame = flush()
            if frame is not None:
                yield frame
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    frame = flush()
    if frame is not None:
        yield frame
