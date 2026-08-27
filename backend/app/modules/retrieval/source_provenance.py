"""Frozen source provenance metadata implementation for P5.18-E v0.1."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

METADATA_CONTRACT_ID = "ION_SOURCE_PROVENANCE_METADATA_CONTRACT_V0_1"
METADATA_CONTRACT_VERSION = "0.1"

SOURCE_TYPE = "FILE"
COLLECTION_METHOD = "OPERATOR_SUPPLIED_CORPUS_FILE"
PROVENANCE_PRODUCER = "ION_CORPUS_INGESTION_PROVENANCE_EMITTER_V0_1"
SOURCE_FILE_SHA256_ALGORITHM = "SHA256"
SOURCE_FILE_SHA256_BASIS = "COMPLETE_RAW_SOURCE_FILE_BYTES"
SOURCE_ORIGIN_SCHEME = "corpus-file://"

KNOWN = "KNOWN"
UNKNOWN = "UNKNOWN"

_RECORD_KEYS = frozenset(
    {
        "source_id",
        "source_origin",
        "source_type",
        "collection_method",
        "collector",
        "collected_at",
        "collected_at_status",
        "provenance_producer",
        "provenance_created_at",
        "provenance_created_at_status",
        "source_file_sha256",
        "source_file_sha256_algorithm",
        "source_file_sha256_basis",
        "metadata_contract_id",
        "metadata_contract_version",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RFC3339_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not _RFC3339_UTC_RE.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _validate_origin(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(SOURCE_ORIGIN_SCHEME):
        raise ValueError("source_origin must use the frozen corpus-file scheme")

    relative = value[len(SOURCE_ORIGIN_SCHEME) :]
    if not relative or relative.startswith("/") or "\\" in relative or ":" in relative:
        raise ValueError("source_origin must contain a relative POSIX corpus path")

    parts = PurePosixPath(relative).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("source_origin contains an invalid relative path")

    return value


def validate_source_provenance(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValueError("source provenance must be a mapping")
    if set(record.keys()) != _RECORD_KEYS:
        raise ValueError("source provenance must contain exactly the frozen field set")

    out = dict(record)

    source_id = out["source_id"]
    if not isinstance(source_id, str) or not source_id or source_id == "unknown":
        raise ValueError("source_id must be governed and non-empty")

    _validate_origin(out["source_origin"])

    if out["source_type"] != SOURCE_TYPE:
        raise ValueError("unsupported source_type")
    if out["collection_method"] != COLLECTION_METHOD:
        raise ValueError("unsupported collection_method")
    if out["provenance_producer"] != PROVENANCE_PRODUCER:
        raise ValueError("unexpected provenance_producer")

    collector = out["collector"]
    if collector is not None and (not isinstance(collector, str) or not collector):
        raise ValueError("collector must be a non-empty string or null")

    collected_status = out["collected_at_status"]
    collected_at = out["collected_at"]
    if collected_status not in (KNOWN, UNKNOWN):
        raise ValueError("invalid collected_at_status")
    if collected_status == KNOWN and not _valid_utc_timestamp(collected_at):
        raise ValueError("KNOWN collected_at requires an explicit RFC3339 UTC timestamp")
    if collected_status == UNKNOWN and collected_at is not None:
        raise ValueError("UNKNOWN collected_at requires null collected_at")

    created_status = out["provenance_created_at_status"]
    created_at = out["provenance_created_at"]
    if created_status not in (KNOWN, UNKNOWN):
        raise ValueError("invalid provenance_created_at_status")
    if created_status == KNOWN and not _valid_utc_timestamp(created_at):
        raise ValueError(
            "KNOWN provenance_created_at requires an explicit RFC3339 UTC timestamp"
        )
    if created_status == UNKNOWN and created_at is not None:
        raise ValueError("UNKNOWN provenance_created_at requires null timestamp")

    source_sha = out["source_file_sha256"]
    if not isinstance(source_sha, str) or not _SHA256_RE.fullmatch(source_sha):
        raise ValueError("source_file_sha256 must be 64 lowercase hexadecimal characters")
    if out["source_file_sha256_algorithm"] != SOURCE_FILE_SHA256_ALGORITHM:
        raise ValueError("source_file_sha256_algorithm must be SHA256")
    if out["source_file_sha256_basis"] != SOURCE_FILE_SHA256_BASIS:
        raise ValueError("unexpected source_file_sha256_basis")

    if out["metadata_contract_id"] != METADATA_CONTRACT_ID:
        raise ValueError("metadata_contract_id mismatch")
    if out["metadata_contract_version"] != METADATA_CONTRACT_VERSION:
        raise ValueError("metadata_contract_version mismatch")

    return out


def source_provenance_complete(record: Mapping[str, Any]) -> bool:
    validated = validate_source_provenance(record)
    return (
        isinstance(validated["collector"], str)
        and bool(validated["collector"])
        and validated["collected_at_status"] == KNOWN
        and validated["provenance_created_at_status"] == KNOWN
    )


def bind_source_provenance(
    record: Mapping[str, Any],
    *,
    source_id: str,
    source_origin: str,
    source_file_sha256: str,
) -> dict[str, Any]:
    """Validate and bind explicit metadata to deterministic ingestion facts."""

    validated = validate_source_provenance(record)
    if validated["source_id"] != source_id:
        raise ValueError("source provenance source_id does not match ingestion source")
    if validated["source_origin"] != source_origin:
        raise ValueError("source provenance origin does not match ingestion source path")
    if validated["source_file_sha256"] != source_file_sha256:
        raise ValueError("source provenance SHA256 does not match source bytes")
    return validated


def build_source_provenance(
    *,
    source_id: str,
    source_origin: str,
    source_file_sha256: str,
    collector: str | None,
    collected_at: str | None,
    collected_at_status: str,
    provenance_created_at: str | None,
    provenance_created_at_status: str,
) -> dict[str, Any]:
    """Build only from explicit caller values; this module never reads a clock."""

    return validate_source_provenance(
        {
            "source_id": source_id,
            "source_origin": source_origin,
            "source_type": SOURCE_TYPE,
            "collection_method": COLLECTION_METHOD,
            "collector": collector,
            "collected_at": collected_at,
            "collected_at_status": collected_at_status,
            "provenance_producer": PROVENANCE_PRODUCER,
            "provenance_created_at": provenance_created_at,
            "provenance_created_at_status": provenance_created_at_status,
            "source_file_sha256": source_file_sha256,
            "source_file_sha256_algorithm": SOURCE_FILE_SHA256_ALGORITHM,
            "source_file_sha256_basis": SOURCE_FILE_SHA256_BASIS,
            "metadata_contract_id": METADATA_CONTRACT_ID,
            "metadata_contract_version": METADATA_CONTRACT_VERSION,
        }
    )