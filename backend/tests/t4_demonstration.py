"""The T4 demonstration harness — one recorded-fixture run record.

Not a test module (no `test_` prefix), so neither pytest nor `run_tests.py`
collects it. `test_t4_emitter.py` drives it against a temporary store; running it
as a script writes the canonical demonstration record.

**What is real here, and what is recorded.** Both matter, and conflating them is
exactly what B4 exists to prevent.

*Real, produced locally by the repository's own code.* The Context Pack, the
governed `ModelContextAssembly` `Core.ask()` materializes from it (TASK 19.3),
and the assembled prompt — built by `ContextPackBuilder` and
`ive_common.build_model_input_prompt` from real documents — so the workload,
prompt and context identities digest bytes that genuinely exist. The wiring is
real too: a `Core` composed through its public keyword-only constructor with
`ObservingIVE` wrapped around each `IVEPort` and resolved through the real
`ModelGateway`, and `Core.ask()` driving the pipeline.

*Recorded, carried from the run shape in the mandate's appendix B.* The per-call
token counts and latencies, and the total wall clock. The provider backends are
fakes returning those recorded counts; **no live provider call occurs** (D3), and
this demonstration is not orchestrator integration and must never be presented as
it (D7).

**Why the environment is the recorded one.** The contract's `implementation` key
set requires ten distribution versions, and on this host three of them —
sentence-transformers, torch, transformers — are not installed. The contract's
state rules say a distribution whose version cannot be read makes the record
unwritable; it is never recorded as absent or as an empty string. So a
live-environment record is *not writable on this host at all*, which is a finding
in its own right. A recorded fixture records the environment of the run it
describes, and that environment is the one the contract's own `implementation-v1`
vector carries. :func:`host_implementation_gaps` reports the host's missing
distributions rather than papering over the difference.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from app.core.config import Settings
from app.core.orchestrator import Core
from app.modules import ive_common
from app.modules.context_pack import ContextPackBuilder
from app.modules.gemini_ive import GeminiIVE
from app.modules.mive import MIVEComparator
from app.modules.model_gateway import ModelGateway
from app.modules.openai_ive import OpenAIIVE
from app.modules.renderer import DeterministicRenderer
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.memory_index import InMemoryRetrieval
from app.modules.telemetry import pricing as pricing_module
from t4 import jcs, manifest
from t4.emitter import Emitter, ObservingIVE, RunObserver
from t4.validation import record_validator
from tests.fakes import DummyClock, make_ive_json

# --------------------------------------------------------------------------- #
# The recorded run shape (mandate appendix B, carried context, not a fact about
# the world — recorded here as the fixture it is).
# --------------------------------------------------------------------------- #
QUESTION = "is money credit or debt?"
RUN_ID = "ion-t4-demo-0001"
TIMESTAMP = "2026-08-08T00:00:00.000000+00:00"

GEMINI_MODEL = "gemini-2.5-pro"      # genuinely absent from the pricing table (D4)
OPENAI_MODEL = "gpt-5.4-mini"        # priced; reproduces the recorded $0.006783
GEMINI_TOKENS = (1437, 1744)
OPENAI_TOKENS = (1658, 1231)
GEMINI_LATENCY_MS = 28_200
OPENAI_LATENCY_MS = 9_400
TOTAL_WALL_CLOCK_MS = 42_000
RECORDED_SOURCE = "recorded_fixture"

# The environment the fixture's run executed in, as the contract's implementation-v1
# vector carries it. Not a claim about this host: see host_implementation_gaps().
RECORDED_ENVIRONMENT = {
    "distributions": {
        "google_genai_version": "2.11.0", "jsonschema_version": "4.26.0",
        "numpy_version": "2.5.1", "openai_version": "2.45.0",
        "pydantic_version": "2.13.4", "qdrant_client_version": "1.18.0",
        "sentence_transformers_version": "5.6.0", "torch_version": "2.13.0",
        "transformers_version": "5.13.1",
    },
    "python": "3.12.13",
}

DOCS = [
    {"document_id": "d1", "source_id": "broken_money", "title": "Credit",
     "content": "money is fundamentally credit and debt between people"},
    {"document_id": "d2", "source_id": "layered_money", "title": "Commodity",
     "content": "commodity money like gold has intrinsic value"},
    {"document_id": "d3", "source_id": "whale", "title": "Whales",
     "content": "the ecological value of whales in the ocean"},
]

COMPONENTS = [
    {"component": "context_pack", "is_primary": False},
    {"component": "gemini_ive", "is_primary": True},
    {"component": "mive", "is_primary": False},
    {"component": "openai_ive", "is_primary": True},
    {"component": "renderer", "is_primary": False},
    {"component": "retrieval", "is_primary": False},
]

_IVE_JSON = make_ive_json(
    claims=[{"claim_id": "c1", "statement": "money is a form of credit and debt",
             "evidence_document_ids": ["d1"], "confidence": 0.8}],
    evidence_mapping={"c1": ["d1"]},
)


class RecordingBackend:
    """A provider backend double that returns the recorded usage and keeps the prompt."""

    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self._in, self._out = input_tokens, output_tokens
        self.system = None
        self.user = None

    def generate(self, *, system: str, user: str, schema: dict):
        self.system, self.user = system, user
        return ive_common.GenerationResult(
            text=_IVE_JSON, input_tokens=self._in, output_tokens=self._out)


class FixtureClock:
    """Yields the recorded elapsed times, in whole milliseconds, in call order."""

    def __init__(self, elapsed_ms: list[int]) -> None:
        self._elapsed = list(elapsed_ms)
        self._now = 0
        self._calls = 0

    def __call__(self) -> int:
        # Each wrapped call reads the clock twice: once before, once after.
        if self._calls % 2 == 1:
            self._now += self._elapsed[self._calls // 2]
        self._calls += 1
        return self._now


def host_implementation_gaps() -> list[str]:
    """Which of the contract's ten distributions this host cannot report."""
    from importlib import metadata

    distributions = {
        "google_genai_version": "google-genai", "jsonschema_version": "jsonschema",
        "numpy_version": "numpy", "openai_version": "openai",
        "pydantic_version": "pydantic", "qdrant_client_version": "qdrant-client",
        "sentence_transformers_version": "sentence-transformers",
        "torch_version": "torch", "transformers_version": "transformers",
    }
    missing = []
    for key, name in sorted(distributions.items()):
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            missing.append(key)
    return missing


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def run_demonstration(store: Path, *, manifest_path: Path | None = None,
                      run_id: str = RUN_ID):
    """Compose the Core, drive one run through the wrapper, and emit one record."""
    manifest_path = manifest_path or manifest.default_path()

    gemini_backend = RecordingBackend(*GEMINI_TOKENS)
    openai_backend = RecordingBackend(*OPENAI_TOKENS)
    observer = RunObserver()
    clock = FixtureClock([GEMINI_LATENCY_MS, OPENAI_LATENCY_MS])

    settings = Settings.load({"OPENAI_MODEL": OPENAI_MODEL, "GEMINI_MODEL": GEMINI_MODEL,
                              "DEFAULT_TOP_K": "3"})
    embedder = HashingEmbedder(dimension=512)
    retrieval = InMemoryRetrieval(embedder)
    retrieval.index(DOCS)
    builder = ContextPackBuilder(char_budget=settings.context_char_budget)

    # The wrapper goes around the IVEPort. The wrapped engines are registered in
    # the Model Gateway under the identity each one delegates from its inner
    # adapter, and the Gateway is injected through the public keyword-only
    # constructor. Dispatch order is gemini then openai, as the orchestrator
    # calls them.
    observed_gemini = ObservingIVE(
        GeminiIVE(gemini_backend, model=GEMINI_MODEL), observer=observer,
        sequence=1, provider="gemini", requested_model=GEMINI_MODEL,
        clock=clock, latency_source=RECORDED_SOURCE)
    observed_openai = ObservingIVE(
        OpenAIIVE(openai_backend, model=OPENAI_MODEL), observer=observer,
        sequence=2, provider="openai", requested_model=OPENAI_MODEL,
        clock=clock, latency_source=RECORDED_SOURCE)

    # TASK 20: Core now requires an injected `execution_profile` and executes
    # only the engine(s) it names. STANDARD_GEMINI/SINGLE names "gemini"
    # only, so `observed_openai` below is registered but NEVER invoked by a
    # live `core.ask()` call — this demonstration's dual-provider dispatch
    # recording (the "planned_calls"/"dispatch order" facts fed to the T4
    # emitter below) is therefore ARCHITECTURALLY STALE against the live
    # policy. Reconciling the T4 recording semantics themselves to a
    # profile-driven world is out of TASK 20's bounded scope; this is the
    # minimum fix required so the script's Core construction does not raise
    # a TypeError. STANDARD_GEMINI is passed explicitly rather than assumed.
    from app.modules.execution_profile import STANDARD_GEMINI

    core = Core(
        retrieval=retrieval,
        context_pack_builder=builder,
        model_gateway=ModelGateway({
            observed_gemini.engine_id: observed_gemini,
            observed_openai.engine_id: observed_openai,
        }),
        mive=MIVEComparator(),
        renderer=DeterministicRenderer(),
        pricing=pricing_module.PricingTable(),
        clock=DummyClock(),
        settings=settings,
        execution_profile=STANDARD_GEMINI,
    )
    result = core.ask(QUESTION, top_k=3)

    # The bytes the identities digest, taken from what the run actually used.
    pack = builder.build(QUESTION, retrieval.retrieve(QUESTION, 3))
    context_bytes = jcs.serialize(pack.to_dict())
    prompt_bytes = (gemini_backend.system + gemini_backend.user).encode("utf-8")
    workload_bytes = jcs.serialize({"question": QUESTION})

    raw_identities = {
        "workload": ("workload", {"bytes_b64": _b64(workload_bytes), "present": True}),
        "prompt": ("prompt", {"bytes_b64": _b64(prompt_bytes), "present": True}),
        "context": ("context", {"bytes_b64": _b64(context_bytes), "present": True}),
        "decoding": ("decoding", {"locally_set": False}),
        "retry": ("retry", {"locally_set": False}),
        "timeout": ("timeout", {"locally_set": False}),
        "termination": ("termination", {"locally_set": False}),
        "dispatch": ("dispatch", {"configurable": False, "mode": "sequential",
                                  "order": ["gemini", "openai"]}),
        "fallback": ("fallback", {"enabled": False, "on_provider_error": "propagate"}),
        "implementation": ("implementation", RECORDED_ENVIRONMENT),
    }

    emitter = Emitter(
        manifest_path=manifest_path,
        store_path=store,
        # Read from the repository's pricing module, never through
        # PricingTable.estimate_cost, which rounds (pricing.py:39).
        rates=pricing_module._PRICES,
        pricing_basis_id=f"ion-pricing-table@{pricing_module.PRICING_AS_OF}",
        validator=record_validator(manifest_path),
    )

    outcome, record = emitter.emit(
        record_origin="recorded_fixture",
        run_id=run_id,
        timestamp=TIMESTAMP,
        raw_identities=raw_identities,
        planned_components=COMPONENTS,
        planned_calls=[
            {"sequence": 1, "provider": "gemini", "requested_model": GEMINI_MODEL},
            {"sequence": 2, "provider": "openai", "requested_model": OPENAI_MODEL},
        ],
        component_results=[{"component": c["component"], "outcome": "completed",
                            "incomplete_reason": None} for c in COMPONENTS],
        observer=observer,
        wall_clock_ms=TOTAL_WALL_CLOCK_MS,
        wall_clock_source=RECORDED_SOURCE,
        # The one measurement the emitter set out to gather and could not: the
        # Gemini cost, because no pricing entry exists for that model (D4).
        unavailable_measurements=["calls[0].cost_value"],
    )
    return outcome, record, result


def default_store() -> Path:
    return manifest.repository_root() / "backend" / "t4" / "records"


if __name__ == "__main__":  # pragma: no cover
    gaps = host_implementation_gaps()
    if gaps:
        print("host cannot report:", ", ".join(gaps))
    store = default_store()
    outcome, record, _ = run_demonstration(store)
    print(jcs.to_canonical_text(outcome.to_dict()))
    if record is not None:
        path = store / f"{record['run_id']}.json"
        raw = path.read_bytes()
        print(f"{hashlib.sha256(raw).hexdigest()}  {path}  ({len(raw)} bytes)")
