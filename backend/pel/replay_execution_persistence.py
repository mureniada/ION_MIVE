"""Derived execution-condition provenance persistence for ION PEL --
ReplayExecutionDescriptor.

``persist_replay_execution_descriptor`` is the only write path for this
object. It turns the ephemeral ``RunRecord``/``ExecutionCondition``/
``session_policy`` information -- which currently disappears after use --
into an immutable, source-bound, write-once, read-back-verified
``ReplayExecutionDescriptor``, strictly downstream of Phase 2A raw-evidence
persistence. It writes exactly one file -- ``descriptor.json`` -- beneath
``{storage_root}/replay-execution/...``, a namespace disjoint from Phase
2A's ``{storage_root}/{run_id}/...`` and Phase 2B.2's
``{storage_root}/normalized/...`` files, which this module reads only (via
``read_raw_evidence``) and never modifies. No app dependency, no t4
dependency, no network. This is a separate, explicit persistence call --
``build_raw_frozen_run_record`` and ``persist_raw_evidence`` are not
modified and are never invoked implicitly from here.
"""

from __future__ import annotations

import os
from pathlib import Path

from .integrity import sha256_bytes
from .models import ExecutionCondition, RunRecord
from .normalized_identity import serialize_deterministic_json
from .readback import read_raw_evidence
from .replay_execution_descriptor_models import (
    ReplayExecutionDescriptor,
    ReplayExecutionDescriptorPersistenceResult,
)
from .replay_execution_identity import (
    REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
    compute_replay_execution_descriptor_id,
    compute_replay_execution_descriptor_schema_id_digest,
)
from .replay_execution_readback import read_replay_execution_descriptor
from .replay_execution_storage import (
    ReplayExecutionDescriptorPersistenceError,
    replay_execution_descriptor_path,
)
from .storage import EvidencePersistenceError
from .validation import PELValidationError, validate_replay_execution_descriptor

__all__ = ["persist_replay_execution_descriptor"]

_CROSS_CHECK_FIELDS = (
    "condition_id",
    "model_family",
    "model_identifier",
    "adapter_id",
    "adapter_version",
)


def _fsync_best_effort(handle) -> None:
    try:
        os.fsync(handle.fileno())
    except OSError:
        pass


def _cleanup(*, descriptor_directory: Path | None, descriptor_path: Path | None) -> list[str]:
    """Remove only what this call created. Never touches a pre-existing path."""
    problems: list[str] = []
    if descriptor_path is not None:
        try:
            if descriptor_path.exists():
                descriptor_path.unlink()
        except OSError as exc:
            problems.append(f"could not remove descriptor.json ({descriptor_path}): {exc}")
    if descriptor_directory is not None:
        try:
            if descriptor_directory.exists():
                descriptor_directory.rmdir()
        except OSError as exc:
            problems.append(
                f"could not remove descriptor directory ({descriptor_directory}): {exc}"
            )
    return problems


