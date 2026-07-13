from __future__ import annotations

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
from app.validation import validate_ive_report
from tests.fakes import DummyClock, FakeBackend, make_ive_json
from tests.util import raises

DOCS = [
    {"document_id": "d1", "source_id": "broken_money", "title": "Credit",
     "content": "money is fundamentally credit and debt between people"},
    {"document_id": "d2", "source_id": "layered_money", "title": "Commodity",
     "content": "commodity money like gold has intrinsic value"},
    {"document_id": "d3", "source_id": "whale", "title": "Whales",
     "content": "the ecological value of whales in the ocean"},
]

_IVE_JSON = make_ive_json(
    claims=[{"claim_id": "c1", "statement": "money is a form of credit and debt",
             "evidence_document_ids": ["d1"], "confidence": 0.8}],
    evidence_mapping={"c1": ["d1"]},
)


def _build_core(gemini_backend, openai_backend, top_k=3):
    embedder = HashingEmbedder(dimension=512)
    retrieval = InMemoryRetrieval(embedder)
    retrieval.index(DOCS)
    settings = Settings.load(
        {"OPENAI_MODEL": "gpt-5.4-mini", "GEMINI_MODEL": "gemini-3.1-flash-lite",
         "DEFAULT_TOP_K": str(top_k)}
    )
    return Core(
        retrieval=retrieval,
        context_pack_builder=ContextPackBuilder(char_budget=settings.context_char_budget),
        gemini_ive=GeminiIVE(gemini_backend, model="gemini-3.1-flash-lite"),
        openai_ive=OpenAIIVE(openai_backend, model="gpt-5.4-mini"),
        mive=MIVEComparator(),
        renderer=DeterministicRenderer(),
        pricing=PricingTable(),
        clock=DummyClock(),
        settings=settings,
    )


def test_full_pipeline_success_with_mocked_providers():
    gem = FakeBackend(_IVE_JSON, input_tokens=1200, output_tokens=250)
    opn = FakeBackend(_IVE_JSON, input_tokens=1100, output_tokens=240)
    core = _build_core(gem, opn)

    result = core.ask("is money credit or debt?", top_k=3)

    assert result.status == "success"
    assert len(result.ive_reports) == 2
    for r in result.ive_reports:
        validate_ive_report(r)

    # both providers received the identical canonical Context Pack
    assert gem.last_prompt == opn.last_prompt
    assert "is money credit or debt?" in gem.last_prompt

    # telemetry: usage + cost captured for both, models are priced
    providers = result.metrics["providers"]
    assert len(providers) == 2
    assert all(p["estimated_cost"] is not None for p in providers)
    assert result.metrics["total_estimated_cost"] is not None
    assert result.metrics["total_estimated_cost"] > 0
    assert result.metrics["retrieved_chunks"] == 3

    assert "primary_answer" in result.rendered


def test_progress_events_are_emitted_in_order():
    core = _build_core(FakeBackend(_IVE_JSON), FakeBackend(_IVE_JSON))
    seen = []
    core.ask("money?", top_k=2, progress=lambda stage, status: seen.append((stage, status)))
    stages = [s for s, _ in seen]
    assert stages.index("retrieval") < stages.index("gemini") < stages.index("mive")
    assert ("answer", "ready") in seen


def test_single_provider_failure_is_not_a_success():
    gem = FakeBackend("", error=RuntimeError("gemini 503"))
    opn = FakeBackend(_IVE_JSON)
    core = _build_core(gem, opn)
    with raises(ProviderError):
        core.ask("is money credit?", top_k=3)


def test_empty_question_rejected_before_calls():
    core = _build_core(FakeBackend(_IVE_JSON), FakeBackend(_IVE_JSON))
    from app.core.errors import IonError
    with raises(IonError):
        core.ask("   ", top_k=3)
