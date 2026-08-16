"""ION PEL Replay Comparability Prerequisite — ReplayExecutionDescriptor
data contracts.

Plain stdlib dataclasses, each with an explicit ``to_dict()``. No app
dependency, no t4 dependency, no network. A ``ReplayExecutionDescriptor``
durably preserves execution-condition provenance that otherwise disappears
after ephemeral ``RunRecord``/``ExecutionCondition`` use. It is evidence
only -- it does not itself compare anything, and it carries no field for
verified same-condition comparability, semantic truth, or model
reliability.
"""

from __future__ import annotations

from dataclasses import dataclass

from .integrity import is_sha256_hex

REPLAY_EXECUTION_DESCRIPTOR_STATUSES = ("EXECUTION_DESCRIPTOR_FROZEN",)
REPLAY_EXECUTION_DESCRIPTOR_PERSISTENCE_RESULT_STATUSES = (
    "EXECUTION_DESCRIPTOR_PERSISTED_VERIFIED",
)

__all__ = [
    "REPLAY_EXECUTION_DESCRIPTOR_STATUSES",
    "REPLAY_EXECUTION_DESCRIPTOR_PERSISTENCE_RESULT_STATUSES",
    "ReplayExecutionDescriptor",
    "ReplayExecutionDescriptorPersistenceResult",
]


def _require_non_empty(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")


def _require_sha256(value: str, *, field_name: str) -> None:
    if not is_sha256_hex(value):
        raise ValueError(
            f"{field_name} must be a lowercase 64-character hex SHA-256 digest, "
            f"got {value!r}"
        )


@dataclass(frozen=True)
class ReplayExecutionDescriptor:
    descriptor_id: str
    run_id: str
    task_sha256: str
    prompt_sha256: str

    condition_id: str
    model_family: str
    model_identifier: str
    adapter_id: str
    adapter_version: str
    provider_settings: tuple[tuple[str, str], ...]

    replay_index: int
    plan_id: str
    session_policy: str

    persisted_at: str
    status: str

    def __post_init__(self) -> None:
        _require_sha256(self.descriptor_id, field_name="descriptor_id")
        for name in (
            "run_id",
            "condition_id",
            "model_family",
            "model_identifier",
            "adapter_id",
            "adapter_version",
            "plan_id",
            "session_policy",
            "persisted_at",
        ):
            _require_non_empty(getattr(self, name), field_name=name)
        _require_sha256(self.task_sha256, field_name="task_sha256")
        _require_sha256(self.prompt_sha256, field_name="prompt_sha256")
        if self.replay_index < 0:
            raise ValueError(f"replay_index must be >= 0, got {self.replay_index}")
        keys = [key for key, _value in self.provider_settings]
        if len(set(keys)) != len(keys):
            raise ValueError(f"provider_settings has duplicate keys: {keys}")
        if self.status not in REPLAY_EXECUTION_DESCRIPTOR_STATUSES:
            raise ValueError(
                f"status must be one of {REPLAY_EXECUTION_DESCRIPTOR_STATUSES}, got "
                f"{self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "descriptor_id": self.descriptor_id,
            "run_id": self.run_id,
            "task_sha256": self.task_sha256,
            "prompt_sha256": self.prompt_sha256,
            "condition_id": self.condition_id,
            "model_family": self.model_family,
            "model_identifier": self.model_identifier,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "provider_settings": {k: v for k, v in self.provider_settings},
            "replay_index": self.replay_index,
            "plan_id": self.plan_id,
            "session_policy": self.session_policy,
            "persisted_at": self.persisted_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class ReplayExecutionDescriptorPersistenceResult:
    descriptor_id: str
    descriptor_bytes_sha256: str
    readback_verified: bool
    status: str

    def __post_init__(self) -> None:
        _require_sha256(self.descriptor_id, field_name="descriptor_id")
        _require_sha256(self.descriptor_bytes_sha256, field_name="descriptor_bytes_sha256")
        if not isinstance(self.readback_verified, bool):
            raise ValueError(
                f"readback_verified must be a bool, got "
                f"{type(self.readback_verified).__name__}"
            )
        if self.status not in REPLAY_EXECUTION_DESCRIPTOR_PERSISTENCE_RESULT_STATUSES:
            raise ValueError(
                f"status must be one of "
                f"{REPLAY_EXECUTION_DESCRIPTOR_PERSISTENCE_RESULT_STATUSES}, got "
                f"{self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "descriptor_id": self.descriptor_id,
            "descriptor_bytes_sha256": self.descriptor_bytes_sha256,
            "readback_verified": self.readback_verified,
            "status": self.status,
        }
