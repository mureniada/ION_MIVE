"""Bounded contract test for Product Governed Evidence Output (v0.1).

Scope is deliberately narrow: this covers the PRODUCT materialization only —
what a `GovernedEvidenceSet` may say about a governance run Core already
completed, and what it refuses to say. Admission, provenance and fingerprint
semantics stay owned and tested by the frozen governance modules; nothing here
re-asserts them, and nothing here exercises them: every native object below is a
stand-in, so a passing run proves the Product contract, not the governance one.

Absence checks are structural, never textual. This module and the module under
test both name `native_gate_error`, bridge rejection reasons and the per-candidate
REJECTED / UNKNOWN vocabulary in their docstrings precisely in order to record
that those concepts are EXCLUDED at v0.1, so a raw-text scan would report the
exact opposite of the truth. These tests interrogate the dataclass field sets,
the module namespaces and the parsed import/identifier graph instead.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules import governed_evidence
import app.modules.governed_evidence.materializer as materializer
import app.modules.governed_evidence.models as models
from app.modules.governed_evidence import (
    ACCOUNTING_STATE_NOT_SUBMITTED,
    CandidateAccountingEntry,
    GovernanceDisposition,
    GovernedEvidenceMaterializationError,
    GovernedEvidenceSet,
    MaterializationInput,
    materialize_governed_evidence_set,
)


VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"

_DEFAULT = object()

MODULE_PATHS = (
    Path(models.__file__),
    Path(materializer.__file__),
    Path(governed_evidence.__file__),
)


# --------------------------------------------------------------------- #
# stand-ins for the native governance objects, shaped as the runtime returns
# them. Nothing here is a governance engine; these only carry fields.
# --------------------------------------------------------------------- #
def _fingerprint(candidate_id, *, hash_value=None):
    return SimpleNamespace(
        algorithm="SHA256",
        hash=hash_value or "FP-" + candidate_id,
        content_id=candidate_id,
    )


def _record(
    candidate_id,
    *,
    status=VERIFIED,
    validation_id=None,
    hash_value=None,
    fingerprint=_DEFAULT,
    evidence_id=None,
):
    return SimpleNamespace(
        evidence_id=candidate_id if evidence_id is None else evidence_id,
        claim='{"contract_id":"STRUCTURAL","evidence_id":"' + candidate_id + '"}',
        status=status,
        source=SimpleNamespace(type="DOCUMENT", identifier="src-" + candidate_id, location="origin"),
        provenance=SimpleNamespace(
            origin="origin",
            collection_method="INGEST",
            collector="collector",
            timestamp="2026-08-20T10:00:00Z",
        ),
        fingerprint=(
            _fingerprint(candidate_id, hash_value=hash_value)
            if fingerprint is _DEFAULT
            else fingerprint
        ),
        created_at="2026-08-24T00:00:00Z",
        updated_at="2026-08-24T00:00:00Z",
        validation_id=validation_id or "VAL-" + candidate_id,
    )


def _validation(
    candidate_id,
    *,
    result=PASS,
    blocking=(),
    validation_id=None,
    hash_value=None,
    evidence_id=None,
):
    return SimpleNamespace(
        validation_id=validation_id or "VAL-" + candidate_id,
        evidence_id=candidate_id if evidence_id is None else evidence_id,
        profile_id="ION_RUNTIME_STRUCTURAL_ADMISSION_VALIDATOR_PROFILE_V0_1",
        result=result,
        checks=(),
        blocking_reasons=blocking,
        receipt_id=None,
        validated_at="2026-08-24T00:00:00Z",
        evidence_fingerprint_hash=hash_value or "FP-" + candidate_id,
        supersedes_validation_id=None,
    )


def _transition(
    candidate_id,
    *,
    from_status=PENDING,
    to_status=VERIFIED,
    validation_id=None,
    evidence_id=None,
):
    return SimpleNamespace(
        transition_id="TR-" + candidate_id,
        evidence_id=candidate_id if evidence_id is None else evidence_id,
        from_status=from_status,
        to_status=to_status,
        actor="ION_RUNTIME_ADMISSION_VALIDATOR_V0_1",
        authority="VALIDATION_RIGHT",
        reason="RUNTIME_STRUCTURAL_ADMISSION_VALIDATION_PASS",
        timestamp="2026-08-24T00:00:00Z",
        validation_id=validation_id or "VAL-" + candidate_id,
        promotion_id=None,
        receipt_id=None,
    )


def _native(records=(), validations=(), transitions=()):
    return SimpleNamespace(
        records=tuple(records),
        validations=tuple(validations),
        transitions=tuple(transitions),
    )


def _native_for(candidate_ids):
    return _native(
        [_record(i) for i in candidate_ids],
        [_validation(i) for i in candidate_ids],
        [_transition(i) for i in candidate_ids],
    )


def _input(
    *,
    retrieved=("EV-1",),
    submitted=None,
    native=None,
    outcome_state="GOVERNANCE_COMPLETE",
    candidate_count=None,
    governed_count=None,
    metadata=None,
    **overrides,
):
    retrieved = tuple(retrieved)
    submitted = retrieved if submitted is None else tuple(submitted)
    native = _native_for(submitted) if native is None else native
    base = dict(
        outcome_state=outcome_state,
        native_result=native,
        retrieved_candidate_ids=retrieved,
        submitted_candidate_ids=submitted,
        candidate_count=len(retrieved) if candidate_count is None else candidate_count,
        governed_count=(
            len(getattr(native, "records", ())) if governed_count is None else governed_count
        ),
        backend_id="TEST-BACKEND",
        mapping_profile_id="TEST-PROFILE",
        adapter_id="ION_CORE_ADAPTER_FACADE_V0_1",
        adapter_version="0.1",
        context_pack_id="CP-001",
        question_id="REQ-001",
        context_pack_metadata=(
            {
                "evidence_count": len(retrieved),
                "included_documents": len(submitted),
                "truncated": len(submitted) != len(retrieved),
            }
            if metadata is None
            else metadata
        ),
    )
    base.update(overrides)
    return MaterializationInput(**base)


def _one(record=None, validation=None, transition=None):
    """A one-candidate input with a single native object replaced."""
    return _input(
        retrieved=("EV-1",),
        native=_native(
            [_record("EV-1") if record is None else record],
            [_validation("EV-1") if validation is None else validation],
            [_transition("EV-1") if transition is None else transition],
        ),
    )


def _identifiers(path):
    """Every identifier the parsed module actually uses. Docstrings excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return names


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute, relative = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.add((node.level, node.module or ""))
            else:
                absolute.add(node.module or "")
    return absolute, relative


