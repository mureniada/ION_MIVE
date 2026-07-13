"""Transport-layer tests that need no web framework and no live provider calls."""

from __future__ import annotations

import json
import os

from app.api import service
from app.core.config import Settings
from app.core.errors import ProviderError
from app.core.orchestrator import Core
from app.modules.context_pack import ContextPackBuilder
from app.modules.gemini_ive import GeminiIVE
from app.modules.mive import MIVEComparator
from app.modules.openai_ive import OpenAIIVE
from app.modules.renderer import DeterministicRenderer
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.memory_index import InMemoryRetrieval
from app.modules.telemetry import PricingTable
from tests.fakes import DummyClock, FakeBackend, make_ive_json
from tests.util import raises

_DOCS = [
    {"document_id": "d1", "source_id": "broken_money", "title": "Credit",
     "content": "money is fundamentally credit and debt between people"},
]
_IVE_JSON = make_ive_json(
    claims=[{"claim_id": "c1", "statement": "money is credit and debt",
             "evidence_document_ids": ["d1"], "confidence": 0.8}],
    evidence_mapping={"c1": ["d1"]},
)


def _core(gemini_backend=None, openai_backend=None):
    retrieval = InMemoryRetrieval(HashingEmbedder(256))
    retrieval.index(_DOCS)
    settings = Settings.load({"OPENAI_MODEL": "gpt-5.4-mini",
                              "GEMINI_MODEL": "gemini-3.1-flash-lite"})
    return Core(
        retrieval=retrieval,
        context_pack_builder=ContextPackBuilder(),
        gemini_ive=GeminiIVE(gemini_backend or FakeBackend(_IVE_JSON), model="gemini-3.1-flash-lite"),
        openai_ive=OpenAIIVE(openai_backend or FakeBackend(_IVE_JSON), model="gpt-5.4-mini"),
        mive=MIVEComparator(),
        renderer=DeterministicRenderer(),
        pricing=PricingTable(),
        clock=DummyClock(),
        settings=settings,
    )


class _SpyCore:
    def __init__(self):
        self.calls = 0

    def ask(self, question, top_k=None, progress=None):
        self.calls += 1

        class _R:
            rendered = {"question": question, "primary_answer": "x",
                        "mive_assessment": {}, "uncertainty": {}, "evidence": [],
                        "operational_metrics": {}, "disclaimer": "d"}
        return _R()


# 2. reject empty question --------------------------------------------------- #
def test_validate_request_rejects_empty_question():
    for bad in ("", "   ", None, 5):
        res = service.validate_request(bad, None)
        assert res is not None and res[0] == 400
        assert res[1]["error_stage"] == "invalid_request"


def test_validate_request_rejects_bad_top_k():
    assert service.validate_request("q", 0)[0] == 400
    assert service.validate_request("q", -1)[0] == 400
    assert service.validate_request("q", "3")[0] == 400
    assert service.validate_request("q", True)[0] == 400
    assert service.validate_request("q", 3) is None
    assert service.validate_request("q", None) is None


# 3. core called exactly once ------------------------------------------------ #
def test_run_ask_calls_core_exactly_once():
    spy = _SpyCore()
    result = service.run_ask(spy, "What is money?")
    assert spy.calls == 1
    assert result.rendered["question"] == "What is money?"


# 4. success preserves all required top-level fields ------------------------- #
def test_success_preserves_required_result_fields():
    result = service.run_ask(_core(), "is money credit?")
    for key in ("question", "primary_answer", "mive_assessment", "uncertainty",
                "evidence", "operational_metrics", "disclaimer"):
        assert key in result.rendered


# 5. provider failure is not converted into success -------------------------- #
def test_provider_failure_is_not_success():
    core = _core(openai_backend=FakeBackend("", error=RuntimeError("openai 503")))
    with raises(ProviderError):
        service.run_ask(core, "q")
    exc = ProviderError("openai call failed", stage="openai")
    code, body = service.core_error_payload(exc)
    assert code == 502 and body["status"] == "error" and body["error_stage"] == "openai"


# 6. SSE preserves canonical progress order ---------------------------------- #
def test_sse_preserves_progress_order_and_ends_with_result():
    events = list(service.sse_events(_core(), "is money credit?"))
    stages = [d["stage"] for name, d in events if name == "progress"]
    assert stages.index("retrieval") < stages.index("gemini")
    assert stages.index("gemini") < stages.index("openai")
    assert stages.index("openai") < stages.index("mive")
    assert events[-1][0] == "result"
    assert "primary_answer" in events[-1][1]


# 7. SSE terminates with an explicit error event on failure ------------------ #
def test_sse_terminates_with_error_event_on_provider_failure():
    core = _core(openai_backend=FakeBackend("", error=RuntimeError("openai down")))
    events = list(service.sse_events(core, "q"))
    assert events[-1][0] == "error"
    assert events[-1][1]["error_stage"] == "openai"
    assert not any(name == "result" for name, _ in events)


# 8. secret values are absent from transport output -------------------------- #
def test_secrets_absent_from_outputs():
    os.environ["OPENAI_API_KEY"] = "SUPER_SECRET_VALUE_123"
    try:
        result = service.run_ask(_core(), "is money credit?")
        blob = json.dumps(result.rendered)
        assert "SUPER_SECRET_VALUE_123" not in blob
        events = list(service.sse_events(_core(), "is money credit?"))
        assert "SUPER_SECRET_VALUE_123" not in json.dumps(events)
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_format_sse_frame_shape():
    frame = service.format_sse("progress", {"stage": "retrieval", "status": "done"})
    assert frame.startswith("event: progress\ndata: ")
    assert frame.endswith("\n\n")
