"""TASK 21.2A — controlled, network-free, first-governed-turn harness.

Drives ONE real `Core.ask()` call through the REAL Product governance stack
(retrieval boundary, `CoreAdapter`, runtime evidence bridge, provenance
resolver, admission gate, `GovernedEvidenceSet` materializer, Model Context
builder, `ModelGateway`, `DeterministicRenderer`, Turn Record materializer)
with a CONTROLLED, deterministic, network-free stand-in engine registered
under the STANDARD_GEMINI-authorized engine identity "gemini".

This module is scoped to TASK 21.2A only:

    - it performs NO live Gemini call, imports no provider adapter
      (`app.modules.gemini_ive`, `app.modules.openai_ive`) and no
      `qdrant_client`, and reads no provider credential;
    - it does not import `app.container` / `app.container.build_core` at
      all, precisely so no network-capable adapter can enter this process
      by transitive import;
    - governance is never mocked, faked, short-circuited, or replaced:
      `CoreAdapter()` is constructed with its normal, no-argument
      constructor (the only way to get a real `CoreAdapter` bound to the
      real `build_qdrant_runtime_bridge()`), and the real evidence
      fingerprint / canonical provenance / admission-gate machinery in
      `app.modules.retrieval` and `app.modules.admission` runs unmodified;
    - the only "controlled" component is the engine registered at the
      Model Gateway (`ControlledDeterministicEngine`), which is explicitly
      NOT Gemini and must never be reported as one (see its own docstring).

H1 (this file, as written by TASK 21.2A-H1) BUILDS the harness only. No
function in this module is invoked by anything in this repository, and this
file is not executed as part of writing it. `main()` exists so that TASK
21.2A, once separately authorized, can invoke this exact file unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# --------------------------------------------------------------------------- #
# Real Product components only. Deliberately NOT imported, anywhere in this
# file: app.container / app.container.build_core (pulls in GeminiIVE /
# OpenAIIVE / QdrantRetrieval by transitive top-level import), and any of
# app.modules.gemini_ive, app.modules.openai_ive, qdrant_client.
# --------------------------------------------------------------------------- #
import app.core.orchestrator as orch
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.models import Claim, IVEReport, Usage
from app.core.orchestrator import Core
from app.modules.context_pack import ContextPackBuilder
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import STANDARD_GEMINI, resolve_execution_profile
from app.modules.mive import MIVEComparator
from app.modules.model_gateway import ModelGateway
from app.modules.renderer import DeterministicRenderer
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.ingest import build_records
from app.modules.retrieval.memory_index import InMemoryRetrieval
from app.modules.retrieval.source_provenance import build_source_provenance
from app.modules.telemetry import PricingTable

RECEIPT_SCHEMA_ID = "ION_TASK21_CONTROLLED_DRY_RECEIPT_V0_1"
CONTROLLED_HARNESS_IDENTITY = "ION_TASK21_CONTROLLED_HARNESS_V0_1"
APPROVED_QUESTION = "Where should operator-approved source documents be placed?"
CONTROLLED_SOURCE_RELATIVE_PATH = "corpus/README.md"

# Names this harness must never import or construct. Checked both statically
# (this list documents the guard) and structurally, at runtime, by
# `verify_network_free_composition()` below.
_FORBIDDEN_COMPONENT_NAMES = (
    "GeminiIVE",
    "GeminiBackend",
    "OpenAIIVE",
    "OpenAIBackend",
    "QdrantRetrieval",
)


# =========================================================================
# Controlled source staging (real ingestion needs a supported extension)
# =========================================================================
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rfc3339_now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stage_controlled_source(repo_root: Path, tmp_root: Path) -> tuple[Path, str]:
    """Stage a byte-identical, `.txt`-suffixed mirror of `corpus/README.md`
    inside an OS temp directory OUTSIDE the repository.

    The real ingestion API (`app.modules.retrieval.ingest.build_records`)
    recognizes only `.txt` and `.pdf` files; `corpus/README.md` is silently
    skipped by its directory scan otherwise (see TASK 21.1's finding). This
    function performs a pure byte-for-byte copy, self-verified by hash, so
    the recorded content and checksum trace to the exact real repository
    file. `corpus/README.md` itself is opened read-only and is never
    modified, moved, or renamed in place.

    Returns (staged_source_dir, source_sha256_of_the_real_file).
    """
    real_readme = repo_root / CONTROLLED_SOURCE_RELATIVE_PATH
    if not real_readme.is_file():
        raise FileNotFoundError(
            f"controlled source not found at expected repository path: {real_readme}"
        )

    raw = real_readme.read_bytes()
    source_sha256 = _sha256_bytes(raw)

    staged_dir = tmp_root / "corpus"
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged_file = staged_dir / "README.txt"
    staged_file.write_bytes(raw)

    if _sha256_bytes(staged_file.read_bytes()) != source_sha256:
        raise RuntimeError(
            "staged controlled source is not byte-identical to the real "
            f"{CONTROLLED_SOURCE_RELATIVE_PATH}; refusing to proceed"
        )
    return staged_dir, source_sha256


def build_controlled_source_provenance(*, source_id: str, source_sha256: str) -> dict[str, Any]:
    """Build the `ion_source_provenance` input record through the REAL
    `build_source_provenance()` API (`app.modules.retrieval.source_provenance`).

    Only the facts the harness genuinely controls are supplied: the
    identity of this controlled harness as collector/producer-context, and
    UTC timestamps read from the harness's own execution environment at
    call time. `source_origin` must equal exactly what `build_records()`
    will independently recompute (`"corpus-file://" + relative_posix_path`
    of the staged file within its ingested directory) — see
    `stage_controlled_source()`, which stages the file at
    `<source_dir>/README.txt`.

    This function does NOT construct `ion_canonical_provenance`,
    `evidence_fingerprint`, or any admission/governance result — those are
    produced exclusively by `build_records(materialize_canonical=True)`
    and, downstream, by the real admission gate.
    """
    now = _rfc3339_now_utc()
    return build_source_provenance(
        source_id=source_id,
        source_origin="corpus-file://README.txt",
        source_file_sha256=source_sha256,
        collector=CONTROLLED_HARNESS_IDENTITY,
        collected_at=now,
        collected_at_status="KNOWN",
        provenance_created_at=now,
        provenance_created_at_status="KNOWN",
    )


def stage_and_materialize_records(repo_root: Path, tmp_root: Path) -> list[dict[str, Any]]:
    """Run the REAL ingestion + canonical-materialization pipeline over the
    staged controlled source. Every provenance/fingerprint value in the
    returned records is produced by `build_records()` itself
    (`app.modules.retrieval.ingest`), never hand-authored here.
    """
    source_dir, source_sha256 = stage_controlled_source(repo_root, tmp_root)
    source_id = "readme"  # must equal ingest.py's own _slug(Path("README.txt").stem)
    provenance_input = build_controlled_source_provenance(
        source_id=source_id, source_sha256=source_sha256
    )
    records = build_records(
        source_dir,
        source_provenance_by_source={source_id: provenance_input},
        materialize_canonical=True,
    )
    if not records:
        raise RuntimeError(
            "real ingestion produced zero records from the staged controlled source"
        )
    return records


# =========================================================================
# Bridging real ingestion records into InMemoryRetrieval's expected shape
# =========================================================================
# The same five candidate-metadata keys QdrantRetrieval's own payload carries
# (backend/app/modules/retrieval/qdrant_store.py:_CANDIDATE_METADATA_KEYS),
# reproduced here only as a KEY NAME list for reshaping -- no value on the
# right of any assignment below is computed by this harness.
_CANDIDATE_METADATA_KEYS = (
    "evidence_fingerprint",
    "evidence_fingerprint_algorithm",
    "evidence_fingerprint_profile_id",
    "ion_source_provenance",
    "ion_canonical_provenance",
)
_RETRIEVAL_METADATA_KEYS = ("checksum", "ingestion_version") + _CANDIDATE_METADATA_KEYS


def records_to_retrieval_documents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reshape real `build_records()` output for `InMemoryRetrieval.index()`.

    `InMemoryRetrieval` reads candidate provenance from a nested `metadata`
    dict (mirroring the real `Evidence.metadata` shape that
    `QdrantRetrieval.retrieve()` reconstructs from a Qdrant payload);
    `build_records()` returns those same keys as flat record fields. This
    function performs ONLY that reshaping. Every value it copies was
    produced by the real ingestion/canonical-materialization call in
    `stage_and_materialize_records()`, not by this function.
    """
    documents = []
    for record in records:
        metadata = {
            key: record[key]
            for key in _RETRIEVAL_METADATA_KEYS
            if key in record and record[key] is not None
        }
        documents.append({**record, "metadata": metadata})
    return documents


# =========================================================================
# The controlled engine (TASK 21.2A only — never Gemini)
# =========================================================================
class ControlledDeterministicEngine:
    """A deterministic, network-free `IVEPort` implementation for TASK
    21.2A only.

    Registered at the Model Gateway under the identity "gemini" ONLY
    because `STANDARD_GEMINI`/`SINGLE` names that engine id as policy
    (`app.modules.execution_profile`) — the Gateway resolves by that
    string, and Core's `SINGLE` branch asks for whatever
    `execution_profile.engine_ids[0]` names. This class performs no
    network call, constructs no provider SDK client, and reads no
    environment credential. `self.provider` is set to the literal
    `"CONTROLLED_FAKE"` so no downstream artifact (metrics, Turn Record,
    receipt) can be misread as a real Gemini provider execution.

    Required behavior (TASK 21.2A-H1 §13), all enforced here:
      - exactly one `run()` call per instance (a second call raises);
      - refuses to run with zero evidence in the received
        `ModelContextAssembly` (fail closed, never fabricate grounding);
      - cites only candidate ids ACTUALLY PRESENT in the `ModelContextAssembly`
        it received at call time — computed from `model_input.evidence`,
        never hardcoded before governance runs;
      - deterministic, no randomness, no retries, no fallback.
    """

    def __init__(self) -> None:
        self._engine_id = "gemini"
        self.provider = "CONTROLLED_FAKE"
        self.model = "task21-controlled-deterministic-engine-v0-1"
        self.call_count = 0

    @property
    def engine_id(self) -> str:
        return self._engine_id

    def run(self, model_input: Any) -> IVEReport:
        self.call_count += 1
        if self.call_count > 1:
            raise RuntimeError(
                "ControlledDeterministicEngine.run() called more than once; "
                "TASK 21.2A requires exactly one controlled execution per turn"
            )
        if not model_input.evidence:
            raise ValueError(
                "ControlledDeterministicEngine refuses to run: the received "
                "ModelContextAssembly carries no evidence"
            )

        started = time.monotonic()
        # Citation ids are read from the ACTUAL received Model Context at
        # call time -- never a value known/hardcoded before governance ran.
        candidate_ids = [item.candidate_id for item in model_input.evidence]

        # Grounded in the real, known content of corpus/README.md ("Place
        # the operator-approved source documents under: `corpus/source/`");
        # not a synthesized or model-generated claim.
        statement = (
            "Operator-approved source documents should be placed under "
            "corpus/source/, per the admitted controlled evidence."
        )
        claim = Claim(
            claim_id="task21-controlled-claim-1",
            statement=statement,
            evidence_document_ids=list(candidate_ids),
            confidence=1.0,
        )
        latency_ms = (time.monotonic() - started) * 1000.0

        return IVEReport(
            engine_id=self._engine_id,
            provider=self.provider,
            model=self.model,
            question=model_input.question,
            abstract=statement,
            highlights=[],
            claims=[claim],
            concepts=[],
            relations=[],
            evidence_mapping={claim.claim_id: list(candidate_ids)},
            uncertainty=[
                "This report was produced by a controlled, non-Gemini "
                "deterministic engine for TASK 21.2A only."
            ],
            confidence=1.0,
            raw_response=None,
            usage=Usage(
                input_tokens=None,
                output_tokens=None,
                latency_ms=latency_ms,
                usage_is_estimated=True,
            ),
        )


class MiveCallCounter:
    """Counts calls while forwarding, unchanged, to the REAL `MIVEComparator`.

    Under `STANDARD_GEMINI`/`SINGLE`, `Core.ask()` never calls
    `self._mive.compare(...)` (see `app/core/orchestrator.py`); this wrapper
    exists only so the harness can MEASURE that (`call_count == 0`) rather
    than merely assert it from prior static reading. If it were ever
    called, it forwards to the real comparator and returns the unchanged
    result — never a fabricated one.
    """

    def __init__(self, real_mive: MIVEComparator) -> None:
        self._real = real_mive
        self.call_count = 0

    def compare(self, reports):
        self.call_count += 1
        return self._real.compare(reports)


# =========================================================================
# Real-function observation spy (wrap, record, restore — never replace)
# =========================================================================
class RealFunctionSpy:
    """Wrap ONE real module-level function to record every call and its
    real return value, then restore the original on exit.

    Allowed instrumentation only: the wrapped function is always invoked
    exactly as called, exactly once per real call, and its real result is
    returned unchanged. This class contains no branch that could replace,
    alter, or short-circuit the wrapped function's behavior or result.
    """

    def __init__(self, module: Any, name: str) -> None:
        self._module = module
        self._name = name
        self._original: Callable = getattr(module, name)
        self.calls: list[tuple[tuple, dict]] = []
        self.results: list[Any] = []

    def _wrapped(self, *args: Any, **kwargs: Any) -> Any:
        result = self._original(*args, **kwargs)
        self.calls.append((args, kwargs))
        self.results.append(result)
        return result

    def __enter__(self) -> "RealFunctionSpy":
        setattr(self._module, self._name, self._wrapped)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        setattr(self._module, self._name, self._original)
        return False

    @property
    def call_count(self) -> int:
        return len(self.calls)


# =========================================================================
# Composition (no app.container; no network-capable adapter constructed)
# =========================================================================
def verify_network_free_composition(core: Core, controlled_engine: ControlledDeterministicEngine) -> None:
    """Design-time / composition-time guard. Refuses to proceed if any
    network-capable production adapter has been wired into this controlled
    harness. Raises `AssertionError`; never downgrades to a warning.
    """
    if not isinstance(core._retrieval, InMemoryRetrieval):
        raise AssertionError(
            "controlled harness requires InMemoryRetrieval; found "
            f"{type(core._retrieval).__name__}"
        )
    engines = dict(core._model_gateway._engines)
    if set(engines) != {"gemini"}:
        raise AssertionError(
            f"expected exactly one registered engine id {{'gemini'}}, found {set(engines)}"
        )
    if engines["gemini"] is not controlled_engine:
        raise AssertionError("registered 'gemini' engine is not the controlled engine instance")
    if not isinstance(core._core_adapter, CoreAdapter):
        raise AssertionError(
            f"core._core_adapter is not a real CoreAdapter; found {type(core._core_adapter).__name__}"
        )
    observed_names = {
        type(core._retrieval).__name__,
        type(engines["gemini"]).__name__,
        type(core._core_adapter).__name__,
    }
    forbidden_hit = observed_names & set(_FORBIDDEN_COMPONENT_NAMES)
    if forbidden_hit:
        raise AssertionError(f"forbidden network-capable component present: {forbidden_hit}")


def build_core_for_controlled_dry_run(
    retrieval_documents: list[dict[str, Any]],
) -> tuple[Core, ControlledDeterministicEngine, MiveCallCounter]:
    """Compose one real `Core` for the controlled dry run.

    Every collaborator is a real, unmodified Product class, constructed
    through its normal public constructor:
      - `InMemoryRetrieval` over `HashingEmbedder` (real RetrievalPort
        adapter; deterministic, dependency-free, no network) — never a
        hand-rolled fake retrieval class;
      - `CoreAdapter()` — REAL, normal, no-argument construction. `Core`
        itself always builds this internally (`Core.__init__` has no
        parameter through which a substitute adapter could be injected),
        so calling `Core(...)` through its normal constructor is itself
        the guarantee that governance is real (TASK 21.2A-H1 §10).
      - the canonical `STANDARD_GEMINI` `ExecutionProfile`, obtained
        through the real `resolve_execution_profile()` resolver;
      - a real `ModelGateway` whose only registered engine is the
        controlled, non-Gemini `ControlledDeterministicEngine`;
      - the real `MIVEComparator`, wrapped only to COUNT calls (never to
        fake or block one);
      - the real `DeterministicRenderer`, `PricingTable`, `SystemClock`.

    `Settings` is loaded from an explicit, empty-plus-override dict — never
    `os.environ` — so this composition path never reads
    `GEMINI_API_KEY`/`OPENAI_API_KEY`/any Qdrant credential, even by
    accident. `retrieval_collection` is overridden to a label that could
    never be mistaken for the real corpus collection.
    """
    settings = Settings.load(env={"VECTOR_COLLECTION": "TASK21_CONTROLLED_INMEMORY_FIXTURE"})

    embedder = HashingEmbedder(dimension=256)
    retrieval = InMemoryRetrieval(embedder)
    retrieval.index(retrieval_documents)

    execution_profile = resolve_execution_profile("STANDARD_GEMINI")
    if execution_profile is not STANDARD_GEMINI:
        raise RuntimeError(
            "resolve_execution_profile('STANDARD_GEMINI') did not return the "
            "canonical STANDARD_GEMINI singleton"
        )

    controlled_engine = ControlledDeterministicEngine()
    model_gateway = ModelGateway({"gemini": controlled_engine})

    real_mive = MIVEComparator()
    mive_counter = MiveCallCounter(real_mive)

    core = Core(
        retrieval=retrieval,
        context_pack_builder=ContextPackBuilder(char_budget=settings.context_char_budget),
        model_gateway=model_gateway,
        mive=mive_counter,
        renderer=DeterministicRenderer(),
        pricing=PricingTable(),
        clock=SystemClock(),
        settings=settings,
        execution_profile=execution_profile,
    )
    verify_network_free_composition(core, controlled_engine)
    return core, controlled_engine, mive_counter


# =========================================================================
# Subset-law verification (fail closed, never merely recorded)
# =========================================================================
def assert_subset_law(
    *,
    retrieved_ids: list[str],
    submitted_ids: list[str],
    admitted_ids: list[str],
    model_context_ids: list[str],
    rendered_ids: list[str],
) -> None:
    """Enforce RENDERED ⊆ MODEL_CONTEXT ⊆ ADMITTED ⊆ SUBMITTED ⊆ RETRIEVED.

    Raises `AssertionError` on any violation. This function never merely
    records the five id sets; a violated subset relation must abort the
    run rather than produce a PASS-looking receipt.
    """
    retrieved_set = set(retrieved_ids)
    submitted_set = set(submitted_ids)
    admitted_set = set(admitted_ids)
    model_context_set = set(model_context_ids)
    rendered_set = set(rendered_ids)

    if not submitted_set <= retrieved_set:
        raise AssertionError(
            f"SUBMITTED not subset of RETRIEVED: {sorted(submitted_set - retrieved_set)}"
        )
    if not admitted_set <= submitted_set:
        raise AssertionError(
            f"ADMITTED not subset of SUBMITTED: {sorted(admitted_set - submitted_set)}"
        )
    if not model_context_set <= admitted_set:
        raise AssertionError(
            f"MODEL_CONTEXT not subset of ADMITTED: {sorted(model_context_set - admitted_set)}"
        )
    if not rendered_set <= model_context_set:
        raise AssertionError(
            f"RENDERED not subset of MODEL_CONTEXT: {sorted(rendered_set - model_context_set)}"
        )


# =========================================================================
# Repository identity (read at RUN time — never hardcoded)
# =========================================================================
def discover_repo_root(start: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()).resolve()


def read_repository_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


# =========================================================================
# The controlled dry turn itself
# =========================================================================
@dataclass
class ControlledDryRunObservation:
    """Everything the harness observed about one controlled dry turn."""

    repository_head: str
    source_path: str
    source_sha256: str
    question: str
    execution_profile_id: str
    execution_profile_version: str
    execution_mode: str
    engine_ids: tuple[str, ...]
    retrieved_candidate_ids: list[str]
    submitted_candidate_ids: list[str]
    admitted_candidate_ids: list[str]
    model_context_evidence_ids: list[str]
    rendered_evidence_ids: list[str]
    controlled_engine_execution_count: int
    openai_execution_count: int
    mive_execution_count: int
    ask_result_status: str
    turn_record_closure_state: str | None
    turn_record_model_execution_count: int | None
    turn_record_engine_ids: list[str] | None
    turn_record_mive_overall_status: str | None
    turn_record_comparison_latency_ms: float | None
    rendered_response: dict[str, Any]
    rendered_response_sha256: str


def run_controlled_dry_turn(
    *, question: str = APPROVED_QUESTION, top_k: int = 1
) -> ControlledDryRunObservation:
    """Run exactly one controlled, network-free governed turn.

    NOT invoked anywhere in this file except from `main()`, which is itself
    never invoked by TASK 21.2A-H1 (build-only phase).
    """
    script_dir = Path(__file__).resolve().parent
    repo_root = discover_repo_root(script_dir)
    repository_head = read_repository_head(repo_root)

    with tempfile.TemporaryDirectory(prefix="ion_task21_controlled_") as tmp:
        tmp_root = Path(tmp)
        records = stage_and_materialize_records(repo_root, tmp_root)
        retrieval_documents = records_to_retrieval_documents(records)
        source_sha256 = records[0]["ion_source_provenance"]["source_file_sha256"]

        core, controlled_engine, mive_counter = build_core_for_controlled_dry_run(
            retrieval_documents
        )

        retrieved_ids: list[str] = []
        real_retrieve = core._retrieval.retrieve

        def spying_retrieve(q: str, k: int):
            result = real_retrieve(q, k)
            retrieved_ids.extend(e.document_id for e in result)
            return result

        core._retrieval.retrieve = spying_retrieve  # real forwarding wrapper only

        progress_events: list[tuple[str, str]] = []

        with RealFunctionSpy(orch, "materialize_governed_evidence_set") as ges_spy, \
             RealFunctionSpy(orch, "build_model_context") as mc_spy, \
             RealFunctionSpy(orch, "materialize_turn_record") as tr_spy, \
             RealFunctionSpy(orch, "materialize_failed_turn_record") as failed_tr_spy:
            result = core.ask(
                question,
                top_k=top_k,
                progress=lambda stage, status: progress_events.append((stage, status)),
            )

        if failed_tr_spy.call_count != 0:
            raise RuntimeError(
                "the turn closed FAILED during a controlled dry run intended to "
                "PASS; inspect the failed Turn Record captured by failed_tr_spy"
            )
        if tr_spy.call_count != 1:
            raise RuntimeError(
                f"expected exactly one COMPLETED Turn Record materialization, "
                f"observed {tr_spy.call_count}"
            )
        if ges_spy.call_count != 1:
            raise RuntimeError(
                f"expected exactly one GovernedEvidenceSet materialization, "
                f"observed {ges_spy.call_count}"
            )
        if mc_spy.call_count != 1:
            raise RuntimeError(
                f"expected exactly one ModelContextAssembly build, "
                f"observed {mc_spy.call_count}"
            )

        governed_evidence = ges_spy.results[0]
        model_context = mc_spy.results[0]
        turn_record = tr_spy.results[0]

        submitted_ids = list(governed_evidence.accounting.submitted_ids)
        admitted_ids = list(governed_evidence.accounting.governed_ids)
        model_context_ids = [item.candidate_id for item in model_context.evidence]
        rendered_ids = [row["document_id"] for row in result.rendered.get("evidence", [])]

        assert_subset_law(
            retrieved_ids=retrieved_ids,
            submitted_ids=submitted_ids,
            admitted_ids=admitted_ids,
            model_context_ids=model_context_ids,
            rendered_ids=rendered_ids,
        )

        model_executions = turn_record.model_executions
        rendered_json = json.dumps(result.rendered, sort_keys=True).encode("utf-8")

        return ControlledDryRunObservation(
            repository_head=repository_head,
            source_path=CONTROLLED_SOURCE_RELATIVE_PATH,
            source_sha256=source_sha256,
            question=question,
            execution_profile_id=core.execution_profile.profile_id,
            execution_profile_version=core.execution_profile.profile_version,
            execution_mode=core.execution_profile.mode.value,
            engine_ids=core.execution_profile.engine_ids,
            retrieved_candidate_ids=retrieved_ids,
            submitted_candidate_ids=submitted_ids,
            admitted_candidate_ids=admitted_ids,
            model_context_evidence_ids=model_context_ids,
            rendered_evidence_ids=rendered_ids,
            controlled_engine_execution_count=controlled_engine.call_count,
            openai_execution_count=0,  # no "openai" key was ever registered; see verify_network_free_composition
            mive_execution_count=mive_counter.call_count,
            ask_result_status=result.status,
            turn_record_closure_state=turn_record.closure_state.value,
            turn_record_model_execution_count=len(model_executions),
            turn_record_engine_ids=[m.engine_id for m in model_executions],
            turn_record_mive_overall_status=turn_record.mive_overall_status,
            turn_record_comparison_latency_ms=turn_record.comparison_latency_ms,
            rendered_response=result.rendered,
            rendered_response_sha256=hashlib.sha256(rendered_json).hexdigest(),
        )


# =========================================================================
# Receipt (structure defined now; writing it is not invoked by H1)
# =========================================================================
def build_receipt(observation: ControlledDryRunObservation, *, run_id: str) -> dict[str, Any]:
    return {
        "receipt_schema_id": RECEIPT_SCHEMA_ID,
        "run_id": run_id,
        "executed_at_utc": _rfc3339_now_utc(),
        "repository_head": observation.repository_head,
        "run_mode": "CONTROLLED_DRY",
        "provider_execution": "CONTROLLED_FAKE",
        "real_gemini_executed": False,
        "source_path": observation.source_path,
        "source_sha256": observation.source_sha256,
        "question": observation.question,
        "execution_profile_id": observation.execution_profile_id,
        "execution_profile_version": observation.execution_profile_version,
        "execution_mode": observation.execution_mode,
        "engine_ids": list(observation.engine_ids),
        "retrieved_candidate_ids": observation.retrieved_candidate_ids,
        "submitted_candidate_ids": observation.submitted_candidate_ids,
        "admitted_candidate_ids": observation.admitted_candidate_ids,
        "model_context_evidence_ids": observation.model_context_evidence_ids,
        "rendered_evidence_ids": observation.rendered_evidence_ids,
        "subset_checks": {
            "rendered_subset_of_model_context": set(observation.rendered_evidence_ids)
            <= set(observation.model_context_evidence_ids),
            "model_context_subset_of_admitted": set(observation.model_context_evidence_ids)
            <= set(observation.admitted_candidate_ids),
            "admitted_subset_of_submitted": set(observation.admitted_candidate_ids)
            <= set(observation.submitted_candidate_ids),
            "submitted_subset_of_retrieved": set(observation.submitted_candidate_ids)
            <= set(observation.retrieved_candidate_ids),
        },
        "controlled_engine_execution_count": observation.controlled_engine_execution_count,
        "openai_execution_count": observation.openai_execution_count,
        "mive_execution_count": observation.mive_execution_count,
        "ask_result_status": observation.ask_result_status,
        "turn_record": {
            "closure_state": observation.turn_record_closure_state,
            "model_execution_count": observation.turn_record_model_execution_count,
            "engine_ids": observation.turn_record_engine_ids,
            "mive_overall_status": observation.turn_record_mive_overall_status,
            "comparison_latency_ms": observation.turn_record_comparison_latency_ms,
        },
        "rendered_response": observation.rendered_response,
        "rendered_response_sha256": observation.rendered_response_sha256,
    }


def write_receipt(receipt: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# =========================================================================
# CLI — deliberately carries no --real / --gemini / --provider-live /
# --network switch, and reads no provider credential.
# =========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "TASK 21.2A controlled, network-free governed-turn harness. "
            "Never executes a real provider call."
        )
    )
    parser.add_argument("--question", default=APPROVED_QUESTION)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument(
        "--run-id",
        default=None,
        help="Receipt run identifier; defaults to a UTC-timestamp-derived id.",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="If given, write the JSON receipt to this path.",
    )
    args = parser.parse_args(argv)

    observation = run_controlled_dry_turn(question=args.question, top_k=args.top_k)

    run_id = args.run_id or ("task21-controlled-dry-" + _rfc3339_now_utc().replace(":", ""))
    receipt = build_receipt(observation, run_id=run_id)

    print(json.dumps(receipt, indent=2, sort_keys=True))

    if args.receipt is not None:
        write_receipt(receipt, args.receipt)
        print(f"receipt written to {args.receipt}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
