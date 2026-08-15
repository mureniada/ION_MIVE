"""ION PEL — Phase 1 deterministic contracts + Phase 2A raw-evidence persistence.

Independence boundary (both phases):

- no app dependency
- no t4 dependency
- no network
- no semantic authority

Phase 1 establishes the deterministic contracts beneath a future reliability
harness: FROZEN TASK -> EXECUTION PLAN -> RUN RECORD CONTRACT. Phase 2A adds
exact-byte raw-evidence persistence and read-back verification, rooted only
beneath an explicit caller-supplied storage root — there is no implicit or
default repository storage location. Normalization, stability analysis,
cross-model comparison, gold evaluation, resource ledgering, and report
emission remain future phases and are not implemented here.
"""

from __future__ import annotations

from .evidence import persist_raw_evidence
from .evidence_models import PersistenceResult, RawEvidenceArtifact
from .integrity import is_sha256_hex, require_sha256_hex, sha256_bytes
from .models import ExecutionCondition, ExecutionPlan, RunRecord, TaskSpec
from .readback import read_raw_evidence
from .receipts import build_raw_frozen_run_record
from .storage import EvidencePersistenceError
from .task_freeze import freeze_task
from .validation import (
    validate_execution_plan,
    validate_persistence_result,
    validate_raw_evidence_artifact,
    validate_run_record,
    validate_task_spec,
)

__all__ = [
    "TaskSpec",
    "ExecutionCondition",
    "ExecutionPlan",
    "RunRecord",
    "RawEvidenceArtifact",
    "PersistenceResult",
    "EvidencePersistenceError",
    "sha256_bytes",
    "is_sha256_hex",
    "require_sha256_hex",
    "freeze_task",
    "build_raw_frozen_run_record",
    "persist_raw_evidence",
    "read_raw_evidence",
    "validate_task_spec",
    "validate_execution_plan",
    "validate_run_record",
    "validate_raw_evidence_artifact",
    "validate_persistence_result",
]
