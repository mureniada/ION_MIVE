"""The T4 offline dry run (operator decision U3) — the emitter on the real path.

Not a test module (no `test_` prefix), so neither pytest nor `run_tests.py` collects
it, and the recorded suite totals stay comparable. Same precedent as
`t4_demonstration.py`, which this module deliberately parallels so the two records
differ only where the *path* differs.

**What is real here, and what is recorded.** Conflating them is what B4 exists to
prevent, so both are stated exactly.

*Real — the repository's own code, executed.*

* Retrieval: the Phase 1 local layer. `LexicalIndex` (`local_layer/lexical_index.py:143`)
  satisfies `RetrievalPort` and is injected straight into `Core.__init__`. It is a
  deterministic lexical index over registry-admitted files on disk: stdlib only, no
  client, no socket, no credential, and Qdrant Cloud out of reach by construction.
* The canonical `ContextPackBuilder` (`context_pack/builder.py:22`), including its
  `validate_context_pack` guarantee, reached through a recording wrapper that keeps the
  pack the run actually used rather than rebuilding one afterwards.
* Prompt construction: `ive_common.build_model_input_prompt`, over the governed
  `ModelContextAssembly` the real `Core.ask()` materializes for this turn (TASK
  19.3) — via the real `GeminiIVE` and `OpenAIIVE` adapters, resolved through
  the real `ModelGateway`; then the real `MIVEComparator`, `DeterministicRenderer`,
  `PricingTable`, `Settings` and `SystemClock`.
* A real `Core.ask()` traversal, end to end, with `ObservingIVE` wrapped around each
  `IVEPort` and injected through the public keyword-only constructor (D7).
* **The component set and the dispatch order are observed, not transcribed.** A
  progress callback records the stage sequence the orchestrator actually emits;
  :data:`STAGE_TO_COMPONENT` maps those stages onto component names, and an observed
  stage set that does not match its domain stops the run instead of falling back to a
  hardcoded list.
* **The ten `implementation` values are read where the run executes**, at emission
  time. A distribution whose version cannot be read stops the run and is named: the
  contract's state rules make such a record unwritable, and it is never recorded as
  absent or as an empty string.

*Recorded — carried unchanged from the demonstration fixture.*

* The per-call token counts and latencies, and the two model names. They are held
  constant on purpose: every difference between this record and `ion-t4-demo-0001` is
  then attributable to the path, not to a changed input. `record_origin` is therefore
  `recorded_fixture`, never `live_observed`.

*Fake — exactly two objects, and nothing else.*

* The two provider **backends**, which return the recorded `GenerationResult` values.
  **No live provider call occurs** (D3). Nothing reaches a provider, and this remains a
  dry run, not orchestrator integration (D7).

`total_wall_clock_ms` is the one measurement taken live, by operator decision of
2026-08-09: the traversal is genuinely timed and `wall_clock_source` says so, while each
call's `latency_source` still says `recorded_fixture`. Every measurement carries its own
source, which is the separation B3 and B4 require.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
from importlib import metadata
from pathlib import Path

from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.orchestrator import Core
from app.modules import ive_common
from app.modules.context_pack import ContextPackBuilder
from app.modules.gemini_ive import GeminiIVE
from app.modules.local_layer.lexical_index import LexicalIndex
from app.modules.local_layer.loader import load_fragments
from app.modules.local_layer.pipeline import CONTROL_QUESTION, LocalLayerPaths
from app.modules.local_layer.registry import load_registry
from app.modules.mive import MIVEComparator
from app.modules.model_gateway import ModelGateway
from app.modules.openai_ive import OpenAIIVE
from app.modules.renderer import DeterministicRenderer
from app.modules.telemetry import pricing as pricing_module
from t4 import jcs, manifest
from t4.emitter import Emitter, ObservingIVE, RunObserver
from t4.validation import record_validator

# --------------------------------------------------------------------------- #
# Identity of this run
# --------------------------------------------------------------------------- #
RUN_ID = "ion-t4-dryrun-0001"

#: The Phase 1 acceptance question. Used because the local layer is the offline
#: retrieval path, and this is the question that layer was accepted against.
QUESTION = CONTROL_QUESTION

TOP_K = 3

# --------------------------------------------------------------------------- #
# The recorded run shape, carried verbatim from t4_demonstration.py
# --------------------------------------------------------------------------- #
GEMINI_MODEL = "gemini-2.5-pro"      # genuinely absent from the pricing table (D4)
OPENAI_MODEL = "gpt-5.4-mini"        # priced
GEMINI_TOKENS = (1437, 1744)
OPENAI_TOKENS = (1658, 1231)
GEMINI_LATENCY_MS = 28_200
OPENAI_LATENCY_MS = 9_400
RECORDED_SOURCE = "recorded_fixture"

#: The wall clock is measured, so it does not claim to be recorded (B4).
OBSERVED_WALL_CLOCK_SOURCE = "observed_core_ask_traversal"

# --------------------------------------------------------------------------- #
# The observed-to-contracted mapping, stated rather than assumed
# --------------------------------------------------------------------------- #
#: Orchestrator progress stages -> component names. `Core.ask` emits these stages at
#: `orchestrator.py:84,98,108,109,112,155`; `_run_engine` emits the two provider stages.
#: The mapping is declared here so a change in either direction is a stop condition
#: rather than a silent re-labelling.
STAGE_TO_COMPONENT = {
    "retrieval": "retrieval",
    "context_pack": "context_pack",
    "gemini": "gemini_ive",
    "openai": "openai_ive",
    "mive": "mive",
    "answer": "renderer",
}

#: The two components a run must complete for the run not to have failed: the
#: independent IVE engines (invariants 3 and 8).
PRIMARY_COMPONENTS = frozenset({"gemini_ive", "openai_ive"})

#: The provider stages, in the order the orchestrator dispatches them. Observed, then
#: checked against this set — the order itself is never assumed.
PROVIDER_STAGES = frozenset({"gemini", "openai"})

#: The nine distributions the contract's `implementation` key set pins, plus
#: `python_version`, which is read from the interpreter.
CONTRACT_DISTRIBUTIONS = {
    "google_genai_version": "google-genai",
    "jsonschema_version": "jsonschema",
    "numpy_version": "numpy",
    "openai_version": "openai",
    "pydantic_version": "pydantic",
    "qdrant_client_version": "qdrant-client",
    "sentence_transformers_version": "sentence-transformers",
    "torch_version": "torch",
    "transformers_version": "transformers",
}


class DryRunStop(Exception):
    """A stop condition fired. Reported, never worked around."""


# --------------------------------------------------------------------------- #
# Environment — read, never assumed
# --------------------------------------------------------------------------- #
def read_implementation() -> dict:
    """The ten contracted `implementation` values, as this environment reports them.

    A distribution whose version cannot be read stops the run and is named. It is
    never recorded as absent, as an empty string, or as the fixture's value: the
    contract's state rules make such a record unwritable, and papering over that would
    destroy the only signal the dry run exists to produce.
    """
    versions: dict[str, str] = {}
    unreadable: list[str] = []
    for key, distribution in sorted(CONTRACT_DISTRIBUTIONS.items()):
        try:
            versions[key] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            unreadable.append(f"{key} ({distribution})")
    if unreadable:
        raise DryRunStop(
            "the contract's implementation key set pins distributions this environment "
            "cannot report: " + ", ".join(unreadable)
        )
    return {
        "distributions": versions,
        "python": ".".join(str(part) for part in sys.version_info[:3]),
    }


# --------------------------------------------------------------------------- #
# The two fakes, and the two recorders
# --------------------------------------------------------------------------- #
class RecordingBackend:
    """A provider backend double returning the recorded usage. It keeps the prompt."""

    def __init__(self, payload: str, input_tokens: int, output_tokens: int) -> None:
        self._payload = payload
        self._in, self._out = input_tokens, output_tokens
        self.system = None
        self.user = None

    def generate(self, *, system: str, user: str, schema: dict):
        self.system, self.user = system, user
        return ive_common.GenerationResult(
            text=self._payload, input_tokens=self._in, output_tokens=self._out)


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


class RecordingContextPackBuilder:
    """Wraps the real builder and keeps the pack the run actually used.

    Structural conformance to `ContextPackBuilderPort`, the same pattern as
    `ObservingIVE`. Rebuilding a second pack afterwards would identify bytes the run
    did not use — close enough to be indistinguishable, and wrong for that reason.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.pack = None

    def build(self, question, evidence):
        self.pack = self._inner.build(question, evidence)
        return self.pack


