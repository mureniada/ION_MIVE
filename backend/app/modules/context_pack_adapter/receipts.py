from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .models import (
    AdapterValidationResult,
    ContextPackEnvelope,
    EvidenceAdmissionRequest,
)


@dataclass(frozen=True)
class AdapterExecutionReceipt:
    adapter_id: str
    adapter_version: str
    context_pack_id: str
    request_id: str
    input_sha256: str
    output_sha256: str
    validation_status: str
    created_at: str


def build_execution_receipt(
    envelope: ContextPackEnvelope,
    request: EvidenceAdmissionRequest,
    validation: AdapterValidationResult,
    *,
    created_at: str | None = None,
) -> AdapterExecutionReceipt:
    return AdapterExecutionReceipt(
        adapter_id="ION_CONTEXT_PACK_EVIDENCE_ADMISSION_ADAPTER",
        adapter_version="0.1",
        context_pack_id=envelope.context_pack_id,
        request_id=request.request_id,
        input_sha256=_sha256(asdict(envelope)),
        output_sha256=_sha256(asdict(request)),
        validation_status=validation.status.value,
        created_at=created_at or _utc_now(),
    )


def _sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
