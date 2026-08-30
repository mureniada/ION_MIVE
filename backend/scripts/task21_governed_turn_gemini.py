"""TASK 21.2B — real Gemini governed-turn harness (LIVE PROVIDER).

Drives ONE real `Core.ask()` call through the SAME REAL Product governance
stack already proven in TASK 21.2A (real ingestion/canonical
materialization, real `InMemoryRetrieval`, real `CoreAdapter`, real runtime
evidence bridge, real provenance resolver, real admission gate, real
`GovernedEvidenceSet`, real `ModelContextAssembly`, `STANDARD_GEMINI`/
`SINGLE`, real `ModelGateway`, real `DeterministicRenderer`, real Turn
Record) — but with the REAL `GeminiIVE`/`GeminiBackend` registered at the
Model Gateway instead of TASK 21.2A's controlled deterministic engine.

Governance staging is NOT duplicated here: `discover_repo_root`,
`read_repository_head`, `stage_and_materialize_records`,
`records_to_retrieval_documents`, `RealFunctionSpy`, `assert_subset_law`,
`MiveCallCounter`, and the SHA256/RFC3339 helpers are imported from the
committed, unmodified TASK 21.2A dry harness (`scripts.task21_governed_turn`)
— that module is never edited by this file, and this file never forks its
governance-staging logic.

Scope and law (TASK 21.2B-H1):

    - `app.modules.gemini_ive.GeminiIVE` and `app.modules.gemini_ive.backend.
      GeminiBackend` are the REAL production classes, imported and
      constructed exactly as `app/container.py` constructs them. Importing
      and constructing them performs NO SDK import and NO client
      construction: `GeminiBackend`'s `google.genai` import is lazy, inside
      `_ensure()`, reached only from `.generate()`. This file exercises
      that guarantee rather than re-implementing it.
    - governance is never mocked, faked, short-circuited, or replaced —
      identical guarantee to TASK 21.2A, for the identical reason: `Core`'s
      own `__init__` always constructs a real `CoreAdapter()` and there is
      no parameter through which a substitute could be injected.
    - the ONLY new "real" component relative to TASK 21.2A is the provider
      path itself. No OpenAI path, no Qdrant path, no retry, no fallback,
      no second engine, no alternate execution profile.
    - a real provider request costs money and leaves provider-side logs the
      instant it is made. This file therefore performs an explicit SDK +
      credential PREFLIGHT check, and refuses to reach `Core.ask()` at all
      if either is missing — no attempt is silently downgraded, and no
      package is installed by this file.

H1 (this file, as written by TASK 21.2B-H1) BUILDS the harness only. No
function in this module is invoked by anything in this repository, and this
file is not executed as part of writing it, and no Gemini API call is made
while writing it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Reused, UNMODIFIED, from the committed TASK 21.2A dry harness. This is the
# ONE shared governance-staging implementation; it is imported, never copied.
# --------------------------------------------------------------------------- #
from scripts.task21_governed_turn import (
    APPROVED_QUESTION,
    CONTROLLED_SOURCE_RELATIVE_PATH,
    MiveCallCounter,
    RealFunctionSpy,
    _rfc3339_now_utc,
    _sha256_bytes,
    assert_subset_law,
    discover_repo_root,
    read_repository_head,
    records_to_retrieval_documents,
    stage_and_materialize_records,
    write_receipt,
)

# --------------------------------------------------------------------------- #
# Real Product components. The REAL Gemini provider path is imported here —
# this is the one file in TASK 21 authorized to do so — alongside the exact
# same non-provider real collaborators TASK 21.2A used. Deliberately NOT
# imported anywhere in this file: app.modules.openai_ive (no OpenAI path),
# qdrant_client / app.modules.retrieval.qdrant_store (no Qdrant path), and
# app.container (would pull in OpenAI/Qdrant by transitive top-level import).
# --------------------------------------------------------------------------- #
import app.core.orchestrator as orch
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.orchestrator import Core
from app.modules.context_pack import ContextPackBuilder
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import STANDARD_GEMINI, resolve_execution_profile
from app.modules.gemini_ive import GeminiIVE
from app.modules.gemini_ive.backend import GeminiBackend
from app.modules.mive import MIVEComparator
from app.modules.model_gateway import ModelGateway
from app.modules.renderer import DeterministicRenderer
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.memory_index import InMemoryRetrieval
from app.modules.telemetry import PricingTable

RECEIPT_SCHEMA_ID = "ION_TASK21_REAL_GEMINI_RECEIPT_V0_1"
PROVIDER_REPORTED_MODEL_NOT_CAPTURED = "NOT_CAPTURED"
EXTERNAL_HTTP_REQUEST_COUNT_UNVERIFIED = "UNVERIFIED"
SDK_INTERNAL_RETRY_STATUS_UNKNOWN = "UNKNOWN_OR_SDK_CONTROLLED"

# Names this harness must never construct. Checked structurally, at runtime,
# by `verify_real_gemini_composition()` below — this is the mirror image of
# TASK 21.2A's forbidden-list (which forbade GeminiIVE); here OpenAI/Qdrant
# remain forbidden, and GeminiIVE/GeminiBackend are REQUIRED instead.
_FORBIDDEN_COMPONENT_NAMES = (
    "OpenAIIVE",
    "OpenAIBackend",
    "QdrantRetrieval",
)


# =========================================================================
# Preflight: SDK + credential presence, BEFORE any governance or Core.ask()
# =========================================================================
class PreflightError(RuntimeError):
    """Raised when this harness must refuse to attempt a real Gemini turn.

    Raised BEFORE ingestion, BEFORE governance, BEFORE `Core` is
    constructed, and BEFORE any receipt could claim a provider attempt was
    made. Never raised after `Core.ask()` has been reached.
    """


def check_gemini_sdk_available() -> bool:
    """Presence check only. Does not import `google.genai` and constructs
    nothing. `importlib.util.find_spec` locates a module's spec without
    executing it; for `google.genai` this touches only the (side-effect-free)
    `google` namespace package, never the SDK's own `__init__`.
    """
    try:
        return importlib.util.find_spec("google.genai") is not None
    except ModuleNotFoundError:
        return False


def check_gemini_config_presence(env: dict[str, str] | None = None) -> dict[str, bool]:
    """Booleans only — never the values (mirrors `app.core.config.secret_presence`,
    extended with `GOOGLE_API_KEY`, which `GeminiBackend`'s lazy `genai.Client()`
    also accepts per its own docstring)."""
    e = env if env is not None else os.environ

    def present(name: str) -> bool:
        v = e.get(name)
        return bool(v and v.strip())

    return {
        "GEMINI_API_KEY": present("GEMINI_API_KEY"),
        "GOOGLE_API_KEY": present("GOOGLE_API_KEY"),
        "GEMINI_MODEL": present("GEMINI_MODEL"),
    }


@dataclass
class PreflightResult:
    sdk_available: bool
    config_presence: dict[str, bool]
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def run_preflight(env: dict[str, str] | None = None) -> PreflightResult:
    sdk_available = check_gemini_sdk_available()
    presence = check_gemini_config_presence(env)
    problems: list[str] = []
    if not sdk_available:
        problems.append("google-genai SDK is not installed/importable (google.genai)")
    if not (presence["GEMINI_API_KEY"] or presence["GOOGLE_API_KEY"]):
        problems.append("neither GEMINI_API_KEY nor GOOGLE_API_KEY is present")
    if not presence["GEMINI_MODEL"]:
        problems.append("GEMINI_MODEL is not present")
    return PreflightResult(sdk_available=sdk_available, config_presence=presence, problems=problems)


def read_requested_model(env: dict[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    model = e.get("GEMINI_MODEL", "")
    if not model.strip():
        raise PreflightError("GEMINI_MODEL is required and was not found present")
    return model


# =========================================================================
# Real-provider observation (pass-through only — D21-12, §13, §14)
# =========================================================================
class RealGeminiCallCounter:
    """Counts `run()` calls while forwarding, unchanged, to the REAL
    `GeminiIVE`. This is the Core/engine-execution-count observer
    (`core_engine_execution_count`). No response modification, no
    exception swallowing, no retry: any exception the real engine raises
    propagates through this wrapper untouched.
    """

    def __init__(self, real_engine: GeminiIVE) -> None:
        self._real = real_engine
        self.call_count = 0

    @property
    def engine_id(self) -> str:
        return self._real.engine_id

    @property
    def provider(self) -> str:
        return self._real.provider

    @property
    def model(self) -> str:
        return self._real.model

    def run(self, model_input: Any):
        self.call_count += 1
        return self._real.run(model_input)


class RealGeminiBackendCallCounter:
    """Counts `generate()` calls while forwarding, unchanged, to the REAL
    `GeminiBackend`. This is the backend-generate-count observer
    (`gemini_backend_generate_count`), distinct from
    `RealGeminiCallCounter.call_count`: one `GeminiIVE.run()` call is
    expected to correspond to exactly one `GeminiBackend.generate()` call,
    and this wrapper lets the receipt state that as an OBSERVED fact
    instead of an assumed one. Does not instrument `google.genai` itself —
    only this codebase's own call to it.
    """

    def __init__(self, real_backend: GeminiBackend) -> None:
        self._real = real_backend
        self.generate_count = 0

    def generate(self, *, system: str, user: str, schema: dict):
        self.generate_count += 1
        return self._real.generate(system=system, user=user, schema=schema)


# =========================================================================
# Composition (real Gemini path; no OpenAI; no Qdrant)
# =========================================================================
def verify_real_gemini_composition(
    core: Core,
    engine_counter: RealGeminiCallCounter,
    backend_counter: RealGeminiBackendCallCounter,
) -> None:
    """Design-time / composition-time guard, the mirror of TASK 21.2A's
    `verify_network_free_composition`: here the REAL `GeminiIVE`/
    `GeminiBackend` are REQUIRED, and OpenAI/Qdrant remain FORBIDDEN.
    """
    if not isinstance(core._retrieval, InMemoryRetrieval):
        raise AssertionError(
            f"expected InMemoryRetrieval; found {type(core._retrieval).__name__}"
        )
    engines = dict(core._model_gateway._engines)
    if set(engines) != {"gemini"}:
        raise AssertionError(
            f"expected exactly one registered engine id {{'gemini'}}, found {set(engines)}"
        )
    if engines["gemini"] is not engine_counter:
        raise AssertionError("registered 'gemini' engine is not the expected call-counter instance")
    if not isinstance(engine_counter._real, GeminiIVE):
        raise AssertionError(
            f"wrapped engine is not a real GeminiIVE; found {type(engine_counter._real).__name__}"
        )
    if engine_counter._real._backend is not backend_counter:
        raise AssertionError("real GeminiIVE is not wired to the expected backend call-counter")
    if not isinstance(backend_counter._real, GeminiBackend):
        raise AssertionError(
            f"wrapped backend is not a real GeminiBackend; found {type(backend_counter._real).__name__}"
        )
    if not isinstance(core._core_adapter, CoreAdapter):
        raise AssertionError(
            f"core._core_adapter is not a real CoreAdapter; found {type(core._core_adapter).__name__}"
        )
    observed_names = {type(core._retrieval).__name__, type(core._core_adapter).__name__}
    forbidden_hit = observed_names & set(_FORBIDDEN_COMPONENT_NAMES)
    if forbidden_hit:
        raise AssertionError(f"forbidden component present: {forbidden_hit}")


def build_core_for_real_gemini_run(
    retrieval_documents: list[dict[str, Any]], *, requested_model: str
) -> tuple[Core, RealGeminiCallCounter, RealGeminiBackendCallCounter, MiveCallCounter]:
    """Compose one real `Core` for the real-Gemini turn.

    Identical in every respect to TASK 21.2A's
    `build_core_for_controlled_dry_run` EXCEPT the registered engine: here
    it is the real `GeminiIVE` over the real `GeminiBackend`, each wrapped
    only by a call-counting pass-through (never a fake, never a
    substitute). `Settings` is loaded from an explicit dict, never
    `os.environ`, so this composition step itself reads no credential —
    the credential is read later, only by `GeminiBackend._ensure()`, only
    at the one `generate()` call this run makes.
    """
    settings = Settings.load(env={"VECTOR_COLLECTION": "TASK21_REAL_GEMINI_INMEMORY_FIXTURE"})

    embedder = HashingEmbedder(dimension=256)
    retrieval = InMemoryRetrieval(embedder)
    retrieval.index(retrieval_documents)

    execution_profile = resolve_execution_profile("STANDARD_GEMINI")
    if execution_profile is not STANDARD_GEMINI:
        raise RuntimeError(
            "resolve_execution_profile('STANDARD_GEMINI') did not return the "
            "canonical STANDARD_GEMINI singleton"
        )

    real_backend = GeminiBackend(requested_model)
    backend_counter = RealGeminiBackendCallCounter(real_backend)
    real_engine = GeminiIVE(backend_counter, model=requested_model, engine_id="gemini")
    engine_counter = RealGeminiCallCounter(real_engine)
    model_gateway = ModelGateway({"gemini": engine_counter})

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
    verify_real_gemini_composition(core, engine_counter, backend_counter)
    return core, engine_counter, backend_counter, mive_counter


# =========================================================================
# Outcome types — success and failure are distinguished, never overloaded
# =========================================================================
@dataclass
class RealGeminiRunObservation:
    """Everything observed about ONE successful real-Gemini governed turn."""

    repository_head: str
    source_path: str
    source_sha256: str
    question: str
    execution_profile_id: str
    execution_profile_version: str
    execution_mode: str
    engine_ids: tuple[str, ...]
    requested_model: str
    retrieved_candidate_ids: list[str]
    submitted_candidate_ids: list[str]
    admitted_candidate_ids: list[str]
    model_context_evidence_ids: list[str]
    rendered_evidence_ids: list[str]
    core_engine_execution_count: int
    gemini_backend_generate_count: int
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


@dataclass
class RealGeminiFailureInfo:
    """Facts observed before a real-Gemini turn failed. Never a raw
    traceback, never a raw exception message (may embed an endpoint, a
    payload fragment, or a credential — see `app/core/orchestrator.py`'s
    own `_turn_failure_for` policy, mirrored here deliberately)."""

    provider_attempted: bool
    error_type: str
    error_stage: str | None
    core_engine_execution_count: int
    gemini_backend_generate_count: int
    retrieved_candidate_ids: list[str]
    submitted_candidate_ids: list[str] | None
    admitted_candidate_ids: list[str] | None
    model_context_evidence_ids: list[str] | None


class RealGeminiTurnFailed(RuntimeError):
    def __init__(self, message: str, *, info: RealGeminiFailureInfo) -> None:
        super().__init__(message)
        self.info = info


# =========================================================================
# The real-Gemini turn itself
# =========================================================================
def run_real_gemini_turn(
    *, question: str = APPROVED_QUESTION, top_k: int = 1
) -> RealGeminiRunObservation:
    """Run exactly ONE real-Gemini governed turn.

    Raises `PreflightError` before any governance or `Core` activity if
    the SDK or credential/model configuration is missing. Raises
    `RealGeminiTurnFailed` (carrying `RealGeminiFailureInfo`) if the turn
    itself fails after preflight passed. Never retries. Never falls back.

    NOT invoked anywhere in this file except from `main()`, which is
    itself never invoked by TASK 21.2B-H1 (build-only phase).
    """
    preflight = run_preflight()
    if not preflight.ok:
        raise PreflightError("; ".join(preflight.problems))
    requested_model = read_requested_model()

    script_dir = Path(__file__).resolve().parent
    repo_root = discover_repo_root(script_dir)
    repository_head = read_repository_head(repo_root)

    with tempfile.TemporaryDirectory(prefix="ion_task21_real_gemini_") as tmp:
        tmp_root = Path(tmp)
        records = stage_and_materialize_records(repo_root, tmp_root)
        retrieval_documents = records_to_retrieval_documents(records)
        source_sha256 = records[0]["ion_source_provenance"]["source_file_sha256"]

        core, engine_counter, backend_counter, mive_counter = build_core_for_real_gemini_run(
            retrieval_documents, requested_model=requested_model
        )

        retrieved_ids: list[str] = []
        real_retrieve = core._retrieval.retrieve

        def spying_retrieve(q: str, k: int):
            result = real_retrieve(q, k)
            retrieved_ids.extend(e.document_id for e in result)
            return result

        core._retrieval.retrieve = spying_retrieve  # real forwarding wrapper only

        submitted_ids: list[str] | None = None
        admitted_ids: list[str] | None = None
        model_context_ids: list[str] | None = None

        try:
            with RealFunctionSpy(orch, "materialize_governed_evidence_set") as ges_spy, \
                 RealFunctionSpy(orch, "build_model_context") as mc_spy, \
                 RealFunctionSpy(orch, "materialize_turn_record") as tr_spy, \
                 RealFunctionSpy(orch, "materialize_failed_turn_record") as failed_tr_spy:
                result = core.ask(question, top_k=top_k, progress=None)

                if ges_spy.results:
                    submitted_ids = list(ges_spy.results[0].accounting.submitted_ids)
                    admitted_ids = list(ges_spy.results[0].accounting.governed_ids)
                if mc_spy.results:
                    model_context_ids = [item.candidate_id for item in mc_spy.results[0].evidence]
        except Exception as exc:  # noqa: BLE001 — captured for a truthful failure receipt only
            info = RealGeminiFailureInfo(
                provider_attempted=engine_counter.call_count > 0,
                error_type=type(exc).__name__,
                error_stage=getattr(exc, "stage", None),
                core_engine_execution_count=engine_counter.call_count,
                gemini_backend_generate_count=backend_counter.generate_count,
                retrieved_candidate_ids=retrieved_ids,
                submitted_candidate_ids=submitted_ids,
                admitted_candidate_ids=admitted_ids,
                model_context_evidence_ids=model_context_ids,
            )
            raise RealGeminiTurnFailed(
                f"real-Gemini governed turn failed: {type(exc).__name__}", info=info
            ) from exc

        if failed_tr_spy.call_count != 0:
            info = RealGeminiFailureInfo(
                provider_attempted=engine_counter.call_count > 0,
                error_type="TurnClosedFailed",
                error_stage=None,
                core_engine_execution_count=engine_counter.call_count,
                gemini_backend_generate_count=backend_counter.generate_count,
                retrieved_candidate_ids=retrieved_ids,
                submitted_candidate_ids=submitted_ids,
                admitted_candidate_ids=admitted_ids,
                model_context_evidence_ids=model_context_ids,
            )
            raise RealGeminiTurnFailed(
                "the turn closed FAILED although no exception propagated", info=info
            )
        if tr_spy.call_count != 1:
            raise RuntimeError(
                f"expected exactly one COMPLETED Turn Record materialization, "
                f"observed {tr_spy.call_count}"
            )
        if ges_spy.call_count != 1 or mc_spy.call_count != 1:
            raise RuntimeError(
                "expected exactly one GES materialization and one ModelContext "
                f"build, observed {ges_spy.call_count} / {mc_spy.call_count}"
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

        return RealGeminiRunObservation(
            repository_head=repository_head,
            source_path=CONTROLLED_SOURCE_RELATIVE_PATH,
            source_sha256=source_sha256,
            question=question,
            execution_profile_id=core.execution_profile.profile_id,
            execution_profile_version=core.execution_profile.profile_version,
            execution_mode=core.execution_profile.mode.value,
            engine_ids=core.execution_profile.engine_ids,
            requested_model=requested_model,
            retrieved_candidate_ids=retrieved_ids,
            submitted_candidate_ids=submitted_ids,
            admitted_candidate_ids=admitted_ids,
            model_context_evidence_ids=model_context_ids,
            rendered_evidence_ids=rendered_ids,
            core_engine_execution_count=engine_counter.call_count,
            gemini_backend_generate_count=backend_counter.generate_count,
            openai_execution_count=0,  # no "openai" key was ever registered; see verify_real_gemini_composition
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
# Receipts — success and failure are structurally distinct documents
# =========================================================================
def build_success_receipt(observation: RealGeminiRunObservation, *, run_id: str) -> dict[str, Any]:
    return {
        "receipt_schema_id": RECEIPT_SCHEMA_ID,
        "run_id": run_id,
        "executed_at_utc": _rfc3339_now_utc(),
        "repository_head": observation.repository_head,
        "run_mode": "REAL_GEMINI",
        "provider_execution": "REAL_GEMINI",
        "provider_attempted": True,
        "provider_succeeded": True,
        "real_gemini_executed": True,
        "source_path": observation.source_path,
        "source_sha256": observation.source_sha256,
        "question": observation.question,
        "execution_profile_id": observation.execution_profile_id,
        "execution_profile_version": observation.execution_profile_version,
        "execution_mode": observation.execution_mode,
        "engine_ids": list(observation.engine_ids),
        "requested_model": observation.requested_model,
        "provider_reported_model": PROVIDER_REPORTED_MODEL_NOT_CAPTURED,
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
        "core_engine_execution_count": observation.core_engine_execution_count,
        "gemini_backend_generate_count": observation.gemini_backend_generate_count,
        "external_http_request_count": EXTERNAL_HTTP_REQUEST_COUNT_UNVERIFIED,
        "sdk_internal_retry_status": SDK_INTERNAL_RETRY_STATUS_UNKNOWN,
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


def build_failure_receipt(
    failure: RealGeminiTurnFailed,
    *,
    run_id: str,
    repository_head: str,
    question: str,
    requested_model: str | None,
) -> dict[str, Any]:
    info = failure.info
    return {
        "receipt_schema_id": RECEIPT_SCHEMA_ID,
        "run_id": run_id,
        "executed_at_utc": _rfc3339_now_utc(),
        "repository_head": repository_head,
        "run_mode": "REAL_GEMINI",
        "provider_execution": "REAL_GEMINI",
        "provider_attempted": info.provider_attempted,
        "provider_succeeded": False,
        "real_gemini_executed": info.provider_attempted,
        "source_path": CONTROLLED_SOURCE_RELATIVE_PATH,
        "question": question,
        "requested_model": requested_model,
        "core_engine_execution_count": info.core_engine_execution_count,
        "gemini_backend_generate_count": info.gemini_backend_generate_count,
        "external_http_request_count": EXTERNAL_HTTP_REQUEST_COUNT_UNVERIFIED,
        "sdk_internal_retry_status": SDK_INTERNAL_RETRY_STATUS_UNKNOWN,
        "ask_result_status": "failure",
        "error_type": info.error_type,
        "error_stage": info.error_stage,
        "retrieved_candidate_ids": info.retrieved_candidate_ids,
        "submitted_candidate_ids": info.submitted_candidate_ids,
        "admitted_candidate_ids": info.admitted_candidate_ids,
        "model_context_evidence_ids": info.model_context_evidence_ids,
    }


# =========================================================================
# CLI — no --gemini/--real/--network switch: this file's entire purpose is
# the real-provider path, so no flag "enables" it; operator authorization
# and credential provisioning are what gate its use, not a CLI switch.
# =========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "TASK 21.2B real-Gemini governed-turn harness. Makes exactly one "
            "real Gemini provider request if preflight passes. Never retries, "
            "never falls back."
        )
    )
    parser.add_argument("--question", default=APPROVED_QUESTION)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="If given, write the JSON receipt (success or failure) to this path.",
    )
    args = parser.parse_args(argv)

    run_id = args.run_id or ("task21-real-gemini-" + _rfc3339_now_utc().replace(":", ""))

    try:
        observation = run_real_gemini_turn(question=args.question, top_k=args.top_k)
    except RealGeminiTurnFailed as failure:
        receipt = build_failure_receipt(
            failure,
            run_id=run_id,
            repository_head=_best_effort_repository_head(),
            question=args.question,
            requested_model=_best_effort_requested_model(),
        )
        print(json.dumps(receipt, indent=2, sort_keys=True), file=sys.stderr)
        if args.receipt is not None:
            write_receipt(receipt, args.receipt)
            print(f"failure receipt written to {args.receipt}", file=sys.stderr)
        return 1
    except PreflightError as exc:
        print(f"PREFLIGHT FAILED, no governance or provider activity occurred: {exc}", file=sys.stderr)
        return 2

    receipt = build_success_receipt(observation, run_id=run_id)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.receipt is not None:
        write_receipt(receipt, args.receipt)
        print(f"receipt written to {args.receipt}", file=sys.stderr)
    return 0


def _best_effort_repository_head() -> str:
    try:
        return read_repository_head(discover_repo_root(Path(__file__).resolve().parent))
    except Exception:  # noqa: BLE001 — best-effort only, for a failure receipt
        return "UNAVAILABLE"


def _best_effort_requested_model() -> str | None:
    try:
        return read_requested_model()
    except PreflightError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
