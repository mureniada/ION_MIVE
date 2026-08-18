"""ION PEL Replay Comparability v0.1 data contracts.

Frozen semantic boundary:
    evidence admission
    -> recorded surface compatibility
    -> replay lineage
    -> replay-set admission
    -> set completeness

This module contains deterministic data contracts only.

It does not implement stability analysis, semantic truth, model reliability,
gold evaluation, provider execution, or runtime observation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canonical_task_binding_models import (
    CanonicalTaskBindingPersistenceResult,
    CanonicalTaskBindingV0_1,
)
from .models import TaskSpec

from .models import ExecutionPlan

from .replay_execution_descriptor_models import (
    ReplayExecutionDescriptor,
    ReplayExecutionDescriptorPersistenceResult,
)

REPLAY_COMPARABILITY_CONTRACT_ID = "ION_PEL_REPLAY_COMPARABILITY_V0_1"
REPLAY_COMPARABILITY_CONTRACT_VERSION = "0.1"
RECORDED_SURFACE_SCOPE_ID = "RECORDED_DESCRIPTOR_SURFACE_V0_2"

EVIDENCE_ADMISSION_STATES = (
    "ADMITTED",
    "UNKNOWN",
)

SURFACE_RESULTS = (
    "SURFACE_COMPATIBLE",
    "SURFACE_INCOMPATIBLE",
    "UNKNOWN",
)

SURFACE_FIELD_RESULTS = (
    "SAME",
    "DIFFERENT",
    "UNVERIFIED",
)

LINEAGE_RESULTS = (
    "LINEAGE_COMPATIBLE",
    "LINEAGE_CONFLICT",
    "CROSS_PLAN",
    "CROSS_CONDITION",
    "UNKNOWN",
)

REPLAY_SET_RESULTS = (
    "REPLAY_SET_ADMISSIBLE",
    "REPLAY_SET_NOT_ADMISSIBLE",
    "UNKNOWN",
)

SET_COMPLETENESS_RESULTS = (
    "SET_COMPLETE",
    "SET_INCOMPLETE",
    "SET_CONFLICTED",
    "UNKNOWN",
)

SURFACE_FIELDS = (
    "task_sha256",
    "prompt_sha256",
    "model_family",
    "model_identifier",
    "adapter_id",
    "adapter_version",
    "provider_settings",
    "session_policy",
)

ADMISSION_REASON_CODES = (
    "DESCRIPTOR_INVALID",
    "DESCRIPTOR_STATUS_INVALID",
    "DESCRIPTOR_EVIDENCE_UNVERIFIED",
    "DESCRIPTOR_VERIFICATION_IDENTITY_MISMATCH",
    "INSUFFICIENT_EVIDENCE",
)

SURFACE_REASON_CODES = (
    "TASK_HASH_MISMATCH",
    "PROMPT_HASH_MISMATCH",
    "MODEL_FAMILY_MISMATCH",
    "MODEL_IDENTIFIER_MISMATCH",
    "ADAPTER_ID_MISMATCH",
    "ADAPTER_VERSION_MISMATCH",
    "PROVIDER_SETTINGS_MISMATCH",
    "SESSION_POLICY_MISMATCH",
)

LINEAGE_REASON_CODES = (
    "CROSS_PLAN",
    "CROSS_CONDITION",
    "REPLAY_SLOT_DUPLICATE_OR_CONFLICT",
    "PLAN_CONTEXT_UNAVAILABLE",
    "CONDITION_CONTEXT_UNAVAILABLE",
    "EXPECTED_REPLAY_SET_IDENTITY_UNAVAILABLE",
)

COMPLETENESS_REASON_CODES = (
    "EXPECTED_REPLAYS_UNAVAILABLE",
    "MISSING_REPLAY_SLOT",
    "REPLAY_SLOT_CONFLICT",
    "CANONICAL_TASK_BINDING_UNAVAILABLE",
    "CANONICAL_TASK_BINDING_UNVERIFIED",
    "CANONICAL_TASK_BINDING_VERIFICATION_IDENTITY_MISMATCH",
    "TASK_SPEC_NOT_FROZEN",
    "EXECUTION_PLAN_TASK_ID_MISMATCH",
    "CANONICAL_TASK_BINDING_RUN_MISMATCH",
    "CANONICAL_TASK_BINDING_TASK_ID_MISMATCH",
    "CANONICAL_TASK_DIGEST_MISMATCH",
    "CANONICAL_TASK_PROMPT_MISMATCH",
)

ALL_REASON_CODES = (
    ADMISSION_REASON_CODES
    + SURFACE_REASON_CODES
    + LINEAGE_REASON_CODES
    + COMPLETENESS_REASON_CODES
)

LINEAGE_FINDING_CODES = (
    "CONDITION_ID_SAME",
    "CONDITION_ID_DIFFERENT",
    "PLAN_ID_SAME",
    "PLAN_ID_DIFFERENT",
    "REPLAY_INDEX_SAME",
    "REPLAY_INDEX_DIFFERENT",
    "REPLAY_SLOT_DUPLICATE_OR_CONFLICT",
)

CONTEXT_FLAGS = (
    "FULL_CONTEXT_NOT_ESTABLISHED",
    "ACTUAL_RUNTIME_CONDITION_NOT_ESTABLISHED",
    "TEMPORAL_COMPARABILITY_NOT_ESTABLISHED",
    "CAPTURE_MODE_RELEVANCE_NOT_ESTABLISHED",
    "FULL_PLAN_EQUIVALENCE_NOT_ESTABLISHED",
    "CROSS_PLAN_ADMISSION_NOT_ESTABLISHED",
)

__all__ = [
    "REPLAY_COMPARABILITY_CONTRACT_ID",
    "REPLAY_COMPARABILITY_CONTRACT_VERSION",
    "RECORDED_SURFACE_SCOPE_ID",
    "EVIDENCE_ADMISSION_STATES",
    "SURFACE_RESULTS",
    "SURFACE_FIELD_RESULTS",
    "LINEAGE_RESULTS",
    "REPLAY_SET_RESULTS",
    "SET_COMPLETENESS_RESULTS",
    "SURFACE_FIELDS",
    "ADMISSION_REASON_CODES",
    "SURFACE_REASON_CODES",
    "LINEAGE_REASON_CODES",
    "COMPLETENESS_REASON_CODES",
    "ALL_REASON_CODES",
    "LINEAGE_FINDING_CODES",
    "CONTEXT_FLAGS",
    "EvidenceAdmission",
    "SurfaceFieldFinding",
    "ReplaySetContext",
    "ReplayComparabilityAssessmentV0_1",
]


def _require_non_empty(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"{field_name} must be a non-empty string, got {value!r}"
        )


def _require_enum(value: str, allowed: tuple[str, ...], *, field_name: str) -> None:
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {allowed}, got {value!r}"
        )


def _require_bool(value: bool, *, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be a bool, got {type(value).__name__}"
        )


def _require_unique_known_codes(
    values: tuple[str, ...],
    allowed: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} contains duplicate values: {values!r}")
    unknown = tuple(value for value in values if value not in allowed)
    if unknown:
        raise ValueError(
            f"{field_name} contains unknown values {unknown!r}; "
            f"allowed values are {allowed!r}"
        )


@dataclass(frozen=True)
class EvidenceAdmission:
    descriptor_id: str | None
    run_id: str | None
    admission: str
    verification_basis: str | None

    def __post_init__(self) -> None:
        _require_enum(
            self.admission,
            EVIDENCE_ADMISSION_STATES,
            field_name="admission",
        )

        if self.descriptor_id is not None:
            _require_non_empty(self.descriptor_id, field_name="descriptor_id")

        if self.run_id is not None:
            _require_non_empty(self.run_id, field_name="run_id")

        if self.verification_basis is not None:
            _require_non_empty(
                self.verification_basis,
                field_name="verification_basis",
            )

        if self.admission == "ADMITTED":
            if self.descriptor_id is None:
                raise ValueError(
                    "descriptor_id is required when admission is ADMITTED"
                )
            if self.run_id is None:
                raise ValueError(
                    "run_id is required when admission is ADMITTED"
                )
            if self.verification_basis is None:
                raise ValueError(
                    "verification_basis is required when admission is ADMITTED"
                )

    def to_dict(self) -> dict:
        return {
            "descriptor_id": self.descriptor_id,
            "run_id": self.run_id,
            "admission": self.admission,
            "verification_basis": self.verification_basis,
        }


@dataclass(frozen=True)
class SurfaceFieldFinding:
    field: str
    result: str
    reason_code: str | None = None

    def __post_init__(self) -> None:
        _require_enum(
            self.field,
            SURFACE_FIELDS,
            field_name="field",
        )
        _require_enum(
            self.result,
            SURFACE_FIELD_RESULTS,
            field_name="result",
        )

        if self.reason_code is not None:
            _require_enum(
                self.reason_code,
                SURFACE_REASON_CODES,
                field_name="reason_code",
            )

        if self.result == "DIFFERENT" and self.reason_code is None:
            raise ValueError(
                "reason_code is required when result is DIFFERENT"
            )

        if self.result == "SAME" and self.reason_code is not None:
            raise ValueError(
                "reason_code must be None when result is SAME"
            )

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "result": self.result,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class ReplaySetContext:
    execution_plan: ExecutionPlan | None
    received_evidence: tuple[
        tuple[
            ReplayExecutionDescriptor | None,
            ReplayExecutionDescriptorPersistenceResult | None,
        ],
        ...,
    ]

    task_spec: TaskSpec | None = None
    received_task_binding_evidence: tuple[
        tuple[
            CanonicalTaskBindingV0_1 | None,
            CanonicalTaskBindingPersistenceResult | None,
        ],
        ...,
    ] = ()

    def __post_init__(self) -> None:
        if (
            self.execution_plan is not None
            and not isinstance(self.execution_plan, ExecutionPlan)
        ):
            raise ValueError(
                "execution_plan must be ExecutionPlan or None, got "
                f"{type(self.execution_plan).__name__}"
            )

        if not isinstance(self.received_evidence, tuple):
            raise ValueError(
                "received_evidence must be a tuple of "
                "(descriptor, persistence_result) pairs"
            )

        for index, item in enumerate(self.received_evidence):
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError(
                    "received_evidence items must be 2-tuples, "
                    f"invalid item at index {index}: {item!r}"
                )

            descriptor, persistence = item

            if (
                descriptor is not None
                and not isinstance(descriptor, ReplayExecutionDescriptor)
            ):
                raise ValueError(
                    "received_evidence descriptor must be "
                    "ReplayExecutionDescriptor or None, got "
                    f"{type(descriptor).__name__} at index {index}"
                )

            if (
                persistence is not None
                and not isinstance(
                    persistence,
                    ReplayExecutionDescriptorPersistenceResult,
                )
            ):
                raise ValueError(
                    "received_evidence persistence result must be "
                    "ReplayExecutionDescriptorPersistenceResult or None, got "
                    f"{type(persistence).__name__} at index {index}"
                )

        if self.task_spec is not None and not isinstance(self.task_spec, TaskSpec):
            raise ValueError(
                "task_spec must be TaskSpec or None, got "
                f"{type(self.task_spec).__name__}"
            )

        if not isinstance(self.received_task_binding_evidence, tuple):
            raise ValueError(
                "received_task_binding_evidence must be a tuple"
            )

        for index, item in enumerate(self.received_task_binding_evidence):
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError(
                    "received_task_binding_evidence items must be 2-tuples, "
                    f"invalid item at index {index}: {item!r}"
                )

            binding, persistence = item

            if binding is not None and not isinstance(binding, CanonicalTaskBindingV0_1):
                raise ValueError(
                    "binding must be CanonicalTaskBindingV0_1 or None"
                )

            if persistence is not None and not isinstance(
                persistence, CanonicalTaskBindingPersistenceResult
            ):
                raise ValueError(
                    "binding persistence must be "
                    "CanonicalTaskBindingPersistenceResult or None"
                )

    def to_dict(self) -> dict:
        return {
            "execution_plan": (
                self.execution_plan.to_dict()
                if self.execution_plan is not None
                else None
            ),
            "received_evidence": [
                {
                    "descriptor": (
                        descriptor.to_dict()
                        if descriptor is not None
                        else None
                    ),
                    "persistence_result": (
                        persistence.to_dict()
                        if persistence is not None
                        else None
                    ),
                }
                for descriptor, persistence in self.received_evidence
            ],
            "task_spec": (
                self.task_spec.to_dict()
                if self.task_spec is not None
                else None
            ),
            "received_task_binding_evidence": [
                {
                    "binding": (
                        binding.to_dict() if binding is not None else None
                    ),
                    "persistence_result": (
                        persistence.to_dict()
                        if persistence is not None
                        else None
                    ),
                }
                for binding, persistence in self.received_task_binding_evidence
            ],
        }


@dataclass(frozen=True)
class ReplayComparabilityAssessmentV0_1:
    contract_id: str
    contract_version: str
    surface_scope_id: str

    evidence_a: EvidenceAdmission
    evidence_b: EvidenceAdmission

    surface_comparison_started: bool
    surface_field_findings: tuple[SurfaceFieldFinding, ...]
    surface_result: str

    lineage_findings: tuple[str, ...]
    lineage_result: str

    replay_set_result: str
    set_completeness_result: str

    reason_codes: tuple[str, ...]
    context_flags: tuple[str, ...]

    full_execution_context_established: bool
    actual_runtime_condition_established: bool
    cross_plan_admission_established: bool
    temporal_comparability_established: bool

    def __post_init__(self) -> None:
        if self.contract_id != REPLAY_COMPARABILITY_CONTRACT_ID:
            raise ValueError(
                "contract_id must be "
                f"{REPLAY_COMPARABILITY_CONTRACT_ID!r}, got {self.contract_id!r}"
            )

        if self.contract_version != REPLAY_COMPARABILITY_CONTRACT_VERSION:
            raise ValueError(
                "contract_version must be "
                f"{REPLAY_COMPARABILITY_CONTRACT_VERSION!r}, "
                f"got {self.contract_version!r}"
            )

        if self.surface_scope_id != RECORDED_SURFACE_SCOPE_ID:
            raise ValueError(
                "surface_scope_id must be "
                f"{RECORDED_SURFACE_SCOPE_ID!r}, got {self.surface_scope_id!r}"
            )

        _require_bool(
            self.surface_comparison_started,
            field_name="surface_comparison_started",
        )

        _require_enum(
            self.surface_result,
            SURFACE_RESULTS,
            field_name="surface_result",
        )
        _require_enum(
            self.lineage_result,
            LINEAGE_RESULTS,
            field_name="lineage_result",
        )
        _require_enum(
            self.replay_set_result,
            REPLAY_SET_RESULTS,
            field_name="replay_set_result",
        )
        _require_enum(
            self.set_completeness_result,
            SET_COMPLETENESS_RESULTS,
            field_name="set_completeness_result",
        )

        _require_unique_known_codes(
            self.lineage_findings,
            LINEAGE_FINDING_CODES,
            field_name="lineage_findings",
        )
        _require_unique_known_codes(
            self.reason_codes,
            ALL_REASON_CODES,
            field_name="reason_codes",
        )
        _require_unique_known_codes(
            self.context_flags,
            CONTEXT_FLAGS,
            field_name="context_flags",
        )

        field_names = tuple(
            finding.field for finding in self.surface_field_findings
        )
        if len(set(field_names)) != len(field_names):
            raise ValueError(
                "surface_field_findings contains duplicate fields: "
                f"{field_names!r}"
            )

        for field_name in (
            "full_execution_context_established",
            "actual_runtime_condition_established",
            "cross_plan_admission_established",
            "temporal_comparability_established",
        ):
            _require_bool(
                getattr(self, field_name),
                field_name=field_name,
            )

        # Frozen v0.1 anti-overclaim boundary.
        if self.full_execution_context_established:
            raise ValueError(
                "full_execution_context_established must be False in v0.1"
            )
        if self.actual_runtime_condition_established:
            raise ValueError(
                "actual_runtime_condition_established must be False in v0.1"
            )
        if self.cross_plan_admission_established:
            raise ValueError(
                "cross_plan_admission_established must be False in v0.1"
            )
        if self.temporal_comparability_established:
            raise ValueError(
                "temporal_comparability_established must be False in v0.1"
            )

        if not self.surface_comparison_started:
            if self.surface_result != "UNKNOWN":
                raise ValueError(
                    "surface_result must be UNKNOWN when "
                    "surface_comparison_started is False"
                )
            if self.surface_field_findings:
                raise ValueError(
                    "surface_field_findings must be empty when "
                    "surface_comparison_started is False"
                )

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "surface_scope_id": self.surface_scope_id,
            "evidence_a": self.evidence_a.to_dict(),
            "evidence_b": self.evidence_b.to_dict(),
            "surface_comparison_started": self.surface_comparison_started,
            "surface_field_findings": [
                finding.to_dict()
                for finding in self.surface_field_findings
            ],
            "surface_result": self.surface_result,
            "lineage_findings": list(self.lineage_findings),
            "lineage_result": self.lineage_result,
            "replay_set_result": self.replay_set_result,
            "set_completeness_result": self.set_completeness_result,
            "reason_codes": list(self.reason_codes),
            "context_flags": list(self.context_flags),
            "full_execution_context_established": (
                self.full_execution_context_established
            ),
            "actual_runtime_condition_established": (
                self.actual_runtime_condition_established
            ),
            "cross_plan_admission_established": (
                self.cross_plan_admission_established
            ),
            "temporal_comparability_established": (
                self.temporal_comparability_established
            ),
        }
