"""E3 derived-index lifecycle receipt objects (v0.1) — fail-closed construction.

Covers: immutability of every public model; fail-closed empty/invalid
collection names; the explicit-timestamp law (no clock default); fail-closed
invalid SHA256/fingerprint fields; deterministic receipt fingerprints; a
wrong receipt fingerprint failing closed; `measured_state_fingerprint`
stability across `measured_at` changes; `MeasuredPointDescriptor` permitting
missing verification fields; canonicalized (sorted) mismatch lists; and
immutable activation/rollback receipt bindings.

No Qdrant client, no network, no embedding, no filesystem is reachable from
any construction path exercised here — every object in this module is built
from plain declarations, so the whole module runs under `netguard`'s
`guarded` decorator.
"""

from __future__ import annotations

import dataclasses
import hashlib

from app.modules.derived_index import BACKEND_FAKE, DISTANCE_COSINE, EmbeddingProfile, VectorSchema
from app.modules.derived_index_lifecycle import (
    ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
    ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE,
    DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
    EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY,
    VERIFICATION_SCOPE_STRUCTURAL_V0_1,
    ActivationReceipt,
    CandidateMaterializationReceipt,
    DerivedIndexLifecycleError,
    MeasuredDerivedIndexDescriptor,
    MeasuredPointDescriptor,
    RollbackReceipt,
    VerificationReceipt,
)
from tests.netguard import guarded
from tests.util import raises

MATERIALIZED_AT = "2026-09-03T09:00:00Z"
MEASURED_AT_1 = "2026-09-03T09:05:00Z"
MEASURED_AT_2 = "2026-09-03T10:15:00Z"
VERIFIED_AT = "2026-09-03T09:10:00Z"
ACTIVATED_AT = "2026-09-03T09:15:00Z"
ROLLED_BACK_AT = "2026-09-03T09:20:00Z"


def _fp(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        backend=BACKEND_FAKE,
        model_name=None,
        model_revision=None,
        implementation_revision="ion-e3d-fake-impl-2026-09-03",
        dimension=8,
        normalization_profile="L2_NORMALIZED_BY_ADAPTER",
    )


def _schema() -> VectorSchema:
    return VectorSchema(dimension=8, distance_metric=DISTANCE_COSINE, vector_name=None)


def _candidate_receipt(**overrides) -> CandidateMaterializationReceipt:
    kwargs = dict(
        expected_derived_index_fingerprint=_fp("expected"),
        candidate_physical_collection="ion_candidate_blue",
        embedding_profile=_profile(),
        vector_schema=_schema(),
        expected_record_count=2,
        written_point_count=2,
        materialized_at=MATERIALIZED_AT,
        materializer_implementation_revision="ion-e3d-materializer-v0-1",
    )
    kwargs.update(overrides)
    return CandidateMaterializationReceipt.create(**kwargs)


def _measured_point(document_id="doc-1", evidence_fingerprint=None, point_id="pt-1") -> MeasuredPointDescriptor:
    return MeasuredPointDescriptor(
        qdrant_point_id=point_id,
        document_id=document_id,
        evidence_fingerprint=evidence_fingerprint if evidence_fingerprint is not None else _fp(document_id or "x"),
    )


def _measured_descriptor(**overrides) -> MeasuredDerivedIndexDescriptor:
    kwargs = dict(
        candidate_physical_collection="ion_candidate_blue",
        vector_schema=_schema(),
        reported_point_count=2,
        enumerated_point_count=2,
        measured_points=(
            _measured_point("doc-1", point_id="pt-1"),
            _measured_point("doc-2", point_id="pt-2"),
        ),
        measured_at=MEASURED_AT_1,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
    )
    kwargs.update(overrides)
    return MeasuredDerivedIndexDescriptor.create(**kwargs)


def _verification_receipt(**overrides) -> VerificationReceipt:
    kwargs = dict(
        verification_scope=VERIFICATION_SCOPE_STRUCTURAL_V0_1,
        expected_derived_index_fingerprint=_fp("expected"),
        candidate_receipt_fingerprint=_fp("candidate"),
        measured_state_fingerprint=_fp("measured"),
        expected_record_count=2,
        candidate_expected_record_count=2,
        candidate_written_point_count=2,
        qdrant_reported_point_count=2,
        enumerated_point_count=2,
        missing_document_ids=(),
        unexpected_document_ids=(),
        duplicate_document_ids=(),
        missing_required_payload_details=(),
        evidence_fingerprint_mismatches=(),
        bindings_match=True,
        schema_match=True,
        embedding_execution_binding=EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY,
        verified_at=VERIFIED_AT,
        verifier_implementation_revision="ion-e3d-verifier-v0-1",
    )
    kwargs.update(overrides)
    return VerificationReceipt.create(**kwargs)


