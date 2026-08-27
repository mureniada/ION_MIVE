from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Sequence

from ..context_pack_adapter.models import EvidenceAdmissionRequest, EvidenceReference
from ..retrieval.evidence_fingerprint import PROFILE_ID, recompute_evidence_fingerprint
from . import (
    AuthorityRight,
    CheckOutcome,
    EvidenceRecord,
    EvidenceStatus,
    EvidenceValidator,
    Fingerprint,
    Provenance,
    SourceRef,
    StateTransitionEngine,
    ValidationContext,
    ValidationOutcome,
)
from .profiles import ValidatorProfile


STRUCTURAL_CLAIM_CONTRACT_ID = "ION_RUNTIME_STRUCTURAL_EVIDENCE_BINDING_V0_1"
RUNTIME_VALIDATOR_PROFILE_ID = "ION_RUNTIME_STRUCTURAL_ADMISSION_VALIDATOR_PROFILE_V0_1"
RUNTIME_VALIDATION_ACTOR = "ION_RUNTIME_ADMISSION_VALIDATOR_V0_1"
RUNTIME_VALIDATION_REASON = "RUNTIME_STRUCTURAL_ADMISSION_VALIDATION_PASS"

RUNTIME_VALIDATOR_PROFILE = ValidatorProfile(
    profile_id=RUNTIME_VALIDATOR_PROFILE_ID,
    identity_required=True,
    provenance_required=False,
    claim_binding_required=True,
    scope_required=False,
    temporal_effectivity_required=False,
    receipt_required=False,
    contradiction_check_required=False,
    authorization_boundary_required=True,
)

_UNKNOWN_TOKENS = frozenset(
    {
        "",
        "UNKNOWN",
        "UNRESOLVED",
        "NOT_AVAILABLE",
        "NOT-AVAILABLE",
        "N/A",
        "NONE",
        "NULL",
    }
)


@dataclass(frozen=True)
class RuntimeAdmissionGateResult:
    records: tuple[EvidenceRecord, ...]
    validations: tuple[Any, ...]
    transitions: tuple[Any, ...]


def _required_text(value: Any, field: str) -> str:
    if value is None:
        raise ValueError(field + " is required")
    text = str(value).strip()
    if not text or text.upper() in _UNKNOWN_TOKENS:
        raise ValueError(field + " is missing or UNKNOWN")
    return text


def _historical_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.upper() in _UNKNOWN_TOKENS:
        return None
    return text


def _required_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(field + " must be a dict")
    return value


def _claim_material(
    request: EvidenceAdmissionRequest,
    ref: EvidenceReference,
) -> dict[str, str]:
    return {
        "authority_scope": _required_text(request.authority_scope, "authority_scope"),
        "context_pack_id": _required_text(request.context_pack_id, "context_pack_id"),
        "contract_id": STRUCTURAL_CLAIM_CONTRACT_ID,
        "evidence_id": _required_text(ref.evidence_id, "evidence_id"),
        "expected_fingerprint": _required_text(ref.fingerprint, "expected_fingerprint"),
        "expected_fingerprint_algorithm": _required_text(
            ref.fingerprint_algorithm,
            "expected_fingerprint_algorithm",
        ),
        "question_id": _required_text(request.question_id, "question_id"),
        "request_id": _required_text(request.request_id, "request_id"),
        "requested_operation": _required_text(
            request.requested_operation,
            "requested_operation",
        ),
        "source_identity": _required_text(ref.source_identity, "source_identity"),
    }


