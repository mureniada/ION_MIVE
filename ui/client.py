"""Thin HTTP client for the ION/MIVE FastAPI transport.

The UI never calls providers, retrieval, MIVE, or the renderer directly — it only
speaks to the backend over HTTP (GET /health, POST /ask, GET /ask/stream). SSE
parsing here mirrors the backend's `service.format_sse` frame format.
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Iterator, Optional, Tuple

import requests


def backend_url() -> str:
    return os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")


def health(base: Optional[str] = None) -> dict:
    base = base or backend_url()
    resp = requests.get(f"{base}/health", timeout=5)
    resp.raise_for_status()
    return resp.json()


def ask(question: str, top_k: Optional[int] = None, base: Optional[str] = None) -> Tuple[int, dict]:
    """POST /ask — returns (status_code, body). Non-2xx bodies are error payloads."""
    base = base or backend_url()
    payload: dict = {"question": question}
    if top_k:
        payload["top_k"] = top_k
    resp = requests.post(f"{base}/ask", json=payload, timeout=300)
    try:
        body = resp.json()
    except ValueError:
        body = {"status": "error", "error_stage": "internal", "message": resp.text}
    return resp.status_code, body


def parse_sse_stream(lines: Iterable) -> Iterator[Tuple[str, Optional[dict]]]:
    """Parse SSE frames into (event, data) tuples. `data` is JSON-decoded."""
    event: Optional[str] = None
    data_lines: list[str] = []

    def flush() -> Optional[Tuple[str, Optional[dict]]]:
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


def stream_ask(question: str, top_k: Optional[int] = None,
               base: Optional[str] = None) -> Iterator[Tuple[str, Optional[dict]]]:
    """GET /ask/stream — yields (event, data) as the pipeline progresses."""
    base = base or backend_url()
    params: dict = {"question": question}
    if top_k:
        params["top_k"] = top_k
    with requests.get(f"{base}/ask/stream", params=params, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        yield from parse_sse_stream(resp.iter_lines(decode_unicode=True))
