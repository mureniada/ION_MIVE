"""Alias activation and rollback (E3 v0.1).

Covers: a FAIL VerificationReceipt cannot activate; bootstrap alias creation
requires PASS; normal activation performs one bounded alias-update request;
the prior physical collection is never deleted; the candidate collection
must exist; a prestate mismatch refuses the update; an alias/physical-name
collision fails closed; the activation receipt binds the verification
receipt; activation never builds/measures; a missing alias capability fails
closed; rollback after normal activation swaps the alias back in one
request; rollback never rebuilds or deletes; the previous collection must
still exist; the current alias target must match the activation receipt;
and a bootstrap activation cannot claim rollback.

No real Qdrant anywhere: `FakeAliasClient` is a small in-memory double
covering exactly `get_aliases` / `collection_exists` /
`update_collection_aliases`, and `qdrant_client.models` (`CreateAlias`,
`DeleteAlias`, ...) is the real lazily-imported library module — importing
just the pydantic model classes touches no network and starts no server.
"""

from __future__ import annotations

import hashlib

from app.modules.derived_index_lifecycle import (
    ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
    ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE,
    VERIFICATION_STATUS_FAIL,
    ActivationReceipt,
    DerivedIndexLifecycleError,
    activate_candidate,
    rollback_activation,
)
from tests.util import raises

ACTIVATED_AT = "2026-09-03T09:15:00Z"
ROLLED_BACK_AT = "2026-09-03T09:20:00Z"
LOGICAL_ALIAS = "ion_retrieval_active"