# --------------------------------------------------------------------- #
# 1-4  the success path
# --------------------------------------------------------------------- #
def test_governed_evidence_v0_1_t01_verified_success_materializes_admitted_entries():
    ges = materialize_governed_evidence_set(_input(retrieved=("EV-1", "EV-2")))

    assert isinstance(ges, GovernedEvidenceSet)
    assert [e.candidate_id for e in ges.admitted] == ["EV-1", "EV-2"]
    assert {e.disposition for e in ges.admitted} == {GovernanceDisposition.ADMITTED}
    assert ges.governed_evidence_set_id == "ION_GOVERNED_EVIDENCE_SET_V0_1"
    assert ges.governed_evidence_set_version == "0.1"
    assert ges.backend_id == "TEST-BACKEND"
    assert ges.mapping_profile_id == "TEST-PROFILE"
    assert ges.adapter_id == "ION_CORE_ADAPTER_FACADE_V0_1"
    assert ges.adapter_version == "0.1"
    assert ges.context_pack_id == "CP-001"
    assert ges.question_id == "REQ-001"


def test_governed_evidence_v0_1_t02_identity_join_is_by_evidence_id_value():
    """Index-joining would mispair every entry here; value-joining cannot."""
    ids = ("EV-1", "EV-2", "EV-3")
    native = _native(
        [_record(i) for i in ids],
        [_validation(i) for i in reversed(ids)],
        [_transition(i) for i in ids[1:] + ids[:1]],
    )

    ges = materialize_governed_evidence_set(_input(retrieved=ids, native=native))

    assert [e.candidate_id for e in ges.admitted] == list(ids)
    for entry in ges.admitted:
        assert entry.native_record.evidence_id == entry.candidate_id
        assert entry.native_validation.evidence_id == entry.candidate_id
        assert entry.native_transition.evidence_id == entry.candidate_id


def test_governed_evidence_v0_1_t03_native_objects_are_preserved_by_reference():
    record, validation, transition = _record("EV-1"), _validation("EV-1"), _transition("EV-1")

    entry = materialize_governed_evidence_set(_one(record, validation, transition)).admitted[0]

    assert entry.native_record is record
    assert entry.native_validation is validation
    assert entry.native_transition is transition
    # the claim survives only as part of the native record: verbatim and opaque
    assert entry.native_record.claim is record.claim


