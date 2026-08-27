"""Bounded runtime bridge from retrieved Evidence to EvidenceAdmissionRequest.

This module is deterministic and fail-closed. It does not retrieve, call model
providers, mutate evidence/context packs, execute admission transitions, or promote.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from ..context_pack_adapter import (
    AdapterMetadata,
    ContextPackAdapter,
    ContextPackEnvelope,
    EvidenceAdmissionRequest,
    EvidenceReference,
    ProvenanceRecord,
)
from ..evidence_provenance import CanonicalizationResult, resolve_evidence_provenance
from ..evidence_provenance.profiles import (
    LOCAL_LEXICAL_BACKEND,
    LOCAL_LEXICAL_PROFILE,
    MEMORY_BACKEND,
    MEMORY_PROFILE,
    QDRANT_BACKEND,
    QDRANT_PROFILE,
)

BRIDGE_ID = "ION_RUNTIME_EVIDENCE_BRIDGE_V0_1"
CONTEXT_PACK_VERSION = "0.1"
ADAPTER_SCHEMA_VERSION = "0.1"
ADAPTER_VERSION = "0.1"
GOVERNED_PACKAGE_KEY = "ion_canonical_provenance"
REQUESTED_OPERATION = "VALIDATE_FOR_ADMISSION"
AUTHORITY_SCOPE = "REQUEST_CONSTRUCTION_ONLY"
SUPPORTED_FINGERPRINT_ALGORITHMS = frozenset({"SHA256"})

_PROFILE_BY_BACKEND = {
    LOCAL_LEXICAL_BACKEND: LOCAL_LEXICAL_PROFILE,
    MEMORY_BACKEND: MEMORY_PROFILE,
    QDRANT_BACKEND: QDRANT_PROFILE,
}


class BridgeStatus(str, Enum):
    VALID = "VALID"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ProvenanceResolution:
    runtime_evidence_id: str
    result: CanonicalizationResult


@dataclass(frozen=True)
class RuntimeEvidenceBridgeResult:
    status: BridgeStatus
    envelope: ContextPackEnvelope | None = None
    request: EvidenceAdmissionRequest | None = None
    reasons: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status is BridgeStatus.VALID


def _value(obj: Any, field: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _governed_profile_data(evidence: Any, backend_id: str) -> dict[str, Any]:
    metadata = _value(evidence, "metadata", {})
    package = metadata.get(GOVERNED_PACKAGE_KEY) if isinstance(metadata, dict) else None

    if not isinstance(package, dict):
        data: dict[str, Any] = {
            "fingerprint_semantics_established": False,
            "provenance_authoritative": False,
            "allowed_fingerprint_algorithms": (),
        }
        if backend_id == QDRANT_BACKEND:
            data["fingerprint_source_field"] = "metadata.checksum"
        return data

    fingerprint = package.get("fingerprint")
    algorithm = package.get("fingerprint_algorithm")
    provenance = package.get("provenance")
    semantic_authority = package.get("fingerprint_semantics_established") is True
    provenance_authority = package.get("provenance_authoritative") is True

    allowed = (str(algorithm),) if algorithm in SUPPORTED_FINGERPRINT_ALGORITHMS else ()

    return {
        "fingerprint": fingerprint,
        "fingerprint_algorithm": algorithm,
        "fingerprint_source_field": "governed_profile_data.fingerprint",
        "fingerprint_semantics_established": semantic_authority,
        "allowed_fingerprint_algorithms": allowed,
        "provenance": dict(provenance) if isinstance(provenance, dict) else provenance,
        "provenance_source_field": "governed_profile_data.provenance",
        "provenance_authoritative": provenance_authority,
    }


class RuntimeEvidenceBridge:
    def __init__(self, *, backend_id: str, mapping_profile_id: str) -> None:
        expected = _PROFILE_BY_BACKEND.get(backend_id)
        if expected is None or expected != mapping_profile_id:
            raise ValueError("Unsupported or mismatched runtime backend/profile binding")
        self._backend_id = backend_id
        self._mapping_profile_id = mapping_profile_id
        self._adapter = ContextPackAdapter()

    @property
    def backend_id(self) -> str:
        return self._backend_id

    @property
    def mapping_profile_id(self) -> str:
        return self._mapping_profile_id

    def resolve(self, evidence: Iterable[Any]) -> tuple[ProvenanceResolution, ...]:
        resolutions: list[ProvenanceResolution] = []
        for item in evidence:
            runtime_id_raw = _value(item, "document_id")
            runtime_id = "" if runtime_id_raw is None else str(runtime_id_raw)
            governed = _governed_profile_data(item, self._backend_id)
            result = resolve_evidence_provenance(
                self._backend_id,
                item,
                self._mapping_profile_id,
                governed,
            )
            resolutions.append(
                ProvenanceResolution(
                    runtime_evidence_id=runtime_id,
                    result=result,
                )
            )
        return tuple(resolutions)

    def build_request(
        self,
        pack: Any,
        resolutions: Iterable[ProvenanceResolution],
        *,
        question_id: str,
        adapter_created_at: str,
    ) -> RuntimeEvidenceBridgeResult:
        if not question_id:
            return self._reject("QUESTION_ID_MISSING")
        if not adapter_created_at:
            return self._reject("ADAPTER_CREATED_AT_MISSING")

        context_pack_id = _value(pack, "context_pack_id")
        documents = tuple(_value(pack, "documents", ()) or ())
        if not context_pack_id or not documents:
            return self._reject("CONTEXT_PACK_INVALID")

        buckets: dict[str, list[ProvenanceResolution]] = {}
        for entry in tuple(resolutions):
            buckets.setdefault(entry.runtime_evidence_id, []).append(entry)

        refs: list[EvidenceReference] = []
        for document in documents:
            document_id_raw = _value(document, "document_id")
            document_id = "" if document_id_raw is None else str(document_id_raw)
            source_raw = _value(document, "source")
            source = "" if source_raw is None else str(source_raw)

            matches = buckets.get(document_id, [])
            if not matches:
                return self._reject("CANONICAL_REJOIN_MISSING:" + document_id)
            if len(matches) != 1:
                return self._reject("CANONICAL_REJOIN_AMBIGUOUS:" + document_id)

            canonical = matches[0].result
            if not canonical.accepted or canonical.record is None:
                suffix = "|".join(canonical.reasons) if canonical.reasons else "REJECTED"
                return self._reject("CANONICAL_REJECTED:" + document_id + ":" + suffix)

            record = canonical.record
            if record.evidence_id != document_id:
                return self._reject("EVIDENCE_ID_REJOIN_CONFLICT:" + document_id)
            if record.source_identity != source:
                return self._reject("SOURCE_IDENTITY_REJOIN_CONFLICT:" + document_id)

            refs.append(
                EvidenceReference(
                    evidence_id=record.evidence_id,
                    source_identity=record.source_identity,
                    fingerprint=record.fingerprint,
                    fingerprint_algorithm=record.fingerprint_algorithm,
                    provenance=ProvenanceRecord(
                        origin=record.provenance.origin,
                        producer=record.provenance.producer,
                        created_at=record.provenance.created_at,
                        chain_id=record.provenance.chain_id,
                    ),
                )
            )

        envelope = ContextPackEnvelope(
            context_pack_id=str(context_pack_id),
            context_pack_version=CONTEXT_PACK_VERSION,
            question_id=question_id,
            evidence_references=tuple(refs),
            metadata=AdapterMetadata(
                producer=BRIDGE_ID,
                created_at=adapter_created_at,
                schema_version=ADAPTER_SCHEMA_VERSION,
                adapter_version=ADAPTER_VERSION,
            ),
        )

        try:
            request = self._adapter.map(
                envelope,
                requested_operation=REQUESTED_OPERATION,
                authority_scope=AUTHORITY_SCOPE,
            )
        except ValueError as exc:
            return self._reject("ADAPTER_REJECTED:" + str(exc))

        return RuntimeEvidenceBridgeResult(
            status=BridgeStatus.VALID,
            envelope=envelope,
            request=request,
            reasons=(),
        )

    @staticmethod
    def _reject(*reasons: str) -> RuntimeEvidenceBridgeResult:
        normalized = tuple(dict.fromkeys(str(r) for r in reasons if r))
        return RuntimeEvidenceBridgeResult(
            status=BridgeStatus.REJECTED,
            envelope=None,
            request=None,
            reasons=normalized,
        )


def build_qdrant_runtime_bridge() -> RuntimeEvidenceBridge:
    return RuntimeEvidenceBridge(
        backend_id=QDRANT_BACKEND,
        mapping_profile_id=QDRANT_PROFILE,
    )
