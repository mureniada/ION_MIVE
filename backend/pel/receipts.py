"""Raw-frozen run-record construction for ION PEL Phase 1.

`build_raw_frozen_run_record` computes exact-byte SHA-256 identity for
supplied raw bytes and produces a `RunRecord` with `run_status = RAW_FROZEN`.
No filesystem writes. No semantic interpretation, parsing, or scoring of the
raw output.
"""

from __future__ import annotations

from .integrity import require_sha256_hex, sha256_bytes
from .models import RunRecord

__all__ = ["build_raw_frozen_run_record"]


def build_raw_frozen_run_record(
    *,
    run_id: str,
    plan_id: str,
    condition_id: str,
    replay_index: int,
    model_family: str,
    model_identifier: str,
    adapter_id: str,
    adapter_version: str,
    task_sha256: str,
    prompt_sha256: str,
    started_at: str | None,
    completed_at: str | None,
    raw_artifact_id: str,
    raw_bytes: bytes,
    capture_mode: str,
) -> RunRecord:
    require_sha256_hex(task_sha256, field_name="task_sha256")
    require_sha256_hex(prompt_sha256, field_name="prompt_sha256")
    return RunRecord(
        run_id=run_id,
        plan_id=plan_id,
        condition_id=condition_id,
        replay_index=replay_index,
        model_family=model_family,
        model_identifier=model_identifier,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        task_sha256=task_sha256,
        prompt_sha256=prompt_sha256,
        started_at=started_at,
        completed_at=completed_at,
        raw_artifact_id=raw_artifact_id,
        raw_sha256=sha256_bytes(raw_bytes),
        raw_bytes=len(raw_bytes),
        capture_mode=capture_mode,
        run_status="RAW_FROZEN",
    )
