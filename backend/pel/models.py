"""ION PEL Phase-1 deterministic domain contracts.

Plain stdlib dataclasses, each with an explicit ``to_dict()``. No app
dependency, no t4 dependency, no network, no runtime persistence.

A `RunRecord` records execution evidence only. It carries no field
representing semantic truth, ground truth, validation, canonicality,
authorization, action-rightness, or a winning/majority model, and it
determines no such outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from .integrity import is_sha256_hex

TASK_SPEC_STATUSES = ("DRAFT", "FROZEN", "SUPERSEDED")
EXECUTION_PLAN_STATUSES = ("DRAFT", "FROZEN", "CLOSED")
GOLD_ACCESS_POLICIES = ("HIDDEN_UNTIL_FREEZE", "NO_GOLD")
RUN_RECORD_STATUSES = ("PLANNED", "RECEIVED", "RAW_FROZEN", "NORMALIZED", "FAILED")

__all__ = [
    "EXECUTION_PLAN_STATUSES",
    "GOLD_ACCESS_POLICIES",
    "RUN_RECORD_STATUSES",
    "TASK_SPEC_STATUSES",
    "ExecutionCondition",
    "ExecutionPlan",
    "RunRecord",
    "TaskSpec",
]


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    task_version: str
    task_class: str
    semantic_boundary: str | None

    bundle_filename: str
    bundle_sha256: str
    bundle_bytes: int

    prompt_id: str
    prompt_sha256: str
    prompt_bytes: int

    output_contract_id: str
    created_at: str
    status: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in TASK_SPEC_STATUSES:
            raise ValueError(
                f"status must be one of {TASK_SPEC_STATUSES}, got {self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_version": self.task_version,
            "task_class": self.task_class,
            "semantic_boundary": self.semantic_boundary,
            "bundle_filename": self.bundle_filename,
            "bundle_sha256": self.bundle_sha256,
            "bundle_bytes": self.bundle_bytes,
            "prompt_id": self.prompt_id,
            "prompt_sha256": self.prompt_sha256,
            "prompt_bytes": self.prompt_bytes,
            "output_contract_id": self.output_contract_id,
            "created_at": self.created_at,
            "status": self.status,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class ExecutionCondition:
    condition_id: str
    model_family: str
    model_identifier: str
    adapter_id: str
    adapter_version: str
    expected_replays: int
    provider_settings: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.expected_replays < 1:
            raise ValueError(
                f"expected_replays must be >= 1, got {self.expected_replays}"
            )
        keys = [key for key, _value in self.provider_settings]
        if len(set(keys)) != len(keys):
            raise ValueError(f"provider_settings has duplicate keys: {keys}")

    def to_dict(self) -> dict:
        return {
            "condition_id": self.condition_id,
            "model_family": self.model_family,
            "model_identifier": self.model_identifier,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "expected_replays": self.expected_replays,
            "provider_settings": {k: v for k, v in self.provider_settings},
        }


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    task_id: str
    conditions: tuple[ExecutionCondition, ...]
    session_policy: str
    execution_order: tuple[str, ...] | None
    stop_rule: str
    gold_access_policy: str
    status: str

    def __post_init__(self) -> None:
        if len(self.conditions) < 1:
            raise ValueError("conditions must contain at least one condition")
        condition_ids = [c.condition_id for c in self.conditions]
        if len(set(condition_ids)) != len(condition_ids):
            raise ValueError(f"condition_id values must be unique: {condition_ids}")
        if self.execution_order is not None:
            known = set(condition_ids)
            unknown = [cid for cid in self.execution_order if cid not in known]
            if unknown:
                raise ValueError(
                    f"execution_order references unknown condition_id values: {unknown}"
                )
        if self.gold_access_policy not in GOLD_ACCESS_POLICIES:
            raise ValueError(
                f"gold_access_policy must be one of {GOLD_ACCESS_POLICIES}, "
                f"got {self.gold_access_policy!r}"
            )
        if self.status not in EXECUTION_PLAN_STATUSES:
            raise ValueError(
                f"status must be one of {EXECUTION_PLAN_STATUSES}, got {self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "conditions": [c.to_dict() for c in self.conditions],
            "session_policy": self.session_policy,
            "execution_order": (
                list(self.execution_order) if self.execution_order is not None else None
            ),
            "stop_rule": self.stop_rule,
            "gold_access_policy": self.gold_access_policy,
            "status": self.status,
        }


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    plan_id: str
    condition_id: str
    replay_index: int

    model_family: str
    model_identifier: str
    adapter_id: str
    adapter_version: str

    task_sha256: str
    prompt_sha256: str

    started_at: str | None
    completed_at: str | None

    raw_artifact_id: str
    raw_sha256: str
    raw_bytes: int

    capture_mode: str
    run_status: str

    def __post_init__(self) -> None:
        if self.replay_index < 0:
            raise ValueError(f"replay_index must be >= 0, got {self.replay_index}")
        if self.raw_bytes < 0:
            raise ValueError(f"raw_bytes must be >= 0, got {self.raw_bytes}")
        for field_name, value in (
            ("task_sha256", self.task_sha256),
            ("prompt_sha256", self.prompt_sha256),
            ("raw_sha256", self.raw_sha256),
        ):
            if not is_sha256_hex(value):
                raise ValueError(
                    f"{field_name} must be a lowercase 64-character hex SHA-256 "
                    f"digest, got {value!r}"
                )
        if self.run_status not in RUN_RECORD_STATUSES:
            raise ValueError(
                f"run_status must be one of {RUN_RECORD_STATUSES}, got "
                f"{self.run_status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "condition_id": self.condition_id,
            "replay_index": self.replay_index,
            "model_family": self.model_family,
            "model_identifier": self.model_identifier,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "task_sha256": self.task_sha256,
            "prompt_sha256": self.prompt_sha256,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "raw_artifact_id": self.raw_artifact_id,
            "raw_sha256": self.raw_sha256,
            "raw_bytes": self.raw_bytes,
            "capture_mode": self.capture_mode,
            "run_status": self.run_status,
        }