def _activation_receipt(**overrides) -> ActivationReceipt:
    kwargs = dict(
        logical_alias="ion_retrieval_active",
        previous_active_collection=None,
        new_active_collection="ion_candidate_blue",
        expected_derived_index_fingerprint=_fp("expected"),
        verification_receipt_fingerprint=_fp("verification"),
        activation_method=ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE,
        activated_at=ACTIVATED_AT,
        activator_implementation_revision="ion-e3d-activator-v0-1",
    )
    kwargs.update(overrides)
    return ActivationReceipt.create(**kwargs)


# --------------------------------------------------------------------------- #
# immutability
# --------------------------------------------------------------------------- #
@guarded
def test_all_public_models_are_immutable():
    candidate = _candidate_receipt()
    with raises(dataclasses.FrozenInstanceError):
        candidate.candidate_physical_collection = "other"

    point = _measured_point()
    with raises(dataclasses.FrozenInstanceError):
        point.document_id = "other"

    measured = _measured_descriptor()
    with raises(dataclasses.FrozenInstanceError):
        measured.candidate_physical_collection = "other"

    verification = _verification_receipt()
    with raises(dataclasses.FrozenInstanceError):
        verification.status = "PASS"

    activation = _activation_receipt()
    with raises(dataclasses.FrozenInstanceError):
        activation.new_active_collection = "other"

    rollback = RollbackReceipt.create(
        logical_alias="ion_retrieval_active",
        from_collection="ion_candidate_green",
        to_collection="ion_candidate_blue",
        activation_receipt_fingerprint=_fp("activation"),
        rolled_back_at=ROLLED_BACK_AT,
        rollback_implementation_revision="ion-e3d-rollback-v0-1",
    )
    with raises(dataclasses.FrozenInstanceError):
        rollback.to_collection = "other"


# --------------------------------------------------------------------------- #
# collection-name / string shape fail-closed
# --------------------------------------------------------------------------- #
@guarded
def test_empty_candidate_physical_collection_fails_closed():
    with raises(DerivedIndexLifecycleError):
        _candidate_receipt(candidate_physical_collection="")


@guarded
def test_whitespace_padded_collection_name_fails_closed():
    with raises(DerivedIndexLifecycleError):
        _candidate_receipt(candidate_physical_collection=" ion_candidate_blue ")


@guarded
def test_empty_logical_alias_fails_closed():
    with raises(DerivedIndexLifecycleError):
        _activation_receipt(logical_alias="")


# --------------------------------------------------------------------------- #
# explicit timestamp law
# --------------------------------------------------------------------------- #
@guarded
def test_non_rfc3339_materialized_at_fails_closed():
    with raises(DerivedIndexLifecycleError):
        _candidate_receipt(materialized_at="2026-09-03")


@guarded
def test_naive_timestamp_without_utc_marker_fails_closed():
    with raises(DerivedIndexLifecycleError):
        _candidate_receipt(materialized_at="2026-09-03T09:00:00")


@guarded
def test_timestamp_is_never_defaulted():
    import inspect

    sig = inspect.signature(CandidateMaterializationReceipt.create)
    assert sig.parameters["materialized_at"].default is inspect.Parameter.empty


# --------------------------------------------------------------------------- #
# fingerprint shape / measured-never-trusted
# --------------------------------------------------------------------------- #
@guarded
def test_invalid_expected_fingerprint_shape_fails_closed():
    with raises(DerivedIndexLifecycleError):
        _candidate_receipt(expected_derived_index_fingerprint="not-a-sha256")


@guarded
def test_candidate_receipt_fingerprint_is_deterministic():
    a = _candidate_receipt()
    b = _candidate_receipt()
    assert a.candidate_receipt_fingerprint == b.candidate_receipt_fingerprint


