from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .models import (
    AdapterValidationResult,
    AdapterValidationState,
    ContextPackEnvelope,
    EvidenceReference,
)


SUPPORTED_SCHEMA_VERSION = "0.1"
SUPPORTED_ADAPTER_VERSION = "0.1"
SUPPORTED_FINGERPRINT_ALGORITHMS = frozenset({"SHA256"})


class ContextPackAdapterValidator:
    def validate(self, envelope: ContextPackEnvelope) -> AdapterValidationResult:
        if envelope.metadata.schema_version != SUPPORTED_SCHEMA_VERSION:
            return AdapterValidationResult(
                AdapterValidationState.UNKNOWN_VERSION,
                ("Unsupported schema_version",),
            )

        if envelope.metadata.adapter_version != SUPPORTED_ADAPTER_VERSION:
            return AdapterValidationResult(
                AdapterValidationState.UNKNOWN_VERSION,
                ("Unsupported adapter_version",),
            )

        if not envelope.context_pack_id or not envelope.context_pack_version or not envelope.question_id:
            return AdapterValidationResult(
                AdapterValidationState.INVALID_SCHEMA,
                ("Required ContextPackEnvelope identity field is empty",),
            )

        if not envelope.evidence_references:
            return AdapterValidationResult(
                AdapterValidationState.INVALID_SCHEMA,
                ("evidence_references must contain at least one item",),
            )

        if not envelope.metadata.producer or not self._is_timestamp(envelope.metadata.created_at):
            return AdapterValidationResult(
                AdapterValidationState.INVALID_SCHEMA,
                ("AdapterMetadata is incomplete or invalid",),
            )

        seen_ids = set()
        for ref in envelope.evidence_references:
            result = self._validate_reference(ref, seen_ids)
            if result is not None:
                return result
            seen_ids.add(ref.evidence_id)

        return AdapterValidationResult(AdapterValidationState.VALID)

    @staticmethod
    def _validate_reference(
        ref: EvidenceReference,
        seen_ids: set[str],
    ) -> AdapterValidationResult | None:
        if not ref.evidence_id or not ref.source_identity:
            return AdapterValidationResult(
                AdapterValidationState.INVALID_IDENTITY,
                ("Evidence identity is incomplete",),
            )

        if ref.evidence_id in seen_ids:
            return AdapterValidationResult(
                AdapterValidationState.INVALID_IDENTITY,
                ("Duplicate evidence_id is not allowed",),
            )

        if not ref.fingerprint:
            return AdapterValidationResult(
                AdapterValidationState.INVALID_FINGERPRINT,
                ("Fingerprint is empty",),
            )

        if ref.fingerprint_algorithm not in SUPPORTED_FINGERPRINT_ALGORITHMS:
            return AdapterValidationResult(
                AdapterValidationState.INVALID_FINGERPRINT,
                ("Unsupported fingerprint algorithm",),
            )

        provenance = ref.provenance
        if (
            not provenance.origin
            or not provenance.producer
            or not ContextPackAdapterValidator._is_timestamp(provenance.created_at)
        ):
            return AdapterValidationResult(
                AdapterValidationState.INVALID_PROVENANCE,
                ("Provenance is incomplete or invalid",),
            )

        return None

    @staticmethod
    def _is_timestamp(value: str) -> bool:
        if not value:
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True