def _fp(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


class _AliasDescription:
    def __init__(self, alias_name, collection_name):
        self.alias_name = alias_name
        self.collection_name = collection_name


class _AliasesResponse:
    def __init__(self, aliases):
        self.aliases = aliases


class FakeAliasClient:
    """In-memory double covering exactly what activation.py calls."""

    def __init__(self, *, collections=None, alias_target: dict[str, str] | None = None):
        self.collections: set[str] = set(collections or ())
        self._alias_target: dict[str, str] = dict(alias_target or {})
        self.update_calls: list[list] = []

    def collection_exists(self, name):
        return name in self.collections

    def get_aliases(self):
        return _AliasesResponse(
            [
                _AliasDescription(alias_name=name, collection_name=target)
                for name, target in self._alias_target.items()
            ]
        )

    def update_collection_aliases(self, change_aliases_operations):
        self.update_calls.append(list(change_aliases_operations))
        for op in change_aliases_operations:
            if hasattr(op, "delete_alias"):
                self._alias_target.pop(op.delete_alias.alias_name, None)
            elif hasattr(op, "create_alias"):
                self._alias_target[op.create_alias.alias_name] = op.create_alias.collection_name
        return True


def _pass_receipt(**overrides):
    from tests.test_derived_index_lifecycle_models_v0_1 import _verification_receipt

    return _verification_receipt(**overrides)


def _fail_receipt():
    from tests.test_derived_index_lifecycle_models_v0_1 import _verification_receipt

    return _verification_receipt(bindings_match=False)


# --------------------------------------------------------------------------- #
# activate_candidate
# --------------------------------------------------------------------------- #
def test_fail_verification_cannot_activate():
    client = FakeAliasClient(collections={"ion_candidate_blue"})
    receipt = _fail_receipt()
    assert receipt.status == VERIFICATION_STATUS_FAIL
    with raises(DerivedIndexLifecycleError):
        activate_candidate(
            verification_receipt=receipt,
            candidate_physical_collection="ion_candidate_blue",
            logical_alias=LOGICAL_ALIAS,
            expected_previous_active_collection=None,
            activated_at=ACTIVATED_AT,
            activator_implementation_revision="ion-e3d-activator-v0-1",
            qdrant_client=client,
        )


def test_bootstrap_alias_creation_requires_pass_and_succeeds():
    client = FakeAliasClient(collections={"ion_candidate_blue"})
    receipt = _pass_receipt()
    activation = activate_candidate(
        verification_receipt=receipt,
        candidate_physical_collection="ion_candidate_blue",
        logical_alias=LOGICAL_ALIAS,
        expected_previous_active_collection=None,
        activated_at=ACTIVATED_AT,
        activator_implementation_revision="ion-e3d-activator-v0-1",
        qdrant_client=client,
    )
    assert activation.activation_method == ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE
    assert activation.previous_active_collection is None
    assert activation.new_active_collection == "ion_candidate_blue"
    assert client._alias_target[LOGICAL_ALIAS] == "ion_candidate_blue"
    assert len(client.update_calls) == 1  # one bounded request


def test_normal_activation_uses_one_alias_update_request_and_keeps_prior_collection():
    client = FakeAliasClient(
        collections={"ion_candidate_blue", "ion_candidate_green"},
        alias_target={LOGICAL_ALIAS: "ion_candidate_blue"},
    )
    receipt = _pass_receipt()
    activation = activate_candidate(
        verification_receipt=receipt,
        candidate_physical_collection="ion_candidate_green",
        logical_alias=LOGICAL_ALIAS,
        expected_previous_active_collection="ion_candidate_blue",
        activated_at=ACTIVATED_AT,
        activator_implementation_revision="ion-e3d-activator-v0-1",
        qdrant_client=client,
    )
    assert activation.activation_method == ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER
    assert activation.previous_active_collection == "ion_candidate_blue"
    assert activation.new_active_collection == "ion_candidate_green"
    assert client._alias_target[LOGICAL_ALIAS] == "ion_candidate_green"
    assert len(client.update_calls) == 1  # delete + create in ONE request
    assert len(client.update_calls[0]) == 2
    assert "ion_candidate_blue" in client.collections  # prior collection never deleted


def test_candidate_collection_must_exist():
    client = FakeAliasClient(collections=set())
    receipt = _pass_receipt()
    with raises(DerivedIndexLifecycleError):
        activate_candidate(
            verification_receipt=receipt,
            candidate_physical_collection="ion_candidate_blue",
            logical_alias=LOGICAL_ALIAS,
            expected_previous_active_collection=None,
            activated_at=ACTIVATED_AT,
            activator_implementation_revision="ion-e3d-activator-v0-1",
            qdrant_client=client,
        )


def test_prestate_mismatch_refuses_update():
    client = FakeAliasClient(
        collections={"ion_candidate_blue", "ion_candidate_green"},
        alias_target={LOGICAL_ALIAS: "ion_candidate_blue"},
    )
    receipt = _pass_receipt()
    with raises(DerivedIndexLifecycleError):
        activate_candidate(
            verification_receipt=receipt,
            candidate_physical_collection="ion_candidate_green",
            logical_alias=LOGICAL_ALIAS,
            expected_previous_active_collection="ion_candidate_stale_guess",
            activated_at=ACTIVATED_AT,
            activator_implementation_revision="ion-e3d-activator-v0-1",
            qdrant_client=client,
        )
    assert client.update_calls == []


def test_alias_name_collision_with_physical_collection_fails_closed():
    client = FakeAliasClient(collections={LOGICAL_ALIAS, "ion_candidate_blue"})
    receipt = _pass_receipt()
    with raises(DerivedIndexLifecycleError):
        activate_candidate(
            verification_receipt=receipt,
            candidate_physical_collection="ion_candidate_blue",
            logical_alias=LOGICAL_ALIAS,
            expected_previous_active_collection=None,
            activated_at=ACTIVATED_AT,
            activator_implementation_revision="ion-e3d-activator-v0-1",
            qdrant_client=client,
        )


def test_activation_receipt_binds_verification_receipt():
    client = FakeAliasClient(collections={"ion_candidate_blue"})
    receipt = _pass_receipt()
    activation = activate_candidate(
        verification_receipt=receipt,
        candidate_physical_collection="ion_candidate_blue",
        logical_alias=LOGICAL_ALIAS,
        expected_previous_active_collection=None,
        activated_at=ACTIVATED_AT,
        activator_implementation_revision="ion-e3d-activator-v0-1",
        qdrant_client=client,
    )
    assert activation.verification_receipt_fingerprint == receipt.verification_receipt_fingerprint
    assert activation.expected_derived_index_fingerprint == receipt.expected_derived_index_fingerprint


def test_missing_alias_capability_fails_closed():
    class IncompleteClient:
        def collection_exists(self, name):
            return True

    receipt = _pass_receipt()
    with raises(DerivedIndexLifecycleError):
        activate_candidate(
            verification_receipt=receipt,
            candidate_physical_collection="ion_candidate_blue",
            logical_alias=LOGICAL_ALIAS,
            expected_previous_active_collection=None,
            activated_at=ACTIVATED_AT,
            activator_implementation_revision="ion-e3d-activator-v0-1",
            qdrant_client=IncompleteClient(),
        )


def test_activation_performs_no_build_or_measurement_side_effects():
    client = FakeAliasClient(collections={"ion_candidate_blue"})
    receipt = _pass_receipt()
    activate_candidate(
        verification_receipt=receipt,
        candidate_physical_collection="ion_candidate_blue",
        logical_alias=LOGICAL_ALIAS,
        expected_previous_active_collection=None,
        activated_at=ACTIVATED_AT,
        activator_implementation_revision="ion-e3d-activator-v0-1",
        qdrant_client=client,
    )
    # the fake client exposes no upsert/scroll/create/delete surface at all;
    # activation calling any such method would raise AttributeError, not
    # silently succeed, so a passing run is itself the proof.
    assert client.collections == {"ion_candidate_blue"}


# --------------------------------------------------------------------------- #
# rollback_activation
# --------------------------------------------------------------------------- #
def _activate_normal(client):
    receipt = _pass_receipt()
    return activate_candidate(
        verification_receipt=receipt,
        candidate_physical_collection="ion_candidate_green",
        logical_alias=LOGICAL_ALIAS,
        expected_previous_active_collection="ion_candidate_blue",
        activated_at=ACTIVATED_AT,
        activator_implementation_revision="ion-e3d-activator-v0-1",
        qdrant_client=client,
    )


def test_rollback_after_normal_activation_switches_alias_back():
    client = FakeAliasClient(
        collections={"ion_candidate_blue", "ion_candidate_green"},
        alias_target={LOGICAL_ALIAS: "ion_candidate_blue"},
    )
    activation = _activate_normal(client)
    rollback = rollback_activation(
        activation_receipt=activation,
        rolled_back_at=ROLLED_BACK_AT,
        rollback_implementation_revision="ion-e3d-rollback-v0-1",
        qdrant_client=client,
    )
    assert client._alias_target[LOGICAL_ALIAS] == "ion_candidate_blue"
    assert rollback.from_collection == "ion_candidate_green"
    assert rollback.to_collection == "ion_candidate_blue"


def test_rollback_performs_one_alias_update_request():
    client = FakeAliasClient(
        collections={"ion_candidate_blue", "ion_candidate_green"},
        alias_target={LOGICAL_ALIAS: "ion_candidate_blue"},
    )
    activation = _activate_normal(client)
    calls_before = len(client.update_calls)
    rollback_activation(
        activation_receipt=activation,
        rolled_back_at=ROLLED_BACK_AT,
        rollback_implementation_revision="ion-e3d-rollback-v0-1",
        qdrant_client=client,
    )
    assert len(client.update_calls) == calls_before + 1
    assert len(client.update_calls[-1]) == 2  # delete + create, one request


def test_rollback_does_not_delete_any_collection():
    client = FakeAliasClient(
        collections={"ion_candidate_blue", "ion_candidate_green"},
        alias_target={LOGICAL_ALIAS: "ion_candidate_blue"},
    )
    activation = _activate_normal(client)
    rollback_activation(
        activation_receipt=activation,
        rolled_back_at=ROLLED_BACK_AT,
        rollback_implementation_revision="ion-e3d-rollback-v0-1",
        qdrant_client=client,
    )
    assert client.collections == {"ion_candidate_blue", "ion_candidate_green"}


def test_rollback_requires_previous_collection_still_exists():
    client = FakeAliasClient(
        collections={"ion_candidate_blue", "ion_candidate_green"},
        alias_target={LOGICAL_ALIAS: "ion_candidate_blue"},
    )
    activation = _activate_normal(client)
    client.collections.discard("ion_candidate_blue")  # simulate external deletion
    with raises(DerivedIndexLifecycleError):
        rollback_activation(
            activation_receipt=activation,
            rolled_back_at=ROLLED_BACK_AT,
            rollback_implementation_revision="ion-e3d-rollback-v0-1",
            qdrant_client=client,
        )


def test_rollback_requires_current_alias_target_matches_activation_receipt():
    client = FakeAliasClient(
        collections={"ion_candidate_blue", "ion_candidate_green", "ion_candidate_red"},
        alias_target={LOGICAL_ALIAS: "ion_candidate_blue"},
    )
    activation = _activate_normal(client)
    # something else moved the alias in between
    client._alias_target[LOGICAL_ALIAS] = "ion_candidate_red"
    with raises(DerivedIndexLifecycleError):
        rollback_activation(
            activation_receipt=activation,
            rolled_back_at=ROLLED_BACK_AT,
            rollback_implementation_revision="ion-e3d-rollback-v0-1",
            qdrant_client=client,
        )


def test_bootstrap_activation_cannot_claim_rollback():
    client = FakeAliasClient(collections={"ion_candidate_blue"})
    receipt = _pass_receipt()
    bootstrap = activate_candidate(
        verification_receipt=receipt,
        candidate_physical_collection="ion_candidate_blue",
        logical_alias=LOGICAL_ALIAS,
        expected_previous_active_collection=None,
        activated_at=ACTIVATED_AT,
        activator_implementation_revision="ion-e3d-activator-v0-1",
        qdrant_client=client,
    )
    assert bootstrap.previous_active_collection is None
    with raises(DerivedIndexLifecycleError):
        rollback_activation(
            activation_receipt=bootstrap,
            rolled_back_at=ROLLED_BACK_AT,
            rollback_implementation_revision="ion-e3d-rollback-v0-1",
            qdrant_client=client,
        )


def test_rollback_receipt_binds_activation_receipt_fingerprint():
    client = FakeAliasClient(
        collections={"ion_candidate_blue", "ion_candidate_green"},
        alias_target={LOGICAL_ALIAS: "ion_candidate_blue"},
    )
    activation = _activate_normal(client)
    rollback = rollback_activation(
        activation_receipt=activation,
        rolled_back_at=ROLLED_BACK_AT,
        rollback_implementation_revision="ion-e3d-rollback-v0-1",
        qdrant_client=client,
    )
    assert rollback.activation_receipt_fingerprint == activation.activation_receipt_fingerprint


def test_rollback_missing_alias_capability_fails_closed():
    class IncompleteClient:
        def collection_exists(self, name):
            return True

    activation = ActivationReceipt.create(
        logical_alias=LOGICAL_ALIAS,
        previous_active_collection="ion_candidate_blue",
        new_active_collection="ion_candidate_green",
        expected_derived_index_fingerprint=_fp("expected"),
        verification_receipt_fingerprint=_fp("verification"),
        activation_method=ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
        activated_at=ACTIVATED_AT,
        activator_implementation_revision="ion-e3d-activator-v0-1",
    )
    with raises(DerivedIndexLifecycleError):
        rollback_activation(
            activation_receipt=activation,
            rolled_back_at=ROLLED_BACK_AT,
            rollback_implementation_revision="ion-e3d-rollback-v0-1",
            qdrant_client=IncompleteClient(),
        )