def test_governed_evidence_v0_1_t04_native_verified_status_is_preserved_not_replaced():
    record = _record("EV-1")

    entry = materialize_governed_evidence_set(_one(record)).admitted[0]

    assert entry.native_status is record.status
    assert entry.native_status == VERIFIED
    assert entry.native_record.status == VERIFIED
    # ADMITTED is an ADDITIONAL Product label over an unchanged native status
    assert entry.disposition is GovernanceDisposition.ADMITTED
    assert entry.disposition != entry.native_status


# --------------------------------------------------------------------- #
# 5-7  fail-closed entry conditions
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "status", ["PENDING", "PROMOTED", "REJECTED", "UNKNOWN", "SOMETHING_ELSE"]
)
def test_governed_evidence_v0_1_t05_non_verified_returned_record_fails_closed(status):
    with pytest.raises(GovernedEvidenceMaterializationError) as excinfo:
        materialize_governed_evidence_set(_one(record=_record("EV-1", status=status)))

    assert VERIFIED in str(excinfo.value)


def test_governed_evidence_v0_1_t06_governance_rejected_creates_no_governed_evidence_set():
    with pytest.raises(GovernedEvidenceMaterializationError):
        materialize_governed_evidence_set(_input(outcome_state="GOVERNANCE_REJECTED"))

    # a fully valid native payload does not rescue a rejected run: the outcome
    # state is authoritative, and set-level rejection carries no per-candidate basis
    with pytest.raises(GovernedEvidenceMaterializationError):
        materialize_governed_evidence_set(
            _input(outcome_state="GOVERNANCE_REJECTED", native=_native_for(("EV-1", "EV-2")))
        )


def test_governed_evidence_v0_1_t07_operational_failure_creates_no_governed_evidence_set():
    with pytest.raises(GovernedEvidenceMaterializationError):
        materialize_governed_evidence_set(
            _input(outcome_state="OPERATIONAL_FAILURE", native_result=None)
        )

    # operational failure is not a governance verdict, complete payload or not
    with pytest.raises(GovernedEvidenceMaterializationError):
        materialize_governed_evidence_set(_input(outcome_state="OPERATIONAL_FAILURE"))


# --------------------------------------------------------------------- #
# 8-9  rejection text has no channel into a per-candidate verdict
# --------------------------------------------------------------------- #
def test_governed_evidence_v0_1_t08_native_gate_error_is_never_parsed_into_a_verdict():
    assert {f.name for f in dataclasses.fields(MaterializationInput)} == {
        "outcome_state",
        "native_result",
        "retrieved_candidate_ids",
        "submitted_candidate_ids",
        "candidate_count",
        "governed_count",
        "backend_id",
        "mapping_profile_id",
        "adapter_id",
        "adapter_version",
        "context_pack_id",
        "question_id",
        "context_pack_metadata",
    }

    # the free-form gate error has no field to enter through ...
    with pytest.raises(TypeError):
        _input(native_gate_error="stored fingerprint mismatch for EV-1")

    # ... and no module under test ever reads or names it as an identifier
    for path in MODULE_PATHS:
        used = _identifiers(path)
        assert "native_gate_error" not in used
        assert "operational_error" not in used
        assert "operational_exception" not in used


def test_governed_evidence_v0_1_t09_bridge_reason_naming_an_evidence_id_yields_no_verdict():
    # a bridge reason can name a document_id ("CANONICAL_REJECTED:EV-1:..."), but
    # that is fail-fast set-level text, not a disposition for EV-1 or anyone else
    with pytest.raises(TypeError):
        _input(native_bridge_reasons=("CANONICAL_REJECTED:EV-1:MISSING_PROVENANCE",))

    for path in MODULE_PATHS:
        used = _identifiers(path)
        assert "native_bridge_reasons" not in used
        assert "split" not in used
        assert "partition" not in used

    # and the run that produced such a reason still materializes nothing
    with pytest.raises(GovernedEvidenceMaterializationError):
        materialize_governed_evidence_set(_input(outcome_state="GOVERNANCE_REJECTED"))