def persist_replay_execution_descriptor(
    *,
    storage_root: Path,
    run_record: RunRecord,
    execution_condition: ExecutionCondition,
    session_policy: str,
    persisted_at: str,
) -> ReplayExecutionDescriptorPersistenceResult:
    # -- pre-write validation. No filesystem mutation above this point;
    # every failure here leaves the storage root unchanged. --

    if not persisted_at:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE",
            "persisted_at must be non-empty",
        )
    if not session_policy:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE",
            "session_policy must be non-empty",
        )

    # 1. RunRecord / ExecutionCondition provenance cross-check (frozen by
    # the completeness addendum + failure-code closure). Stable single
    # code regardless of which field(s) disagree.
    mismatched = [
        field_name
        for field_name in _CROSS_CHECK_FIELDS
        if getattr(run_record, field_name) != getattr(execution_condition, field_name)
    ]
    if mismatched:
        detail = "; ".join(
            f"{name}: run_record={getattr(run_record, name)!r} "
            f"execution_condition={getattr(execution_condition, name)!r}"
            for name in mismatched
        )
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_CONDITION_PROVENANCE_MISMATCH", detail
        )

    # 2. verify the source raw evidence artifact. run_id is the physical
    # source-addressing key (Phase 2B.2 Resolution 3).
    try:
        raw_artifact, _raw_bytes = read_raw_evidence(
            storage_root=storage_root, run_id=run_record.run_id
        )
    except EvidencePersistenceError as exc:
        if exc.code == "STORAGE_ROOT_VIOLATION":
            raise ReplayExecutionDescriptorPersistenceError(
                "EXECUTION_DESCRIPTOR_STORAGE_ROOT_VIOLATION", str(exc)
            ) from exc
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_SOURCE_RAW_NOT_FOUND",
            f"could not read source raw evidence for run_id {run_record.run_id!r}: {exc}",
        ) from exc

    if raw_artifact.task_sha256 != run_record.task_sha256:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_TASK_SHA256_MISMATCH",
            f"run_record.task_sha256 {run_record.task_sha256!r} does not match raw "
            f"evidence task_sha256 {raw_artifact.task_sha256!r} for run_id "
            f"{run_record.run_id!r}",
        )
    if raw_artifact.prompt_sha256 != run_record.prompt_sha256:
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_PROMPT_SHA256_MISMATCH",
            f"run_record.prompt_sha256 {run_record.prompt_sha256!r} does not match "
            f"raw evidence prompt_sha256 {raw_artifact.prompt_sha256!r} for run_id "
            f"{run_record.run_id!r}",
        )

    # 3. compute identity (must precede full construction: descriptor_id is
    # itself one of the descriptor's own fields).
    schema_id = REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID
    descriptor_id = compute_replay_execution_descriptor_id(
        run_id=run_record.run_id, replay_execution_descriptor_schema_id=schema_id
    )
    schema_id_digest = compute_replay_execution_descriptor_schema_id_digest(schema_id)

    # 4. resolve the (unwritten) storage path.
    descriptor_directory, descriptor_path = replay_execution_descriptor_path(
        storage_root=storage_root, run_id=run_record.run_id, schema_id_digest=schema_id_digest
    )

    # -- the write sequence. Everything from here that creates a path is
    # tracked so a failure can clean up exactly what this call made. --
    created_directory = False
    created_descriptor = False
    try:
        # 5. construct the descriptor. ReplayExecutionDescriptor.__post_init__
        # independently re-validates field shape (e.g. non-empty strings);
        # a TypeError/ValueError here is shape validation of the constructed
        # descriptor -- the same semantic boundary step 6 below checks via
        # JSON Schema, and the one read_replay_execution_descriptor already
        # maps identically for its own equivalent construction call.
        try:
            descriptor = ReplayExecutionDescriptor(
                descriptor_id=descriptor_id,
                run_id=run_record.run_id,
                task_sha256=run_record.task_sha256,
                prompt_sha256=run_record.prompt_sha256,
                condition_id=run_record.condition_id,
                model_family=run_record.model_family,
                model_identifier=run_record.model_identifier,
                adapter_id=run_record.adapter_id,
                adapter_version=run_record.adapter_version,
                provider_settings=execution_condition.provider_settings,
                replay_index=run_record.replay_index,
                plan_id=run_record.plan_id,
                session_policy=session_policy,
                persisted_at=persisted_at,
                status="EXECUTION_DESCRIPTOR_FROZEN",
            )
        except (TypeError, ValueError) as exc:
            raise ReplayExecutionDescriptorPersistenceError(
                "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE", str(exc)
            ) from exc

        # 6. schema validation.
        try:
            validate_replay_execution_descriptor(descriptor.to_dict())
        except PELValidationError as exc:
            raise ReplayExecutionDescriptorPersistenceError(
                "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE", str(exc)
            ) from exc

        # 7. serialize.
        descriptor_bytes = serialize_deterministic_json(descriptor.to_dict())

        # 8. create the leaf directory (exist_ok=False); shared parent
        # (the run_id level) is tolerated if it already exists from a
        # prior, different schema-version descriptor for the same run.
        try:
            descriptor_directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ReplayExecutionDescriptorPersistenceError(
                "EXECUTION_DESCRIPTOR_ALREADY_EXISTS",
                f"descriptor already exists for identity {descriptor_id!r}: "
                f"{descriptor_directory}",
            ) from exc
        except OSError as exc:
            raise ReplayExecutionDescriptorPersistenceError(
                "EXECUTION_DESCRIPTOR_WRITE_FAILURE",
                f"could not create descriptor directory {descriptor_directory}: {exc}",
            ) from exc
        created_directory = True

        # 9. exclusive-create write.
        try:
            with open(descriptor_path, "xb") as handle:
                created_descriptor = True
                handle.write(descriptor_bytes)
                handle.flush()
                _fsync_best_effort(handle)
        except OSError as exc:
            raise ReplayExecutionDescriptorPersistenceError(
                "EXECUTION_DESCRIPTOR_WRITE_FAILURE", f"could not write descriptor: {exc}"
            ) from exc

        # 10. read-back verification (reuses read_replay_execution_descriptor's
        # own schema re-validation and descriptor_id self-consistency checks).
        read_descriptor, read_descriptor_bytes = read_replay_execution_descriptor(
            storage_root=storage_root,
            run_id=run_record.run_id,
            replay_execution_descriptor_schema_id=schema_id,
        )
        if read_descriptor_bytes != descriptor_bytes:
            raise ReplayExecutionDescriptorPersistenceError(
                "EXECUTION_DESCRIPTOR_DIGEST_MISMATCH",
                "read-back descriptor bytes do not match the bytes just written",
            )

        # 11. only then return the result.
        return ReplayExecutionDescriptorPersistenceResult(
            descriptor_id=read_descriptor.descriptor_id,
            descriptor_bytes_sha256=sha256_bytes(read_descriptor_bytes),
            readback_verified=True,
            status="EXECUTION_DESCRIPTOR_PERSISTED_VERIFIED",
        )
    except Exception as exc:
        cleanup_problems = _cleanup(
            descriptor_directory=descriptor_directory if created_directory else None,
            descriptor_path=descriptor_path if created_descriptor else None,
        )
        if isinstance(exc, ReplayExecutionDescriptorPersistenceError) and cleanup_problems:
            raise ReplayExecutionDescriptorPersistenceError(
                exc.code,
                f"{exc}; additionally, cleanup after failure encountered: "
                f"{'; '.join(cleanup_problems)}",
            ) from exc
        raise
