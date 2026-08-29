"""B0 governance guarantees, re-expressed at the Core Adapter boundary.

TASK 12.2 moved the ownership of the two governance calls (the runtime evidence
bridge and the runtime admission gate) out of the orchestrator and behind
`app.modules.core_adapter`. Nothing about the guarantees themselves changed, so
every original test id (t27-t38) is preserved here and asserts the same thing it
asserted in B0 — only the seam it observes has moved.

The migration also took the chance to drop source-text index comparisons in
favour of observed call order: ordering is now proven by driving the real
`CoreAdapter` over a stand-in bridge and recording when each stage runs, which
survives any later reformatting of the modules under test.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import errors
import app.core.orchestrator as orch
import app.modules.core_adapter.facade as facade
from app.modules.core_adapter import CoreAdapter
from app.modules.execution_profile import STANDARD_GEMINI


REPO_ROOT = Path(os.environ["ION_REPO_ROOT"]).resolve()

VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"


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
    """Stands in for the frozen runtime evidence bridge, inside the adapter."""

    backend_id = "TEST-BACKEND"
    mapping_profile_id = "TEST-PROFILE"

    def __init__(self, *, accepted=True, reasons=()):
        self.resolve_count = 0
        self.build_count = 0
        self.accepted = accepted
        self.reasons = reasons
        self.request = SimpleNamespace()

    def resolve(self, evidence):
        self.resolve_count += 1
        return ()

    def build_request(self, *args, **kwargs):
        self.build_count += 1
        return SimpleNamespace(
            accepted=self.accepted, request=self.request, reasons=self.reasons
        )


def _adapter(bridge):
    """A real CoreAdapter over a stand-in bridge — the facade logic is genuine."""
    adapter = CoreAdapter.__new__(CoreAdapter)
    adapter._bridge = bridge
    return adapter


# `_Retrieval` always returns exactly one candidate, "EV-001". The Context
# Pack must submit that same one candidate — with the full `ContextDocument`
# field set the live Model Context materialization step now reads (TASK
# 19.3) — and the passing gate below must ADMIT that same one candidate, so
# the governed basis is genuinely non-empty. Fidelity only: no assertion below
# depends on these specific values.
_CANDIDATE_ID = "EV-001"


def _native_for(candidate_ids):
    """Shaped exactly as the real `RuntimeAdmissionGateResult` (mirrors the
    identical helper in the sibling TASK 14 / TASK 18 orchestrator suites)."""
    return SimpleNamespace(
        records=tuple(
            SimpleNamespace(
                evidence_id=candidate_id,
                status=VERIFIED,
                validation_id="VAL-" + candidate_id,
                fingerprint=SimpleNamespace(
                    algorithm="SHA256",
                    hash="FP-" + candidate_id,
                    content_id=candidate_id,
                ),
            )
            for candidate_id in candidate_ids
        ),
        validations=tuple(
            SimpleNamespace(
                validation_id="VAL-" + candidate_id,
                evidence_id=candidate_id,
                result=PASS,
                blocking_reasons=(),
                evidence_fingerprint_hash="FP-" + candidate_id,
            )
            for candidate_id in candidate_ids
        ),
        transitions=tuple(
            SimpleNamespace(
                transition_id="TR-" + candidate_id,
                evidence_id=candidate_id,
                from_status=PENDING,
                to_status=VERIFIED,
                validation_id="VAL-" + candidate_id,
            )
            for candidate_id in candidate_ids
        ),
    )


def _core(bridge=None):
    # `metadata` mirrors the real ContextPack, which always carries one
    # (core/models.py). Fidelity only — no assertion below depends on it.
    # `title` / `source` / `page` / `chunk_id` mirror the real
    # `ContextDocument`, which always carries all six fields — the live
    # Model Context materialization step now reads every one of them.
    pack = SimpleNamespace(
        context_pack_id="CP-001",
        documents=[
            SimpleNamespace(
                document_id=_CANDIDATE_ID, content="body",
                title="Title-" + _CANDIDATE_ID, source="SRC-" + _CANDIDATE_ID,
                page=None, chunk_id=None,
            )
        ],
        metadata={},
    )
    bridge = _Bridge() if bridge is None else bridge
    core = orch.Core.__new__(orch.Core)
    core._settings = SimpleNamespace(default_top_k=1)
    core._clock = _Clock()
    core._retrieval = _Retrieval()
    core._build = _Builder(pack)
    core._core_adapter = _adapter(bridge)
    core._execution_profile = STANDARD_GEMINI
    core._mive = object()
    core._renderer = object()
    core._pricing = object()
    return core, pack, bridge


def _patch_gate(monkeypatch, fn):
    """Patch the admission gate where the Core Adapter now imports it."""
    monkeypatch.setattr(facade, "run_runtime_admission_gate", fn)


def _passing_gate(**kwargs):
    # ADMITS exactly the one candidate `_Retrieval`/`_core()` submit, so the
    # governed basis the live Model Context materialization step joins
    # against is genuinely non-empty — never a fabricated admission, since
    # `_Retrieval` and the Context Pack above always agree on this one id.
    return _native_for((_CANDIDATE_ID,))


def _failing_gate(**kwargs):
    raise ValueError("blocked")


def test_p5_18ab_t27_admission_gate_executes_after_bridge_acceptance_gate(monkeypatch):
    gate_calls = []

    def gate(**kwargs):
        gate_calls.append(kwargs)
        return _passing_gate(**kwargs)

    _patch_gate(monkeypatch, gate)
    core, _, bridge = _core(_Bridge(accepted=False, reasons=("R1", "R2")))

    with pytest.raises(errors.ContextPackError) as excinfo:
        core.ask("Question", top_k=1)

    assert bridge.build_count == 1
    assert gate_calls == []
    assert str(excinfo.value) == "Runtime evidence bridge rejected: R1|R2"


def _ordered_run(monkeypatch):
    """Record the real order of gate and provider execution in one ask()."""
    order = []

    def gate(**kwargs):
        order.append("gate")
        return _passing_gate(**kwargs)

    _patch_gate(monkeypatch, gate)
    core, _, _ = _core()

    def provider(engine, provider_pack, stage, emit):
        order.append(stage)
        raise RuntimeError("stop-after-provider")

    core._run_engine = provider

    with pytest.raises(RuntimeError, match="stop-after-provider"):
        core.ask("Question", top_k=1)

    return order


def test_p5_18ab_t28_admission_gate_executes_before_gemini_ive(monkeypatch):
    order = _ordered_run(monkeypatch)
    assert order.index("gate") < order.index(errors.STAGE_GEMINI)


# T29 (admission gate executes before openai_ive) is REMOVED, not
# reconciled: STANDARD_GEMINI/SINGLE (TASK 20) never reaches an OpenAI stage
# at all, so there is no ordering left to prove against a stage that no
# longer runs on any live policy.


def test_p5_18ab_t30_admission_failure_prevents_both_provider_calls(monkeypatch):
    core, _, _ = _core()
    provider_calls = []

    def provider(*args, **kwargs):
        provider_calls.append(1)
        raise AssertionError("provider must not execute")

    _patch_gate(monkeypatch, _failing_gate)
    core._run_engine = provider

    with pytest.raises(errors.ContextPackError) as excinfo:
        core.ask("Question", top_k=1)

    assert provider_calls == []
    assert str(excinfo.value) == "Runtime admission gate rejected: blocked"


def test_p5_18ab_t31_all_pass_gate_permits_the_provider_call_attempt(monkeypatch):
    """T31, reconciled for TASK 20 SINGLE.

    Originally: a passing gate permitted BOTH provider call attempts.
    STANDARD_GEMINI/SINGLE makes exactly one call attempt; the underlying law
    — a passing gate genuinely permits the provider to be reached — is
    preserved for the one attempt that now exists.
    """
    core, _, _ = _core()
    provider_calls = []

    def provider(engine, pack, stage, emit):
        provider_calls.append((engine, pack, stage))
        raise RuntimeError("stop-after-provider")

    _patch_gate(monkeypatch, _passing_gate)
    core._run_engine = provider

    with pytest.raises(RuntimeError, match="stop-after-provider"):
        core.ask("Question", top_k=1)

    assert len(provider_calls) == 1


def test_p5_18ab_t32_the_one_engine_receives_the_real_model_context_not_the_pack(monkeypatch):
    """T32, reconciled for TASK 20 SINGLE (previously reconciled for TASK 19.3).

    Originally: both engines reused the SAME `ContextPack` instance the gate
    itself saw. TASK 19.3 strengthened this to: both engines reused the SAME
    live `ModelContextAssembly`, never the `ContextPack`. STANDARD_GEMINI/
    SINGLE (TASK 20) narrows this further: there is exactly one engine now,
    so "both engines share one instance" no longer applies — but the
    underlying law survives intact for the one recipient that exists: it
    receives the real, live `ModelContextAssembly`, never the upstream
    `ContextPack` the admission gate saw.
    """
    core, pack, _ = _core()
    seen = {"gate": None, "providers": []}

    def gate(**kwargs):
        seen["gate"] = kwargs["pack"]
        return _passing_gate(**kwargs)

    def provider(engine, model_input, stage, emit):
        seen["providers"].append(model_input)
        raise RuntimeError("stop-after-provider")

    _patch_gate(monkeypatch, gate)
    core._run_engine = provider

    with pytest.raises(RuntimeError):
        core.ask("Question", top_k=1)

    # the admission gate still sees the real, upstream Context Pack...
    assert seen["gate"] is pack
    assert len(seen["providers"]) == 1
    # ...but the engine receives the live ModelContextAssembly, never the
    # Context Pack the gate saw: only admitted governed content may reach a
    # provider (TASK 19.3).
    assert all(item is not pack for item in seen["providers"])
    from app.modules.model_context import ModelContextAssembly
    assert all(isinstance(item, ModelContextAssembly) for item in seen["providers"])


def test_p5_18ab_t33_no_second_retrieval_call(monkeypatch):
    core, _, _ = _core()

    _patch_gate(monkeypatch, _failing_gate)

    with pytest.raises(errors.ContextPackError):
        core.ask("Question", top_k=1)

    assert core._retrieval.count == 1


def test_p5_18ab_t34_no_second_context_pack_build(monkeypatch):
    core, _, _ = _core()

    _patch_gate(monkeypatch, _failing_gate)

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


def test_p5_18ab_t39_orchestrator_reaches_governance_only_through_core_adapter():
    """The direct-import bypass B0 relied on must no longer exist."""
    for bypassed in (
        "run_runtime_admission_gate",
        "build_qdrant_runtime_bridge",
        "_evidence_bridge",
    ):
        assert not hasattr(orch, bypassed)
        assert not hasattr(orch.Core, bypassed)


def test_p5_18ab_t40_operational_failure_propagates_the_original_exception(monkeypatch):
    """Operational failure is not a governance verdict: B0 raised it untouched."""
    core, _, _ = _core()
    boom = RuntimeError("qdrant unreachable")

    def gate(**kwargs):
        raise boom

    _patch_gate(monkeypatch, gate)
    core._run_engine = lambda *a, **k: pytest.fail("provider must not execute")

    with pytest.raises(RuntimeError) as excinfo:
        core.ask("Question", top_k=1)

    assert excinfo.value is boom
