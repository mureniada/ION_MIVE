"""ION PEL E-05 canonical task-bound RunRecord ingress.

Creates a new RunRecord only from an authoritative FROZEN TaskSpec-derived
canonical task identity and co-produces CanonicalTaskBinding v0.1 evidence.

The legacy build_raw_frozen_run_record() API remains unchanged.
No persistence, filesystem write, network access, scoring, or interpretation.
"""

from __future__ import annotations

import json

from .canonical_task_binding_models import (
    CANONICAL_TASK_BINDING_SCHEMA_ID,
    CanonicalTaskBindingV0_1,
)
from .canonical_task_identity import (
    CANONICAL_TASK_IDENTITY_CONTRACT_ID,
    CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID,
    compute_canonical_task_sha256,
)
from .integrity import sha256_bytes
from .models import RunRecord, TaskSpec
from .receipts import build_raw_frozen_run_record


__all__ = [
    "compute_canonical_task_binding_id",
    "build_canonical_task_bound_run_record",
]


def compute_canonical_task_binding_id(*, run_id: str) -> str:
    """Frozen CanonicalTaskBinding v0.1 binding-slot identity."""

    if not isinstance(run_id, str) or not run_id:
        raise ValueError(
            f"run_id must be a non-empty string, got {run_id!r}"
        )

    canonical_bytes = json.dumps(
        [run_id, CANONICAL_TASK_BINDING_SCHEMA_ID],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    return sha256_bytes(canonical_bytes)


def build_canonical_task_bound_run_record(
    *,
    task_spec: TaskSpec,
    run_id: str,
    plan_id: str,
    condition_id: str,
    replay_index: int,
    model_family: str,
    model_identifier: str,
    adapter_id: str,
    adapter_version: str,
    started_at: str | None,
    completed_at: str | None,
    raw_artifact_id: str,
    raw_bytes: bytes,
    capture_mode: str,
) -> tuple[RunRecord, CanonicalTaskBindingV0_1]:
    """Create one canonical-bound RunRecord and its provenance binding.

    task_sha256 and prompt_sha256 are deliberately absent from the caller
    surface. They are derived from the supplied authoritative TaskSpec.
    """

    canonical_task_sha256 = compute_canonical_task_sha256(task_spec)

    record = build_raw_frozen_run_record(
        run_id=run_id,
        plan_id=plan_id,
        condition_id=condition_id,
        replay_index=replay_index,
        model_family=model_family,
        model_identifier=model_identifier,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        task_sha256=canonical_task_sha256,
        prompt_sha256=task_spec.prompt_sha256,
        started_at=started_at,
        completed_at=completed_at,
        raw_artifact_id=raw_artifact_id,
        raw_bytes=raw_bytes,
        capture_mode=capture_mode,
    )

    binding = CanonicalTaskBindingV0_1(
        binding_id=compute_canonical_task_binding_id(run_id=record.run_id),
        run_id=record.run_id,
        task_id=task_spec.task_id,
        canonical_task_sha256=canonical_task_sha256,
        prompt_sha256=task_spec.prompt_sha256,
        identity_contract_id=CANONICAL_TASK_IDENTITY_CONTRACT_ID,
        serialization_profile_id=(
            CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID
        ),
        status="CANONICAL_TASK_BINDING_FROZEN",
    )

    return record, binding