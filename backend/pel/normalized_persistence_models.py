"""ION PEL Phase 2B.2 derived normalized-judgment persistence data
contracts.

Plain stdlib dataclasses, each with an explicit ``to_dict()``. No app
dependency, no t4 dependency, no network. A ``NormalizedJudgmentArtifact``
is a downstream, immutable, provenance-linked persistence record for an
already-produced ``NormalizedJudgmentV0_2_2``; it does not re-interpret,
summarize, or validate that judgment's semantic content, and it carries no
field for semantic truth, gold correctness, checker reliability, model
stability, or protocol validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .integrity import is_sha256_hex

NORMALIZED_JUDGMENT_ARTIFACT_STATUSES = ("NORMALIZED_FROZEN",)
NORMALIZED_JUDGMENT_PERSISTENCE_RESULT_STATUSES = ("NORMALIZED_PERSISTED_VERIFIED",)

__all__ = [
    "NORMALIZED_JUDGMENT_ARTIFACT_STATUSES",
    "NORMALIZED_JUDGMENT_PERSISTENCE_RESULT_STATUSES",
    "NormalizedJudgmentArtifact",
    "NormalizedJudgmentPersistenceResult",
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
class NormalizedJudgmentArtifact:
    normalized_artifact_id: str
    run_id: str
    evidence_id: str
    source_raw_sha256: str

    output_contract_id: str
    parser_id: str
    parser_version: str
    normalized_schema_id: str

    relative_path: str
    normalized_content_sha256: str
    artifact_bytes_sha256: str

    persisted_at: str
    status: str

    def __post_init__(self) -> None:
        _require_sha256(self.normalized_artifact_id, field_name="normalized_artifact_id")
        for name in (
            "run_id",
            "evidence_id",
            "output_contract_id",
            "parser_id",
            "parser_version",
            "normalized_schema_id",
            "relative_path",
            "persisted_at",
        ):
            _require_non_empty(getattr(self, name), field_name=name)
        _require_sha256(self.source_raw_sha256, field_name="source_raw_sha256")
        _require_sha256(self.normalized_content_sha256, field_name="normalized_content_sha256")
        _require_sha256(self.artifact_bytes_sha256, field_name="artifact_bytes_sha256")
        if self.status not in NORMALIZED_JUDGMENT_ARTIFACT_STATUSES:
            raise ValueError(
                f"status must be one of {NORMALIZED_JUDGMENT_ARTIFACT_STATUSES}, got "
                f"{self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "normalized_artifact_id": self.normalized_artifact_id,
            "run_id": self.run_id,
            "evidence_id": self.evidence_id,
            "source_raw_sha256": self.source_raw_sha256,
            "output_contract_id": self.output_contract_id,
            "parser_id": self.parser_id,
            "parser_version": self.parser_version,
            "normalized_schema_id": self.normalized_schema_id,
            "relative_path": self.relative_path,
            "normalized_content_sha256": self.normalized_content_sha256,
            "artifact_bytes_sha256": self.artifact_bytes_sha256,
            "persisted_at": self.persisted_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class NormalizedJudgmentPersistenceResult:
    normalized_artifact_id: str
    normalized_content_sha256: str
    artifact_bytes_sha256: str
    receipt_sha256: str
    readback_verified: bool
    status: str

    def __post_init__(self) -> None:
        _require_sha256(self.normalized_artifact_id, field_name="normalized_artifact_id")
        _require_sha256(self.normalized_content_sha256, field_name="normalized_content_sha256")
        _require_sha256(self.artifact_bytes_sha256, field_name="artifact_bytes_sha256")
        _require_sha256(self.receipt_sha256, field_name="receipt_sha256")
        if not isinstance(self.readback_verified, bool):
            raise ValueError(
                f"readback_verified must be a bool, got "
                f"{type(self.readback_verified).__name__}"
            )
        if self.status not in NORMALIZED_JUDGMENT_PERSISTENCE_RESULT_STATUSES:
            raise ValueError(
                f"status must be one of {NORMALIZED_JUDGMENT_PERSISTENCE_RESULT_STATUSES}, "
                f"got {self.status!r}"
            )

    def to_dict(self) -> dict:
        return {
            "normalized_artifact_id": self.normalized_artifact_id,
            "normalized_content_sha256": self.normalized_content_sha256,
            "artifact_bytes_sha256": self.artifact_bytes_sha256,
            "receipt_sha256": self.receipt_sha256,
            "readback_verified": self.readback_verified,
            "status": self.status,
        }