@guarded
def test_wrong_candidate_receipt_fingerprint_fails_closed():
    good = _candidate_receipt()
    with raises(DerivedIndexLifecycleError):
        CandidateMaterializationReceipt(
            lifecycle_contract_version=good.lifecycle_contract_version,
            expected_derived_index_fingerprint=good.expected_derived_index_fingerprint,
            candidate_physical_collection=good.candidate_physical_collection,
            embedding_profile=good.embedding_profile,
            vector_schema=good.vector_schema,
            expected_record_count=good.expected_record_count,
            written_point_count=good.written_point_count,
            materialized_at=good.materialized_at,
            materializer_implementation_revision=good.materializer_implementation_revision,
            embedding_execution_binding=good.embedding_execution_binding,
            candidate_receipt_fingerprint=_fp("wrong"),
        )


@guarded
def test_wrong_verification_receipt_fingerprint_fails_closed():
    good = _verification_receipt()
    fields = {
        f.name: getattr(good, f.name)
        for f in dataclasses.fields(good)
        if f.name != "verification_receipt_fingerprint"
    }
    fields["verification_receipt_fingerprint"] = _fp("wrong")
    with raises(DerivedIndexLifecycleError):
        VerificationReceipt(**fields)


@guarded
def test_wrong_activation_receipt_fingerprint_fails_closed():
    good = _activation_receipt()
    fields = {
        f.name: getattr(good, f.name)
        for f in dataclasses.fields(good)
        if f.name != "activation_receipt_fingerprint"
    }
    fields["activation_receipt_fingerprint"] = _fp("wrong")
    with raises(DerivedIndexLifecycleError):
        ActivationReceipt(**fields)


# --------------------------------------------------------------------------- #
# measured_state_fingerprint stability
# --------------------------------------------------------------------------- #
@guarded
def test_measured_state_fingerprint_stable_across_measured_at_changes():
    a = _measured_descriptor(measured_at=MEASURED_AT_1)
    b = _measured_descriptor(measured_at=MEASURED_AT_2)
    assert a.measured_state_fingerprint == b.measured_state_fingerprint
    assert a.measured_at != b.measured_at


@guarded
def test_measured_state_fingerprint_changes_with_point_count():
    a = _measured_descriptor()
    b = _measured_descriptor(
        reported_point_count=3,
        enumerated_point_count=3,
        measured_points=a.measured_points + (_measured_point("doc-3", point_id="pt-3"),),
    )
    assert a.measured_state_fingerprint != b.measured_state_fingerprint


# --------------------------------------------------------------------------- #
# MeasuredPointDescriptor permits invalid/unverifiable store state
# --------------------------------------------------------------------------- #
@guarded
def test_measured_point_permits_missing_document_id():
    point = MeasuredPointDescriptor(
        qdrant_point_id="pt-x", document_id=None, evidence_fingerprint=_fp("x")
    )
    assert point.document_id is None


@guarded
def test_measured_point_permits_missing_evidence_fingerprint():
    point = MeasuredPointDescriptor(
        qdrant_point_id="pt-x", document_id="doc-x", evidence_fingerprint=None
    )
    assert point.evidence_fingerprint is None


@guarded
def test_measured_point_permits_both_missing():
    point = MeasuredPointDescriptor(
        qdrant_point_id="pt-x", document_id=None, evidence_fingerprint=None
    )
    assert point.document_id is None and point.evidence_fingerprint is None


@guarded
def test_measured_points_must_be_canonically_ordered_in_direct_construction():
    with raises(DerivedIndexLifecycleError):
        MeasuredDerivedIndexDescriptor(
            lifecycle_contract_version=DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
            candidate_physical_collection="ion_candidate_blue",
            vector_schema=_schema(),
            reported_point_count=2,
            enumerated_point_count=2,
            measured_points=(
                _measured_point("doc-2", point_id="pt-2"),
                _measured_point("doc-1", point_id="pt-1"),
            ),
            measured_at=MEASURED_AT_1,
            measurement_implementation_revision="ion-e3d-measurer-v0-1",
            measured_state_fingerprint=_fp("irrelevant-checked-after-order"),
        )


@guarded
def test_measured_descriptor_create_sorts_points_canonically():
    descriptor = MeasuredDerivedIndexDescriptor.create(
        candidate_physical_collection="ion_candidate_blue",
        vector_schema=_schema(),
        reported_point_count=2,
        enumerated_point_count=2,
        measured_points=(
            _measured_point("doc-2", point_id="pt-2"),
            _measured_point("doc-1", point_id="pt-1"),
        ),
        measured_at=MEASURED_AT_1,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
    )
    assert [p.qdrant_point_id for p in descriptor.measured_points] == ["pt-1", "pt-2"]


