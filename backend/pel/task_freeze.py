"""Frozen-task construction for ION PEL Phase 1.

`freeze_task` computes exact-byte SHA-256 identity for a task's bundle and
prompt bytes. It writes nothing, normalizes no line endings, and never
decodes and re-encodes the supplied bytes: the exact supplied bytes are the
identity basis.
"""

from __future__ import annotations

from .integrity import sha256_bytes
from .models import TaskSpec

__all__ = ["freeze_task"]


def freeze_task(
    *,
    task_id: str,
    task_version: str,
    task_class: str,
    semantic_boundary: str | None,
    bundle_filename: str,
    bundle_bytes: bytes,
    prompt_id: str,
    prompt_bytes: bytes,
    output_contract_id: str,
    created_at: str,
    provenance: tuple[str, ...] = (),
) -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        task_version=task_version,
        task_class=task_class,
        semantic_boundary=semantic_boundary,
        bundle_filename=bundle_filename,
        bundle_sha256=sha256_bytes(bundle_bytes),
        bundle_bytes=len(bundle_bytes),
        prompt_id=prompt_id,
        prompt_sha256=sha256_bytes(prompt_bytes),
        prompt_bytes=len(prompt_bytes),
        output_contract_id=output_contract_id,
        created_at=created_at,
        status="FROZEN",
        provenance=tuple(provenance),
    )