# --------------------------------------------------------------------- #
# 10-11  the accounting axis
# --------------------------------------------------------------------- #
def test_governed_evidence_v0_1_t10_not_submitted_entry_has_no_disposition_field():
    names = {f.name for f in dataclasses.fields(CandidateAccountingEntry)}
    assert names == {"candidate_id", "accounting_state"}
    assert "disposition" not in names

    ges = materialize_governed_evidence_set(
        _input(retrieved=("EV-1", "EV-2"), submitted=("EV-1",))
    )
    entry = ges.accounting.not_submitted[0]

    assert entry.candidate_id == "EV-2"
    assert entry.accounting_state == ACCOUNTING_STATE_NOT_SUBMITTED == "NOT_SUBMITTED"
    assert not hasattr(entry, "disposition")
    # never governed, never admitted, never eligible as evidence
    assert entry.candidate_id not in ges.accounting.governed_ids
    assert entry.candidate_id not in {e.candidate_id for e in ges.admitted}


def test_governed_evidence_v0_1_t11_candidate_accounting_is_exact():
    metadata = {
        "evidence_count": 3,
        "included_documents": 2,
        "truncated": True,
        "char_budget": 60000,
        "total_characters": 59000,
    }

    ges = materialize_governed_evidence_set(
        _input(
            retrieved=("EV-1", "EV-2", "EV-3"),
            submitted=("EV-1", "EV-2"),
            metadata=metadata,
        )
    )
    accounting = ges.accounting

    assert accounting.retrieved_ids == ("EV-1", "EV-2", "EV-3")
    assert accounting.submitted_ids == ("EV-1", "EV-2")
    assert accounting.governed_ids == ("EV-1", "EV-2")
    assert tuple(e.candidate_id for e in accounting.not_submitted) == ("EV-3",)
    assert accounting.retrieved_count == 3
    assert accounting.governed_count == 2
    assert set(accounting.governed_ids).isdisjoint(
        {e.candidate_id for e in accounting.not_submitted}
    )
    assert set(accounting.retrieved_ids) == set(accounting.submitted_ids) | {
        e.candidate_id for e in accounting.not_submitted
    }
    # Product-owned accounting context, carried verbatim and never reinterpreted
    assert dict(accounting.context_pack_metadata) == metadata


# --------------------------------------------------------------------- #
# 12-13  fail-closed invariants
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "build",
    [
        lambda: _input(retrieved=("EV-1", "EV-1"), submitted=("EV-1",)),
        lambda: _input(
            retrieved=("EV-1",),
            submitted=("EV-1",),
            native=_native(
                [_record("EV-1"), _record("EV-1")],
                [_validation("EV-1"), _validation("EV-1")],
                [_transition("EV-1"), _transition("EV-1")],
            ),
        ),
        lambda: _input(retrieved=("EV-1",), submitted=("EV-1",), native=_native_for(("EV-9",))),
        lambda: _input(retrieved=("EV-1",), submitted=("EV-1", "EV-2")),
        lambda: _input(
            retrieved=("EV-1", "EV-2"),
            native=_native(
                [_record("EV-1"), _record("EV-2")],
                [_validation("EV-1"), _validation("EV-9")],
                [_transition("EV-1"), _transition("EV-2")],
            ),
        ),
        lambda: _input(
            retrieved=("EV-1", "EV-2"),
            native=_native(
                [_record("EV-1"), _record("EV-2")],
                [_validation("EV-1"), _validation("EV-2")],
                [_transition("EV-1"), _transition("EV-9")],
            ),
        ),
        lambda: _input(
            retrieved=("EV-1", "EV-2"),
            native=_native(
                [_record("EV-1"), _record("EV-2")],
                [_validation("EV-1")],
                [_transition("EV-1"), _transition("EV-2")],
            ),
        ),
        lambda: _input(retrieved=("EV-1",), candidate_count=99),
        lambda: _input(retrieved=("EV-1",), governed_count=99),
    ],
    ids=[
        "duplicate-retrieved-id",
        "duplicate-record-id",
        "governed-id-not-submitted",
        "submitted-id-not-retrieved",
        "validation-identity-mismatch",
        "transition-identity-mismatch",
        "cardinality-mismatch",
        "candidate-count-mismatch",
        "governed-count-mismatch",
    ],
)
def test_governed_evidence_v0_1_t12_identity_defects_fail_closed(build):
    with pytest.raises(GovernedEvidenceMaterializationError):
        materialize_governed_evidence_set(build())


