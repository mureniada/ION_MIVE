"""VOE G2 Stage A — controlled, network-free, VOE-composed-turn dry-run harness.

Drives ONE real `Core.ask()` call with the VOE Response Composer wired in,
through the SAME real Product governance stack TASK 21.2A already exercises
(retrieval boundary, `CoreAdapter`, runtime evidence bridge, provenance
resolver, admission gate, `GovernedEvidenceSet` materializer, Model Context
builder, `ModelGateway`, `DeterministicRenderer`, Turn Record materializer),
and then through Gate 4's composition block in `Core.ask()`.

What is real:
    - the VOE Dialogue Profile, loaded through the real loading path:
      `Settings.load(explicit env)` -> `resolve_voe_profile(enabled=...,
      bundle_dir=...)` — the exact call `app.container.build_voe_composer`
      and `app.config_check.require_ready` make — over the committed,
      hash-pinned assets in `app/modules/voe_profile/assets/`;
    - `VOEResponseComposer` itself (system instruction, user payload,
      output schema, fail-closed output validation, local error mapping);
    - every governance component, exactly as TASK 21.2A runs it.

What is controlled (and must never be reported as a provider execution):
    - the IVE engine: TASK 21.2A's `ControlledDeterministicEngine`, reused
      unchanged (`provider == "CONTROLLED_FAKE"`);
    - the composer backend: `ControlledComposerBackend` below, a
      network-free stand-in for `GeminiBackend.generate(system, user,
      schema)`. Its composed text carries an explicit CONTROLLED FAKE
      prefix so no receipt can be mistaken for real provider output.

Scope is VOE G2 Stage A only:
    - NO provider call, NO provider adapter import (`app.modules.gemini_ive`,
      `app.modules.openai_ive`), NO `qdrant_client`, NO `app.container`
      (which would pull those in transitively);
    - NO credential read: `Settings` is built from an explicit dict, never
      `os.environ`;
    - the CLI carries no real/live/provider switch. Stage B (a real
      provider call) is a separate, separately authorized phase.

Run from `backend/`:  python -m scripts.voe_g2_stage_a_dry_run --composer-mode success
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Real Product components only. Deliberately NOT imported, anywhere in this
# file: app.container, app.modules.gemini_ive, app.modules.openai_ive,
# qdrant_client, openai, google.
# --------------------------------------------------------------------------- #
import app.core.orchestrator as orch
import app.modules.voe_profile as voe_profile_package
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.orchestrator import Core
from app.modules.context_pack import ContextPackBuilder
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import STANDARD_GEMINI, resolve_execution_profile
from app.modules.ive_common import GenerationResult
from app.modules.mive import MIVEComparator
from app.modules.model_gateway import ModelGateway
from app.modules.renderer import DeterministicRenderer
from app.modules.response_composer import (
    COMPOSER_RESPONSE_SCHEMA,
    VOEResponseComposer,
    build_composer_system_instruction,
)
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.memory_index import InMemoryRetrieval
from app.modules.telemetry import PricingTable
from app.modules.voe_profile import VOERuntimeProfile, resolve_voe_profile

from scripts.task21_governed_turn import (
    APPROVED_QUESTION,
    CONTROLLED_SOURCE_RELATIVE_PATH,
    ControlledDeterministicEngine,
    MiveCallCounter,
    RealFunctionSpy,
    assert_subset_law,
    discover_repo_root,
    read_repository_head,
    records_to_retrieval_documents,
    stage_and_materialize_records,
    write_receipt,
)

RECEIPT_SCHEMA_ID = "ION_VOE_G2_STAGE_A_DRY_RECEIPT_V0_1"
HARNESS_IDENTITY = "ION_VOE_G2_STAGE_A_HARNESS_V0_1"

FAKE_COMPOSER_PROVIDER = "CONTROLLED_FAKE"
FAKE_COMPOSER_MODEL = "voe-g2-stage-a-controlled-composer-backend-v0-1"
COMPOSED_TEXT_PREFIX = "[CONTROLLED FAKE COMPOSITION - not a provider output] "

# composer mode -> the composition status Core must disclose for it
EXPECTED_COMPOSITION_STATUS: dict[str, str] = {
    "success": "COMPOSED",
    "provider_error": "FALLBACK_PROVIDER_ERROR",
    "malformed_output": "FALLBACK_MALFORMED_OUTPUT",
}
COMPOSER_MODES = tuple(EXPECTED_COMPOSITION_STATUS)

# The exact keys `build_composer_user_payload` may emit, and per claim.
_EXPECTED_USER_PAYLOAD_KEYS = frozenset(
    {"question", "abstract", "highlights", "claims", "uncertainty", "confidence"}
)
_EXPECTED_CLAIM_KEYS = frozenset({"statement", "confidence"})

_FORBIDDEN_COMPONENT_NAMES = (
    "GeminiIVE",
    "GeminiBackend",
    "OpenAIIVE",
    "OpenAIBackend",
    "QdrantRetrieval",
)


class StageACheckError(RuntimeError):
    """A Stage A expectation did not hold. Raised, never recorded as a pass."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rfc3339_now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise StageACheckError(message)


