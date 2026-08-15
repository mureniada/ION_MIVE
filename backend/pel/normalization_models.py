"""ION PEL Phase 2B.1R3 normalization data contracts.

Plain stdlib dataclasses, each with an explicit ``to_dict()``. No app
dependency, no t4 dependency, no network. A `NormalizedJudgmentV0_2_2` is not
truth: `PARSED != TRUE`, `YES != VALIDATED`, `HIGH CONFIDENCE != HIGH
RELIABILITY`, `UNIQUE STRUCTURAL PARSE != SEMANTIC TRUTH`. It answers only
what structured judgment can be deterministically reconstructed from exact
raw bytes under the frozen `ION_PEL_SINGLE_TARGET_DEFECT_ADMISSION_V0_2_2`
contract -- and `PARSED` is returned only when the structural interpretation
of sections and required fields is unique under that grammar AND every
closed-enum token and every semantic free-text value keeps its full lexical
extent -- not merely when every returned byte span happens to hash
correctly.
"""

from __future__ import annotations

from dataclasses import dataclass

from .integrity import is_sha256_hex
from .normalization_contract import (
    CONFIDENCE_VALUES,
    DIAGNOSTIC_CODES,
    FIELD_STATES,
    FINAL_RESULTS,
    PARSE_STATUSES,
    PARSER_ID,
    PARSER_VERSION,
    PRIMARY_VERDICTS,
    TRACE_KINDS,
)

__all__ = ["FieldTrace", "NormalizedJudgmentV0_2_2", "ParserDiagnostic"]

_OTHER_FINDINGS_STATES = ("NONE", "PRESENT")


def _require_non_empty(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")


def _require_optional_enum(value, allowed, *, field_name: str) -> None:
    if value is not None and value not in allowed:
        raise ValueError(f"{field_name} must be one of {allowed} or null, got {value!r}")


@dataclass(frozen=True)
class FieldTrace:
    field_name: str
    trace_kind: str
    start_byte: int | None
    end_byte: int | None
    source_excerpt_sha256: str | None
    rule_id: str | None
    state: str

    def __post_init__(self) -> None:
        _require_non_empty(self.field_name, field_name="field_name")
        if self.trace_kind not in TRACE_KINDS:
            raise ValueError(f"trace_kind must be one of {TRACE_KINDS}, got {self.trace_kind!r}")
        if self.state not in FIELD_STATES:
            raise ValueError(f"state must be one of {FIELD_STATES}, got {self.state!r}")
        if (self.start_byte is None) != (self.end_byte is None):
            raise ValueError("start_byte and end_byte must both be null or both non-null")
        if self.start_byte is not None:
            if self.start_byte < 0 or self.start_byte > self.end_byte:
                raise ValueError(
                    f"start_byte/end_byte must satisfy 0 <= start_byte <= end_byte, "
                    f"got start_byte={self.start_byte}, end_byte={self.end_byte}"
                )
        if self.source_excerpt_sha256 is not None and not is_sha256_hex(self.source_excerpt_sha256):
            raise ValueError(
                f"source_excerpt_sha256 must be null or a lowercase 64-character hex "
                f"SHA-256 digest, got {self.source_excerpt_sha256!r}"
            )
        has_span = self.start_byte is not None
        if self.trace_kind == "EXACT_EXTRACT":
            if not has_span or self.source_excerpt_sha256 is None:
                raise ValueError("EXACT_EXTRACT requires a source span and source_excerpt_sha256")
        elif self.trace_kind == "CONTRACT_MAP":
            if not has_span or self.source_excerpt_sha256 is None:
                raise ValueError("CONTRACT_MAP requires a source span and source_excerpt_sha256")
            if not self.rule_id:
                raise ValueError("CONTRACT_MAP requires a non-empty rule_id")
        elif self.trace_kind == "NO_SOURCE_VALUE":
            if has_span or self.source_excerpt_sha256 is not None:
                raise ValueError(
                    "NO_SOURCE_VALUE must not carry a source span or source_excerpt_sha256"
                )

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "trace_kind": self.trace_kind,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "source_excerpt_sha256": self.source_excerpt_sha256,
            "rule_id": self.rule_id,
            "state": self.state,
        }


