"""FastAPI wiring tests via TestClient. Skipped where FastAPI/httpx are absent
(the thin sandbox); they run in the built Docker image. No live provider calls:
these only hit /health and the pre-core validation path.
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from unittest import mock


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


def test_ask_stream_returns_404_when_debug_false():
    client = _client()
    old = os.environ.pop("DEBUG", None)
    try:
        resp = client.get("/ask/stream", params={"question": "what is money?"})
        assert resp.status_code == 404
    finally:
        if old is not None:
            os.environ["DEBUG"] = old


def test_ask_stream_404_skips_readiness_and_core_init():
    client = _client()
    import app.main as main

    old = os.environ.pop("DEBUG", None)
    try:
        with mock.patch.object(main, "require_ready") as mocked_ready, \
             mock.patch.object(main, "_get_core") as mocked_core:
            resp = client.get("/ask/stream", params={"question": "what is money?"})
            assert resp.status_code == 404
            mocked_ready.assert_not_called()
            mocked_core.assert_not_called()
    finally:
        if old is not None:
            os.environ["DEBUG"] = old


def test_ask_stream_available_when_debug_true():
    client = _client()
    old = os.environ.get("DEBUG")
    os.environ["DEBUG"] = "true"
    try:
        resp = client.get("/ask/stream", params={"question": "   "})
        assert resp.status_code == 400
        assert resp.json()["error_stage"] == "invalid_request"
    finally:
        if old is None:
            os.environ.pop("DEBUG", None)
        else:
            os.environ["DEBUG"] = old


def test_post_ask_returns_complete_rendered_result_for_real_question():
    """I2: proves POST /ask, via the real ASGI route, reaches injected fake
    providers and retrieval exactly once with the exact request values, and
    returns the renderer's output byte-for-byte through HTTP.

    The renderer is substituted with a deterministic sentinel double rather than
    hand-predicting its real numeric output (which depends on non-deterministic
    wall-clock provider latency inside the adapters), so the HTTP-body assertion
    below is exact and risk-free. Retrieval, both fake providers, and MIVE still
    run for real, proving the request is correctly plumbed all the way through.
    """
    client = _client()
    import app.main as main
    from app.core.config import Settings
    from app.core.orchestrator import Core
    from app.modules.context_pack import ContextPackBuilder
    from app.modules.gemini_ive import GeminiIVE
    from app.modules.mive import MIVEComparator
    from app.modules.model_gateway import ModelGateway
    from app.modules.openai_ive import OpenAIIVE
    from app.modules.retrieval.embeddings import HashingEmbedder
    from app.modules.retrieval.memory_index import InMemoryRetrieval
    from app.modules.telemetry import PricingTable
    from tests.fakes import DummyClock, FakeBackend, make_ive_json

    class _RecordingRetrieval:
        def __init__(self, inner):
            self._inner = inner
            self.calls = []

        def retrieve(self, question, top_k):
            self.calls.append((question, top_k))
            return self._inner.retrieve(question, top_k)

    inner_retrieval = InMemoryRetrieval(HashingEmbedder(dimension=64))
    inner_retrieval.index([
        {"document_id": "d1", "source_id": "s1", "title": "Money",
         "content": "money is a medium of exchange"},
    ])
    retrieval = _RecordingRetrieval(inner_retrieval)

    gem_backend = FakeBackend(make_ive_json(), input_tokens=100, output_tokens=50)
    openai_backend = FakeBackend(make_ive_json(), input_tokens=100, output_tokens=50)

    sentinel = {
        "question": "sentinel-question",
        "primary_answer": "SENTINEL_PRIMARY_ANSWER",
        "mive_assessment": {"overall_status": "sentinel_status"},
        "uncertainty": {"shared": [], "per_engine": {}},
        "evidence": [],
        "operational_metrics": {"total_estimated_cost": None},
        "disclaimer": "SENTINEL_DISCLAIMER",
    }
    fake_renderer = mock.Mock()
    fake_renderer.render.return_value = sentinel

    settings = Settings.load({"OPENAI_MODEL": "gpt-test", "GEMINI_MODEL": "gemini-test"})
    gemini = GeminiIVE(gem_backend, model="gemini-test")
    openai = OpenAIIVE(openai_backend, model="gpt-test")
    fake_core = Core(
        retrieval=retrieval,
        context_pack_builder=ContextPackBuilder(char_budget=settings.context_char_budget),
        model_gateway=ModelGateway(
            {gemini.engine_id: gemini, openai.engine_id: openai}
        ),
        mive=MIVEComparator(),
        renderer=fake_renderer,
        pricing=PricingTable(),
        clock=DummyClock(),
        settings=settings,
    )

    with mock.patch.object(main, "_get_core", return_value=(settings, fake_core)), \
         mock.patch.object(main, "require_ready"):
        resp = client.post("/ask", json={"question": "What is money?", "top_k": 5})

    assert resp.status_code == 200
    assert resp.json() == sentinel

    assert gem_backend.calls == 1
    assert openai_backend.calls == 1

    assert retrieval.calls == [("What is money?", 5)]

    fake_renderer.render.assert_called_once()
    assert fake_renderer.render.call_args.kwargs["question"] == "What is money?"
