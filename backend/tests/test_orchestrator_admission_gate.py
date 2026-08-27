from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import errors
import app.core.orchestrator as orch


REPO_ROOT = Path(os.environ["ION_REPO_ROOT"]).resolve()


class _Clock:
    def __init__(self):
        self.value = 0

    def monotonic_ms(self):
        self.value += 1
        return self.value

    def now_iso(self):
        return "2026-08-24T00:00:00Z"


class _Retrieval:
    def __init__(self):
        self.count = 0

    def retrieve(self, question, top_k):
        self.count += 1
        return [SimpleNamespace(document_id="EV-001")]


class _Builder:
    def __init__(self, pack):
        self.count = 0
        self.pack = pack

    def build(self, question, evidence):
        self.count += 1
        return self.pack


class _Bridge:
    def __init__(self):
        self.resolve_count = 0
        self.build_count = 0
        self.request = SimpleNamespace()

    def resolve(self, evidence):
        self.resolve_count += 1
        return ()

    def build_request(self, *args, **kwargs):
        self.build_count += 1
        return SimpleNamespace(accepted=True, request=self.request, reasons=())


def _core():
    pack = SimpleNamespace(context_pack_id="CP-001", documents=[])
    core = orch.Core.__new__(orch.Core)
    core._settings = SimpleNamespace(default_top_k=1)
    core._clock = _Clock()
    core._retrieval = _Retrieval()
    core._build = _Builder(pack)
    core._evidence_bridge = _Bridge()
    core._gemini = object()
    core._openai = object()
    core._mive = object()
    core._renderer = object()
    core._pricing = object()
    return core, pack


def _source():
    return inspect.getsource(orch)


def _gate_call_index(source):
    return source.index("            run_runtime_admission_gate(")


def test_p5_18ab_t27_admission_gate_executes_after_bridge_acceptance_gate():
    source = _source()
    assert source.index("if not bridge_result.accepted:") < _gate_call_index(source)


def test_p5_18ab_t28_admission_gate_executes_before_gemini_ive():
    source = _source()
    assert _gate_call_index(source) < source.index(
        "gemini_report = self._run_engine(self._gemini"
    )


def test_p5_18ab_t29_admission_gate_executes_before_openai_ive():
    source = _source()
    assert _gate_call_index(source) < source.index(
        "openai_report = self._run_engine(self._openai"
    )


def test_p5_18ab_t30_admission_failure_prevents_both_provider_calls(monkeypatch):
    core, _ = _core()
    provider_calls = []

    def fail_gate(**kwargs):
        raise ValueError("blocked")

    def provider(*args, **kwargs):
        provider_calls.append(1)
        raise AssertionError("provider must not execute")

    monkeypatch.setattr(orch, "run_runtime_admission_gate", fail_gate)
    core._run_engine = provider

    with pytest.raises(errors.ContextPackError):
        core.ask("Question", top_k=1)

    assert provider_calls == []


def test_p5_18ab_t31_all_pass_gate_permits_both_provider_call_attempts(monkeypatch):
    core, _ = _core()
    provider_calls = []

    def pass_gate(**kwargs):
        return SimpleNamespace()

    def provider(engine, pack, stage, emit):
        provider_calls.append((engine, pack, stage))
        if len(provider_calls) == 2:
            raise RuntimeError("stop-after-second-provider")
        return object()

    monkeypatch.setattr(orch, "run_runtime_admission_gate", pass_gate)
    core._run_engine = provider

    with pytest.raises(RuntimeError, match="stop-after-second-provider"):
        core.ask("Question", top_k=1)

    assert len(provider_calls) == 2


def test_p5_18ab_t32_same_context_pack_instance_reused_only_after_all_pass_gate(monkeypatch):
    core, pack = _core()
    seen = {"gate": None, "providers": []}

    def pass_gate(**kwargs):
        seen["gate"] = kwargs["pack"]
        return SimpleNamespace()

    def provider(engine, provider_pack, stage, emit):
        seen["providers"].append(provider_pack)
        if len(seen["providers"]) == 2:
            raise RuntimeError("stop-after-second-provider")
        return object()

    monkeypatch.setattr(orch, "run_runtime_admission_gate", pass_gate)
    core._run_engine = provider

    with pytest.raises(RuntimeError):
        core.ask("Question", top_k=1)

    assert seen["gate"] is pack
    assert len(seen["providers"]) == 2
    assert all(item is pack for item in seen["providers"])


def test_p5_18ab_t33_no_second_retrieval_call(monkeypatch):
    core, _ = _core()

    monkeypatch.setattr(
        orch,
        "run_runtime_admission_gate",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("stop")),
    )

    with pytest.raises(errors.ContextPackError):
        core.ask("Question", top_k=1)

    assert core._retrieval.count == 1


def test_p5_18ab_t34_no_second_context_pack_build(monkeypatch):
    core, _ = _core()

    monkeypatch.setattr(
        orch,
        "run_runtime_admission_gate",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("stop")),
    )

    with pytest.raises(errors.ContextPackError):
        core.ask("Question", top_k=1)

    assert core._build.count == 1


def test_p5_18ab_t35_claim_adjudication_has_no_llm_or_provider_call_capability():
    source = (
        REPO_ROOT
        / "backend"
        / "app"
        / "modules"
        / "admission"
        / "claim_adjudication.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in ("gemini", "openai", "mive", "provider.", "engine.run("):
        assert forbidden not in source


def test_p5_18ab_t36_claim_adjudication_has_no_qdrant_mutation_capability():
    source = (
        REPO_ROOT
        / "backend"
        / "app"
        / "modules"
        / "admission"
        / "claim_adjudication.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "qdrantclient",
        "qdrant_client",
        ".upsert(",
        ".delete(",
        ".create_collection(",
        ".recreate_collection(",
    ):
        assert forbidden not in source


def test_p5_18ab_t37_no_wall_clock_or_random_identity_in_adjudicator():
    source = (
        REPO_ROOT
        / "backend"
        / "app"
        / "modules"
        / "admission"
        / "claim_adjudication.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "uuid4",
        "import uuid",
        "import random",
        "datetime.now",
        "datetime.utcnow",
        "time.time",
    ):
        assert forbidden not in source


def test_p5_18ab_t38_protected_qdrant_store_remains_byte_identical():
    path = REPO_ROOT / "backend" / "app" / "modules" / "retrieval" / "qdrant_store.py"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == "c0ddd327914567ecfb5b5b388d55d555b8c513fce58695dea9e9a68356d1dce3"