# =========================================================================
# The real VOE profile loading path
# =========================================================================
def committed_voe_bundle_dir() -> Path:
    """The committed, hash-pinned runtime bundle shipped with the loader."""
    return Path(voe_profile_package.__file__).resolve().parent / "assets"


def build_voe_enabled_settings(bundle_dir: Path) -> Settings:
    """Settings for this dry run, from an explicit dict — never `os.environ`,
    so no provider credential can be read, even by accident.

    VOE is enabled through the same strict `VOE_PROFILE_ENABLED` parser the
    Product uses; the collection label can never be mistaken for the real
    corpus collection.
    """
    return Settings.load(
        env={
            "VECTOR_COLLECTION": "VOE_G2_STAGE_A_CONTROLLED_INMEMORY_FIXTURE",
            "VOE_PROFILE_ENABLED": "true",
            "VOE_PROFILE_BUNDLE_DIR": str(bundle_dir),
        }
    )


def load_voe_profile_through_settings(settings: Settings) -> VOERuntimeProfile:
    """The exact resolution call `app.container.build_voe_composer` and
    `app.config_check.require_ready` make. Any load failure propagates
    unchanged (`VOEProfileLoadError`) — never downgraded to "disabled"."""
    _check(settings.voe_profile_enabled is True, "VOE must be enabled for Stage A")
    profile = resolve_voe_profile(
        enabled=settings.voe_profile_enabled,
        bundle_dir=settings.voe_profile_bundle_dir,
    )
    _check(isinstance(profile, VOERuntimeProfile), "profile did not resolve")
    return profile


# =========================================================================
# The controlled composer backend (Stage A only — never a provider)
# =========================================================================
class ControlledProviderFailure(Exception):
    """The controlled stand-in for a provider/SDK/network failure."""


