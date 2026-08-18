"""ION PEL CanonicalTaskBinding v0.1 data contracts.

Frozen stdlib dataclasses for durable canonical-task provenance evidence.

CanonicalTaskBinding distinguishes a run produced through the E-05
canonical-bound ingress from a historical RunRecord whose task_sha256 merely
happens to equal a canonical task digest.

No filesystem I/O, no network, no app dependency, no t4 dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canonical_task_identity import (
    CANONICAL_TASK_IDENTITY_CONTRACT_ID,
    CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID,
)
from .integrity import is_sha256_hex


CANONICAL_TASK_BINDING_SCHEMA_ID = (
    "https://ion.local/schemas/pel_canonical_task_binding_v0_1.schema.json"
)

CANONICAL_TASK_BINDING_STATUSES = (
    "CANONICAL_TASK_BINDING_FROZEN",
)

CANONICAL_TASK_BINDING_PERSISTENCE_RESULT_STATUSES = (
    "CANONICAL_TASK_BINDING_PERSISTED_VERIFIED",
)


__all__ = [
    "CANONICAL_TASK_BINDING_SCHEMA_ID",
    "CANONICAL_TASK_BINDING_STATUSES",
    "CANONICAL_TASK_BINDING_PERSISTENCE_RESULT_STATUSES",
    "CanonicalTaskBindingV0_1",
    "CanonicalTaskBindingPersistenceResult",
]


def _require_non_empty(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"{field_name} must be a non-empty string, got {value!r}"
        )


def _require_sha256(value: str, *, field_name: str) -> None:
    if not is_sha256_hex(value):
        raise ValueError(
            f"{field_name} must be a lowercase 64-character hex SHA-256 "
            f"digest, got {value!r}"
        )


@dataclass(frozen=True)
class CanonicalTaskBindingV0_1:
    binding_id: str
    run_id: str
    task_id: str
    canonical_task_sha256: str
    prompt_sha256: str
    identity_contract_id: str
    serialization_profile_id: str
    status: str

    def __post_init__(self) -> None:
        _require_sha256(self.binding_id, field_name="binding_id")
        _require_non_empty(self.run_id, field_name="run_id")
        _require_non_empty(self.task_id, field_name="task_id")
        _require_sha256(
            self.canonical_task_sha256,
            field_name="canonical_task_sha256",
        )
        _require_sha256(
            self.prompt_sha256,
            field_name="prompt_sha256",
        )

        if self.identity_contract_id != CANONICAL_TASK_IDENTITY_CONTRACT_ID:
            raise ValueError(
                "identity_contract_id must be "
                f"{CANONICAL_TASK_IDENTITY_CONTRACT_ID!r}, got "
                f"{self.identity_contract_id!r}"
            )

        if (
            self.serialization_profile_id
            != CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID
        ):
            raise ValueError(
                "serialization_profile_id must be "
                f"{CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID!r}, got "
                f"{self.serialization_profile_id!r}"
            )

        if self.status not in CANONICAL_TASK_BINDING_STATUSES:
            raise ValueError(
                f"status must be one of {CANONICAL_TASK_BINDING_STATUSES}, "
                f"got {self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "binding_id": self.binding_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "canonical_task_sha256": self.canonical_task_sha256,
            "prompt_sha256": self.prompt_sha256,
            "identity_contract_id": self.identity_contract_id,
            "serialization_profile_id": self.serialization_profile_id,
            "status": self.status,
        }


@dataclass(frozen=True)
class CanonicalTaskBindingPersistenceResult:
    binding_id: str
    binding_bytes_sha256: str
    readback_verified: bool
    status: str

    def __post_init__(self) -> None:
        _require_sha256(self.binding_id, field_name="binding_id")
        _require_sha256(
            self.binding_bytes_sha256,
            field_name="binding_bytes_sha256",
        )

        if not isinstance(self.readback_verified, bool):
            raise ValueError(
                "readback_verified must be a bool, got "
                f"{type(self.readback_verified).__name__}"
            )

        if self.readback_verified is not True:
            raise ValueError(
                "readback_verified must be True for a canonical task "
                "binding persistence result"
            )

        if (
            self.status
            not in CANONICAL_TASK_BINDING_PERSISTENCE_RESULT_STATUSES
        ):
            raise ValueError(
                "status must be one of "
                f"{CANONICAL_TASK_BINDING_PERSISTENCE_RESULT_STATUSES}, "
                f"got {self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "binding_id": self.binding_id,
            "binding_bytes_sha256": self.binding_bytes_sha256,
            "readback_verified": self.readback_verified,
            "status": self.status,
        }