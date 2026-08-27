from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from .models import ContextPackEnvelope, EvidenceAdmissionRequest
from .validator import ContextPackAdapterValidator


class ContextPackAdapter:
    def __init__(self, validator: ContextPackAdapterValidator | None = None) -> None:
        self._validator = validator or ContextPackAdapterValidator()

    def map(
        self,
        envelope: ContextPackEnvelope,
        *,
        requested_operation: str,
        authority_scope: str,
    ) -> EvidenceAdmissionRequest:
        validation = self._validator.validate(envelope)
        if not validation.is_valid:
            raise ValueError(
                "Adapter validation failed: "
                + validation.status.value
                + ":"
                + "|".join(validation.reasons)
            )

        if not requested_operation:
            raise ValueError("requested_operation is required")
        if not authority_scope:
            raise ValueError("authority_scope is required")

        request_id = self._deterministic_request_id(
            envelope,
            requested_operation=requested_operation,
            authority_scope=authority_scope,
        )

        return EvidenceAdmissionRequest(
            request_id=request_id,
            context_pack_id=envelope.context_pack_id,
            question_id=envelope.question_id,
            evidence_records=envelope.evidence_references,
            requested_operation=requested_operation,
            authority_scope=authority_scope,
        )

    @staticmethod
    def _deterministic_request_id(
        envelope: ContextPackEnvelope,
        *,
        requested_operation: str,
        authority_scope: str,
    ) -> str:
        payload: dict[str, Any] = {
            "context_pack": asdict(envelope),
            "requested_operation": requested_operation,
            "authority_scope": authority_scope,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        return "CPAA-" + digest
