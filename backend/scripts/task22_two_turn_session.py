"""TASK 22.4 — controlled, network-free, TWO-TURN Session/Turn Controller
integration proof harness.

Drives ONE real `SessionController` around ONE real `Core`, through the REAL
Product governed-turn pipeline (retrieval boundary, `CoreAdapter`, runtime
evidence bridge, admission gate, `GovernedEvidenceSet` materializer, Model
Context builder, `ModelGateway`, `DeterministicRenderer`, Turn Record
materializer/capture), TWICE in the SAME session — with a CONTROLLED,
deterministic, network-free stand-in engine registered under the
STANDARD_GEMINI-authorized engine identity "gemini".

This module is scoped to TASK 22.4B (build-only) and 22.4 (its later,
separately authorized run):

    - it performs NO live Gemini call, imports no provider adapter
      (`app.modules.gemini_ive`, `app.modules.openai_ive`) and no
      `qdrant_client`, and reads no provider credential;
    - it never imports `app.container` / `app.container.build_core`, so no
      network-capable adapter can enter this process by transitive import;
    - governance is never mocked, faked, short-circuited, or replaced:
      `Core(...)` is constructed through its normal public constructor,
      which is itself the only way to obtain a real `CoreAdapter` bound to
      the real runtime evidence bridge (`Core.__init__` has no parameter
      through which a substitute adapter could be injected);
    - the only controlled component is the engine registered at the Model
      Gateway (`ControlledTwoTurnEngine`), which is explicitly NOT Gemini
      and must never be reported as one.

TASK-21 helper reuse (TASK 22.4A determination D, frozen): SELECTIVE reuse,
by import, of exactly four pure/turn-agnostic pieces from
`task21_governed_turn.py` — `RealFunctionSpy`, `MiveCallCounter`,
`assert_subset_law`, `verify_network_free_composition`. Everything else in
this file is Task-22-local and NOT copied from Task 21, because it is
shaped for exactly one turn and is unsafe to reuse for two:
Task 21's `ControlledDeterministicEngine` raises on a second `run()` call;
its `spying_retrieve` wrapper accumulates retrieved ids into ONE FLAT LIST
across a run (this proof's whole point is that TURN 1 and TURN 2 evidence
accounting must never share one flat set); its receipt shape carries no
turn ordinal, `turn_id`, or session identity; and its provenance collector
label names the Task-21 harness, not this one. `governed_evidence_set_id`
is a fixed module-level contract constant (identical across every turn by
design) and is never read here as evidence that TURN 1 and TURN 2 differ —
per-turn identity is `question_id` / `context_pack_id` / `turn_id`, each
freshly minted per `Core.ask()` call.

Per-turn observability (TASK 22.4A determination E): every spy below wraps
BOTH `run_turn()` calls under ONE `with` block and records each call's
arguments/result by POSITION — `spy.calls[0]`/`spy.results[0]` is TURN 1,
`spy.calls[1]`/`spy.results[1]` is TURN 2. Evidence-accounting id lists
(retrieved/submitted/admitted/model-context/rendered) are read out of that
per-call position into two separate `TurnObservation` instances and are
never merged into one set or one running list.

Every spy in this file is PASS-THROUGH: it calls the real implementation
exactly once per call and forwards its real, unmodified result. No spy
replaces, mocks, or short-circuits governance, retrieval, model execution,
or session/turn-record semantics.

H (this file, as written by TASK 22.4B) BUILDS the harness only. No
function in this module is invoked by anything in this repository, and this
file is not executed as part of writing it — importing it runs no Core, no
SessionController, no retrieval, and no engine. `main()` exists so that
TASK 22.4, once separately authorized, can invoke this exact file unchanged.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import inspect
import json
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# sys.path bootstrap: makes `python3 backend/scripts/task22_two_turn_session.py`
# runnable from any cwd (no PYTHONPATH required) and makes the sibling Task-21
# harness importable by file location, not by package installation.
# --------------------------------------------------------------------------- #
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent
for _p in (str(_BACKEND_DIR), str(_THIS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
from app.modules.session import Session, SessionController, SessionStatus, SessionTurnEntry
from app.modules.telemetry import PricingTable
from app.modules.turn_record import TurnClosureState, TurnRecord

# Selective reuse only (see module docstring): pure spy/verification helpers,
# never the Task-21 controlled engine, its flat retrieved-ids list, or its
# single-turn receipt shape.
from task21_governed_turn import (  # type: ignore[import-not-found]
    MiveCallCounter,
    RealFunctionSpy,
    assert_subset_law,
    verify_network_free_composition,
)

RECEIPT_SCHEMA_ID = "ION_TASK22_TWO_TURN_CONTROLLED_RECEIPT_V0_1"
RECEIPT_VERSION = "0.1"
CONTROLLED_HARNESS_IDENTITY = "ION_TASK22_CONTROLLED_HARNESS_V0_1"
CONTROLLED_SOURCE_RELATIVE_PATH = "corpus/README.md"
EXPECTED_SOURCE_SHA256 = "4ae11758719dc8cada9cdbedb07011c3347cd805c59079edf0e8609cc03fa1ee"

TURN_1_QUESTION = "Where should operator-approved source documents be placed?"
TURN_2_QUESTION = "What must not be included in the corpus source document location?"

_EXPECTED_CORE_ASK_PARAMS = {"self", "question", "top_k", "progress", "on_turn_record"}

# Module NAMES (never arbitrary substrings of unrelated identifiers) this
# harness must never see imported, checked structurally at runtime.
_FORBIDDEN_MODULE_SUBSTRINGS = ("qdrant", "openai", "google.genai", "gemini_ive", "openai_ive")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rfc3339_now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def verify_source_identity(repo_root: Path) -> str:
    """Read-only source-identity guard. FAILS CLOSED, before any staging,
    ingestion, or Core/SessionController composition, if the real
    `corpus/README.md` on disk does not hash to exactly the frozen expected
    value. Never reads a byte beyond that one file; never modifies it.
    """
    real_readme = repo_root / CONTROLLED_SOURCE_RELATIVE_PATH
    if not real_readme.is_file():
        raise FileNotFoundError(f"controlled source not found at expected repository path: {real_readme}")
    actual_sha256 = _sha256_bytes(real_readme.read_bytes())
    if actual_sha256 != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            "controlled source identity mismatch: expected "
            f"{EXPECTED_SOURCE_SHA256}, found {actual_sha256}; refusing to proceed"
        )
    return actual_sha256


def stage_controlled_source(repo_root: Path, tmp_root: Path) -> Path:
    """Stage a byte-identical, `.txt`-suffixed mirror of `corpus/README.md`
    inside an OS temp directory OUTSIDE the repository (the real ingestion
    API only recognizes `.txt`/`.pdf`). `corpus/README.md` itself is opened
    read-only and is never modified, moved, or renamed in place. Caller must
    already have verified source identity via `verify_source_identity()`.
    """
    real_readme = repo_root / CONTROLLED_SOURCE_RELATIVE_PATH
    raw = real_readme.read_bytes()
    staged_dir = tmp_root / "corpus"
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged_file = staged_dir / "README.txt"
    staged_file.write_bytes(raw)
    if _sha256_bytes(staged_file.read_bytes()) != _sha256_bytes(raw):
        raise RuntimeError(
            "staged controlled source is not byte-identical to the real "
            f"{CONTROLLED_SOURCE_RELATIVE_PATH}; refusing to proceed"
        )
    return staged_dir


def stage_and_materialize_records(repo_root: Path, tmp_root: Path, source_sha256: str) -> list[dict[str, Any]]:
    """Run the REAL ingestion + canonical-materialization pipeline over the
    staged controlled source. Every provenance/fingerprint value in the
    returned records is produced by `build_records()` itself
    (`app.modules.retrieval.ingest`), never hand-authored here.
    """
    source_dir = stage_controlled_source(repo_root, tmp_root)
    source_id = "readme"  # must equal ingest.py's own _slug(Path("README.txt").stem)
    now = _rfc3339_now_utc()
    provenance_input = build_source_provenance(
        source_id=source_id,
        source_origin="corpus-file://README.txt",
        source_file_sha256=source_sha256,
        collector=CONTROLLED_HARNESS_IDENTITY,
        collected_at=now,
        collected_at_status="KNOWN",
        provenance_created_at=now,
        provenance_created_at_status="KNOWN",
    )
    records = build_records(
        source_dir,
        source_provenance_by_source={source_id: provenance_input},
        materialize_canonical=True,
    )
    if not records:
        raise RuntimeError("real ingestion produced zero records from the staged controlled source")
    return records


# Same five candidate-metadata keys QdrantRetrieval's own payload carries
# (backend/app/modules/retrieval/qdrant_store.py), reproduced here only as a
# KEY NAME list for reshaping real build_records() output into the nested
# `metadata` shape InMemoryRetrieval.index() expects.
_CANDIDATE_METADATA_KEYS = (
    "evidence_fingerprint",
    "evidence_fingerprint_algorithm",
    "evidence_fingerprint_profile_id",
    "ion_source_provenance",
    "ion_canonical_provenance",
)
_RETRIEVAL_METADATA_KEYS = ("checksum", "ingestion_version") + _CANDIDATE_METADATA_KEYS


def records_to_retrieval_documents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents = []
    for record in records:
        metadata = {key: record[key] for key in _RETRIEVAL_METADATA_KEYS if key in record and record[key] is not None}
        documents.append({**record, "metadata": metadata})
    return documents


# =========================================================================
# The controlled engine (TASK 22.4 only — never Gemini). Task-22-local:
# unlike Task 21's engine, this one permits exactly TWO logical executions
# (one per turn), answers from a frozen per-question table, and refuses any
# question it does not recognize rather than reusing a prior turn's answer.
# =========================================================================
class ControlledTwoTurnEngine:
    """A deterministic, network-free `IVEPort` implementation for TASK 22.4
    only.

    Registered at the Model Gateway under the identity "gemini" ONLY because
    `STANDARD_GEMINI`/`SINGLE` names that engine id as policy
    (`app.modules.execution_profile`); this class performs no network call,
    constructs no provider SDK client, and reads no environment credential.
    `self.provider` is set to the literal `"CONTROLLED_FAKE"` so no
    downstream artifact (metrics, Turn Record, receipt) can be misread as a
    real Gemini provider execution.

    Required behavior, all enforced here:
      - exactly two `run()` calls total (one per turn); a third raises;
      - refuses to run with zero evidence in the received
        `ModelContextAssembly` (fail closed, never fabricate grounding);
      - answers strictly from a frozen `{question: (statement, required_
        grounding_phrase)}` table, and fails closed on any question not in
        that table — never falls back to a prior turn's answer;
      - additionally refuses to run unless the received evidence content
        actually contains that question's required grounding phrase, so the
        answer stays a property of the current turn's own ModelContext, not
        of the engine's own memory;
      - cites only candidate ids ACTUALLY PRESENT in the
        `ModelContextAssembly` it received at call time;
      - deterministic, no randomness, no retries, no fallback.
    """

    _ANSWERS: dict[str, tuple[str, str]] = {
        TURN_1_QUESTION: (
            "Operator-approved source documents should be placed under "
            "corpus/source/, per the admitted controlled evidence.",
            "corpus/source/",
        ),
        TURN_2_QUESTION: (
            "Application code must not be included in the corpus source "
            "document location, per the admitted controlled evidence.",
            "Do not include application code",
        ),
    }

    def __init__(self) -> None:
        self._engine_id = "gemini"
        self.provider = "CONTROLLED_FAKE"
        self.model = "task22-controlled-two-turn-engine-v0-1"
        self.call_count = 0

    @property
    def engine_id(self) -> str:
        return self._engine_id

    def run(self, model_input: Any) -> IVEReport:
        self.call_count += 1
        if self.call_count > 2:
            raise RuntimeError(
                "ControlledTwoTurnEngine.run() called more than twice; TASK 22.4 "
                "authorizes exactly one controlled execution per turn, two turns total"
            )
        if not model_input.evidence:
            raise ValueError("ControlledTwoTurnEngine refuses to run: the received ModelContextAssembly carries no evidence")

        question = model_input.question
        if question not in self._ANSWERS:
            raise ValueError(f"ControlledTwoTurnEngine refuses to run: unrecognised question {question!r}")
        statement, required_phrase = self._ANSWERS[question]
        if not any(required_phrase in item.content for item in model_input.evidence):
            raise ValueError(
                "ControlledTwoTurnEngine refuses to run: required grounding phrase "
                f"{required_phrase!r} is not present in the received evidence content"
            )

        started = time.monotonic()
        # Citation ids are read from the ACTUAL received Model Context at
        # call time -- never a value known/hardcoded before governance ran.
        candidate_ids = [item.candidate_id for item in model_input.evidence]
        claim = Claim(
            claim_id=f"task22-controlled-claim-turn{self.call_count}",
            statement=statement,
            evidence_document_ids=list(candidate_ids),
            confidence=1.0,
        )
        latency_ms = (time.monotonic() - started) * 1000.0

        return IVEReport(
            engine_id=self._engine_id,
            provider=self.provider,
            model=self.model,
            question=question,
            abstract=statement,
            highlights=[],
            claims=[claim],
            concepts=[],
            relations=[],
            evidence_mapping={claim.claim_id: list(candidate_ids)},
            uncertainty=[
                "This report was produced by a controlled, non-Gemini "
                "deterministic engine for TASK 22.4 only."
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


# =========================================================================
# Composition (no app.container; no network-capable adapter constructed)
# =========================================================================
def _verify_no_forbidden_modules() -> None:
    hit = sorted(name for name in sys.modules if any(f in name for f in _FORBIDDEN_MODULE_SUBSTRINGS))
    if hit:
        raise AssertionError(f"forbidden network-capable module present in sys.modules: {hit}")


def build_core_and_controller(
    retrieval_documents: list[dict[str, Any]],
) -> tuple[Core, SessionController, ControlledTwoTurnEngine, MiveCallCounter]:
    """Compose one real `Core` and one real `SessionController` around it
    for the controlled two-turn proof.

    Every collaborator is a real, unmodified Product class, constructed
    through its normal public constructor -- `InMemoryRetrieval` over
    `HashingEmbedder`, the real `CoreAdapter` (`Core.__init__` always builds
    this internally; there is no parameter through which a substitute could
    be injected), the canonical `STANDARD_GEMINI` `ExecutionProfile`
    resolved through `resolve_execution_profile()`, a real `ModelGateway`
    whose only registered engine is the controlled, non-Gemini
    `ControlledTwoTurnEngine`, the real `MIVEComparator` (wrapped only to
    COUNT calls), the real `DeterministicRenderer`, `PricingTable`,
    `SystemClock`, and finally a real `SessionController(core)`.

    `Settings` is loaded from an explicit, empty-plus-override dict -- never
    `os.environ` -- so this composition path never reads
    `GEMINI_API_KEY`/`OPENAI_API_KEY`/any Qdrant credential, even by
    accident.
    """
    settings = Settings.load(env={"VECTOR_COLLECTION": "TASK22_CONTROLLED_INMEMORY_FIXTURE"})

    embedder = HashingEmbedder(dimension=256)
    retrieval = InMemoryRetrieval(embedder)
    retrieval.index(retrieval_documents)

    execution_profile = resolve_execution_profile("STANDARD_GEMINI")
    if execution_profile is not STANDARD_GEMINI:
        raise RuntimeError("resolve_execution_profile('STANDARD_GEMINI') did not return the canonical STANDARD_GEMINI singleton")

    controlled_engine = ControlledTwoTurnEngine()
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
    _verify_no_forbidden_modules()

    controller = SessionController(core)
    return core, controller, controlled_engine, mive_counter


# =========================================================================
# Per-turn / whole-run observation shapes
# =========================================================================
@dataclass
class TurnObservation:
    """Everything the harness observed about ONE turn. TURN 1 and TURN 2 each
    get their own instance; nothing here is ever merged across turns."""

    ordinal: int
    question: str
    turn_id: str
    request_id: str
    context_pack_id: str
    question_id: str
    closure_state: str
    retrieved_candidate_ids: list[str]
    submitted_candidate_ids: list[str]
    admitted_candidate_ids: list[str]
    model_context_evidence_ids: list[str]
    rendered_evidence_ids: list[str]
    subset_checks: dict[str, bool]
    controlled_engine_execution_count: int
    rendered_response: dict[str, Any]
    rendered_response_sha256: str


@dataclass
class TwoTurnProof:
    repository_head: str
    source_sha256: str
    session_id: str
    initial_session: dict[str, Any]
    execution_profile: dict[str, str]
    turns: list[TurnObservation]
    aggregate_counts: dict[str, int]
    cross_turn_authority_checks: dict[str, bool]
    provider_counts: dict[str, int]
    pre_close_session: dict[str, Any]
    post_close_session: dict[str, Any]
    final_close_checks: dict[str, bool]


def _subset_checks(
    retrieved_ids: list[str],
    submitted_ids: list[str],
    admitted_ids: list[str],
    model_context_ids: list[str],
    rendered_ids: list[str],
) -> dict[str, bool]:
    """RENDERED subset of MODEL_CONTEXT subset of ADMITTED subset of
    SUBMITTED subset of RETRIEVED, computed independently per turn."""
    retrieved, submitted, admitted, model_context, rendered = (
        set(retrieved_ids), set(submitted_ids), set(admitted_ids), set(model_context_ids), set(rendered_ids),
    )
    return {
        "submitted_subset_of_retrieved": submitted <= retrieved,
        "admitted_subset_of_submitted": admitted <= submitted,
        "model_context_subset_of_admitted": model_context <= admitted,
        "rendered_subset_of_model_context": rendered <= model_context,
    }


def _session_dict(session: Session) -> dict[str, Any]:
    return {
        "status": session.status.value,
        "ordered_ordinals": [e.turn_ordinal for e in session.ordered_turns],
        "turn_ids": [e.turn_id for e in session.ordered_turns],
        "next_turn_ordinal": session.next_turn_ordinal,
        "active_turn": None if session.active_turn is None else session.active_turn.reservation_id,
    }


# =========================================================================
# The controlled two-turn proof itself
# =========================================================================
def run_controlled_two_turn_proof(
    *, turn_1_question: str = TURN_1_QUESTION, turn_2_question: str = TURN_2_QUESTION, top_k: int = 1,
) -> TwoTurnProof:
    """Run exactly two controlled, network-free governed turns in ONE real
    session. Aborts with an exception -- never a PASS-looking partial result
    -- on any proof-gate violation.

    NOT invoked anywhere in this file except from `main()`, which is itself
    never invoked by TASK 22.4B (build-only phase).
    """
    script_dir = Path(__file__).resolve().parent
    repo_root = discover_repo_root(script_dir)
    repository_head = read_repository_head(repo_root)

    # Fail closed on source identity BEFORE any staging, ingestion, or
    # Core/SessionController composition.
    source_sha256 = verify_source_identity(repo_root)

    with tempfile.TemporaryDirectory(prefix="ion_task22_controlled_") as tmp:
        tmp_root = Path(tmp)
        records = stage_and_materialize_records(repo_root, tmp_root, source_sha256)
        retrieval_documents = records_to_retrieval_documents(records)
        if records[0]["ion_source_provenance"]["source_file_sha256"] != source_sha256:
            raise RuntimeError("ingested source hash diverged from the pre-verified source identity; refusing to proceed")

        core, controller, controlled_engine, mive_counter = build_core_and_controller(retrieval_documents)

        session = controller.create_session()
        session_id = session.session_id
        initial_session = _session_dict(session)
        if (
            session.status is not SessionStatus.ACTIVE
            or session.ordered_turns != ()
            or session.next_turn_ordinal != 1
            or session.active_turn is not None
        ):
            raise AssertionError(f"initial session snapshot violates the required shape: {initial_session}")

        questions = [turn_1_question, turn_2_question]
        turns: list[TurnObservation] = []
        entry_snapshots: list[SessionTurnEntry] = []

        with ExitStack() as stack:
            run_turn_spy = stack.enter_context(RealFunctionSpy(controller, "run_turn"))
            core_ask_spy = stack.enter_context(RealFunctionSpy(core, "ask"))
            retrieve_spy = stack.enter_context(RealFunctionSpy(core._retrieval, "retrieve"))
            govern_spy = stack.enter_context(RealFunctionSpy(core._core_adapter, "govern"))
            ges_spy = stack.enter_context(RealFunctionSpy(orch, "materialize_governed_evidence_set"))
            mc_spy = stack.enter_context(RealFunctionSpy(orch, "build_model_context"))
            tr_spy = stack.enter_context(RealFunctionSpy(orch, "materialize_turn_record"))
            failed_tr_spy = stack.enter_context(RealFunctionSpy(orch, "materialize_failed_turn_record"))
            engine_spy = stack.enter_context(RealFunctionSpy(controlled_engine, "run"))

            for idx, question in enumerate(questions):
                ordinal = idx + 1
                ask_result = controller.run_turn(session_id, question, top_k)

                # --- per-turn execution-count gate (fails closed immediately) ---
                for label, spy in (
                    ("run_turn", run_turn_spy), ("Core.ask", core_ask_spy),
                    ("retrieval", retrieve_spy), ("governance", govern_spy),
                    ("governed-evidence materialization", ges_spy),
                    ("ModelContext build", mc_spy), ("TurnRecord materialization", tr_spy),
                    ("controlled engine", engine_spy),
                ):
                    if spy.call_count != ordinal:
                        raise RuntimeError(f"{label} call count mismatch after turn {ordinal}: {spy.call_count}")
                if failed_tr_spy.call_count != 0:
                    raise RuntimeError(f"a FAILED TurnRecord was materialized during turn {ordinal}; the controlled proof must PASS cleanly")

                # --- per-turn session-shape gate ---
                session_now = controller.get_session(session_id)
                if len(session_now.ordered_turns) != ordinal:
                    raise RuntimeError(f"session history length mismatch after turn {ordinal}: {len(session_now.ordered_turns)}")
                entry = session_now.ordered_turns[-1]
                if entry.turn_ordinal != ordinal:
                    raise RuntimeError(f"entry ordinal mismatch: expected {ordinal}, found {entry.turn_ordinal}")
                if session_now.next_turn_ordinal != ordinal + 1:
                    raise RuntimeError(f"next_turn_ordinal mismatch after turn {ordinal}: {session_now.next_turn_ordinal}")
                if session_now.active_turn is not None:
                    raise RuntimeError(f"active_turn did not clear after turn {ordinal}")

                turn_record = tr_spy.results[idx]
                if turn_record.closure_state is not TurnClosureState.COMPLETED:
                    raise RuntimeError(f"turn {ordinal} TurnRecord is not COMPLETED: {turn_record.closure_state}")
                if entry.turn_id != turn_record.turn_id:
                    raise RuntimeError("entry.turn_id does not match the captured TurnRecord.turn_id")
                if entry.turn_record is not turn_record:
                    raise RuntimeError("captured SessionTurnEntry.turn_record is not the exact object Core produced")
                if entry.turn_id != ask_result.request_id:
                    raise RuntimeError("entry.turn_id does not match AskResult.request_id")

                # --- per-turn evidence accounting (never merged across turns) ---
                governed_evidence = ges_spy.results[idx]
                model_context = mc_spy.results[idx]

                retrieved_ids = [e.document_id for e in retrieve_spy.results[idx]]
                submitted_ids = list(governed_evidence.accounting.submitted_ids)
                admitted_ids = list(governed_evidence.accounting.governed_ids)
                model_context_ids = [item.candidate_id for item in model_context.evidence]
                rendered_ids = [row["document_id"] for row in ask_result.rendered.get("evidence", [])]

                # Fails closed (raises) on any subset-law violation; never
                # merely records one.
                assert_subset_law(
                    retrieved_ids=retrieved_ids, submitted_ids=submitted_ids, admitted_ids=admitted_ids,
                    model_context_ids=model_context_ids, rendered_ids=rendered_ids,
                )
                subset_checks = _subset_checks(retrieved_ids, submitted_ids, admitted_ids, model_context_ids, rendered_ids)
                if not all(subset_checks.values()):
                    raise AssertionError(f"subset law violated for turn {ordinal}: {subset_checks}")

                rendered_json = json.dumps(ask_result.rendered, sort_keys=True).encode("utf-8")
                turns.append(
                    TurnObservation(
                        ordinal=ordinal, question=question, turn_id=entry.turn_id,
                        request_id=ask_result.request_id,
                        context_pack_id=governed_evidence.context_pack_id,
                        question_id=governed_evidence.question_id,
                        closure_state=turn_record.closure_state.value,
                        retrieved_candidate_ids=retrieved_ids, submitted_candidate_ids=submitted_ids,
                        admitted_candidate_ids=admitted_ids, model_context_evidence_ids=model_context_ids,
                        rendered_evidence_ids=rendered_ids, subset_checks=subset_checks,
                        controlled_engine_execution_count=1,
                        rendered_response=ask_result.rendered, rendered_response_sha256=_sha256_bytes(rendered_json),
                    )
                )
                entry_snapshots.append(entry)

            # --- whole-history shape, after both turns ---
            session_after_turn2 = controller.get_session(session_id)
            if [e.turn_ordinal for e in session_after_turn2.ordered_turns] != [1, 2]:
                raise RuntimeError("session history ordinals are not exactly [1, 2] after turn 2")
            if session_after_turn2.ordered_turns[0] is not entry_snapshots[0]:
                raise RuntimeError("TURN 1 SessionTurnEntry changed identity after TURN 2 (append-only violated)")
            if turns[0].turn_id == turns[1].turn_id:
                raise RuntimeError("TURN 1 and TURN 2 turn_id are not distinct")

            # --- cross-turn negative proof: derived from actual observed
            # call arguments/boundaries, never hardcoded True ------------- #
            turn1_rendered_text = turns[0].rendered_response.get("primary_answer") or ""
            core_ask_params = set(inspect.signature(Core.ask).parameters)

            t2_ask_args, t2_ask_kwargs = core_ask_spy.calls[1]
            no_turn_record_in_t2_ask_call = not any(isinstance(a, TurnRecord) for a in t2_ask_args) and not any(
                isinstance(v, TurnRecord) for v in t2_ask_kwargs.values()
            )
            no_session_entry_in_t2_ask_call = not any(isinstance(a, SessionTurnEntry) for a in t2_ask_args) and not any(
                isinstance(v, SessionTurnEntry) for v in t2_ask_kwargs.values()
            )
            turn1_turn_record_not_input_to_turn2 = core_ask_params == _EXPECTED_CORE_ASK_PARAMS and no_turn_record_in_t2_ask_call
            turn1_session_entry_not_input_to_turn2 = core_ask_params == _EXPECTED_CORE_ASK_PARAMS and no_session_entry_in_t2_ask_call

            t2_retrieve_args, t2_retrieve_kwargs = retrieve_spy.calls[1]
            turn1_rendered_response_not_retrieval_input_to_turn2 = (
                t2_retrieve_args == (turn_2_question, top_k)
                and not t2_retrieve_kwargs
                and (not turn1_rendered_text or turn1_rendered_text not in str(t2_retrieve_args))
            )

            t2_govern_args, _t2_govern_kwargs = govern_spy.calls[1]
            t2_govern_request = t2_govern_args[0]
            t2_govern_candidate_ids = [c.document_id for c in t2_govern_request.candidates]
            t2_govern_candidate_content = [getattr(c, "content", "") for c in t2_govern_request.candidates]
            turn1_rendered_response_not_governance_input_to_turn2 = (
                t2_govern_candidate_ids == turns[1].retrieved_candidate_ids
                and (not turn1_rendered_text or all(turn1_rendered_text not in c for c in t2_govern_candidate_content))
            )

            t2_model_context = mc_spy.results[1]
            turn1_model_output_not_evidence_for_turn2 = not turn1_rendered_text or all(
                turn1_rendered_text not in item.content for item in t2_model_context.evidence
            )

            turn2_fresh_pipeline_executed = (
                retrieve_spy.call_count == 2
                and ges_spy.call_count == 2
                and mc_spy.call_count == 2
                and turns[0].context_pack_id != turns[1].context_pack_id
                and turns[0].question_id != turns[1].question_id
            )

            cross_turn_authority_checks = {
                "turn1_turn_record_not_input_to_turn2": turn1_turn_record_not_input_to_turn2,
                "turn1_session_entry_not_input_to_turn2": turn1_session_entry_not_input_to_turn2,
                "turn1_rendered_response_not_retrieval_input_to_turn2": turn1_rendered_response_not_retrieval_input_to_turn2,
                "turn1_rendered_response_not_governance_input_to_turn2": turn1_rendered_response_not_governance_input_to_turn2,
                "turn1_model_output_not_evidence_for_turn2": turn1_model_output_not_evidence_for_turn2,
                "turn2_fresh_pipeline_executed": turn2_fresh_pipeline_executed,
            }
            if not all(cross_turn_authority_checks.values()):
                raise AssertionError(f"cross-turn authority check failed: {cross_turn_authority_checks}")

            # --- provider counts (structural; no network was ever reachable) --- #
            gemini_is_controlled_only = (
                set(core._model_gateway._engines) == {"gemini"}
                and core._model_gateway._engines["gemini"] is controlled_engine
                and controlled_engine.provider == "CONTROLLED_FAKE"
            )
            _verify_no_forbidden_modules()
            provider_counts = {
                "real_gemini": 0 if gemini_is_controlled_only else 1,
                "openai": 0,
                "mive": mive_counter.call_count,
                "qdrant": 0 if isinstance(core._retrieval, InMemoryRetrieval) else 1,
            }
            if any(provider_counts.values()):
                raise AssertionError(f"provider-count guarantee violated: {provider_counts}")

            aggregate_counts = {
                "session_controller_run_turn_count": run_turn_spy.call_count,
                "core_ask_count": core_ask_spy.call_count,
                "retrieval_count": retrieve_spy.call_count,
                "governed_evidence_materialization_count": ges_spy.call_count,
                "model_context_build_count": mc_spy.call_count,
                "controlled_engine_execution_count": engine_spy.call_count,
                "turn_record_capture_count": len(session_after_turn2.ordered_turns),
            }
            if any(count != 2 for count in aggregate_counts.values()) or failed_tr_spy.call_count != 0:
                raise AssertionError(f"aggregate execution counts are not all exactly 2: {aggregate_counts}")

            pre_close_session = _session_dict(session_after_turn2)
            counts_before_close = dict(aggregate_counts)

            closed_session = controller.close_session(session_id)

            counts_after_close = {
                "session_controller_run_turn_count": run_turn_spy.call_count,
                "core_ask_count": core_ask_spy.call_count,
                "retrieval_count": retrieve_spy.call_count,
                "governed_evidence_materialization_count": ges_spy.call_count,
                "model_context_build_count": mc_spy.call_count,
                "controlled_engine_execution_count": engine_spy.call_count,
                "turn_record_capture_count": len(closed_session.ordered_turns),
            }
            post_close_session = _session_dict(closed_session)

            final_close_checks = {
                "status_closed": closed_session.status is SessionStatus.CLOSED,
                "ordered_ordinals_unchanged": post_close_session["ordered_ordinals"] == [1, 2],
                "entries_unchanged": (
                    closed_session.ordered_turns[0] is entry_snapshots[0]
                    and closed_session.ordered_turns[1] is entry_snapshots[1]
                ),
                "next_turn_ordinal_unchanged": closed_session.next_turn_ordinal == 3,
                "active_turn_none": closed_session.active_turn is None,
                "counts_unchanged_by_close": counts_after_close == counts_before_close,
                "close_not_counted_as_third_turn": run_turn_spy.call_count == 2 and core_ask_spy.call_count == 2,
            }
            if not all(final_close_checks.values()):
                raise AssertionError(f"final-close verification failed: {final_close_checks}")

        execution_profile = {
            "profile_id": core.execution_profile.profile_id,
            "profile_version": core.execution_profile.profile_version,
            "mode": core.execution_profile.mode.value,
        }

        return TwoTurnProof(
            repository_head=repository_head,
            source_sha256=source_sha256,
            session_id=session_id,
            initial_session=initial_session,
            execution_profile=execution_profile,
            turns=turns,
            aggregate_counts=aggregate_counts,
            cross_turn_authority_checks=cross_turn_authority_checks,
            provider_counts=provider_counts,
            pre_close_session=pre_close_session,
            post_close_session=post_close_session,
            final_close_checks=final_close_checks,
        )


# =========================================================================
# Receipt (structure defined now; writing it is not invoked by 22.4B)
# =========================================================================
def build_receipt(proof: TwoTurnProof, *, run_id: str) -> dict[str, Any]:
    return {
        "receipt_schema_id": RECEIPT_SCHEMA_ID,
        "receipt_version": RECEIPT_VERSION,
        "run_id": run_id,
        "executed_at_utc": _rfc3339_now_utc(),
        "repository_head": proof.repository_head,
        "source_path": CONTROLLED_SOURCE_RELATIVE_PATH,
        "source_sha256": proof.source_sha256,
        "session_id": proof.session_id,
        "initial_session": proof.initial_session,
        "execution_profile": proof.execution_profile,
        "turns": [dataclasses.asdict(t) for t in proof.turns],
        "aggregate_counts": proof.aggregate_counts,
        "cross_turn_authority_checks": proof.cross_turn_authority_checks,
        "provider_counts": proof.provider_counts,
        "pre_close_session": proof.pre_close_session,
        "post_close_session": proof.post_close_session,
        "final_close_checks": proof.final_close_checks,
    }


def write_receipt(receipt: dict[str, Any], path: Path) -> None:
    """Write the receipt ATOMICALLY (write-temp, then rename) so a reader
    never observes a partially-written file. Called only after every proof
    gate above has already passed; a failed gate raises before this point
    and no receipt is written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


