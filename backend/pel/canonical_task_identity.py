"""ION PEL Canonical Task Identity v0.1.

Pure deterministic implementation of the frozen E-05 identity pipeline:

    TaskSpec(FROZEN)
        -> CanonicalTaskIdentityPayload v0.1
        -> ION_PEL_CANONICAL_TASK_JSON_V0_1
        -> exact canonical bytes
        -> SHA-256 lowercase hex

No filesystem I/O, no network, no app dependency, no t4 dependency.

Important:
- TaskSpec.status participates in source eligibility, not digest payload.
- prompt_id is intentionally excluded.
- historical task_sha256 values are not interpreted by this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .integrity import sha256_bytes
from .models import TaskSpec

CANONICAL_TASK_IDENTITY_CONTRACT_ID = (
    "ION_PEL_CANONICAL_TASK_IDENTITY_V0_1"
)

CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID = (
    "ION_PEL_CANONICAL_TASK_JSON_V0_1"
)

CANONICAL_TASK_IDENTITY_FIELDS = (
    "identity_contract_id",
    "task_id",
    "task_version",
    "task_class",
    "semantic_boundary",
    "bundle_sha256",
    "prompt_sha256",
    "output_contract_id",
)

__all__ = [
    "CANONICAL_TASK_IDENTITY_CONTRACT_ID",
    "CANONICAL_TASK_IDENTITY_SERIALIZATION_PROFILE_ID",
    "CANONICAL_TASK_IDENTITY_FIELDS",
    "CanonicalTaskIdentityPayloadV0_1",
    "project_canonical_task_identity",
    "serialize_canonical_task_identity_payload",
    "compute_canonical_task_sha256",
]


@dataclass(frozen=True)
class CanonicalTaskIdentityPayloadV0_1:
    identity_contract_id: str
    task_id: str
    task_version: str
    task_class: str
    semantic_boundary: str | None
    bundle_sha256: str
    prompt_sha256: str
    output_contract_id: str

    def __post_init__(self) -> None:
        if self.identity_contract_id != CANONICAL_TASK_IDENTITY_CONTRACT_ID:
            raise ValueError(
                "identity_contract_id must be "
                f"{CANONICAL_TASK_IDENTITY_CONTRACT_ID!r}, got "
                f"{self.identity_contract_id!r}"
            )

    def to_dict(self) -> dict:
        return {
            "identity_contract_id": self.identity_contract_id,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "task_class": self.task_class,
            "semantic_boundary": self.semantic_boundary,
            "bundle_sha256": self.bundle_sha256,
            "prompt_sha256": self.prompt_sha256,
            "output_contract_id": self.output_contract_id,
        }


def project_canonical_task_identity(
    task_spec: TaskSpec,
) -> CanonicalTaskIdentityPayloadV0_1:
    """Project an authoritative frozen TaskSpec into the v0.1 identity payload."""

    if not isinstance(task_spec, TaskSpec):
        raise TypeError(
            "task_spec must be TaskSpec, got "
            f"{type(task_spec).__name__}"
        )

    if task_spec.status != "FROZEN":
        raise ValueError(
            "canonical task identity requires TaskSpec.status == 'FROZEN', "
            f"got {task_spec.status!r}"
        )

    return CanonicalTaskIdentityPayloadV0_1(
        identity_contract_id=CANONICAL_TASK_IDENTITY_CONTRACT_ID,
        task_id=task_spec.task_id,
        task_version=task_spec.task_version,
        task_class=task_spec.task_class,
        semantic_boundary=task_spec.semantic_boundary,
        bundle_sha256=task_spec.bundle_sha256,
        prompt_sha256=task_spec.prompt_sha256,
        output_contract_id=task_spec.output_contract_id,
    )


def serialize_canonical_task_identity_payload(
    payload: CanonicalTaskIdentityPayloadV0_1,
) -> bytes:
    """Serialize exactly under ION_PEL_CANONICAL_TASK_JSON_V0_1."""

    if not isinstance(payload, CanonicalTaskIdentityPayloadV0_1):
        raise TypeError(
            "payload must be CanonicalTaskIdentityPayloadV0_1, got "
            f"{type(payload).__name__}"
        )

    payload_dict = payload.to_dict()

    if tuple(payload_dict.keys()) != CANONICAL_TASK_IDENTITY_FIELDS:
        raise ValueError(
            "canonical task identity payload field set/order drifted: "
            f"{tuple(payload_dict.keys())!r}"
        )

    return (
        json.dumps(
            payload_dict,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        .encode("utf-8")
        + b"\n"
    )


def compute_canonical_task_sha256(task_spec: TaskSpec) -> str:
    """Derive the frozen canonical task SHA-256 from a FROZEN TaskSpec."""

    payload = project_canonical_task_identity(task_spec)
    canonical_bytes = serialize_canonical_task_identity_payload(payload)
    return sha256_bytes(canonical_bytes)