"""Read-back verification for ION PEL ReplayExecutionDescriptor
persistence.

Reads a previously persisted ``ReplayExecutionDescriptor`` back from a
caller-supplied storage root, verifying: the descriptor's own
``(run_id, replay_execution_descriptor_schema_id)`` components reproduce
its own stored ``descriptor_id`` (self-consistency); and exact-byte
identity of the persisted ``descriptor.json``. Performs no writes and
alters no file.
"""

from __future__ import annotations

import json
from pathlib import Path

from .replay_execution_descriptor_models import ReplayExecutionDescriptor
from .replay_execution_identity import (
    compute_replay_execution_descriptor_id,
    compute_replay_execution_descriptor_schema_id_digest,
)
from .replay_execution_storage import (
    ReplayExecutionDescriptorPersistenceError,
    replay_execution_descriptor_path,
)
from .validation import PELValidationError, validate_replay_execution_descriptor

__all__ = ["read_replay_execution_descriptor"]


def read_replay_execution_descriptor(
    *, storage_root: Path, run_id: str, replay_execution_descriptor_schema_id: str
) -> tuple[ReplayExecutionDescriptor, bytes]:
    schema_id_digest = compute_replay_execution_descriptor_schema_id_digest(
        replay_execution_descriptor_schema_id
    )
    _descriptor_directory, descriptor_path = replay_execution_descriptor_path(
        storage_root=storage_root, run_id=run_id, schema_id_digest=schema_id_digest
    )

    if not descriptor_path.is_file():
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_READBACK_FAILURE",
            f"missing descriptor file: {descriptor_path}",
        )

    try:
        descriptor_bytes = descriptor_path.read_bytes()
    except OSError as exc:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_READBACK_FAILURE", f"could not read descriptor: {exc}"
        ) from exc

    try:
        payload = json.loads(descriptor_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_READBACK_FAILURE",
            f"descriptor is not valid UTF-8 JSON: {exc}",
        ) from exc

    try:
        validate_replay_execution_descriptor(payload)
    except PELValidationError as exc:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE", str(exc)
        ) from exc

    try:
        constructor_fields = dict(payload)
        raw_provider_settings = constructor_fields.pop("provider_settings")
        constructor_fields["provider_settings"] = tuple(
            sorted(raw_provider_settings.items())
        )
        descriptor = ReplayExecutionDescriptor(**constructor_fields)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE",
            f"descriptor does not construct a valid object: {exc}",
        ) from exc

    if descriptor.run_id != run_id:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_IDENTITY_MISMATCH",
            f"descriptor run_id {descriptor.run_id!r} does not match requested {run_id!r}",
        )

    recomputed_id = compute_replay_execution_descriptor_id(
        run_id=descriptor.run_id,
        replay_execution_descriptor_schema_id=replay_execution_descriptor_schema_id,
    )
    if recomputed_id != descriptor.descriptor_id:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_IDENTITY_MISMATCH",
            f"descriptor_id {descriptor.descriptor_id!r} does not match recomputation "
            f"from its own stored identity components ({recomputed_id!r})",
        )

    return descriptor, descriptor_bytes