# =========================================================================
# CLI — deliberately carries no --real / --gemini / --provider-live /
# --network switch, and reads no provider credential.
# =========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "TASK 22.4 controlled, network-free, two-turn Session/Turn Controller "
            "integration proof harness. Never executes a real provider call."
        )
    )
    parser.add_argument("--run-id", default=None, help="Receipt run identifier; defaults to a UTC-timestamp-derived id.")
    parser.add_argument("--receipt", type=Path, default=None, help="If given, write the JSON receipt to this path.")
    parser.add_argument(
        "--selfcheck", action="store_true",
        help="Verify the controlled source identity only and exit; does NOT run the two-turn proof.",
    )
    args = parser.parse_args(argv)

    if args.selfcheck:
        script_dir = Path(__file__).resolve().parent
        repo_root = discover_repo_root(script_dir)
        actual_sha256 = verify_source_identity(repo_root)
        print(json.dumps({"selfcheck": "PASS", "source_path": CONTROLLED_SOURCE_RELATIVE_PATH, "source_sha256": actual_sha256}, indent=2, sort_keys=True))
        return 0

    proof = run_controlled_two_turn_proof()

    run_id = args.run_id or ("task22-two-turn-controlled-" + _rfc3339_now_utc().replace(":", ""))
    receipt = build_receipt(proof, run_id=run_id)

    print(json.dumps(receipt, indent=2, sort_keys=True))

    if args.receipt is not None:
        write_receipt(receipt, args.receipt)
        print(f"receipt written to {args.receipt}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
