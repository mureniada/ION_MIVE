"""Alias activation and rollback (E3 v0.1) — the bounded blue/green cutover.

`activate_candidate` consumes a PASS `VerificationReceipt` and performs
exactly one `update_collection_aliases` request: a bootstrap create (alias
was absent) or an atomic cutover (delete-from-A + create-to-B in the same
request — the shape the E3C alias experiment already proved). It never
builds, embeds, measures, verifies, or deletes a collection.

`rollback_activation` consumes an `ActivationReceipt` and performs the
reverse cutover, alias back to the collection the activation replaced. It
never rebuilds, re-embeds, or deletes anything either. A bootstrap
activation (`previous_active_collection is None`) has nothing to roll back
to and is refused.

    VERIFY != ACTIVATE
    ROLLBACK != REBUILD
    CANDIDATE != ACTIVE
    VERIFIED != ACTIVE

Concurrency qualification (binding, not advisory): this module provides no
transactional compare-and-swap lock against multiple concurrent lifecycle
writers. The `expected_previous_active_collection` prestate check reduces
stale-operator/race risk by refusing to act on a target that has already
moved, but it is a precondition check, not a distributed lock. E3 v0.1
requires exclusive lifecycle-writer authority during activation and
rollback; concurrent alias writers are out of scope.
"""

from __future__ import annotations

from typing import Any

from .models import (
    ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
    ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE,
    VERIFICATION_STATUS_PASS,
    ActivationReceipt,
    DerivedIndexLifecycleError,
    RollbackReceipt,
    VerificationReceipt,
)

__all__ = ["activate_candidate", "rollback_activation"]

_REQUIRED_ALIAS_CAPABILITIES: tuple[str, ...] = (
    "get_aliases",
    "collection_exists",
    "update_collection_aliases",
)


def _require_alias_capability(qdrant_client: Any) -> None:
    missing = [name for name in _REQUIRED_ALIAS_CAPABILITIES if not hasattr(qdrant_client, name)]
    if missing:
        raise DerivedIndexLifecycleError(
            f"the injected Qdrant client is missing required alias capability method(s) "
            f"{missing}; refusing to activate/rollback rather than inferring capability "
            "from a package version string"
        )


def _current_alias_target(qdrant_client: Any, logical_alias: str) -> str | None:
    """Read current alias state for `logical_alias`. None means alias absent."""
    response = qdrant_client.get_aliases()
    matches = [alias for alias in response.aliases if alias.alias_name == logical_alias]
    if len(matches) > 1:
        raise DerivedIndexLifecycleError(
            f"logical alias {logical_alias!r} resolves to {len(matches)} ambiguous targets; "
            "refusing to reinterpret an ambiguous alias state"
        )
    if not matches:
        if qdrant_client.collection_exists(logical_alias):
            raise DerivedIndexLifecycleError(
                f"logical alias name {logical_alias!r} collides with an existing physical "
                "collection of the same name; refusing to bootstrap an alias over it"
            )
        return None
    return matches[0].collection_name