# --------------------------------------------------------------------------- #
# verification receipt: mismatch lists canonicalized, status self-consistent
# --------------------------------------------------------------------------- #
@guarded
def test_unsorted_missing_document_ids_fails_closed():
    good = _verification_receipt()
    fields = {f.name: getattr(good, f.name) for f in dataclasses.fields(good)}
    fields["missing_document_ids"] = ("doc-2", "doc-1")
    with raises(DerivedIndexLifecycleError):
        VerificationReceipt(**fields)


@guarded
def test_verification_status_must_match_computed_outcome():
    good = _verification_receipt()
    fields = {
        f.name: getattr(good, f.name)
        for f in dataclasses.fields(good)
        if f.name not in ("status", "verification_receipt_fingerprint")
    }
    fields["status"] = "FAIL"
    fields["verification_receipt_fingerprint"] = good.verification_receipt_fingerprint
    with raises(DerivedIndexLifecycleError):
        VerificationReceipt(**fields)


@guarded
def test_verification_create_derives_fail_from_missing_ids():
    receipt = _verification_receipt(
        missing_document_ids=("doc-3",),
        candidate_expected_record_count=2,
    )
    assert receipt.status == "FAIL"


@guarded
def test_verification_create_pass_when_all_clean():
    receipt = _verification_receipt()
    assert receipt.status == "PASS"


@guarded
def test_verification_create_fail_when_bindings_do_not_match():
    receipt = _verification_receipt(bindings_match=False)
    assert receipt.status == "FAIL"


@guarded
def test_verification_scope_is_always_structural_v0_1():
    receipt = _verification_receipt()
    assert receipt.verification_scope == "STRUCTURAL_V0_1"


# --------------------------------------------------------------------------- #
# activation / rollback receipt bindings
# --------------------------------------------------------------------------- #
@guarded
def test_bootstrap_activation_requires_previous_none():
    with raises(DerivedIndexLifecycleError):
        _activation_receipt(
            previous_active_collection="ion_candidate_green",
            activation_method=ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE,
        )


@guarded
def test_cutover_activation_requires_previous_not_none():
    with raises(DerivedIndexLifecycleError):
        _activation_receipt(
            previous_active_collection=None,
            new_active_collection="ion_candidate_blue",
            activation_method=ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
        )


@guarded
def test_activation_new_and_previous_collection_must_differ():
    with raises(DerivedIndexLifecycleError):
        _activation_receipt(
            previous_active_collection="ion_candidate_blue",
            new_active_collection="ion_candidate_blue",
            activation_method=ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
        )


@guarded
def test_rollback_from_and_to_collection_must_differ():
    with raises(DerivedIndexLifecycleError):
        RollbackReceipt.create(
            logical_alias="ion_retrieval_active",
            from_collection="ion_candidate_blue",
            to_collection="ion_candidate_blue",
            activation_receipt_fingerprint=_fp("activation"),
            rolled_back_at=ROLLED_BACK_AT,
            rollback_implementation_revision="ion-e3d-rollback-v0-1",
        )


@guarded
def test_rollback_receipt_binds_activation_receipt_fingerprint():
    activation = _activation_receipt(
        previous_active_collection="ion_candidate_blue",
        new_active_collection="ion_candidate_green",
        activation_method=ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
    )
    rollback = RollbackReceipt.create(
        logical_alias=activation.logical_alias,
        from_collection=activation.new_active_collection,
        to_collection=activation.previous_active_collection,
        activation_receipt_fingerprint=activation.activation_receipt_fingerprint,
        rolled_back_at=ROLLED_BACK_AT,
        rollback_implementation_revision="ion-e3d-rollback-v0-1",
    )
    assert rollback.activation_receipt_fingerprint == activation.activation_receipt_fingerprint


@guarded
def test_rollback_receipt_fingerprint_deterministic():
    kwargs = dict(
        logical_alias="ion_retrieval_active",
        from_collection="ion_candidate_green",
        to_collection="ion_candidate_blue",
        activation_receipt_fingerprint=_fp("activation"),
        rolled_back_at=ROLLED_BACK_AT,
        rollback_implementation_revision="ion-e3d-rollback-v0-1",
    )
    a = RollbackReceipt.create(**kwargs)
    b = RollbackReceipt.create(**kwargs)
    assert a.rollback_receipt_fingerprint == b.rollback_receipt_fingerprint