class ControlledComposerBackend:
    """A deterministic, network-free stand-in for `GeminiBackend.generate`.

    Same call shape (`generate(*, system, user, schema)`) and same return
    type (`GenerationResult`) as the real backend, so `VOEResponseComposer`
    runs unmodified. Constructs no SDK client and reads no credential.

    Modes:
      - "success": returns `{"composed_text": PREFIX + <abstract read from
        the received user payload>}` — the composed text is derived from
        what the composer actually sent, never from a value known before
        the turn ran;
      - "provider_error": raises `ControlledProviderFailure`;
      - "malformed_output": returns text that is not JSON.

    Usage is reported as unknown (tokens None, `usage_is_estimated=True`),
    exactly as TASK 21.2A's controlled engine does: no token count is ever
    fabricated. Exactly one call per instance; a second call raises.
    """

    def __init__(self, mode: str) -> None:
        if mode not in COMPOSER_MODES:
            raise ValueError(f"unknown composer mode {mode!r}; expected one of {COMPOSER_MODES}")
        self.mode = mode
        self.call_count = 0
        self.received_system: str | None = None
        self.received_user: str | None = None
        self.received_schema: dict | None = None

    def generate(self, *, system: str, user: str, schema: dict) -> GenerationResult:
        self.call_count += 1
        if self.call_count > 1:
            raise RuntimeError(
                "ControlledComposerBackend.generate() called more than once; "
                "Stage A requires exactly one composer execution per turn"
            )
        self.received_system = system
        self.received_user = user
        self.received_schema = schema

        if self.mode == "provider_error":
            raise ControlledProviderFailure("controlled provider failure (VOE G2 Stage A)")
        if self.mode == "malformed_output":
            return GenerationResult(text="controlled malformed output: not JSON", usage_is_estimated=True)

        abstract = json.loads(user)["abstract"]
        return GenerationResult(
            text=json.dumps({"composed_text": COMPOSED_TEXT_PREFIX + abstract}),
            input_tokens=None,
            output_tokens=None,
            usage_is_estimated=True,
        )


# =========================================================================
# Composition (no app.container; no network-capable adapter constructed)
# =========================================================================
def verify_network_free_voe_composition(
    core: Core,
    controlled_engine: ControlledDeterministicEngine,
    composer: VOEResponseComposer,
    composer_backend: ControlledComposerBackend,
    voe_runtime_profile: VOERuntimeProfile,
) -> None:
    """Refuse to proceed if any network-capable adapter is wired in, or if
    the composer/profile Core holds are not the ones this harness built."""
    _check(
        isinstance(core._retrieval, InMemoryRetrieval),
        f"harness requires InMemoryRetrieval; found {type(core._retrieval).__name__}",
    )
    engines = dict(core._model_gateway._engines)
    _check(set(engines) == {"gemini"}, f"expected exactly engine id 'gemini', found {set(engines)}")
    _check(engines["gemini"] is controlled_engine, "registered engine is not the controlled engine")
    _check(isinstance(core._core_adapter, CoreAdapter), "core adapter is not a real CoreAdapter")
    _check(core._composer is composer, "Core does not hold the harness's composer")
    _check(composer._backend is composer_backend, "composer does not hold the controlled backend")
    _check(
        core._voe_runtime_profile is voe_runtime_profile,
        "Core does not hold the profile the real loader produced",
    )
    observed = {
        type(core._retrieval).__name__,
        type(engines["gemini"]).__name__,
        type(core._core_adapter).__name__,
        type(composer_backend).__name__,
    }
    forbidden = observed & set(_FORBIDDEN_COMPONENT_NAMES)
    _check(not forbidden, f"forbidden network-capable component present: {forbidden}")


def build_core_for_voe_dry_run(
    retrieval_documents: list[dict[str, Any]],
    *,
    settings: Settings,
    voe_runtime_profile: VOERuntimeProfile,
    composer_mode: str,
) -> tuple[Core, ControlledDeterministicEngine, MiveCallCounter, ControlledComposerBackend]:
    """Compose one real `Core` with the VOE composer wired exactly as
    `app.container.build_core` wires it (`composer=`, `voe_runtime_profile=`),
    except that the composer's backend is the controlled stand-in."""
    embedder = HashingEmbedder(dimension=256)
    retrieval = InMemoryRetrieval(embedder)
    retrieval.index(retrieval_documents)

    execution_profile = resolve_execution_profile("STANDARD_GEMINI")
    _check(
        execution_profile is STANDARD_GEMINI,
        "resolve_execution_profile('STANDARD_GEMINI') did not return the canonical singleton",
    )

    controlled_engine = ControlledDeterministicEngine()
    model_gateway = ModelGateway({"gemini": controlled_engine})
    mive_counter = MiveCallCounter(MIVEComparator())

    composer_backend = ControlledComposerBackend(composer_mode)
    composer = VOEResponseComposer(
        composer_backend, provider=FAKE_COMPOSER_PROVIDER, requested_model=FAKE_COMPOSER_MODEL
    )

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
        composer=composer,
        voe_runtime_profile=voe_runtime_profile,
    )
    verify_network_free_voe_composition(
        core, controlled_engine, composer, composer_backend, voe_runtime_profile
    )
    return core, controlled_engine, mive_counter, composer_backend


