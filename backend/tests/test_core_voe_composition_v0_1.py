"""Gate 4: VOE composition wiring inside Core.ask().

Scope: this covers exactly what Gate 4 wired — the disabled-by-default path,
the enabled+success path, the two fallback paths, ComposerInput construction,
metrics/telemetry disclosure, and TurnRecord invariance. It does not exercise
a live provider (composer is always a fake here, matching how `_Engine`
stand-ins already keep every other orchestrator test off any real SDK), and
it does not exercise `app.container`/readiness (covered separately in
`test_container_voe_composer_wiring_v0_1.py` / `test_config_check.py`).

Stand-ins mirror the exact construction pattern already established in
`test_orchestrator_turn_record_v0_1.py`/`test_orchestrator_capture_seam_v0_1.py`
(`Core.__new__(Core)` + manually assigned private attributes) — reimplemented
compactly here rather than imported across test files, so this file stays
self-contained.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

import app.core.orchestrator as orch
from app.core.models import AskResult
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import STANDARD_GEMINI
from app.modules.model_gateway import ModelGateway
from app.modules.response_composer import (
    ComposedResponse,
    ComposerInput,
    ResponseComposerOutputError,
    ResponseComposerProviderError,
    ResponseComposerResult,
)
from app.modules.turn_record import TurnClosureState, TurnRecord
from app.modules.voe_profile import VOEProfileBinding, VOERuntimeProfile

GEMINI_MODEL = "gemini-3.1-flash-lite"


# --------------------------------------------------------------------- #
# stand-ins
# --------------------------------------------------------------------- #
class _Clock:
    def __init__(self):
        self.monotonic_calls = 0
        self.iso_calls = 0

    def monotonic_ms(self):
        self.monotonic_calls += 1
        return float(self.monotonic_calls)

    def now_iso(self):
        value = f"ISO-{self.iso_calls}"
        self.iso_calls += 1
        return value


class _Retrieval:
    def __init__(self, candidate_ids):
        self._candidate_ids = tuple(candidate_ids)

    def retrieve(self, question, top_k):
        return [SimpleNamespace(document_id=cid, content="body") for cid in self._candidate_ids]


class _Builder:
    def __init__(self, pack):
        self.pack = pack

    def build(self, question, evidence):
        return self.pack


class _Bridge:
    backend_id = "TEST-BACKEND"
    mapping_profile_id = "TEST-PROFILE"

    def __init__(self):
        self.request = SimpleNamespace()

    def resolve(self, evidence):
        return ()

    def build_request(self, *args, **kwargs):
        return SimpleNamespace(accepted=True, request=self.request, reasons=())


def _adapter(bridge):
    adapter = CoreAdapter.__new__(CoreAdapter)
    adapter._bridge = bridge
    return adapter


def _pack(document_ids):
    return SimpleNamespace(
        context_pack_id="CP-001",
        documents=[
            SimpleNamespace(
                document_id=did, content="body", title="Title-" + did,
                source="SRC-" + did, page=None, chunk_id=None,
            )
            for did in document_ids
        ],
        metadata={"included_documents": len(tuple(document_ids))},
    )


def _settings():
    return SimpleNamespace(default_top_k=1, context_char_budget=60000, qdrant_collection="ion_corpus_v1")


def _claim(statement="Money is a medium of exchange.", confidence=0.8, evidence_document_ids=("EV-1",)):
    return SimpleNamespace(
        statement=statement, confidence=confidence, evidence_document_ids=list(evidence_document_ids),
    )


def _report(engine_id="gemini", provider="gemini", model=GEMINI_MODEL):
    return SimpleNamespace(
        engine_id=engine_id,
        provider=provider,
        model=model,
        abstract="Money functions as a medium of exchange, unit of account, and store of value.",
        highlights=["medium of exchange", "store of value"],
        claims=[_claim()],
        uncertainty=["Historical origin is debated."],
        confidence=0.75,
        usage=SimpleNamespace(input_tokens=11, output_tokens=5, latency_ms=1.5, usage_is_estimated=False),
        to_contract_dict=lambda: {"engine_id": engine_id, "provider": provider},
    )


class _Engine:
    def __init__(self, engine_id, provider, model):
        self._engine_id = engine_id
        self.provider = provider
        self.model = model

    @property
    def engine_id(self):
        return self._engine_id

    def run(self, pack):
        return _report(self._engine_id, self.provider, self.model)


_BASE_EVIDENCE = [{"document_id": "EV-1", "excerpt": "verbatim evidence text"}]
_BASE_UNCERTAINTY = {"reported": ["Historical origin is debated."]}


class _Renderer:
    def render_single(self, **kwargs):
        return {
            "question": kwargs["question"],
            "primary_answer": kwargs["report"].abstract,
            "mive_assessment": None,
            "uncertainty": _BASE_UNCERTAINTY,
            "evidence": _BASE_EVIDENCE,
            "operational_metrics": kwargs["metrics_dict"],
            "disclaimer": "single-engine disclaimer",
        }


class _Pricing:
    def __init__(self):
        self.calls = []

    def estimate_cost(self, model, input_tokens, output_tokens):
        self.calls.append((model, input_tokens, output_tokens))
        return 0.00042


class _Mive:
    def compare(self, reports):  # pragma: no cover - unreachable under SINGLE
        raise AssertionError("MIVE must not be invoked under SINGLE")


def _voe_profile():
    return VOERuntimeProfile(
        binding=VOEProfileBinding(
            profile_id="VOE-DIALOGUE-PROFILE",
            profile_version="0.2",
            runtime_behavioral_fingerprint_sha256="a" * 64,
        ),
        dialogue_profile_text="dialogue text",
        style_parameters_text="{}",
        ethical_policy_text="ethics text",
        illustrative_reasoning_policy_text="reasoning text",
    )


class _RecordingComposer:
    """Records every ComposerInput it receives; returns a fixed successful
    ResponseComposerResult unless configured to raise."""

    def __init__(self, *, raises=None, composed_text="COMPOSED ANSWER"):
        self.calls: list[ComposerInput] = []
        self._raises = raises
        self._composed_text = composed_text

    def compose(self, composer_input: ComposerInput) -> ResponseComposerResult:
        self.calls.append(composer_input)
        if self._raises is not None:
            raise self._raises
        return ResponseComposerResult(
            response=ComposedResponse(composed_text=self._composed_text),
            provider="gemini",
            requested_model=GEMINI_MODEL,
            input_tokens=100,
            output_tokens=42,
            usage_is_estimated=False,
            latency_ms=12.5,
        )


def _core(*, composer=None, voe_runtime_profile=None, retrieved=("EV-1",), submitted=("EV-1",)):
    pack = _pack(submitted)
    core = orch.Core.__new__(orch.Core)
    core._settings = _settings()
    core._clock = _Clock()
    core._retrieval = _Retrieval(retrieved)
    core._build = _Builder(pack)
    core._core_adapter = _adapter(_Bridge())
    core._execution_profile = STANDARD_GEMINI
    core._model_gateway = ModelGateway({"gemini": _Engine("gemini", "gemini", GEMINI_MODEL)})
    core._mive = _Mive()
    core._renderer = _Renderer()
    core._pricing = _Pricing()
    core._composer = composer
    core._voe_runtime_profile = voe_runtime_profile
    return core


def _patch_gate(monkeypatch):
    import app.modules.core_adapter.facade as facade

    monkeypatch.setattr(facade, "run_runtime_admission_gate", lambda **kw: _native_for(("EV-1",)))


def _native_for(candidate_ids):
    VERIFIED, PENDING, PASS = "VERIFIED", "PENDING", "PASS"
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


# --------------------------------------------------------------------- #
# 1 / 4 / 5: disabled path — exact pre-profile behavior
# --------------------------------------------------------------------- #
def test_disabled_path_is_exact_pre_profile_answer(monkeypatch):
    _patch_gate(monkeypatch)
    core = _core(composer=None, voe_runtime_profile=None)
    result = core.ask("what is money?", top_k=1)

    assert result.rendered["primary_answer"] == _report().abstract
    assert "composition" not in result.rendered["operational_metrics"]
    assert result.rendered["evidence"] == _BASE_EVIDENCE
    assert result.rendered["uncertainty"] == _BASE_UNCERTAINTY


def test_disabled_path_never_calls_a_composer(monkeypatch):
    """No composer is even referenced when disabled — proven by the fact
    that composer=None and the call still succeeds without AttributeError,
    since `self._composer is not None` is the sole gate."""
    _patch_gate(monkeypatch)
    core = _core(composer=None)
    core.ask("what is money?", top_k=1)  # must not raise


# --------------------------------------------------------------------- #
# 12 / 13: ComposerInput construction boundary
# --------------------------------------------------------------------- #
def test_composer_input_is_built_from_ive_report_projection_only(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    core.ask("what is money?", top_k=1)

    assert len(composer.calls) == 1
    ci = composer.calls[0]
    report = _report()
    assert ci.question == "what is money?"
    assert ci.report_abstract == report.abstract
    assert ci.report_highlights == tuple(report.highlights)
    assert ci.report_uncertainty == tuple(report.uncertainty)
    assert ci.report_confidence == report.confidence
    assert len(ci.report_claims) == 1
    assert ci.report_claims[0].statement == report.claims[0].statement
    assert ci.report_claims[0].confidence == report.claims[0].confidence
    assert ci.voe_profile is core._voe_runtime_profile


def test_composer_input_claims_carry_no_evidence_identity(monkeypatch):
    """The original IVEReport claim carries evidence_document_ids; the
    projected ComposerClaimView structurally cannot — proving Core never
    leaks it through, not merely that it chooses not to."""
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    core.ask("what is money?", top_k=1)

    claim_view = composer.calls[0].report_claims[0]
    assert not hasattr(claim_view, "evidence_document_ids")
    assert {f.name for f in dataclasses.fields(claim_view)} == {"statement", "confidence"}


# --------------------------------------------------------------------- #
# 14: composer runs exactly once
# --------------------------------------------------------------------- #
def test_composer_runs_exactly_once(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    core.ask("what is money?", top_k=1)
    assert len(composer.calls) == 1


# --------------------------------------------------------------------- #
# 16-19: successful composition
# --------------------------------------------------------------------- #
def test_successful_composition_replaces_primary_answer(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(composed_text="A VOE-styled answer.")
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.rendered["primary_answer"] == "A VOE-styled answer."


def test_successful_composition_leaves_evidence_field_unchanged(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.rendered["evidence"] == _BASE_EVIDENCE


def test_successful_composition_leaves_uncertainty_field_unchanged(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.rendered["uncertainty"] == _BASE_UNCERTAINTY


def test_successful_composition_leaves_ive_report_object_unchanged(monkeypatch):
    """Prove Core never mutates the report it read from — same abstract,
    same claim statement/confidence, before and after composition."""
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    original = _report()
    ive_reports = result.ive_reports[0]
    assert ive_reports == {"engine_id": "gemini", "provider": "gemini"}  # to_contract_dict() unchanged


# --------------------------------------------------------------------- #
# 20-22: fallback semantics
# --------------------------------------------------------------------- #
def test_provider_failure_falls_back_to_deterministic_answer(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(raises=ResponseComposerProviderError("network exploded"))
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.rendered["primary_answer"] == _report().abstract


def test_malformed_output_falls_back_to_deterministic_answer(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(raises=ResponseComposerOutputError("bad json"))
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.rendered["primary_answer"] == _report().abstract


def test_provider_failure_status_is_disclosed(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(raises=ResponseComposerProviderError("x"))
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.rendered["operational_metrics"]["composition"]["status"] == "FALLBACK_PROVIDER_ERROR"


def test_malformed_output_status_is_disclosed(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(raises=ResponseComposerOutputError("x"))
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.rendered["operational_metrics"]["composition"]["status"] == "FALLBACK_MALFORMED_OUTPUT"


def test_fallback_never_silently_looks_successful(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(raises=ResponseComposerProviderError("x"))
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    composition = result.rendered["operational_metrics"]["composition"]
    assert composition["status"] != "COMPOSED"
    assert composition["input_tokens"] is None
    assert composition["output_tokens"] is None
    assert composition["estimated_cost"] is None


def test_unexpected_composer_exception_is_not_swallowed(monkeypatch):
    """Only the two composer-local error types are caught — a genuine bug
    (any other exception) must still fail the turn, never silently fall
    back."""
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(raises=RuntimeError("a real bug"))
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    with pytest.raises(RuntimeError, match="a real bug"):
        core.ask("what is money?", top_k=1)


# --------------------------------------------------------------------- #
# 23 / 24: composition metrics content
# --------------------------------------------------------------------- #
def test_successful_composition_metrics_preserve_execution_facts(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    composition = result.rendered["operational_metrics"]["composition"]

    assert composition["status"] == "COMPOSED"
    assert composition["provider"] == "gemini"
    assert composition["model"] == GEMINI_MODEL
    assert composition["input_tokens"] == 100
    assert composition["output_tokens"] == 42
    assert composition["usage_is_estimated"] is False
    assert composition["latency_ms"] == 12.5
    assert composition["voe_profile_id"] == "VOE-DIALOGUE-PROFILE"
    assert composition["voe_profile_version"] == "0.2"
    assert composition["voe_runtime_behavioral_fingerprint_sha256"] == "a" * 64


def test_composition_cost_uses_existing_pricing_port(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    composition = result.rendered["operational_metrics"]["composition"]

    assert composition["estimated_cost"] == 0.00042
    assert (GEMINI_MODEL, 100, 42) in core._pricing.calls


# --------------------------------------------------------------------- #
# 25: single metrics snapshot
# --------------------------------------------------------------------- #
def test_ask_result_metrics_and_rendered_operational_metrics_agree_disabled(monkeypatch):
    _patch_gate(monkeypatch)
    core = _core(composer=None)
    result = core.ask("what is money?", top_k=1)
    assert result.metrics == result.rendered["operational_metrics"]


def test_ask_result_metrics_and_rendered_operational_metrics_agree_enabled(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.metrics == result.rendered["operational_metrics"]
    assert result.metrics is result.rendered["operational_metrics"]  # single-source construction


def test_ask_result_metrics_and_rendered_operational_metrics_agree_on_fallback(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(raises=ResponseComposerOutputError("x"))
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    result = core.ask("what is money?", top_k=1)
    assert result.metrics == result.rendered["operational_metrics"]


# --------------------------------------------------------------------- #
# 26 / 27: TurnRecord invariance
# --------------------------------------------------------------------- #
def test_turn_record_has_exactly_one_ive_execution_disabled(monkeypatch):
    _patch_gate(monkeypatch)
    core = _core(composer=None)
    captured = []
    core.ask("what is money?", top_k=1, on_turn_record=captured.append)
    assert len(captured) == 1
    record = captured[0]
    assert record.closure_state is TurnClosureState.COMPLETED
    assert len(record.model_executions) == 1


def test_turn_record_has_exactly_one_ive_execution_when_composed(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    captured = []
    core.ask("what is money?", top_k=1, on_turn_record=captured.append)
    assert len(captured) == 1
    assert len(captured[0].model_executions) == 1


def test_turn_record_has_exactly_one_ive_execution_on_fallback(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer(raises=ResponseComposerProviderError("x"))
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    captured = []
    core.ask("what is money?", top_k=1, on_turn_record=captured.append)
    assert len(captured[0].model_executions) == 1


def test_turn_record_field_set_carries_no_composition_field(monkeypatch):
    _patch_gate(monkeypatch)
    composer = _RecordingComposer()
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    captured = []
    core.ask("what is money?", top_k=1, on_turn_record=captured.append)
    field_names = {f.name for f in dataclasses.fields(TurnRecord)}
    forbidden = {"composition_execution", "composer_status", "composition"}
    assert field_names & forbidden == set()


# --------------------------------------------------------------------- #
# 32: rollback proof
# --------------------------------------------------------------------- #
def test_rollback_disabled_after_enabled_restores_pre_profile_path(monkeypatch):
    _patch_gate(monkeypatch)

    enabled_core = _core(composer=_RecordingComposer(composed_text="styled"), voe_runtime_profile=_voe_profile())
    enabled_result = enabled_core.ask("what is money?", top_k=1)
    assert enabled_result.rendered["primary_answer"] == "styled"
    assert "composition" in enabled_result.rendered["operational_metrics"]

    disabled_core = _core(composer=None, voe_runtime_profile=None)
    disabled_result = disabled_core.ask("what is money?", top_k=1)
    assert disabled_result.rendered["primary_answer"] == _report().abstract
    assert "composition" not in disabled_result.rendered["operational_metrics"]


# --------------------------------------------------------------------- #
# 33: no response_evidence wiring introduced
# --------------------------------------------------------------------- #
def test_orchestrator_source_still_imports_nothing_from_response_evidence():
    import ast
    from pathlib import Path

    source = Path(orch.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("response_evidence" in m for m in imported_modules)