def canonical_structural_claim(
    request: EvidenceAdmissionRequest,
    ref: EvidenceReference,
) -> str:
    return json.dumps(
        _claim_material(request, ref),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _claim_digest(claim: str) -> str:
    return hashlib.sha256(claim.encode("utf-8")).hexdigest()


def _validate_request_binding(
    request: EvidenceAdmissionRequest,
    pack: Any,
    question_id: str,
) -> tuple[EvidenceReference, ...]:
    if request is None:
        raise ValueError("EvidenceAdmissionRequest is required")

    _required_text(request.request_id, "request.request_id")
    _required_text(request.context_pack_id, "request.context_pack_id")
    _required_text(request.question_id, "request.question_id")
    _required_text(request.requested_operation, "request.requested_operation")
    _required_text(request.authority_scope, "request.authority_scope")

    pack_id = _required_text(getattr(pack, "context_pack_id", None), "pack.context_pack_id")
    bound_question_id = _required_text(question_id, "question_id")

    if str(request.context_pack_id) != pack_id:
        raise ValueError("context_pack_id binding mismatch")
    if str(request.question_id) != bound_question_id:
        raise ValueError("question_id binding mismatch")

    refs = tuple(request.evidence_records)
    if not refs:
        raise ValueError("request evidence_records must be non-empty")

    ref_ids = [str(ref.evidence_id) for ref in refs]
    if any(not item for item in ref_ids):
        raise ValueError("empty evidence_id in request")
    if len(ref_ids) != len(set(ref_ids)):
        raise ValueError("duplicate evidence_id in request")

    documents = tuple(getattr(pack, "documents", ()))
    pack_ids = [str(getattr(doc, "document_id", "")) for doc in documents]
    if ref_ids != pack_ids:
        raise ValueError("request evidence set does not exactly match ContextPack")

    return refs


def _adjudicate_reference(
    request: EvidenceAdmissionRequest,
    ref: EvidenceReference,
    evidence: Sequence[Any],
) -> tuple[EvidenceRecord, ValidationContext, str]:
    evidence_id = _required_text(ref.evidence_id, "evidence_id")

    matches = [item for item in evidence if str(getattr(item, "document_id", "")) == evidence_id]
    if len(matches) != 1:
        raise ValueError(
            "retrieved Evidence cardinality invalid for evidence_id="
            + evidence_id
            + " count="
            + str(len(matches))
        )

    item = matches[0]
    source_identity = _required_text(ref.source_identity, "source_identity")
    runtime_source = _required_text(getattr(item, "source_id", None), "Evidence.source_id")
    if source_identity != runtime_source:
        raise ValueError("source_identity mismatch for " + evidence_id)

    metadata = _required_dict(getattr(item, "metadata", None), "Evidence.metadata")

    expected_fingerprint = _required_text(ref.fingerprint, "fingerprint")
    stored_fingerprint = _required_text(
        metadata.get("evidence_fingerprint"),
        "Evidence.metadata.evidence_fingerprint",
    )
    if expected_fingerprint != stored_fingerprint:
        raise ValueError("stored fingerprint mismatch for " + evidence_id)

    expected_algorithm = _required_text(
        ref.fingerprint_algorithm,
        "fingerprint_algorithm",
    )
    stored_algorithm = _required_text(
        metadata.get("evidence_fingerprint_algorithm"),
        "Evidence.metadata.evidence_fingerprint_algorithm",
    )
    if expected_algorithm != stored_algorithm:
        raise ValueError("fingerprint algorithm mismatch for " + evidence_id)

    stored_profile = _required_text(
        metadata.get("evidence_fingerprint_profile_id"),
        "Evidence.metadata.evidence_fingerprint_profile_id",
    )
    if stored_profile != PROFILE_ID:
        raise ValueError("fingerprint profile mismatch for " + evidence_id)

    recomputed = recompute_evidence_fingerprint(item)
    if recomputed != expected_fingerprint:
        raise ValueError("recomputed fingerprint mismatch for " + evidence_id)

    canonical = _required_dict(
        metadata.get("ion_canonical_provenance"),
        "Evidence.metadata.ion_canonical_provenance",
    )
    source_package = _required_dict(
        metadata.get("ion_source_provenance"),
        "Evidence.metadata.ion_source_provenance",
    )

    if _required_text(canonical.get("evidence_id"), "canonical.evidence_id") != evidence_id:
        raise ValueError("canonical evidence_id mismatch for " + evidence_id)
    if (
        _required_text(canonical.get("source_identity"), "canonical.source_identity")
        != source_identity
    ):
        raise ValueError("canonical source_identity mismatch for " + evidence_id)
    if (
        _required_text(canonical.get("fingerprint"), "canonical.fingerprint")
        != expected_fingerprint
    ):
        raise ValueError("canonical fingerprint mismatch for " + evidence_id)
    if (
        _required_text(
            canonical.get("fingerprint_algorithm"),
            "canonical.fingerprint_algorithm",
        )
        != expected_algorithm
    ):
        raise ValueError("canonical fingerprint algorithm mismatch for " + evidence_id)
    if canonical.get("provenance_authoritative") is not True:
        raise ValueError("canonical provenance is not authoritative for " + evidence_id)

    canonical_provenance = _required_dict(
        canonical.get("provenance"),
        "canonical.provenance",
    )
    provenance_origin = _required_text(
        canonical_provenance.get("origin"),
        "canonical.provenance.origin",
    )

    if _required_text(source_package.get("source_id"), "source_provenance.source_id") != runtime_source:
        raise ValueError("source provenance source_id mismatch for " + evidence_id)

    source_type = _required_text(
        source_package.get("source_type"),
        "source_provenance.source_type",
    )
    collection_method = _required_text(
        source_package.get("collection_method"),
        "source_provenance.collection_method",
    )
    source_origin = _required_text(
        source_package.get("source_origin"),
        "source_provenance.source_origin",
    )

    claim = canonical_structural_claim(request, ref)
    material = json.loads(claim)

    exact_bindings = {
        "request_id": str(request.request_id),
        "question_id": str(request.question_id),
        "context_pack_id": str(request.context_pack_id),
        "requested_operation": str(request.requested_operation),
        "authority_scope": str(request.authority_scope),
        "evidence_id": evidence_id,
        "source_identity": source_identity,
        "expected_fingerprint": expected_fingerprint,
        "expected_fingerprint_algorithm": expected_algorithm,
        "contract_id": STRUCTURAL_CLAIM_CONTRACT_ID,
    }
    if material != exact_bindings:
        raise ValueError("structural claim binding mismatch for " + evidence_id)

    record = EvidenceRecord(
        evidence_id=evidence_id,
        claim=claim,
        source=SourceRef(
            type=source_type,
            identifier=source_identity,
            location=source_origin,
        ),
        provenance=Provenance(
            origin=provenance_origin,
            collection_method=collection_method,
            collector=_historical_optional(source_package.get("collector")),
            timestamp=_historical_optional(source_package.get("collected_at")),
        ),
        fingerprint=Fingerprint(
            algorithm=expected_algorithm,
            hash=expected_fingerprint,
            content_id=evidence_id,
        ),
        status=EvidenceStatus.PENDING,
    )

    context = ValidationContext(
        actual_fingerprint_hash=recomputed,
        claim_binding=CheckOutcome.PASS,
        scope=CheckOutcome.UNKNOWN,
        effectivity=CheckOutcome.UNKNOWN,
        receipt=CheckOutcome.NOT_APPLICABLE,
        contradiction=CheckOutcome.UNKNOWN,
        authorization_boundary=CheckOutcome.PASS,
    )
    return record, context, claim


def run_runtime_admission_gate(
    *,
    evidence: Sequence[Any],
    pack: Any,
    question_id: str,
    request: EvidenceAdmissionRequest,
) -> RuntimeAdmissionGateResult:
    refs = _validate_request_binding(request, pack, question_id)

    retrieved_ids = [str(getattr(item, "document_id", "")) for item in evidence]
    if len(retrieved_ids) != len(set(retrieved_ids)):
        raise ValueError("duplicate document_id in retrieved Evidence")

    records: list[EvidenceRecord] = []
    validations: list[Any] = []
    transitions: list[Any] = []

    validator = EvidenceValidator()
    transition_engine = StateTransitionEngine()

    for ref in refs:
        record, context, claim = _adjudicate_reference(request, ref, evidence)
        digest = _claim_digest(claim)
        validation_id = "VAL-RUNTIME-" + digest
        transition_id = "TR-RUNTIME-" + digest

        validation = validator.validate(
            record,
            context,
            validation_id=validation_id,
            profile=RUNTIME_VALIDATOR_PROFILE,
        )
        if validation.result != ValidationOutcome.PASS:
            raise ValueError(
                "runtime admission validation did not PASS for "
                + record.evidence_id
                + ":"
                + validation.result.value
            )

        transition_outcome = transition_engine.transition(
            record,
            EvidenceStatus.VERIFIED,
            actor=RUNTIME_VALIDATION_ACTOR,
            authority=AuthorityRight.VALIDATION_RIGHT,
            reason=RUNTIME_VALIDATION_REASON,
            validation=validation,
            transition_id=transition_id,
        )
        if transition_outcome.record.status != EvidenceStatus.VERIFIED:
            raise ValueError(
                "runtime admission transition did not reach VERIFIED for "
                + record.evidence_id
            )

        records.append(transition_outcome.record)
        validations.append(validation)
        transitions.append(transition_outcome.transition)

    if len(records) != len(refs):
        raise ValueError("all-or-nothing admission gate cardinality failure")

    return RuntimeAdmissionGateResult(
        records=tuple(records),
        validations=tuple(validations),
        transitions=tuple(transitions),
    )