"""Write-once persistence for CanonicalTaskBinding v0.1."""

from __future__ import annotations

import os
from pathlib import Path

from .canonical_task_binding import (
    compute_canonical_task_binding_id,
)
from .canonical_task_binding_models import (
    CanonicalTaskBindingPersistenceResult,
    CanonicalTaskBindingV0_1,
)
from .canonical_task_binding_readback import (
    read_canonical_task_binding,
)
from .canonical_task_binding_storage import (
    CanonicalTaskBindingPersistenceError,
    canonical_task_binding_path,
)
from .canonical_task_identity import (
    compute_canonical_task_sha256,
)
from .integrity import sha256_bytes
from .models import RunRecord, TaskSpec
from .normalized_identity import serialize_deterministic_json
from .validation import (
    PELValidationError,
    validate_canonical_task_binding_persistence_result,
    validate_canonical_task_binding_v0_1,
    validate_run_record,
    validate_task_spec,
)


__all__ = ["persist_canonical_task_binding"]


def _fsync_best_effort(handle) -> None:
    try:
        os.fsync(handle.fileno())
    except OSError:
        pass


def _cleanup(
    *,
    binding_directory: Path | None,
    binding_path: Path | None,
) -> list[str]:
    problems: list[str] = []

    if binding_path is not None:
        try:
            if binding_path.exists():
                binding_path.unlink()
        except OSError as exc:
            problems.append(
                f"could not remove binding.json ({binding_path}): {exc}"
            )

    if binding_directory is not None:
        try:
            if binding_directory.exists():
                binding_directory.rmdir()
        except OSError as exc:
            problems.append(
                f"could not remove binding directory "
                f"({binding_directory}): {exc}"
            )

    return problems


def persist_canonical_task_binding(
    *,
    storage_root: Path,
    task_spec: TaskSpec,
    run_record: RunRecord,
    binding: CanonicalTaskBindingV0_1,
) -> CanonicalTaskBindingPersistenceResult:

    try:
        validate_task_spec(task_spec.to_dict())
        validate_run_record(run_record.to_dict())
        validate_canonical_task_binding_v0_1(binding.to_dict())
    except PELValidationError as exc:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_SCHEMA_VALIDATION_FAILURE",
            str(exc),
        ) from exc

    if task_spec.status != "FROZEN":
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_SOURCE_MISMATCH",
            f"TaskSpec.status must be 'FROZEN', got "
            f"{task_spec.status!r}",
        )

    expected_task_sha256 = compute_canonical_task_sha256(task_spec)
    expected_binding_id = compute_canonical_task_binding_id(
        run_id=run_record.run_id
    )

    source_mismatches = []

    if binding.binding_id != expected_binding_id:
        source_mismatches.append("binding_id")

    if binding.run_id != run_record.run_id:
        source_mismatches.append("run_id")

    if binding.task_id != task_spec.task_id:
        source_mismatches.append("task_id")

    if binding.canonical_task_sha256 != expected_task_sha256:
        source_mismatches.append("canonical_task_sha256")

    if run_record.task_sha256 != binding.canonical_task_sha256:
        source_mismatches.append("run_record.task_sha256")

    if binding.prompt_sha256 != task_spec.prompt_sha256:
        source_mismatches.append("binding.prompt_sha256")

    if run_record.prompt_sha256 != task_spec.prompt_sha256:
        source_mismatches.append("run_record.prompt_sha256")

    if source_mismatches:
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_SOURCE_MISMATCH",
            "source relation mismatch: "
            + ", ".join(source_mismatches),
        )

    binding_bytes = serialize_deterministic_json(
        binding.to_dict()
    )

    binding_directory, binding_path = canonical_task_binding_path(
        storage_root=storage_root,
        run_id=run_record.run_id,
        binding_id=binding.binding_id,
    )

    created_directory = False
    created_binding = False

    try:
        try:
            binding_directory.mkdir(
                parents=True,
                exist_ok=False,
            )
        except FileExistsError as exc:
            raise CanonicalTaskBindingPersistenceError(
                "CANONICAL_TASK_BINDING_ALREADY_EXISTS",
                f"binding already exists for identity "
                f"{binding.binding_id!r}: {binding_directory}",
            ) from exc
        except OSError as exc:
            raise CanonicalTaskBindingPersistenceError(
                "CANONICAL_TASK_BINDING_WRITE_FAILURE",
                f"could not create binding directory: {exc}",
            ) from exc

        created_directory = True

        try:
            with open(binding_path, "xb") as handle:
                created_binding = True
                handle.write(binding_bytes)
                handle.flush()
                _fsync_best_effort(handle)
        except OSError as exc:
            raise CanonicalTaskBindingPersistenceError(
                "CANONICAL_TASK_BINDING_WRITE_FAILURE",
                f"could not write binding: {exc}",
            ) from exc

        read_binding, read_binding_bytes = (
            read_canonical_task_binding(
                storage_root=storage_root,
                run_id=run_record.run_id,
            )
        )

        if read_binding != binding:
            raise CanonicalTaskBindingPersistenceError(
                "CANONICAL_TASK_BINDING_IDENTITY_MISMATCH",
                "readback binding differs from source binding",
            )

        if read_binding_bytes != binding_bytes:
            raise CanonicalTaskBindingPersistenceError(
                "CANONICAL_TASK_BINDING_READBACK_FAILURE",
                "readback bytes differ from exact persisted bytes",
            )

        result = CanonicalTaskBindingPersistenceResult(
            binding_id=read_binding.binding_id,
            binding_bytes_sha256=sha256_bytes(
                read_binding_bytes
            ),
            readback_verified=True,
            status=(
                "CANONICAL_TASK_BINDING_PERSISTED_VERIFIED"
            ),
        )

        try:
            validate_canonical_task_binding_persistence_result(
                result.to_dict()
            )
        except PELValidationError as exc:
            raise CanonicalTaskBindingPersistenceError(
                "CANONICAL_TASK_BINDING_SCHEMA_VALIDATION_FAILURE",
                str(exc),
            ) from exc

        return result

    except Exception as exc:
        cleanup_problems = _cleanup(
            binding_directory=(
                binding_directory
                if created_directory
                else None
            ),
            binding_path=(
                binding_path
                if created_binding
                else None
            ),
        )

        if isinstance(
            exc,
            CanonicalTaskBindingPersistenceError,
        ):
            if cleanup_problems:
                raise CanonicalTaskBindingPersistenceError(
                    exc.code,
                    f"{exc}; cleanup problems: "
                    + "; ".join(cleanup_problems),
                ) from exc
            raise

        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_WRITE_FAILURE",
            str(exc),
        ) from exc