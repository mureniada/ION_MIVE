"""Bounded contract test for the Product-facing Core Adapter facade (v0.1).

Scope is deliberately narrow: this covers the BOUNDARY only — what the facade
promises to Product code and what it refuses to expose — not the governance
semantics behind it. Admission, provenance and fingerprint behaviour stay owned
and tested by the frozen B0 modules; nothing here re-asserts them.

Absence checks are structural, never textual. The facade and its models name
`GovernedEvidenceSet` and the per-candidate ADMITTED / REJECTED / UNKNOWN
vocabulary in their docstrings precisely in order to record that those concepts
are EXCLUDED at v0.1, so a raw-text scan would report the exact opposite of the
truth. These tests interrogate the module namespaces, the enum members and the
dataclass fields instead.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from app.modules import admission
from app.modules import core_adapter
import app.modules.core_adapter.facade as facade
import app.modules.core_adapter.models as models
from app.modules.core_adapter import (
    CoreAdapter,
    CoreAdapterOutcome,
    CoreAdapterOutcomeState,
    CoreAdapterRequest,
    CoreInvocationMode,
)


class _Bridge:
    """Stand-in for the frozen runtime evidence bridge."""

    backend_id = "TEST-BACKEND"
    mapping_profile_id = "TEST-PROFILE"

    def __init__(self, *, accepted=True, reasons=(), resolve_error=None):
        self.resolve_count = 0
        self.build_count = 0
        self.accepted = accepted
        self.reasons = reasons
        self.resolve_error = resolve_error
        self.request = SimpleNamespace()

    def resolve(self, evidence):
        self.resolve_count += 1
        if self.resolve_error is not None:
            raise self.resolve_error
        return ()

    def build_request(self, *args, **kwargs):
        self.build_count += 1
        return SimpleNamespace(
            accepted=self.accepted, request=self.request, reasons=self.reasons
        )


def _adapter(bridge):
    adapter = CoreAdapter.__new__(CoreAdapter)
    adapter._bridge = bridge
    return adapter


def _request(**overrides):
    base = dict(
        candidate_set_id="REQ-001",
        question_id="REQ-001",
        candidates=[SimpleNamespace(document_id="EV-001")],
        context_pack=SimpleNamespace(context_pack_id="CP-001", documents=[]),
        adapter_created_at="2026-08-24T00:00:00Z",
    )
    base.update(overrides)
    return CoreAdapterRequest(**base)


def _never(**kwargs):
    raise AssertionError("admission gate must not be reached")


# --------------------------------------------------------------------- #
# identity and invocation authority
# --------------------------------------------------------------------- #
def test_core_adapter_facade_v0_1_t01_adapter_identity_is_pinned():
    adapter = _adapter(_Bridge())
    assert adapter.adapter_id == "ION_CORE_ADAPTER_FACADE_V0_1"
    assert adapter.adapter_version == "0.1"
    # every outcome is stamped with the same identity by default
    assert CoreAdapterOutcome(outcome=CoreAdapterOutcomeState.GOVERNANCE_COMPLETE).adapter_id == (
        adapter.adapter_id
    )


def test_core_adapter_facade_v0_1_t02_read_only_is_the_only_invocation_mode():
    assert list(CoreInvocationMode) == [CoreInvocationMode.READ_ONLY]
    assert CoreInvocationMode.READ_ONLY.value == "READ_ONLY"
    assert CoreAdapterRequest.__dataclass_fields__["mode"].default is (
        CoreInvocationMode.READ_ONLY
    )


@pytest.mark.parametrize("refused_mode", ["READ_ONLY", "PROMOTE", None])
def test_core_adapter_facade_v0_1_t03_foreign_mode_refused_before_any_governance_call(
    monkeypatch, refused_mode
):
    """The gate is identity-based: even an equal-valued string is refused."""
    monkeypatch.setattr(facade, "run_runtime_admission_gate", _never)
    bridge = _Bridge()
    adapter = _adapter(bridge)

    with pytest.raises(ValueError, match="READ_ONLY"):
        adapter.govern(_request(mode=refused_mode))

    assert bridge.resolve_count == 0
    assert bridge.build_count == 0


def test_core_adapter_facade_v0_1_t04_read_only_authority_surface_is_minimal():
    """No promotion, persistence or state-transition entry point is reachable."""
    public = {name for name in dir(CoreAdapter) if not name.startswith("_")}
    assert public == {"govern", "adapter_id", "adapter_version"}


# --------------------------------------------------------------------- #
# outcome semantics — native results are carried, never reinterpreted
# --------------------------------------------------------------------- #
def test_core_adapter_facade_v0_1_t05_governance_complete_holds_native_result_by_reference(
    monkeypatch,
):
    native = SimpleNamespace(records=("R1", "R2"))
    monkeypatch.setattr(facade, "run_runtime_admission_gate", lambda **kwargs: native)
    bridge = _Bridge()

    outcome = _adapter(bridge).govern(_request())

    assert outcome.outcome is CoreAdapterOutcomeState.GOVERNANCE_COMPLETE
    assert outcome.is_complete is True
    assert outcome.native_result is native
    assert outcome.candidate_count == 1
    assert outcome.governed_count == 2
    assert outcome.backend_id == bridge.backend_id
    assert outcome.mapping_profile_id == bridge.mapping_profile_id
    assert outcome.native_gate_error is None
    assert outcome.native_bridge_reasons == ()


def test_core_adapter_facade_v0_1_t06_bridge_rejection_preserves_reasons_and_skips_gate(
    monkeypatch,
):
    monkeypatch.setattr(facade, "run_runtime_admission_gate", _never)
    bridge = _Bridge(accepted=False, reasons=("MISSING_PROVENANCE", "ADAPTER_REJECTED:x"))

    outcome = _adapter(bridge).govern(_request())

    assert outcome.outcome is CoreAdapterOutcomeState.GOVERNANCE_REJECTED
    assert outcome.is_complete is False
    assert outcome.native_bridge_reasons == ("MISSING_PROVENANCE", "ADAPTER_REJECTED:x")
    assert outcome.native_gate_error is None
    assert outcome.native_result is None
    assert bridge.build_count == 1


def test_core_adapter_facade_v0_1_t07_gate_rejection_preserves_native_error_text(
    monkeypatch,
):
    monkeypatch.setattr(
        facade,
        "run_runtime_admission_gate",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("duplicate document_id")),
    )

    outcome = _adapter(_Bridge()).govern(_request())

    assert outcome.outcome is CoreAdapterOutcomeState.GOVERNANCE_REJECTED
    assert outcome.native_gate_error == "duplicate document_id"
    assert outcome.native_bridge_reasons == ()
    assert outcome.native_result is None


def test_core_adapter_facade_v0_1_t08_operational_failure_preserves_original_exception(
    monkeypatch,
):
    """An operational fault is classified apart from any governance verdict."""
    monkeypatch.setattr(facade, "run_runtime_admission_gate", _never)
    boom = RuntimeError("qdrant unreachable")

    outcome = _adapter(_Bridge(resolve_error=boom)).govern(_request())

    assert outcome.outcome is CoreAdapterOutcomeState.OPERATIONAL_FAILURE
    assert outcome.operational_exception is boom
    assert outcome.operational_error == "RuntimeError: qdrant unreachable"
    # never laundered into a governance verdict
    assert outcome.native_gate_error is None
    assert outcome.native_bridge_reasons == ()
    assert outcome.native_result is None


# --------------------------------------------------------------------- #
# closed boundary
# --------------------------------------------------------------------- #
def test_core_adapter_facade_v0_1_t09_export_surface_is_closed():
    assert set(core_adapter.__all__) == {
        "CoreAdapter",
        "CoreAdapterOutcome",
        "CoreAdapterOutcomeState",
        "CoreAdapterRequest",
        "CoreInvocationMode",
    }
    # the promotion / authority / receipt vocabulary must not be reachable here
    forbidden = set(admission.__all__) | {
        "AUTHORITY_SCOPE",
        "BRIDGE_ID",
        "GOVERNED_PACKAGE_KEY",
        "REQUESTED_OPERATION",
        "RuntimeEvidenceBridge",
    }
    for name in forbidden:
        assert not hasattr(core_adapter, name), name


def test_core_adapter_facade_v0_1_t10_facade_imports_exactly_two_governance_entry_points():
    imported = {
        name
        for name, value in vars(facade).items()
        if getattr(value, "__module__", "").startswith(
            ("app.modules.admission", "app.modules.runtime_evidence_bridge")
        )
    }
    assert imported == {"run_runtime_admission_gate", "build_qdrant_runtime_bridge"}


def test_core_adapter_facade_v0_1_t11_task_13_evidence_set_semantics_are_structurally_absent():
    """Verified against the live API, not against source text.

    The docstrings mention these names only to record their exclusion, so a
    raw-text scan would assert the opposite of what is true here.
    """
    for module in (core_adapter, facade, models):
        assert not hasattr(module, "GovernedEvidenceSet")

    # whole-invocation states only; no per-candidate verdict vocabulary
    assert set(CoreAdapterOutcomeState.__members__) == {
        "GOVERNANCE_COMPLETE",
        "GOVERNANCE_REJECTED",
        "OPERATIONAL_FAILURE",
    }
    for verdict in ("ADMITTED", "REJECTED", "UNKNOWN"):
        assert verdict not in CoreAdapterOutcomeState.__members__

    assert {f.name for f in dataclasses.fields(CoreAdapterRequest)} == {
        "candidate_set_id",
        "question_id",
        "candidates",
        "context_pack",
        "adapter_created_at",
        "mode",
    }
    assert {f.name for f in dataclasses.fields(CoreAdapterOutcome)} == {
        "outcome",
        "native_result",
        "native_bridge_reasons",
        "native_gate_error",
        "operational_error",
        "operational_exception",
        "candidate_count",
        "governed_count",
        "backend_id",
        "mapping_profile_id",
        "adapter_id",
        "adapter_version",
    }
