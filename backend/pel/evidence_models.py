"""ION PEL Phase-2A raw-evidence data contracts.

Plain stdlib dataclasses, each with an explicit ``to_dict()``. No app
dependency, no t4 dependency, no network. `RawEvidenceArtifact` is evidence
metadata — it is not a second run ontology, and it carries no field for
semantic truth, normalization, stability, comparison, or gold evaluation.
Raw evidence remains uninterpreted bytes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .integrity import is_sha256_hex

RAW_EVIDENCE_ARTIFACT_STATUSES = ("RAW_FROZEN",)
PERSISTENCE_RESULT_STATUSES = ("PERSISTED_VERIFIED",)

__all__ = [
    "PERSISTENCE_RESULT_STATUSES",
    "RAW_EVIDENCE_ARTIFACT_STATUSES",
    "PersistenceResult",
    "RawEvidenceArtifact",
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
class RawEvidenceArtifact:
    evidence_id: str
    run_id: str

    task_sha256: str
    prompt_sha256: str

    relative_path: str
    sha256: str
    byte_count: int

    capture_mode: str
    persisted_at: str
    status: str

    def __post_init__(self) -> None:
        _require_non_empty(self.evidence_id, field_name="evidence_id")
        _require_non_empty(self.run_id, field_name="run_id")
        _require_sha256(self.task_sha256, field_name="task_sha256")
        _require_sha256(self.prompt_sha256, field_name="prompt_sha256")
        _require_non_empty(self.relative_path, field_name="relative_path")
        _require_sha256(self.sha256, field_name="sha256")
        if self.byte_count < 0:
            raise ValueError(f"byte_count must be >= 0, got {self.byte_count}")
        _require_non_empty(self.capture_mode, field_name="capture_mode")
        _require_non_empty(self.persisted_at, field_name="persisted_at")
        if self.status not in RAW_EVIDENCE_ARTIFACT_STATUSES:
            raise ValueError(
                f"status must be one of {RAW_EVIDENCE_ARTIFACT_STATUSES}, got "
                f"{self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "task_sha256": self.task_sha256,
            "prompt_sha256": self.prompt_sha256,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "capture_mode": self.capture_mode,
            "persisted_at": self.persisted_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class PersistenceResult:
    evidence_id: str
    run_id: str
    raw_sha256: str
    raw_bytes: int
    receipt_sha256: str
    readback_verified: bool
    status: str

    def __post_init__(self) -> None:
        _require_sha256(self.raw_sha256, field_name="raw_sha256")
        if self.raw_bytes < 0:
            raise ValueError(f"raw_bytes must be >= 0, got {self.raw_bytes}")
        _require_sha256(self.receipt_sha256, field_name="receipt_sha256")
        if not isinstance(self.readback_verified, bool):
            raise ValueError(
                f"readback_verified must be a bool, got "
                f"{type(self.readback_verified).__name__}"
            )
        if self.status not in PERSISTENCE_RESULT_STATUSES:
            raise ValueError(
                f"status must be one of {PERSISTENCE_RESULT_STATUSES}, got "
                f"{self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "raw_sha256": self.raw_sha256,
            "raw_bytes": self.raw_bytes,
            "receipt_sha256": self.receipt_sha256,
            "readback_verified": self.readback_verified,
            "status": self.status,
        }