# =========================================================================
# The controlled VOE-composed dry turn
# =========================================================================
@dataclass
class VOEDryRunObservation:
    """Everything the harness observed about one controlled composed turn."""

    repository_head: str
    composer_mode: str
    expected_composition_status: str
    source_path: str
    source_sha256: str
    question: str
    execution_profile_id: str
    execution_profile_version: str
    execution_mode: str
    engine_ids: tuple[str, ...]
    voe_profile_id: str
    voe_profile_version: str
    voe_runtime_behavioral_fingerprint_sha256: str
    voe_bundle_dir: str
    retrieved_candidate_ids: list[str]
    submitted_candidate_ids: list[str]
    admitted_candidate_ids: list[str]
    model_context_evidence_ids: list[str]
    rendered_evidence_ids: list[str]
    ive_engine_execution_count: int
    composer_backend_generate_count: int
    openai_execution_count: int
    mive_execution_count: int
    composer_system_instruction_sha256: str
    composer_system_instruction_characters: int
    composer_user_payload_sha256: str
    composer_user_payload_keys: list[str]
    base_primary_answer: str
    final_primary_answer: str
    composition: dict[str, Any]
    ask_result_status: str
    turn_record_closure_state: str
    turn_record_model_execution_count: int
    turn_record_engine_ids: list[str]
    rendered_response: dict[str, Any]
    rendered_response_sha256: str
    checks: dict[str, bool]


