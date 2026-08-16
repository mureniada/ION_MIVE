"""ION PEL — Phase 1 deterministic contracts + Phase 2A raw-evidence
persistence + Phase 2B.1R3 pure deterministic normalization.

Independence boundary (all phases):

- no app dependency
- no t4 dependency
- no network
- no semantic authority

Phase 1 establishes the deterministic contracts beneath a future reliability
harness: FROZEN TASK -> EXECUTION PLAN -> RUN RECORD CONTRACT. Phase 2A adds
exact-byte raw-evidence persistence and read-back verification, rooted only
beneath an explicit caller-supplied storage root — there is no implicit or
default repository storage location. Phase 2B.1R3 adds a pure,
side-effect-free deterministic parser for exactly the frozen, clarified
`ION_PEL_SINGLE_TARGET_DEFECT_ADMISSION_V0_2_2` checker-output contract: it
performs no filesystem I/O, no clock lookup, and returns `PARSED` only when
the structural interpretation of sections and required fields is unique
under that grammar, every closed-enum token and semantic free-text value
keeps its full lexical extent, and unknown-assignment structural authority
is limited to standalone assignment lines and valid table rows rather than
any label-shaped substring — a hash-correct byte span is necessary but
never sufficient. It never answers whether the judgment is true, reliable,
or stable. Stability analysis, cross-model comparison, gold evaluation,
resource ledgering, and report emission remain future phases and are not
implemented here.
"""

from __future__ import annotations

from .evidence import persist_raw_evidence
from .evidence_models import PersistenceResult, RawEvidenceArtifact
from .integrity import is_sha256_hex, require_sha256_hex, sha256_bytes
from .models import ExecutionCondition, ExecutionPlan, RunRecord, TaskSpec
from .normalization import normalize_single_target_checker_output
from .normalization_contract import OUTPUT_CONTRACT_ID, PARSER_ID, PARSER_VERSION
from .normalization_models import FieldTrace, NormalizedJudgmentV0_2_2, ParserDiagnostic
from .normalized_identity import NORMALIZED_SCHEMA_ID
from .normalized_persistence import persist_normalized_judgment
from .normalized_persistence_models import (
    NormalizedJudgmentArtifact,
    NormalizedJudgmentPersistenceResult,
)
from .normalized_readback import read_normalized_judgment
from .normalized_storage import NormalizedPersistenceError
from .readback import read_raw_evidence
from .receipts import build_raw_frozen_run_record
from .replay_execution_descriptor_models import (
    ReplayExecutionDescriptor,
    ReplayExecutionDescriptorPersistenceResult,
)
from .replay_execution_identity import REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID
from .replay_execution_persistence import persist_replay_execution_descriptor
from .replay_execution_readback import read_replay_execution_descriptor
from .replay_execution_storage import ReplayExecutionDescriptorPersistenceError
from .storage import EvidencePersistenceError
from .task_freeze import freeze_task
from .validation import (
    validate_execution_plan,
    validate_normalized_judgment_artifact,
    validate_normalized_judgment_persistence_result,
    validate_normalized_judgment_v0_2_2,
    validate_persistence_result,
    validate_raw_evidence_artifact,
    validate_replay_execution_descriptor,
    validate_replay_execution_descriptor_persistence_result,
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
    "FieldTrace",
    "ParserDiagnostic",
    "NormalizedJudgmentV0_2_2",
    "OUTPUT_CONTRACT_ID",
    "PARSER_ID",
    "PARSER_VERSION",
    "NORMALIZED_SCHEMA_ID",
    "NormalizedJudgmentArtifact",
    "NormalizedJudgmentPersistenceResult",
    "NormalizedPersistenceError",
    "REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID",
    "ReplayExecutionDescriptor",
    "ReplayExecutionDescriptorPersistenceResult",
    "ReplayExecutionDescriptorPersistenceError",
    "sha256_bytes",
    "is_sha256_hex",
    "require_sha256_hex",
    "freeze_task",
    "build_raw_frozen_run_record",
    "persist_raw_evidence",
    "read_raw_evidence",
    "persist_normalized_judgment",
    "read_normalized_judgment",
    "persist_replay_execution_descriptor",
    "read_replay_execution_descriptor",
    "normalize_single_target_checker_output",
    "validate_task_spec",
    "validate_execution_plan",
    "validate_run_record",
    "validate_raw_evidence_artifact",
    "validate_persistence_result",
    "validate_normalized_judgment_v0_2_2",
    "validate_normalized_judgment_artifact",
    "validate_normalized_judgment_persistence_result",
    "validate_replay_execution_descriptor",
    "validate_replay_execution_descriptor_persistence_result",
]