@dataclass(frozen=True)
class ParserDiagnostic:
    code: str
    message: str
    start_byte: int | None
    end_byte: int | None

    def __post_init__(self) -> None:
        if self.code not in DIAGNOSTIC_CODES:
            raise ValueError(f"code must be one of {DIAGNOSTIC_CODES}, got {self.code!r}")
        _require_non_empty(self.message, field_name="message")
        if (self.start_byte is None) != (self.end_byte is None):
            raise ValueError("start_byte and end_byte must both be null or both non-null")
        if self.start_byte is not None and (self.start_byte < 0 or self.start_byte > self.end_byte):
            raise ValueError(
                f"start_byte/end_byte must satisfy 0 <= start_byte <= end_byte, "
                f"got start_byte={self.start_byte}, end_byte={self.end_byte}"
            )

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
        }


@dataclass(frozen=True)
class NormalizedJudgmentV0_2_2:
    run_id: str
    evidence_id: str
    source_raw_sha256: str

    output_contract_id: str
    focus_key: str
    parser_id: str
    parser_version: str

    primary_verdict: str | None
    noticed: bool | None
    declined_as_borderline: bool | None
    defect_description_text: str | None
    rule_basis_text: str | None
    confidence: str | None

    other_findings_state: str | None
    other_findings_text: str | None

    final_result: str | None

    parse_status: str
    field_traces: tuple[FieldTrace, ...]
    diagnostics: tuple[ParserDiagnostic, ...]

    normalized_at: str

    def __post_init__(self) -> None:
        for name in ("run_id", "evidence_id", "focus_key", "normalized_at", "output_contract_id"):
            _require_non_empty(getattr(self, name), field_name=name)
        if not is_sha256_hex(self.source_raw_sha256):
            raise ValueError(
                f"source_raw_sha256 must be a lowercase 64-character hex SHA-256 "
                f"digest, got {self.source_raw_sha256!r}"
            )
        # parser_id/parser_version always identify this exact parser
        # implementation, regardless of whether the requested output
        # contract was supported.
        if self.parser_id != PARSER_ID:
            raise ValueError(f"parser_id must equal the frozen constant {PARSER_ID!r}")
        if self.parser_version != PARSER_VERSION:
            raise ValueError(f"parser_version must equal the frozen constant {PARSER_VERSION!r}")
        _require_optional_enum(self.primary_verdict, PRIMARY_VERDICTS, field_name="primary_verdict")
        _require_optional_enum(self.confidence, CONFIDENCE_VALUES, field_name="confidence")
        _require_optional_enum(
            self.other_findings_state, _OTHER_FINDINGS_STATES, field_name="other_findings_state"
        )
        _require_optional_enum(self.final_result, FINAL_RESULTS, field_name="final_result")
        if self.parse_status not in PARSE_STATUSES:
            raise ValueError(f"parse_status must be one of {PARSE_STATUSES}, got {self.parse_status!r}")
        if self.noticed is not None and not isinstance(self.noticed, bool):
            raise ValueError(f"noticed must be a bool or null, got {type(self.noticed).__name__}")
        if self.declined_as_borderline is not None and not isinstance(self.declined_as_borderline, bool):
            raise ValueError(
                f"declined_as_borderline must be a bool or null, got "
                f"{type(self.declined_as_borderline).__name__}"
            )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "evidence_id": self.evidence_id,
            "source_raw_sha256": self.source_raw_sha256,
            "output_contract_id": self.output_contract_id,
            "focus_key": self.focus_key,
            "parser_id": self.parser_id,
            "parser_version": self.parser_version,
            "primary_verdict": self.primary_verdict,
            "noticed": self.noticed,
            "declined_as_borderline": self.declined_as_borderline,
            "defect_description_text": self.defect_description_text,
            "rule_basis_text": self.rule_basis_text,
            "confidence": self.confidence,
            "other_findings_state": self.other_findings_state,
            "other_findings_text": self.other_findings_text,
            "final_result": self.final_result,
            "parse_status": self.parse_status,
            "field_traces": [t.to_dict() for t in self.field_traces],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "normalized_at": self.normalized_at,
        }
