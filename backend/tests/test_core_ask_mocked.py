"""TASK 20 policy reconciliation: live policy is STANDARD_GEMINI/SINGLE.

Several tests below drive a real `Core()` (real `CoreAdapter` included) over
document id "d1", which is a KNOWN, PRE-EXISTING, Task-20-unrelated fixture
condition in this environment (a canonical evidence/provenance gate rejects
"d1" for reasons unrelated to engine count — the same condition affects
`test_transport_service.py` and `test_sse_roundtrip.py` identically, and
fails at the governance stage, strictly before any engine executes). That
fixture is left untouched here: this reconciliation makes each test's LOGIC
correct for SINGLE without "fixing" the pre-existing provenance failure
cluster.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ProviderError
from app.core.orchestrator import Core
from app.modules.context_pack import ContextPackBuilder
from app.modules.execution_profile import STANDARD_GEMINI
from app.modules.gemini_ive import GeminiIVE
from app.modules.mive import MIVEComparator
from app.modules.model_gateway import ModelGateway
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


def _build_core(gemini_backend, top_k=3):
    embedder = HashingEmbedder(dimension=512)
    retrieval = InMemoryRetrieval(embedder)
    retrieval.index(DOCS)
    settings = Settings.load(
        {"GEMINI_MODEL": "gemini-3.1-flash-lite", "DEFAULT_TOP_K": str(top_k)}
    )
    gemini = GeminiIVE(gemini_backend, model="gemini-3.1-flash-lite")
    return Core(
        retrieval=retrieval,
        context_pack_builder=ContextPackBuilder(char_budget=settings.context_char_budget),
        model_gateway=ModelGateway({gemini.engine_id: gemini}),
        mive=MIVEComparator(),
        renderer=DeterministicRenderer(),
        pricing=PricingTable(),
        clock=DummyClock(),
        settings=settings,
        execution_profile=STANDARD_GEMINI,
    )


def test_full_pipeline_success_with_mocked_provider():
    gem = FakeBackend(_IVE_JSON, input_tokens=1200, output_tokens=250)
    core = _build_core(gem)

    result = core.ask("is money credit or debt?", top_k=3)

    assert result.status == "success"
    assert len(result.ive_reports) == 1
    for r in result.ive_reports:
        validate_ive_report(r)

    assert "is money credit or debt?" in gem.last_prompt

    # telemetry: usage + cost captured, the one model is priced
    providers = result.metrics["providers"]
    assert len(providers) == 1
    assert all(p["estimated_cost"] is not None for p in providers)
    assert result.metrics["total_estimated_cost"] is not None
    assert result.metrics["total_estimated_cost"] > 0
    assert result.metrics["retrieved_chunks"] == 3

    # comparison is NOT APPLICABLE under SINGLE — never a fabricated result
    assert result.mive_result is None

    assert "primary_answer" in result.rendered


def test_progress_events_are_emitted_in_order():
    core = _build_core(FakeBackend(_IVE_JSON))
    seen = []
    core.ask("money?", top_k=2, progress=lambda stage, status: seen.append((stage, status)))
    stages = [s for s, _ in seen]
    assert stages.index("retrieval") < stages.index("gemini")
    assert "openai" not in stages
    assert "mive" not in stages
    assert ("answer", "ready") in seen


def test_the_sole_provider_failure_is_not_a_success():
    """TASK 20 policy reconciliation: STANDARD_GEMINI/SINGLE has one
    configured engine. Its failure fails the turn outright — there is no
    second engine to fall back to (D20-00/§31: configured SINGLE is not a
    fallback, and a failed sole attempt is never silently reclassified)."""
    gem = FakeBackend("", error=RuntimeError("gemini 503"))
    core = _build_core(gem)
    with raises(ProviderError):
        core.ask("is money credit?", top_k=3)


def test_empty_question_rejected_before_calls():
    core = _build_core(FakeBackend(_IVE_JSON))
    from app.core.errors import IonError
    with raises(IonError):
        core.ask("   ", top_k=3)