@pytest.mark.parametrize(
    "build",
    [
        lambda: _one(record=_record("EV-1", hash_value="FP-OTHER")),
        lambda: _one(record=_record("EV-1", fingerprint=None)),
        lambda: _one(validation=_validation("EV-1", result="FAIL")),
        lambda: _one(validation=_validation("EV-1", result="UNKNOWN")),
        lambda: _one(validation=_validation("EV-1", blocking=("V01:fingerprint mismatch",))),
        lambda: _one(record=_record("EV-1", validation_id="VAL-OTHER")),
        lambda: _one(transition=_transition("EV-1", validation_id="VAL-OTHER")),
        lambda: _one(transition=_transition("EV-1", from_status="UNKNOWN")),
        lambda: _one(transition=_transition("EV-1", to_status="PROMOTED")),
    ],
    ids=[
        "fingerprint-hash-mismatch",
        "fingerprint-absent",
        "validation-fail",
        "validation-unknown",
        "validation-blocking-reasons",
        "record-validation-id-mismatch",
        "transition-validation-id-mismatch",
        "transition-from-status-not-pending",
        "transition-to-status-not-verified",
    ],
)
def test_governed_evidence_v0_1_t13_governance_basis_defects_fail_closed(build):
    with pytest.raises(GovernedEvidenceMaterializationError):
        materialize_governed_evidence_set(build())


# --------------------------------------------------------------------- #
# 14-16  v0.1 production law and the closed boundary
# --------------------------------------------------------------------- #
def test_governed_evidence_v0_1_t14_rejected_and_unknown_collections_stay_empty():
    assert set(GovernanceDisposition.__members__) == {"ADMITTED", "REJECTED", "UNKNOWN"}

    ges = materialize_governed_evidence_set(_input(retrieved=("EV-1", "EV-2")))

    assert ges.rejected == ()
    assert ges.unknown == ()
    assert {e.disposition for e in ges.admitted} == {GovernanceDisposition.ADMITTED}

    # structurally pinned: no construction path may populate either collection
    entry = ges.admitted[0]
    for populated in ({"rejected": (entry,)}, {"unknown": (entry,)}):
        with pytest.raises(GovernedEvidenceMaterializationError):
            dataclasses.replace(ges, **populated)


def test_governed_evidence_v0_1_t15_module_has_no_governance_or_mutation_authority():
    allowed_stdlib = {"__future__", "collections", "dataclasses", "enum", "types", "typing"}
    own_modules = {"materializer", "models"}

    for path in MODULE_PATHS:
        absolute, relative = _imports(path)
        for module in absolute:
            assert module.split(".")[0] in allowed_stdlib, (path.name, module)
        for level, module in relative:
            assert level == 1, (path.name, level, module)
            assert module in own_modules, (path.name, module)

    # no governance, adapter, bridge, provenance or retrieval name is reachable
    forbidden = (
        "CoreAdapter",
        "CoreAdapterOutcome",
        "run_runtime_admission_gate",
        "build_qdrant_runtime_bridge",
        "RuntimeEvidenceBridge",
        "ProvenanceResolution",
        "resolve_evidence_provenance",
        "ContextPackAdapter",
        "EvidenceValidator",
        "StateTransitionEngine",
        "PromotionEngine",
        "PromotionResult",
        "AuthorityRight",
        "EvidenceStatus",
        "QdrantRetrieval",
    )
    for module in (governed_evidence, materializer, models):
        for name in forbidden:
            assert not hasattr(module, name), (module.__name__, name)

    assert set(governed_evidence.__all__) == {
        "ACCOUNTING_STATE_NOT_SUBMITTED",
        "GOVERNANCE_COMPLETE",
        "GOVERNED_EVIDENCE_SET_ID",
        "GOVERNED_EVIDENCE_SET_VERSION",
        "MATERIALIZER_ID",
        "MATERIALIZER_VERSION",
        "CandidateAccounting",
        "CandidateAccountingEntry",
        "GovernanceDisposition",
        "GovernedEvidenceEntry",
        "GovernedEvidenceMaterializationError",
        "GovernedEvidenceSet",
        "MaterializationInput",
        "materialize_governed_evidence_set",
    }


def test_governed_evidence_v0_1_t16_no_wall_clock_or_random_identity_is_generated():
    for path in MODULE_PATHS:
        absolute, _ = _imports(path)
        for module in absolute:
            assert module.split(".")[0] not in {"datetime", "time", "uuid", "random", "re"}

        used = _identifiers(path)
        for forbidden in ("now", "utcnow", "utc_now_iso", "monotonic", "uuid4", "uuid", "random"):
            assert forbidden not in used, (path.name, forbidden)

    set_fields = {f.name for f in dataclasses.fields(GovernedEvidenceSet)}
    assert not any(
        token in name for name in set_fields for token in ("_at", "time", "clock", "date")
    )
