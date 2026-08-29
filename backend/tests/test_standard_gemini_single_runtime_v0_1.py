"""TASK 20.3B contract test: STANDARD_GEMINI/SINGLE as the LIVE execution
policy — the atomic runtime cutover.

Three concerns, kept separate:

    CONTAINER COMPOSITION   Settings -> resolved profile -> engines -> Core
    READINESS               profile-driven require_ready, no OpenAI required
    RUNTIME                 a real Core.ask() executing under STANDARD_GEMINI

The runtime section reuses the proven stand-in pattern from
`test_orchestrator_turn_record_v0_1.py` (a real `Core`/`CoreAdapter` over a
stand-in bridge, retrieval and builder): only the seams are fake, `ask()`
itself is genuine. This avoids the unrelated, pre-existing canonical
evidence/provenance fixture condition that affects real end-to-end runs
using document id "d1" in this environment (see that file's docstring and
`test_core_ask_mocked.py`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.container import (
    _build_engines,
    build_core,
    resolve_active_execution_profile,
)
from app.config_check import require_ready
from app.core import errors
from app.core.config import Settings
from app.core.errors import ConfigurationError, ProviderError
import app.core.orchestrator as orch
import app.modules.core_adapter.facade as facade
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import ExecutionMode, STANDARD_GEMINI
from app.modules.model_gateway import ModelGateway
from app.modules.turn_record import TurnClosureState

VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"

GEMINI_MODEL = "gemini-3.1-flash-lite"


def _offline_settings(**overrides):
    values = {
        "EXECUTION_PROFILE": "STANDARD_GEMINI",
        "EMBEDDING_BACKEND": "fake",
        "GEMINI_MODEL": GEMINI_MODEL,
    }
    values.update(overrides)
    return Settings.load(values)


# =========================================================================
# CONTAINER COMPOSITION (§9, §10, §34)
# =========================================================================
def test_resolve_active_execution_profile_returns_standard_gemini_by_identity():
    settings = _offline_settings()
    assert resolve_active_execution_profile(settings) is STANDARD_GEMINI


def test_resolve_active_execution_profile_missing_id_fails_closed():
    settings = _offline_settings(EXECUTION_PROFILE="")
    assert settings.execution_profile_id == ""
    with pytest.raises(ConfigurationError):
        resolve_active_execution_profile(settings)


def test_resolve_active_execution_profile_unknown_id_fails_closed():
    settings = _offline_settings(EXECUTION_PROFILE="NOT_A_REAL_PROFILE")
    with pytest.raises(ConfigurationError):
        resolve_active_execution_profile(settings)


def test_resolve_active_execution_profile_case_or_whitespace_variant_fails_closed():
    for variant in ("standard_gemini", " STANDARD_GEMINI", "STANDARD_GEMINI "):
        settings = _offline_settings(EXECUTION_PROFILE=variant)
        with pytest.raises(ConfigurationError):
            resolve_active_execution_profile(settings)


def test_build_engines_constructs_gemini_only_under_standard_gemini():
    settings = _offline_settings()
    engines = _build_engines(STANDARD_GEMINI, settings)
    assert set(engines) == {"gemini"}
    assert engines["gemini"].engine_id == "gemini"


def test_build_core_under_standard_gemini_has_no_openai_engine_registered():
    settings = _offline_settings()
    core = build_core(settings)
    assert core.execution_profile is STANDARD_GEMINI
    # the Gateway itself proves it: an id it never registered is refused —
    # the SAME fail-closed behaviour a genuinely unregistered id gets.
    with pytest.raises(ConfigurationError):
        core._model_gateway.execute("openai", object())


def test_build_core_injects_the_resolved_profile_by_identity():
    settings = _offline_settings()
    core = build_core(settings)
    assert core.execution_profile is STANDARD_GEMINI
    assert core.execution_profile.profile_id == "STANDARD_GEMINI"
    assert core.execution_profile.profile_version == "0.1"
    assert core.execution_profile.mode is ExecutionMode.SINGLE
    assert core.execution_profile.engine_ids == ("gemini",)


def test_build_core_fails_closed_on_missing_profile_configuration():
    settings = _offline_settings(EXECUTION_PROFILE="")
    with pytest.raises(ConfigurationError):
        build_core(settings)


def test_build_engines_unrecognized_engine_id_fails_closed():
    from app.modules.execution_profile import ExecutionProfile

    bogus = ExecutionProfile(
        profile_id="X", profile_version="0.1", mode=ExecutionMode.SINGLE,
        engine_ids=("not-a-real-engine",),
    )
    with pytest.raises(ConfigurationError):
        _build_engines(bogus, _offline_settings())


# =========================================================================
# READINESS WITHOUT OPENAI (§11, §32, §37)
# =========================================================================
def test_standard_gemini_pilot_is_ready_with_only_gemini_configured():
    """The exact pilot-viability proof: GEMINI_API_KEY/GEMINI_MODEL present,
    OPENAI_API_KEY/OPENAI_MODEL entirely absent — STANDARD_GEMINI is READY."""
    settings = _offline_settings()  # OPENAI_MODEL never set
    env = {"GEMINI_API_KEY": "gk-abc123"}  # OPENAI_API_KEY never set
    require_ready(settings, STANDARD_GEMINI, env=env)  # should not raise


def test_standard_gemini_composition_and_readiness_together_offline():
    """The full pre-turn composition sequence, offline: resolve, compose,
    then check readiness against the SAME resolved profile — no network, no
    provider call, matching the main.py seam exactly (core.execution_profile
    -> require_ready)."""
    settings = _offline_settings()
    core = build_core(settings)
    require_ready(settings, core.execution_profile, env={"GEMINI_API_KEY": "gk-abc123"})


# =========================================================================
# RUNTIME: a real Core.ask() under STANDARD_GEMINI (§35, §38, §39)
# =========================================================================
class _Clock:
    def __init__(self):
        self.value = 0

    def monotonic_ms(self):
        self.value += 1
        return float(self.value)

    def now_iso(self):
        return "2026-08-29T00:00:00Z"


class _Retrieval:
    def __init__(self, candidate_ids):
        self._candidate_ids = tuple(candidate_ids)
        self.calls = 0

    def retrieve(self, question, top_k):
        self.calls += 1
        return [
            SimpleNamespace(document_id=cid, content="body") for cid in self._candidate_ids
        ]


class _Builder:
    def __init__(self, pack):
        self.pack = pack

    def build(self, question, evidence):
        return self.pack


class _Bridge:
    backend_id = "TEST-BACKEND"
    mapping_profile_id = "TEST-PROFILE"

    def resolve(self, evidence):
        return ()

    def build_request(self, *args, **kwargs):
        return SimpleNamespace(accepted=True, request=SimpleNamespace(), reasons=())


def _adapter():
    adapter = CoreAdapter.__new__(CoreAdapter)
    adapter._bridge = _Bridge()
    return adapter


def _native_for(candidate_ids):
    return SimpleNamespace(
        records=tuple(
            SimpleNamespace(
                evidence_id=cid, status=VERIFIED, validation_id="VAL-" + cid,
                fingerprint=SimpleNamespace(algorithm="SHA256", hash="FP-" + cid, content_id=cid),
            )
            for cid in candidate_ids
        ),
        validations=tuple(
            SimpleNamespace(
                validation_id="VAL-" + cid, evidence_id=cid, result=PASS,
                blocking_reasons=(), evidence_fingerprint_hash="FP-" + cid,
            )
            for cid in candidate_ids
        ),
        transitions=tuple(
            SimpleNamespace(
                transition_id="TR-" + cid, evidence_id=cid,
                from_status=PENDING, to_status=VERIFIED, validation_id="VAL-" + cid,
            )
            for cid in candidate_ids
        ),
    )


def _pack(document_ids):
    return SimpleNamespace(
        context_pack_id="CP-001",
        documents=[
            SimpleNamespace(
                document_id=did, content="body-" + did, title="Title-" + did,
                source="SRC-" + did, page=None, chunk_id=None,
            )
            for did in document_ids
        ],
        metadata={"included_documents": len(tuple(document_ids))},
    )


class _Engine:
    def __init__(self, engine_id, *, error=None):
        self._engine_id = engine_id
        self.provider = engine_id
        self.model = GEMINI_MODEL
        self.calls = 0
        self.error = error

    @property
    def engine_id(self):
        return self._engine_id

    def run(self, model_input):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            engine_id=self._engine_id, provider=self.provider, model=self.model,
            abstract="a truthful single-engine synthesis",
            claims=[],
            uncertainty=["Origins of money are debated."],
            usage=SimpleNamespace(
                input_tokens=11, output_tokens=5, latency_ms=1.5, usage_is_estimated=False,
            ),
            to_contract_dict=lambda: {"engine_id": self._engine_id, "provider": self.provider},
        )


class _Mive:
    def __init__(self):
        self.calls = 0

    def compare(self, reports):
        self.calls += 1
        raise AssertionError("MIVE must never be called under SINGLE")


class _Pricing:
    def estimate_cost(self, model, input_tokens, output_tokens):
        return 0.5


def _real_renderer_stub():
    """A minimal but genuine RendererPort-shaped double: exercises the ACTUAL
    `render_single` contract shape (kwargs), without needing a real
    ModelContextAssembly.evidence tuple for this wiring-focused test."""

    class _Renderer:
        def __init__(self):
            self.render_calls = 0
            self.render_single_calls = 0
            self.last_kwargs = None

        def render(self, **kwargs):
            self.render_calls += 1
            return {"primary_answer": "comparison answer"}

        def render_single(self, **kwargs):
            self.render_single_calls += 1
            self.last_kwargs = kwargs
            return {
                "question": kwargs["question"],
                "primary_answer": kwargs["report"].abstract,
                "mive_assessment": None,
                "uncertainty": {"reported": kwargs["report"].uncertainty},
                "evidence": [],
                "operational_metrics": kwargs["metrics_dict"],
                "disclaimer": "single-engine disclaimer",
            }

    return _Renderer()


def _core(*, gemini_error=None, retrieved=("EV-1", "EV-2"), submitted=("EV-1", "EV-2")):
    pack = _pack(submitted)
    clock = _Clock()
    renderer = _real_renderer_stub()
    gemini_engine = _Engine("gemini", error=gemini_error)

    core = orch.Core.__new__(orch.Core)
    core._settings = SimpleNamespace(
        default_top_k=1, context_char_budget=60000, qdrant_collection="ion_corpus_v1",
    )
    core._clock = clock
    core._retrieval = _Retrieval(retrieved)
    core._build = _Builder(pack)
    core._core_adapter = _adapter()
    core._execution_profile = STANDARD_GEMINI
    core._model_gateway = ModelGateway({"gemini": gemini_engine})
    core._mive = _Mive()
    core._renderer = renderer
    core._pricing = _Pricing()
    return core, gemini_engine, renderer


def _patch_gate(monkeypatch, candidate_ids):
    monkeypatch.setattr(facade, "run_runtime_admission_gate", lambda **kw: _native_for(candidate_ids))


# --------------------------------------------------------------------- #
# the SINGLE success test (§35, §38, §56)
# --------------------------------------------------------------------- #
def test_standard_gemini_single_success_end_to_end(monkeypatch):
    core, gemini_engine, renderer = _core()
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    outputs = []
    real_materialize = orch.materialize_turn_record

    def spy_materialize(**kwargs):
        produced = real_materialize(**kwargs)
        outputs.append(produced)
        return produced

    monkeypatch.setattr(orch, "materialize_turn_record", spy_materialize)

    seen_progress = []
    result = core.ask(
        "Question", top_k=1,
        progress=lambda stage, status: seen_progress.append((stage, status)),
    )

    # active profile
    assert core.execution_profile.profile_id == "STANDARD_GEMINI"
    assert core.execution_profile.profile_version == "0.1"
    assert core.execution_profile.mode is ExecutionMode.SINGLE
    assert core.execution_profile.engine_ids == ("gemini",)

    # exactly one Gemini execution, zero OpenAI, zero MIVE
    assert gemini_engine.calls == 1
    assert core._mive.calls == 0
    assert not hasattr(core, "_openai_engine")  # no OpenAI object exists at all

    # AskResult shape
    assert result.status == "success"
    assert result.mive_result is None
    assert len(result.ive_reports) == 1
    assert len(result.metrics["providers"]) == 1

    # renderer used the SINGLE path, never the comparison path
    assert renderer.render_single_calls == 1
    assert renderer.render_calls == 0
    assert "Both engines" not in str(result.rendered)

    # Turn Record: COMPLETED, profile bound, comparison not applicable
    assert len(outputs) == 1
    record = outputs[0]
    assert record.closure_state is TurnClosureState.COMPLETED
    assert record.execution_profile.profile_id == "STANDARD_GEMINI"
    assert record.execution_profile.profile_version == "0.1"
    assert record.execution_profile.mode == "SINGLE"
    assert len(record.model_executions) == 1
    assert record.model_executions[0].engine_id == "gemini"
    assert record.mive_overall_status is None
    assert record.comparison_latency_ms is None

    # progress: exactly the truthful SINGLE sequence
    assert seen_progress == [
        ("retrieval", "started"), ("retrieval", "done"),
        ("context_pack", "started"), ("context_pack", "done"),
        (errors.STAGE_GEMINI, "started"), (errors.STAGE_GEMINI, "done"),
        ("answer", "ready"),
    ]
    assert not any(stage == errors.STAGE_OPENAI for stage, _ in seen_progress)
    assert not any(stage == "mive" for stage, _ in seen_progress)


# --------------------------------------------------------------------- #
# the SINGLE failure test — no fallback (§30, §31, §39, §59)
# --------------------------------------------------------------------- #
def test_standard_gemini_gemini_failure_has_no_openai_fallback(monkeypatch):
    core, gemini_engine, renderer = _core(gemini_error=RuntimeError("gemini 503"))
    _patch_gate(monkeypatch, ("EV-1", "EV-2"))

    failed_outputs = []
    real_failed = orch.materialize_failed_turn_record

    def spy_failed(**kwargs):
        produced = real_failed(**kwargs)
        failed_outputs.append(produced)
        return produced

    monkeypatch.setattr(orch, "materialize_failed_turn_record", spy_failed)

    with pytest.raises(ProviderError) as excinfo:
        core.ask("Question", top_k=1)

    # the original provider failure is preserved, staged as "gemini"
    assert excinfo.value.stage == errors.STAGE_GEMINI

    # exactly one attempt; no fallback of any kind
    assert gemini_engine.calls == 1
    assert core._mive.calls == 0
    assert renderer.render_single_calls == 0
    assert renderer.render_calls == 0

    # exactly one FAILED Turn Record, bound to the active policy
    assert len(failed_outputs) == 1
    record = failed_outputs[0]
    assert record.closure_state is TurnClosureState.FAILED
    assert record.model_executions == ()
    assert record.execution_profile is not None
    assert record.execution_profile.profile_id == "STANDARD_GEMINI"
    assert record.execution_profile.profile_version == "0.1"
    assert record.execution_profile.mode == "SINGLE"
    assert record.failure.error_stage == errors.STAGE_GEMINI


# --------------------------------------------------------------------- #
# configured SINGLE vs. degraded fallback — a structural proof (§31, §36)
# --------------------------------------------------------------------- #
def test_no_source_path_catches_a_gemini_failure_and_calls_a_second_engine():
    """Structural proof, not merely a runtime observation: `Core.ask()`'s
    source contains no `except` clause between the one `_run_engine` call
    and the renderer call that could catch a provider failure and attempt a
    second engine. `_run_engine` itself re-raises every failure (see its own
    source), so this is the only place such a catch-and-retry could live."""
    import inspect

    source = inspect.getsource(orch.Core.ask)
    run_engine_at = source.index("self._run_engine(")
    render_at = source.index("self._renderer.render_single(")
    between = source[run_engine_at:render_at]
    assert "except" not in between
    assert "openai" not in between.lower()
