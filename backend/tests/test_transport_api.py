"""FastAPI wiring tests via TestClient. Skipped where FastAPI/httpx are absent
(the thin sandbox); they run in the built Docker image. No live provider calls:
these only hit /health and the pre-core validation path.
"""

from __future__ import annotations

import importlib.util
import unittest


def _client():
    if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx") is None:
        raise unittest.SkipTest("fastapi/httpx not installed (present in the Docker image)")
    from fastapi.testclient import TestClient

    import app.main as main
    return TestClient(main.app)


def test_health_returns_ok():
    client = _client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ask_rejects_empty_question():
    client = _client()
    resp = client.post("/ask", json={"question": "   "})
    assert resp.status_code == 400
    assert resp.json()["error_stage"] == "invalid_request"