def _verify_composer_input(
    backend: ControlledComposerBackend,
    profile: VOERuntimeProfile,
    ive_report: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    """Verify what the composer actually sent against what it must send."""
    _check(backend.received_system is not None, "composer backend received no system instruction")
    _check(
        backend.received_system == build_composer_system_instruction(profile),
        "system instruction differs from the one built from the loaded profile",
    )
    _check(
        backend.received_schema is COMPOSER_RESPONSE_SCHEMA,
        "composer did not request its own COMPOSER_RESPONSE_SCHEMA",
    )
    payload = json.loads(backend.received_user)
    _check(
        set(payload) == _EXPECTED_USER_PAYLOAD_KEYS,
        f"user payload keys {sorted(payload)} differ from the approved projection",
    )
    _check(
        all(set(c) == _EXPECTED_CLAIM_KEYS for c in payload["claims"]),
        "a projected claim carries keys beyond statement/confidence",
    )
    _check(payload["question"] == question, "user payload question differs from the asked question")
    _check(payload["abstract"] == ive_report["abstract"], "user payload abstract differs from the IVE report")
    _check(
        payload["uncertainty"] == ive_report["uncertainty"],
        "user payload uncertainty differs from the IVE report",
    )
    return payload


def run_voe_dry_turn(
    *,
    composer_mode: str = "success",
    question: str = APPROVED_QUESTION,
    top_k: int = 1,
    bundle_dir: Path | None = None,
) -> VOEDryRunObservation:
    """Run exactly one controlled, network-free, VOE-composed governed turn.

    Every expectation below is enforced (`StageACheckError`), never merely
    recorded: a receipt is only ever built from an observation that passed.
    """
    if composer_mode not in COMPOSER_MODES:
        raise ValueError(f"unknown composer mode {composer_mode!r}; expected one of {COMPOSER_MODES}")
    expected_status = EXPECTED_COMPOSITION_STATUS[composer_mode]

    script_dir = Path(__file__).resolve().parent
    repo_root = discover_repo_root(script_dir)
    repository_head = read_repository_head(repo_root)

    resolved_bundle_dir = (bundle_dir or committed_voe_bundle_dir()).resolve()
    settings = build_voe_enabled_settings(resolved_bundle_dir)
    voe_runtime_profile = load_voe_profile_through_settings(settings)

    with tempfile.TemporaryDirectory(prefix="ion_voe_g2_stage_a_") as tmp:
        records = stage_and_materialize_records(repo_root, Path(tmp))
        retrieval_documents = records_to_retrieval_documents(records)
        source_sha256 = records[0]["ion_source_provenance"]["source_file_sha256"]

        core, controlled_engine, mive_counter, composer_backend = build_core_for_voe_dry_run(
            retrieval_documents,
            settings=settings,
            voe_runtime_profile=voe_runtime_profile,
            composer_mode=composer_mode,
        )

        retrieved_ids: list[str] = []
        real_retrieve = core._retrieval.retrieve

        def spying_retrieve(q: str, k: int):
            result = real_retrieve(q, k)
            retrieved_ids.extend(e.document_id for e in result)
            return result

        core._retrieval.retrieve = spying_retrieve  # real forwarding wrapper only

        with RealFunctionSpy(orch, "materialize_governed_evidence_set") as ges_spy, \
             RealFunctionSpy(orch, "build_model_context") as mc_spy, \
             RealFunctionSpy(orch, "materialize_turn_record") as tr_spy, \
             RealFunctionSpy(orch, "materialize_failed_turn_record") as failed_tr_spy:
            result = core.ask(question, top_k=top_k)

    _check(failed_tr_spy.call_count == 0, "the turn closed FAILED")
    _check(tr_spy.call_count == 1, f"expected one COMPLETED Turn Record, saw {tr_spy.call_count}")
    _check(ges_spy.call_count == 1, f"expected one GovernedEvidenceSet, saw {ges_spy.call_count}")
    _check(mc_spy.call_count == 1, f"expected one ModelContextAssembly, saw {mc_spy.call_count}")
    _check(result.status == "success", f"AskResult status is {result.status!r}")

    governed_evidence = ges_spy.results[0]
    model_context = mc_spy.results[0]
    turn_record = tr_spy.results[0]

    submitted_ids = list(governed_evidence.accounting.submitted_ids)
    admitted_ids = list(governed_evidence.accounting.governed_ids)
    model_context_ids = [item.candidate_id for item in model_context.evidence]
    rendered = result.rendered
    rendered_ids = [row["document_id"] for row in rendered.get("evidence", [])]
    assert_subset_law(
        retrieved_ids=retrieved_ids,
        submitted_ids=submitted_ids,
        admitted_ids=admitted_ids,
        model_context_ids=model_context_ids,
        rendered_ids=rendered_ids,
    )

    # --- execution counts ---
    _check(controlled_engine.call_count == 1, f"IVE engine ran {controlled_engine.call_count} times")
    _check(composer_backend.call_count == 1, f"composer backend ran {composer_backend.call_count} times")
    _check(mive_counter.call_count == 0, f"MIVE ran {mive_counter.call_count} times under SINGLE")
    model_executions = turn_record.model_executions
    _check(len(model_executions) == 1, "Turn Record must bind exactly one IVE execution")

    # --- what the composer received ---
    ive_report = result.ive_reports[0]
    payload = _verify_composer_input(composer_backend, voe_runtime_profile, ive_report, question)

    # --- what Core did with the composer's outcome ---
    operational_metrics = rendered["operational_metrics"]
    composition = operational_metrics.get("composition")
    _check(isinstance(composition, dict), "rendered operational_metrics carries no composition block")
    _check(
        composition["status"] == expected_status,
        f"composition status {composition['status']!r}, expected {expected_status!r}",
    )
    binding = voe_runtime_profile.binding
    _check(composition["voe_profile_id"] == binding.profile_id, "composition profile_id mismatch")
    _check(composition["voe_profile_version"] == binding.profile_version, "composition version mismatch")
    _check(
        composition["voe_runtime_behavioral_fingerprint_sha256"]
        == binding.runtime_behavioral_fingerprint_sha256,
        "composition fingerprint mismatch",
    )
    _check(result.metrics == operational_metrics, "AskResult.metrics and rendered metrics differ")

    base_primary_answer = ive_report["abstract"]
    final_primary_answer = rendered["primary_answer"]
    if expected_status == "COMPOSED":
        _check(
            final_primary_answer == COMPOSED_TEXT_PREFIX + base_primary_answer,
            "composed primary_answer is not the controlled composition of the IVE abstract",
        )
        _check(composition["provider"] == FAKE_COMPOSER_PROVIDER, "composition provider mislabelled")
        _check(composition["model"] == FAKE_COMPOSER_MODEL, "composition model mislabelled")
    else:
        _check(
            final_primary_answer == base_primary_answer,
            "fallback turn did not ship the deterministic base answer",
        )
        _check(composition["provider"] is None, "fallback must not claim a provider")
        _check(composition["latency_ms"] is None, "fallback must not claim a latency")

    _check(
        rendered["uncertainty"] == {"reported": list(ive_report["uncertainty"])},
        "rendered uncertainty differs from the IVE report",
    )

    checks = {
        "real_governance_ran": True,
        "voe_profile_loaded_through_settings": True,
        "system_instruction_built_from_loaded_profile": True,
        "composer_schema_is_composer_response_schema": True,
        "user_payload_is_approved_projection_only": True,
        "composition_status_as_expected": True,
        "primary_answer_as_expected": True,
        "uncertainty_unchanged": True,
        "subset_law_holds": True,
        "single_metrics_snapshot": True,
        "turn_record_binds_one_ive_execution": True,
        "no_mive_execution": True,
    }

    rendered_json = json.dumps(rendered, sort_keys=True).encode("utf-8")
    return VOEDryRunObservation(
        repository_head=repository_head,
        composer_mode=composer_mode,
        expected_composition_status=expected_status,
        source_path=CONTROLLED_SOURCE_RELATIVE_PATH,
        source_sha256=source_sha256,
        question=question,
        execution_profile_id=core.execution_profile.profile_id,
        execution_profile_version=core.execution_profile.profile_version,
        execution_mode=core.execution_profile.mode.value,
        engine_ids=core.execution_profile.engine_ids,
        voe_profile_id=binding.profile_id,
        voe_profile_version=binding.profile_version,
        voe_runtime_behavioral_fingerprint_sha256=binding.runtime_behavioral_fingerprint_sha256,
        voe_bundle_dir=_repo_relative(resolved_bundle_dir, repo_root),
        retrieved_candidate_ids=retrieved_ids,
        submitted_candidate_ids=submitted_ids,
        admitted_candidate_ids=admitted_ids,
        model_context_evidence_ids=model_context_ids,
        rendered_evidence_ids=rendered_ids,
        ive_engine_execution_count=controlled_engine.call_count,
        composer_backend_generate_count=composer_backend.call_count,
        openai_execution_count=0,  # no "openai" engine registered; see verify_network_free_voe_composition
        mive_execution_count=mive_counter.call_count,
        composer_system_instruction_sha256=_sha256_text(composer_backend.received_system),
        composer_system_instruction_characters=len(composer_backend.received_system),
        composer_user_payload_sha256=_sha256_text(composer_backend.received_user),
        composer_user_payload_keys=sorted(payload),
        base_primary_answer=base_primary_answer,
        final_primary_answer=final_primary_answer,
        composition=dict(composition),
        ask_result_status=result.status,
        turn_record_closure_state=turn_record.closure_state.value,
        turn_record_model_execution_count=len(model_executions),
        turn_record_engine_ids=[m.engine_id for m in model_executions],
        rendered_response=rendered,
        rendered_response_sha256=hashlib.sha256(rendered_json).hexdigest(),
        checks=checks,
    )


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


# =========================================================================
# Receipt
# =========================================================================
def build_receipt(observation: VOEDryRunObservation, *, run_id: str) -> dict[str, Any]:
    return {
        "receipt_schema_id": RECEIPT_SCHEMA_ID,
        "harness_identity": HARNESS_IDENTITY,
        "run_id": run_id,
        "executed_at_utc": _rfc3339_now_utc(),
        "repository_head": observation.repository_head,
        "stage": "VOE_G2_STAGE_A",
        "run_mode": "CONTROLLED_DRY",
        "provider_execution": "CONTROLLED_FAKE",
        "real_provider_executed": False,
        "credentials_read": False,
        "composer_mode": observation.composer_mode,
        "expected_composition_status": observation.expected_composition_status,
        "observed_composition_status": observation.composition["status"],
        "source_path": observation.source_path,
        "source_sha256": observation.source_sha256,
        "question": observation.question,
        "execution_profile_id": observation.execution_profile_id,
        "execution_profile_version": observation.execution_profile_version,
        "execution_mode": observation.execution_mode,
        "engine_ids": list(observation.engine_ids),
        "voe_profile": {
            "profile_id": observation.voe_profile_id,
            "profile_version": observation.voe_profile_version,
            "runtime_behavioral_fingerprint_sha256": (
                observation.voe_runtime_behavioral_fingerprint_sha256
            ),
            "bundle_dir": observation.voe_bundle_dir,
            "loaded_via": "Settings.load(explicit env) -> resolve_voe_profile",
        },
        "execution_counts": {
            "ive_engine": observation.ive_engine_execution_count,
            "composer_backend_generate": observation.composer_backend_generate_count,
            "openai": observation.openai_execution_count,
            "mive": observation.mive_execution_count,
        },
        "composer_input": {
            "system_instruction_sha256": observation.composer_system_instruction_sha256,
            "system_instruction_characters": observation.composer_system_instruction_characters,
            "user_payload_sha256": observation.composer_user_payload_sha256,
            "user_payload_keys": observation.composer_user_payload_keys,
        },
        "answers": {
            "base_primary_answer": observation.base_primary_answer,
            "final_primary_answer": observation.final_primary_answer,
            "primary_answer_replaced": (
                observation.final_primary_answer != observation.base_primary_answer
            ),
        },
        "composition": observation.composition,
        "retrieved_candidate_ids": observation.retrieved_candidate_ids,
        "submitted_candidate_ids": observation.submitted_candidate_ids,
        "admitted_candidate_ids": observation.admitted_candidate_ids,
        "model_context_evidence_ids": observation.model_context_evidence_ids,
        "rendered_evidence_ids": observation.rendered_evidence_ids,
        "ask_result_status": observation.ask_result_status,
        "turn_record": {
            "closure_state": observation.turn_record_closure_state,
            "model_execution_count": observation.turn_record_model_execution_count,
            "engine_ids": observation.turn_record_engine_ids,
        },
        "checks": dict(observation.checks),
        "rendered_response": observation.rendered_response,
        "rendered_response_sha256": observation.rendered_response_sha256,
    }


# =========================================================================
# CLI — deliberately carries no --real / --live / --provider switch, and
# reads no provider credential.
# =========================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VOE G2 Stage A controlled, network-free, VOE-composed turn harness. "
            "Never executes a real provider call."
        )
    )
    parser.add_argument("--composer-mode", choices=COMPOSER_MODES, default="success")
    parser.add_argument("--question", default=APPROVED_QUESTION)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--receipt", type=Path, default=None, help="If given, write the JSON receipt to this path."
    )
    args = parser.parse_args(argv)

    observation = run_voe_dry_turn(
        composer_mode=args.composer_mode, question=args.question, top_k=args.top_k
    )
    run_id = args.run_id or (
        f"voe-g2-stage-a-{args.composer_mode}-" + _rfc3339_now_utc().replace(":", "")
    )
    receipt = build_receipt(observation, run_id=run_id)
    print(json.dumps(receipt, indent=2, sort_keys=True))

    if args.receipt is not None:
        write_receipt(receipt, args.receipt)
        print(f"receipt written to {args.receipt}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