class StageRecorder:
    """Records the orchestrator's progress events — the run's own account of itself."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def __call__(self, stage: str, status: str) -> None:
        self.events.append((stage, status))

    def stages_in_order(self) -> list[str]:
        seen: list[str] = []
        for stage, _status in self.events:
            if stage not in seen:
                seen.append(stage)
        return seen

    def failed_stages(self) -> set[str]:
        return {stage for stage, status in self.events if status == "failed"}

    def provider_order(self) -> list[str]:
        return [s for s in self.stages_in_order() if s in PROVIDER_STAGES]

    def components(self) -> list[dict]:
        """The observed component set, checked against the declared mapping."""
        observed = self.stages_in_order()
        unmapped = sorted(set(observed) - set(STAGE_TO_COMPONENT))
        unseen = sorted(set(STAGE_TO_COMPONENT) - set(observed))
        if unmapped or unseen:
            raise DryRunStop(
                "the observed stage set does not match the declared stage-to-component "
                f"mapping (unmapped={unmapped}, declared-but-not-observed={unseen}); "
                "the component set is observed, never substituted"
            )
        return [
            {"component": STAGE_TO_COMPONENT[stage],
             "is_primary": STAGE_TO_COMPONENT[stage] in PRIMARY_COMPONENTS}
            for stage in observed
        ]

    def results(self) -> list[dict]:
        failed = {STAGE_TO_COMPONENT[s] for s in self.failed_stages()}
        return [
            {"component": c["component"],
             "outcome": "incomplete" if c["component"] in failed else "completed",
             "incomplete_reason": ("the orchestrator reported this stage failed"
                                   if c["component"] in failed else None)}
            for c in self.components()
        ]


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _ive_payload(document_ids: list[str]) -> str:
    """A recorded IVE response citing the documents the real pack actually carries."""
    return json.dumps({
        "abstract": "Adaptive Dialogue is described in the registered local material.",
        "highlights": ["Adaptive Dialogue is a named ION capability."],
        "claims": [{"claim_id": "c1",
                    "statement": "Adaptive Dialogue is a named ION capability.",
                    "evidence_document_ids": document_ids[:1],
                    "confidence": 0.8}],
        "concepts": [{"name": "Adaptive Dialogue",
                      "description": "The capability the material introduces."}],
        "relations": [],
        "evidence_mapping": {"c1": document_ids[:1]},
        "uncertainty": ["The material is working-layer, not validated knowledge."],
        "confidence": 0.7,
    })


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #
def build_retrieval(materials_dir=None) -> tuple[LexicalIndex, dict]:
    """The Phase 1 local layer as the `RetrievalPort`. No network, no credential."""
    paths = LocalLayerPaths.resolve(materials_dir)
    registry = load_registry(paths.registry)
    loaded = load_fragments(registry, paths.documents)
    index = LexicalIndex.build(loaded.fragments)
    provenance = {
        "materials_dir": str(paths.materials),
        "registry_version": registry.registry_version,
        "materials": len(registry.materials),
        "retrievable": len(registry.retrievable),
        "fragments": len(loaded.fragments),
        "unregistered": list(loaded.unregistered),
        "excluded_material_ids": list(loaded.excluded_material_ids),
        "index_fingerprint": index.fingerprint(),
    }
    return index, provenance


def run_dry_run(store: Path, *, manifest_path: Path | None = None,
                run_id: str = RUN_ID, materials_dir=None):
    """Compose the Core over the real offline path, traverse it once, emit one record."""
    manifest_path = manifest_path or manifest.default_path()

    # -- the environment, read where the run executes --------------------------
    implementation = read_implementation()

    # -- real retrieval --------------------------------------------------------
    retrieval, retrieval_provenance = build_retrieval(materials_dir)
    evidence = retrieval.retrieve(QUESTION, TOP_K)
    if not evidence:
        raise DryRunStop(
            f"the local layer returned no evidence for {QUESTION!r}; there is nothing "
            "for a real traversal to carry"
        )
    payload = _ive_payload([e.document_id for e in evidence])

    # -- the two fakes ---------------------------------------------------------
    gemini_backend = RecordingBackend(payload, *GEMINI_TOKENS)
    openai_backend = RecordingBackend(payload, *OPENAI_TOKENS)

    observer = RunObserver()
    stages = StageRecorder()
    call_clock = FixtureClock([GEMINI_LATENCY_MS, OPENAI_LATENCY_MS])

    settings = Settings.load({"OPENAI_MODEL": OPENAI_MODEL, "GEMINI_MODEL": GEMINI_MODEL,
                              "DEFAULT_TOP_K": str(TOP_K)})
    builder = RecordingContextPackBuilder(
        ContextPackBuilder(char_budget=settings.context_char_budget))

    # The wrapper still goes around the IVEPort; the wrapped engines are now
    # registered in the Model Gateway under the identity each one delegates from
    # its inner adapter, and the Gateway is what the Core is injected with.
    observed_gemini = ObservingIVE(
        GeminiIVE(gemini_backend, model=GEMINI_MODEL), observer=observer,
        sequence=1, provider="gemini", requested_model=GEMINI_MODEL,
        clock=call_clock, latency_source=RECORDED_SOURCE)
    observed_openai = ObservingIVE(
        OpenAIIVE(openai_backend, model=OPENAI_MODEL), observer=observer,
        sequence=2, provider="openai", requested_model=OPENAI_MODEL,
        clock=call_clock, latency_source=RECORDED_SOURCE)

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
        clock=SystemClock(),
        settings=settings,
    )

    # -- the traversal, timed --------------------------------------------------
    timestamp = SystemClock().now_iso()
    started_ns = time.perf_counter_ns()
    result = core.ask(QUESTION, top_k=TOP_K, progress=stages)
    wall_clock_ms = (time.perf_counter_ns() - started_ns) // 1_000_000

    # -- what the run says about itself ---------------------------------------
    components = stages.components()          # stops if the stage set is unexpected
    component_results = stages.results()
    provider_order = stages.provider_order()
    if len(provider_order) != len(PROVIDER_STAGES):
        raise DryRunStop(
            f"observed provider dispatch {provider_order!r} does not cover the two "
            "independent engines"
        )

    pack = builder.pack
    if pack is None:
        raise DryRunStop("the traversal produced no Context Pack to identify")

    # -- the bytes the identities digest, taken from what the run used ---------
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
                                  "order": provider_order}),
        "fallback": ("fallback", {"enabled": False, "on_provider_error": "propagate"}),
        "implementation": ("implementation", implementation),
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
        timestamp=timestamp,
        raw_identities=raw_identities,
        planned_components=components,
        planned_calls=[
            {"sequence": 1, "provider": "gemini", "requested_model": GEMINI_MODEL},
            {"sequence": 2, "provider": "openai", "requested_model": OPENAI_MODEL},
        ],
        component_results=component_results,
        observer=observer,
        wall_clock_ms=wall_clock_ms,
        wall_clock_source=OBSERVED_WALL_CLOCK_SOURCE,
        # The one measurement the emitter set out to gather and could not: the Gemini
        # cost, because no pricing entry exists for that model (D4).
        unavailable_measurements=["calls[0].cost_value"],
    )

    evidence_of_the_run = {
        "implementation": implementation,
        "retrieval": retrieval_provenance,
        "stages": stages.events,
        "components": [c["component"] for c in components],
        "provider_order": provider_order,
        "context_pack_id": pack.context_pack_id,
        "context_bytes": len(context_bytes),
        "prompt_bytes": len(prompt_bytes),
        "workload_bytes": len(workload_bytes),
        "wall_clock_ms": wall_clock_ms,
        "ask_status": result.status,
    }
    return outcome, record, evidence_of_the_run


def default_store() -> Path:
    return manifest.repository_root() / "backend" / "t4" / "records"


if __name__ == "__main__":  # pragma: no cover
    store = default_store()
    try:
        outcome, record, evidence = run_dry_run(store)
    except DryRunStop as stop:
        print("STOP:", stop)
        raise SystemExit(2)

    print(json.dumps(evidence, indent=2, sort_keys=True, default=str))
    print(jcs.to_canonical_text(outcome.to_dict()))
    if record is not None:
        path = store / f"{record['run_id']}.json"
        raw = path.read_bytes()
        print(f"{hashlib.sha256(raw).hexdigest()}  {path}  ({len(raw)} bytes)")