def activate_candidate(
    *,
    verification_receipt: VerificationReceipt,
    candidate_physical_collection: str,
    logical_alias: str,
    expected_previous_active_collection: str | None,
    activated_at: str,
    activator_implementation_revision: str,
    qdrant_client: Any,
) -> ActivationReceipt:
    """Activate one verified candidate behind `logical_alias`.

    Requires `verification_receipt.status == PASS` and that
    `verification_receipt` binds `candidate_physical_collection` (via its
    `candidate_receipt_fingerprint`/measured-state linkage is the caller's
    responsibility to have verified together — here we bind on the physical
    collection address the verification measured against, which
    `verify_candidate` always sets equal to `measured_descriptor
    .candidate_physical_collection` on a real PASS).
    """
    if verification_receipt.status != VERIFICATION_STATUS_PASS:
        raise DerivedIndexLifecycleError(
            f"activation requires a PASS VerificationReceipt, found "
            f"{verification_receipt.status!r}; a candidate that failed structural "
            "verification must never be activated"
        )

    _require_alias_capability(qdrant_client)

    if not qdrant_client.collection_exists(candidate_physical_collection):
        raise DerivedIndexLifecycleError(
            f"candidate physical collection {candidate_physical_collection!r} does not "
            "exist; cannot activate a candidate that is not present"
        )

    actual_target = _current_alias_target(qdrant_client, logical_alias)
    if actual_target != expected_previous_active_collection:
        raise DerivedIndexLifecycleError(
            f"alias {logical_alias!r} prestate mismatch: expected previous active "
            f"collection {expected_previous_active_collection!r}, actual current target "
            f"{actual_target!r}. Refusing to activate against a stale prestate."
        )

    if actual_target == candidate_physical_collection:
        raise DerivedIndexLifecycleError(
            f"logical alias {logical_alias!r} already targets "
            f"{candidate_physical_collection!r}; activation requires the candidate to "
            "differ from the currently active physical collection"
        )

    from qdrant_client import models as qmodels  # lazy: no client/network at import time

    if actual_target is None:
        operations = [
            qmodels.CreateAliasOperation(
                create_alias=qmodels.CreateAlias(
                    alias_name=logical_alias, collection_name=candidate_physical_collection
                )
            )
        ]
        activation_method = ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE
    else:
        operations = [
            qmodels.DeleteAliasOperation(
                delete_alias=qmodels.DeleteAlias(alias_name=logical_alias)
            ),
            qmodels.CreateAliasOperation(
                create_alias=qmodels.CreateAlias(
                    alias_name=logical_alias, collection_name=candidate_physical_collection
                )
            ),
        ]
        activation_method = ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER

    qdrant_client.update_collection_aliases(change_aliases_operations=operations)

    return ActivationReceipt.create(
        logical_alias=logical_alias,
        previous_active_collection=actual_target,
        new_active_collection=candidate_physical_collection,
        expected_derived_index_fingerprint=verification_receipt.expected_derived_index_fingerprint,
        verification_receipt_fingerprint=verification_receipt.verification_receipt_fingerprint,
        activation_method=activation_method,
        activated_at=activated_at,
        activator_implementation_revision=activator_implementation_revision,
    )


def rollback_activation(
    *,
    activation_receipt: ActivationReceipt,
    rolled_back_at: str,
    rollback_implementation_revision: str,
    qdrant_client: Any,
) -> RollbackReceipt:
    """Reverse exactly one `ActivationReceipt` by one alias cutover.

    A bootstrap activation (`previous_active_collection is None`) has no
    prior physical collection to return to and cannot be rolled back.
    """
    if activation_receipt.previous_active_collection is None:
        raise DerivedIndexLifecycleError(
            "this ActivationReceipt has no previous_active_collection (bootstrap "
            "activation); rollback is not available"
        )

    _require_alias_capability(qdrant_client)

    actual_target = _current_alias_target(qdrant_client, activation_receipt.logical_alias)
    if actual_target != activation_receipt.new_active_collection:
        raise DerivedIndexLifecycleError(
            f"alias {activation_receipt.logical_alias!r} no longer targets "
            f"{activation_receipt.new_active_collection!r} (found {actual_target!r}); "
            "refusing to roll back a stale activation"
        )

    if not qdrant_client.collection_exists(activation_receipt.previous_active_collection):
        raise DerivedIndexLifecycleError(
            f"previous active physical collection "
            f"{activation_receipt.previous_active_collection!r} no longer exists; "
            "cannot roll back to a collection that is not present"
        )

    from qdrant_client import models as qmodels  # lazy: no client/network at import time

    operations = [
        qmodels.DeleteAliasOperation(
            delete_alias=qmodels.DeleteAlias(alias_name=activation_receipt.logical_alias)
        ),
        qmodels.CreateAliasOperation(
            create_alias=qmodels.CreateAlias(
                alias_name=activation_receipt.logical_alias,
                collection_name=activation_receipt.previous_active_collection,
            )
        ),
    ]
    qdrant_client.update_collection_aliases(change_aliases_operations=operations)

    return RollbackReceipt.create(
        logical_alias=activation_receipt.logical_alias,
        from_collection=activation_receipt.new_active_collection,
        to_collection=activation_receipt.previous_active_collection,
        activation_receipt_fingerprint=activation_receipt.activation_receipt_fingerprint,
        rolled_back_at=rolled_back_at,
        rollback_implementation_revision=rollback_implementation_revision,
    )
