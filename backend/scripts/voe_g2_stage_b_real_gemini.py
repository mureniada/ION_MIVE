"""VOE G2 Stage B — variant B1: controlled IVE + ONE real Gemini composer call.

Drives ONE `Core.ask()` call through the same real Product governance stack
as VOE G2 Stage A (`scripts/voe_g2_stage_a_dry_run.py`) and TASK 21, with:

    - the IVE engine CONTROLLED: TASK 21.2A's `ControlledDeterministicEngine`
      (`provider == "CONTROLLED_FAKE"`, no provider call);
    - the VOE Response Composer REAL: `VOEResponseComposer` over the real
      `GeminiBackend`, constructed exactly as `app.container.build_voe_composer`
      constructs it (`GeminiBackend(model)`, `provider="gemini"`,
      `requested_model=model`), wrapped only by `OneCallComposerBackend`,
      which forwards at most ONE `generate()` call to the real backend and
      refuses any further one without forwarding it.

So a Stage B run makes at most exactly one real provider request. There is
no retry, no loop, no second engine, no variant switch, no question switch.

Operator-approved decisions this file implements (2026-09-28):
    D1 = B1 (controlled IVE + real Gemini composer, one real provider call);
    D2 = source identity is the COMMITTED BLOB of `corpus/README.md`
         (`git cat-file blob HEAD:corpus/README.md`, SHA-256
         `APPROVED_SOURCE_SHA256`), never working-copy bytes, which on a
         CRLF checkout differ only in line endings. The working-copy file is
         never read or modified by this harness.

Gates, all checked BEFORE any backend object exists (ABORTED receipt, no
provider-capable object constructed, if any fails):
    - environment presence (booleans only, never values): google-genai SDK
      locatable; EXACTLY ONE of GEMINI_API_KEY / GOOGLE_API_KEY; that key
      header-safe; GEMINI_MODEL present and whitespace-free; OPENAI_API_KEY
      absent; GEMINI_MODEL priced in `PricingTable` (unless explicitly
      allowed otherwise);
    - repository: working tree clean, HEAD equal to the operator-supplied
      `--expected-head`;
    - source: committed blob SHA-256 equals `APPROVED_SOURCE_SHA256`;
    - VOE profile: the committed bundle loads through the real loading path.

Secret handling: this module reads a credential value only to (a) test
header-safety and (b) prove, in memory, that no credential value appears in
the serialized receipt. It never prints, logs, stores or returns one. The
credential is used for the provider request only inside the SDK
(`GeminiBackend._ensure()` -> `genai.Client()`). A receipt that would contain
a credential value is withheld (`SecretLeakError`). Failure receipts carry an
exception TYPE and stage only, never a message.

CLI (run from `backend/`):
    preflight only (default; never constructs a backend):
        python -m scripts.voe_g2_stage_b_real_gemini [--expected-head SHA]
    the single real call (requires separate operator approval):
        python -m scripts.voe_g2_stage_b_real_gemini --execute-one-real-call \
            --expected-head SHA --receipt PATH
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import app.core.orchestrator as orch
from app.config_check import _key_is_header_safe
from app.core.clock import SystemClock
from app.core.orchestrator import Core
from app.modules.context_pack import ContextPackBuilder
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import STANDARD_GEMINI, resolve_execution_profile
from app.modules.gemini_ive.backend import GeminiBackend
from app.modules.mive import MIVEComparator
from app.modules.model_gateway import ModelGateway
from app.modules.renderer import DeterministicRenderer
from app.modules.response_composer import VOEResponseComposer
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.ingest import build_records
from app.modules.retrieval.memory_index import InMemoryRetrieval
from app.modules.retrieval.source_provenance import build_source_provenance
from app.modules.telemetry import PricingTable
from app.modules.voe_profile import VOEProfileLoadError, VOERuntimeProfile

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
    write_receipt,
)
from scripts.task21_governed_turn_gemini import (
    APPROVED_SOURCE_SHA256,
    EXTERNAL_HTTP_REQUEST_COUNT_UNVERIFIED,
    PROVIDER_REPORTED_MODEL_NOT_CAPTURED,
    SDK_INTERNAL_RETRY_STATUS_UNKNOWN,
)
from scripts.voe_g2_stage_a_dry_run import (
    _verify_composer_input,
    build_voe_enabled_settings,
    committed_voe_bundle_dir,
    load_voe_profile_through_settings,
)

RECEIPT_SCHEMA_ID = "ION_VOE_G2_STAGE_B_REAL_GEMINI_RECEIPT_V0_1"
HARNESS_IDENTITY = "ION_VOE_G2_STAGE_B_HARNESS_V0_1"
VARIANT = "B1"
QUESTION = APPROVED_QUESTION
TOP_K = 1
COMPOSER_PROVIDER = "gemini"

OUTCOME_ABORTED = "ABORTED_PREFLIGHT"
OUTCOME_PASS = "AUTOMATED_PASS_PENDING_HUMAN_REVIEW"
OUTCOME_SAFE_FAIL = "SAFE_FAIL_FALLBACK"
OUTCOME_CHECK_FAILED = "AUTOMATED_CHECK_FAILED"
OUTCOME_TURN_FAILED = "TURN_FAILED"

_EXIT_CODES = {OUTCOME_PASS: 0, OUTCOME_ABORTED: 3}

_CREDENTIAL_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
_SCANNED_SECRET_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY")

_FORBIDDEN_COMPONENT_NAMES = ("OpenAIIVE", "OpenAIBackend", "QdrantRetrieval")


class ProviderCallBudgetExceeded(RuntimeError):
    """A second real provider call was requested. It was NOT forwarded."""


class SecretLeakError(RuntimeError):
    """A credential value appears in the would-be receipt; it is withheld."""


def _rfc3339_now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
        cwd=repo_root,
        capture_output=True,
        check=True,
    ).stdout


# =========================================================================
# Environment preflight — presence booleans only, never values
# =========================================================================
def _sdk_probe() -> bool:
    """Locate `google.genai` without importing it or constructing anything."""
    try:
        return importlib.util.find_spec("google.genai") is not None
    except ImportError:
        return False


def _sdk_version() -> str | None:
    try:
        return importlib.metadata.version("google-genai")
    except importlib.metadata.PackageNotFoundError:
        return None


@dataclass
class EnvironmentCheck:
    sdk_available: bool
    presence: dict[str, bool]
    credential_header_safe: bool
    model_whitespace_free: bool
    model_priced: bool
    problems: list[str] = field(default_factory=list)

    def to_receipt(self) -> dict[str, Any]:
        return {
            "sdk_available": self.sdk_available,
            "presence": dict(self.presence),
            "credential_header_safe": self.credential_header_safe,
            "model_whitespace_free": self.model_whitespace_free,
            "model_priced": self.model_priced,
        }


def check_environment(env: Mapping[str, str], *, allow_unpriced_model: bool = False) -> EnvironmentCheck:
    def present(name: str) -> bool:
        value = env.get(name)
        return bool(value and value.strip())

    presence = {
        name: present(name)
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY")
    }
    credentials = [name for name in _CREDENTIAL_NAMES if presence[name]]
    header_safe = bool(credentials) and all(
        _key_is_header_safe(name, dict(env)) for name in credentials
    )
    model = env.get("GEMINI_MODEL") or ""
    model_whitespace_free = bool(model) and model == model.strip()
    model_priced = presence["GEMINI_MODEL"] and PricingTable().estimate_cost(model, 0, 0) is not None
    sdk_available = _sdk_probe()

    problems: list[str] = []
    if not sdk_available:
        problems.append("google-genai SDK is not locatable (google.genai)")
    if len(credentials) == 0:
        problems.append("neither GEMINI_API_KEY nor GOOGLE_API_KEY is present")
    elif len(credentials) > 1:
        problems.append("both GEMINI_API_KEY and GOOGLE_API_KEY are present; exactly one is required")
    elif not header_safe:
        problems.append("the present Gemini credential is not header-safe")
    if not presence["GEMINI_MODEL"]:
        problems.append("GEMINI_MODEL is not present")
    elif not model_whitespace_free:
        problems.append("GEMINI_MODEL carries leading/trailing whitespace")
    elif not model_priced and not allow_unpriced_model:
        problems.append("GEMINI_MODEL is not priced in PricingTable and unpriced models are not allowed")
    if presence["OPENAI_API_KEY"]:
        problems.append("OPENAI_API_KEY is present; it must be unset for Stage B")

    return EnvironmentCheck(
        sdk_available=sdk_available,
        presence=presence,
        credential_header_safe=header_safe,
        model_whitespace_free=model_whitespace_free,
        model_priced=model_priced,
        problems=problems,
    )


# =========================================================================
# Repository and committed-source gates
# =========================================================================
def read_worktree_status(repo_root: Path) -> str:
    return _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all").decode("utf-8")


@dataclass
class RepositoryCheck:
    head: str
    tree_clean: bool
    expected_head_supplied: bool
    head_matches_expected: bool
    problems: list[str] = field(default_factory=list)

    def to_receipt(self) -> dict[str, Any]:
        return {
            "repository_head": self.head,
            "tree_clean": self.tree_clean,
            "expected_head_supplied": self.expected_head_supplied,
            "head_matches_expected": self.head_matches_expected,
        }


def check_repository(repo_root: Path, expected_head: str | None) -> RepositoryCheck:
    head = read_repository_head(repo_root)
    tree_clean = read_worktree_status(repo_root).strip() == ""
    supplied = bool(expected_head)
    matches = supplied and head == expected_head
    problems: list[str] = []
    if not tree_clean:
        problems.append("working tree is not clean")
    if not supplied:
        problems.append("no expected HEAD was supplied")
    elif not matches:
        problems.append("HEAD does not equal the expected HEAD")
    return RepositoryCheck(head, tree_clean, supplied, matches, problems)


def read_committed_source_blob(repo_root: Path) -> bytes:
    """The committed bytes of `corpus/README.md` at HEAD (D2). Never reads,
    normalizes, or modifies the working-copy file."""
    return _git(repo_root, "cat-file", "blob", f"HEAD:{CONTROLLED_SOURCE_RELATIVE_PATH}")


def stage_and_materialize_committed_source(blob: bytes, tmp_root: Path) -> list[dict[str, Any]]:
    """Stage the committed blob as `README.txt` in a temp dir OUTSIDE the
    repository and run the real ingestion/canonical-materialization over it
    (same shape as TASK 21.2A's staging, but from the committed blob)."""
    staged_dir = tmp_root / "corpus"
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged_file = staged_dir / "README.txt"
    staged_file.write_bytes(blob)
    if _sha256_bytes(staged_file.read_bytes()) != APPROVED_SOURCE_SHA256:
        raise RuntimeError("staged source is not byte-identical to the approved committed blob")

    now = _rfc3339_now_utc()
    provenance = build_source_provenance(
        source_id="readme",
        source_origin="corpus-file://README.txt",
        source_file_sha256=APPROVED_SOURCE_SHA256,
        collector=HARNESS_IDENTITY,
        collected_at=now,
        collected_at_status="KNOWN",
        provenance_created_at=now,
        provenance_created_at_status="KNOWN",
    )
    records = build_records(
        staged_dir,
        source_provenance_by_source={"readme": provenance},
        materialize_canonical=True,
    )
    if not records:
        raise RuntimeError("real ingestion produced zero records from the committed source")
    return records


# =========================================================================
# The one-call composer backend wrapper
# =========================================================================
class OneCallComposerBackend:
    """Pass-through to the real composer backend that forwards AT MOST ONE
    `generate()` call. A second request raises `ProviderCallBudgetExceeded`
    WITHOUT being forwarded. Records what the composer sent, so the harness
    can verify it (same attribute names as Stage A's controlled backend)."""

    MAX_FORWARDED_CALLS = 1

    def __init__(self, real_backend: Any) -> None:
        self._real = real_backend
        self.attempt_count = 0
        self.forwarded_count = 0
        self.received_system: str | None = None
        self.received_user: str | None = None
        self.received_schema: dict | None = None

    def generate(self, *, system: str, user: str, schema: dict):
        self.attempt_count += 1
        if self.forwarded_count >= self.MAX_FORWARDED_CALLS:
            raise ProviderCallBudgetExceeded(
                "Stage B permits exactly one real provider call; a further call was refused"
            )
        self.received_system = system
        self.received_user = user
        self.received_schema = schema
        self.forwarded_count += 1
        return self._real.generate(system=system, user=user, schema=schema)


def verify_stage_b_composition(
    core: Core,
    controlled_engine: ControlledDeterministicEngine,
    composer: VOEResponseComposer,
    budget_backend: OneCallComposerBackend,
    voe_runtime_profile: VOERuntimeProfile,
) -> None:
    """Refuse to proceed unless Core is wired exactly as B1 requires."""
    checks = [
        (isinstance(core._retrieval, InMemoryRetrieval), "retrieval is not InMemoryRetrieval"),
        (set(core._model_gateway._engines) == {"gemini"}, "gateway must register exactly 'gemini'"),
        (core._model_gateway._engines.get("gemini") is controlled_engine, "IVE engine is not controlled"),
        (isinstance(core._core_adapter, CoreAdapter), "core adapter is not a real CoreAdapter"),
        (core._composer is composer, "Core does not hold the harness's composer"),
        (composer._backend is budget_backend, "composer backend is not the one-call wrapper"),
        (core._voe_runtime_profile is voe_runtime_profile, "Core does not hold the loaded profile"),
    ]
    for ok, message in checks:
        if not ok:
            raise AssertionError(message)
    observed = {type(core._retrieval).__name__, type(budget_backend._real).__name__}
    forbidden = observed & set(_FORBIDDEN_COMPONENT_NAMES)
    if forbidden:
        raise AssertionError(f"forbidden component present: {forbidden}")


# =========================================================================
# Receipt helpers
# =========================================================================
def _secret_values(env: Mapping[str, str]) -> list[str]:
    values = []
    for name in _SCANNED_SECRET_NAMES:
        value = env.get(name)
        if value and value.strip():
            values.extend({value, value.strip()})
    return values


def assert_receipt_free_of_secrets(receipt: dict[str, Any], env: Mapping[str, str]) -> None:
    serialized = json.dumps(receipt, sort_keys=True, ensure_ascii=False)
    for value in _secret_values(env):
        if value in serialized:
            raise SecretLeakError("a credential value appears in the receipt; the receipt is withheld")


def _base_receipt(
    *,
    run_id: str,
    env_check: EnvironmentCheck,
    repo_check: RepositoryCheck,
    requested_model: str | None,
    source: dict[str, Any],
    voe_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "receipt_schema_id": RECEIPT_SCHEMA_ID,
        "harness_identity": HARNESS_IDENTITY,
        "run_id": run_id,
        "executed_at_utc": _rfc3339_now_utc(),
        "stage": "VOE_G2_STAGE_B",
        "variant": VARIANT,
        "question": QUESTION,
        "repository": repo_check.to_receipt(),
        "preflight": env_check.to_receipt(),
        "sdk_version": _sdk_version(),
        "provider": COMPOSER_PROVIDER,
        "requested_model": requested_model,
        "provider_reported_model": PROVIDER_REPORTED_MODEL_NOT_CAPTURED,
        "sdk_internal_retry_status": SDK_INTERNAL_RETRY_STATUS_UNKNOWN,
        "external_http_request_count": EXTERNAL_HTTP_REQUEST_COUNT_UNVERIFIED,
        "source": source,
        "voe_profile": voe_profile,
        "pricing_as_of": PricingTable().as_of,
        "human_review": {"status": "PENDING", "recorded_separately": True},
    }


def _finalize(receipt: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    receipt["secret_value_absent_from_receipt"] = True
    assert_receipt_free_of_secrets(receipt, env)
    return receipt


# =========================================================================
# The Stage B run
# =========================================================================
def run_stage_b(
    *,
    env: Mapping[str, str],
    expected_head: str | None,
    run_id: str,
    allow_unpriced_model: bool = False,
    backend_factory: Callable[[str], Any] = GeminiBackend,
) -> dict[str, Any]:
    """Run B1 once and return its receipt (every outcome yields one).

    No backend object is constructed unless every gate passes. At most one
    real provider request is forwarded. Raises `SecretLeakError` instead of
    returning a receipt that would contain a credential value.
    """
    repo_root = discover_repo_root(Path(__file__).resolve().parent)
    env_check = check_environment(env, allow_unpriced_model=allow_unpriced_model)
    repo_check = check_repository(repo_root, expected_head)

    problems = list(env_check.problems) + list(repo_check.problems)

    blob = read_committed_source_blob(repo_root)
    blob_sha256 = _sha256_bytes(blob)
    source = {
        "path": CONTROLLED_SOURCE_RELATIVE_PATH,
        "identity_basis": "COMMITTED_BLOB_AT_HEAD",
        "committed_blob_sha256": blob_sha256,
        "approved_sha256": APPROVED_SOURCE_SHA256,
        "matches_approved": blob_sha256 == APPROVED_SOURCE_SHA256,
    }
    if not source["matches_approved"]:
        problems.append("committed corpus/README.md blob does not match the approved SHA-256")

    voe_runtime_profile: VOERuntimeProfile | None = None
    voe_profile: dict[str, Any] | None = None
    settings = build_voe_enabled_settings(committed_voe_bundle_dir())
    try:
        voe_runtime_profile = load_voe_profile_through_settings(settings)
    except VOEProfileLoadError:
        problems.append("the committed VOE profile bundle failed to load")
    else:
        binding = voe_runtime_profile.binding
        voe_profile = {
            "profile_id": binding.profile_id,
            "profile_version": binding.profile_version,
            "runtime_behavioral_fingerprint_sha256": binding.runtime_behavioral_fingerprint_sha256,
            "bundle_dir": "backend/app/modules/voe_profile/assets",
        }

    requested_model = env.get("GEMINI_MODEL") if env_check.model_whitespace_free else None
    receipt = _base_receipt(
        run_id=run_id,
        env_check=env_check,
        repo_check=repo_check,
        requested_model=requested_model,
        source=source,
        voe_profile=voe_profile,
    )

    if problems:
        receipt.update(
            outcome=OUTCOME_ABORTED,
            preflight_problems=problems,
            real_provider_executed=False,
            execution_counts={"real_provider_calls_forwarded": 0},
        )
        return _finalize(receipt, env)

    # ---- every gate passed: the only point a backend is ever constructed ----
    with tempfile.TemporaryDirectory(prefix="ion_voe_g2_stage_b_") as tmp:
        records = stage_and_materialize_committed_source(blob, Path(tmp))
        retrieval_documents = records_to_retrieval_documents(records)

    retrieval = InMemoryRetrieval(HashingEmbedder(dimension=256))
    retrieval.index(retrieval_documents)
    execution_profile = resolve_execution_profile("STANDARD_GEMINI")
    if execution_profile is not STANDARD_GEMINI:
        raise RuntimeError("STANDARD_GEMINI did not resolve to its canonical singleton")

    controlled_engine = ControlledDeterministicEngine()
    mive_counter = MiveCallCounter(MIVEComparator())
    real_backend = backend_factory(requested_model)
    budget_backend = OneCallComposerBackend(real_backend)
    composer = VOEResponseComposer(
        budget_backend, provider=COMPOSER_PROVIDER, requested_model=requested_model
    )
    core = Core(
        retrieval=retrieval,
        context_pack_builder=ContextPackBuilder(char_budget=settings.context_char_budget),
        model_gateway=ModelGateway({"gemini": controlled_engine}),
        mive=mive_counter,
        renderer=DeterministicRenderer(),
        pricing=PricingTable(),
        clock=SystemClock(),
        settings=settings,
        execution_profile=execution_profile,
        composer=composer,
        voe_runtime_profile=voe_runtime_profile,
    )
    verify_stage_b_composition(core, controlled_engine, composer, budget_backend, voe_runtime_profile)

    backend_class = type(real_backend).__name__
    retrieved_ids: list[str] = []
    real_retrieve = core._retrieval.retrieve

    def spying_retrieve(q: str, k: int):
        result = real_retrieve(q, k)
        retrieved_ids.extend(e.document_id for e in result)
        return result

    core._retrieval.retrieve = spying_retrieve  # real forwarding wrapper only

    try:
        with RealFunctionSpy(orch, "materialize_governed_evidence_set") as ges_spy, \
             RealFunctionSpy(orch, "build_model_context") as mc_spy, \
             RealFunctionSpy(orch, "materialize_turn_record") as tr_spy:
            result = core.ask(QUESTION, top_k=TOP_K)
    except Exception as exc:  # noqa: BLE001 — type and stage only, never the message
        receipt.update(
            outcome=OUTCOME_TURN_FAILED,
            failure={"error_type": type(exc).__name__, "error_stage": getattr(exc, "stage", None)},
            composer_backend_class=backend_class,
            real_provider_executed=(
                isinstance(real_backend, GeminiBackend) and budget_backend.forwarded_count > 0
            ),
            execution_counts={
                "ive_engine": controlled_engine.call_count,
                "real_provider_calls_forwarded": budget_backend.forwarded_count,
                "composer_generate_attempts": budget_backend.attempt_count,
                "openai": 0,
                "mive": mive_counter.call_count,
            },
        )
        return _finalize(receipt, env)

    receipt.update(
        _observe_completed_turn(
            result=result,
            core=core,
            controlled_engine=controlled_engine,
            mive_counter=mive_counter,
            budget_backend=budget_backend,
            real_backend=real_backend,
            voe_runtime_profile=voe_runtime_profile,
            retrieved_ids=retrieved_ids,
            governed_evidence=ges_spy.results[0] if ges_spy.results else None,
            model_context=mc_spy.results[0] if mc_spy.results else None,
            turn_records=tr_spy.results,
        )
    )
    return _finalize(receipt, env)


def _observe_completed_turn(
    *,
    result,
    core: Core,
    controlled_engine: ControlledDeterministicEngine,
    mive_counter: MiveCallCounter,
    budget_backend: OneCallComposerBackend,
    real_backend: Any,
    voe_runtime_profile: VOERuntimeProfile,
    retrieved_ids: list[str],
    governed_evidence,
    model_context,
    turn_records: list,
) -> dict[str, Any]:
    """Record every automated check as a boolean. After the provider call
    has happened, nothing here raises: the receipt must exist either way."""
    rendered = result.rendered
    operational_metrics = rendered.get("operational_metrics", {})
    composition = dict(operational_metrics.get("composition") or {})
    ive_report = result.ive_reports[0]

    submitted_ids = list(governed_evidence.accounting.submitted_ids) if governed_evidence else []
    admitted_ids = list(governed_evidence.accounting.governed_ids) if governed_evidence else []
    model_context_ids = [i.candidate_id for i in model_context.evidence] if model_context else []
    rendered_ids = [row["document_id"] for row in rendered.get("evidence", [])]
    try:
        assert_subset_law(
            retrieved_ids=retrieved_ids,
            submitted_ids=submitted_ids,
            admitted_ids=admitted_ids,
            model_context_ids=model_context_ids,
            rendered_ids=rendered_ids,
        )
        subset_ok = True
    except AssertionError:
        subset_ok = False

    try:
        _verify_composer_input(budget_backend, voe_runtime_profile, ive_report, QUESTION)
        composer_input_ok = True
    except Exception:  # noqa: BLE001 — recorded as a failed check
        composer_input_ok = False

    status = composition.get("status")
    base_answer = ive_report["abstract"]
    final_answer = rendered.get("primary_answer")
    turn_record = turn_records[0] if len(turn_records) == 1 else None
    binding = voe_runtime_profile.binding

    checks = {
        "ive_engine_ran_once": controlled_engine.call_count == 1,
        "exactly_one_real_provider_call_forwarded": budget_backend.forwarded_count == 1,
        "no_further_composer_call_attempted": budget_backend.attempt_count == 1,
        "no_mive_execution": mive_counter.call_count == 0,
        "subset_law_holds": subset_ok,
        "turn_record_completed_with_one_ive_execution": (
            turn_record is not None
            and turn_record.closure_state.value == "COMPLETED"
            and len(turn_record.model_executions) == 1
        ),
        "composer_input_verified": composer_input_ok,
        "composition_status_composed": status == "COMPOSED",
        "composition_bound_to_loaded_profile": (
            composition.get("voe_runtime_behavioral_fingerprint_sha256")
            == binding.runtime_behavioral_fingerprint_sha256
        ),
        "primary_answer_replaced": status == "COMPOSED" and final_answer != base_answer,
        "uncertainty_unchanged": rendered.get("uncertainty") == {"reported": list(ive_report["uncertainty"])},
        "tokens_reported": (
            composition.get("input_tokens") is not None and composition.get("output_tokens") is not None
        ),
        "usage_not_estimated": composition.get("usage_is_estimated") is False,
        "latency_recorded": composition.get("latency_ms") is not None,
        "single_metrics_snapshot": result.metrics == operational_metrics,
    }

    if status is not None and status.startswith("FALLBACK_"):
        outcome = OUTCOME_SAFE_FAIL
    elif status == "COMPOSED" and all(checks.values()):
        outcome = OUTCOME_PASS
    else:
        outcome = OUTCOME_CHECK_FAILED

    rendered_json = json.dumps(rendered, sort_keys=True).encode("utf-8")
    return {
        "outcome": outcome,
        "composer_backend_class": type(real_backend).__name__,
        "real_provider_executed": (
            isinstance(real_backend, GeminiBackend) and budget_backend.forwarded_count > 0
        ),
        "execution_counts": {
            "ive_engine": controlled_engine.call_count,
            "ive_engine_provider": "CONTROLLED_FAKE",
            "real_provider_calls_forwarded": budget_backend.forwarded_count,
            "composer_generate_attempts": budget_backend.attempt_count,
            "openai": 0,
            "mive": mive_counter.call_count,
        },
        "composer_input": {
            "system_instruction_sha256": (
                hashlib.sha256(budget_backend.received_system.encode("utf-8")).hexdigest()
                if budget_backend.received_system is not None
                else None
            ),
            "system_instruction_characters": (
                len(budget_backend.received_system) if budget_backend.received_system else None
            ),
            "user_payload_sha256": (
                hashlib.sha256(budget_backend.received_user.encode("utf-8")).hexdigest()
                if budget_backend.received_user is not None
                else None
            ),
        },
        "composition": composition,
        "answers": {
            "base_primary_answer": base_answer,
            "final_primary_answer": final_answer,
            "primary_answer_replaced": final_answer != base_answer,
        },
        "retrieved_candidate_ids": retrieved_ids,
        "submitted_candidate_ids": submitted_ids,
        "admitted_candidate_ids": admitted_ids,
        "model_context_evidence_ids": model_context_ids,
        "rendered_evidence_ids": rendered_ids,
        "ask_result_status": result.status,
        "turn_record": {
            "closure_state": turn_record.closure_state.value if turn_record else None,
            "model_execution_count": len(turn_record.model_executions) if turn_record else None,
        },
        "checks": checks,
        "rendered_response": rendered,
        "rendered_response_sha256": hashlib.sha256(rendered_json).hexdigest(),
    }


# =========================================================================
# CLI — preflight by default; exactly one flag enables the single real call.
# No question, variant, repeat, retry, or model-override switch exists.
# =========================================================================
def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    backend_factory: Callable[[str], Any] = GeminiBackend,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VOE G2 Stage B (B1): controlled IVE + ONE real Gemini composer call. "
            "Preflight only unless --execute-one-real-call is given."
        )
    )
    parser.add_argument("--execute-one-real-call", action="store_true")
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--allow-unpriced-model", action="store_true")
    args = parser.parse_args(argv)
    e = os.environ if env is None else env

    if not args.execute_one_real_call:
        repo_root = discover_repo_root(Path(__file__).resolve().parent)
        env_check = check_environment(e, allow_unpriced_model=args.allow_unpriced_model)
        repo_check = check_repository(repo_root, args.expected_head)
        blob_sha256 = _sha256_bytes(read_committed_source_blob(repo_root))
        report = {
            "mode": "PREFLIGHT_ONLY",
            "provider_call_made": False,
            "preflight": env_check.to_receipt(),
            "repository": repo_check.to_receipt(),
            "committed_source_matches_approved": blob_sha256 == APPROVED_SOURCE_SHA256,
            "problems": env_check.problems + repo_check.problems,
        }
        assert_receipt_free_of_secrets(report, e)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["problems"] and report["committed_source_matches_approved"] else 3

    if not args.expected_head or args.receipt is None:
        parser.error("--execute-one-real-call requires --expected-head and --receipt")

    run_id = args.run_id or ("voe-g2-stage-b-b1-" + _rfc3339_now_utc().replace(":", ""))
    receipt = run_stage_b(
        env=e,
        expected_head=args.expected_head,
        run_id=run_id,
        allow_unpriced_model=args.allow_unpriced_model,
        backend_factory=backend_factory,
    )
    write_receipt(receipt, args.receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print(f"receipt written to {args.receipt}", file=sys.stderr)
    return _EXIT_CODES.get(receipt["outcome"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
