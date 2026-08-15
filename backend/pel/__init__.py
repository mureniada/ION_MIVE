"""ION PEL — Phase 1 deterministic contracts.

Phase-1 independence boundary:

- no app dependency
- no t4 dependency
- no network
- no runtime persistence
- no semantic authority

This package establishes only the deterministic contracts beneath a future
reliability harness: FROZEN TASK -> EXECUTION PLAN -> RUN RECORD CONTRACT.
Raw evidence capture, normalization, stability analysis, cross-model
comparison, gold evaluation, resource ledgering, and report emission are
future phases and are not implemented here.
"""

from __future__ import annotations

from .integrity import is_sha256_hex, require_sha256_hex, sha256_bytes
from .models import ExecutionCondition, ExecutionPlan, RunRecord, TaskSpec
from .receipts import build_raw_frozen_run_record
from .task_freeze import freeze_task
from .validation import validate_execution_plan, validate_run_record, validate_task_spec

__all__ = [
    "TaskSpec",
    "ExecutionCondition",
    "ExecutionPlan",
    "RunRecord",
    "sha256_bytes",
    "is_sha256_hex",
    "require_sha256_hex",
    "freeze_task",
    "build_raw_frozen_run_record",
    "validate_task_spec",
    "validate_execution_plan",
    "validate_run_record",
]
