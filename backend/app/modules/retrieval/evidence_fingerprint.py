"""Frozen per-Evidence fingerprint implementation for P5.18-F v0.1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

PROFILE_ID = "ION_EVIDENCE_FINGERPRINT_PROFILE_V0_1"
PROFILE_VERSION = "0.1"
ALGORITHM = "SHA256"
CANONICALIZATION = "RFC8785_JSON_CANONICALIZATION"

_PROJECTION_KEYS = frozenset(
    {
        "profile_id",
        "document_id",
        "source_identity",
        "title",
        "page",
        "chunk_id",
        "content",
    }
)


def _require_string(value: Any, field: str, *, non_empty: bool) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if non_empty and value == "":
        raise ValueError(f"{field} must be non-empty")
    return value


def _validate_projection(projection: Mapping[str, Any]) -> dict[str, Any]:
    if set(projection.keys()) != _PROJECTION_KEYS:
        raise ValueError("fingerprint projection must contain exactly the frozen seven fields")

    if projection["profile_id"] != PROFILE_ID:
        raise ValueError("profile_id does not match the frozen profile")

    document_id = _require_string(projection["document_id"], "document_id", non_empty=True)
    source_identity = _require_string(
        projection["source_identity"], "source_identity", non_empty=True
    )
    if source_identity == "unknown":
        raise ValueError('source_identity literal "unknown" is not governed')

    title = _require_string(projection["title"], "title", non_empty=False)
    chunk_id = _require_string(projection["chunk_id"], "chunk_id", non_empty=True)
    content = _require_string(projection["content"], "content", non_empty=False)

    page = projection["page"]
    if page is not None and (not isinstance(page, int) or isinstance(page, bool)):
        raise ValueError("page must be an integer or null")

    return {
        "profile_id": PROFILE_ID,
        "document_id": document_id,
        "source_identity": source_identity,
        "title": title,
        "page": page,
        "chunk_id": chunk_id,
        "content": content,
    }


def projection_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    try:
        projection = {
            "profile_id": PROFILE_ID,
            "document_id": record["document_id"],
            "source_identity": record["source_id"],
            "title": record["title"],
            "page": record["page"],
            "chunk_id": record["chunk_id"],
            "content": record["content"],
        }
    except KeyError as exc:
        raise ValueError(f"missing fingerprint field: {exc.args[0]}") from exc
    return _validate_projection(projection)


def projection_from_evidence(evidence: Any) -> dict[str, Any]:
    try:
        projection = {
            "profile_id": PROFILE_ID,
            "document_id": evidence.document_id,
            "source_identity": evidence.source_id,
            "title": evidence.title,
            "page": evidence.page,
            "chunk_id": evidence.chunk_id,
            "content": evidence.content,
        }
    except AttributeError as exc:
        raise ValueError("evidence object is missing a frozen fingerprint field") from exc
    return _validate_projection(projection)


def canonicalize_projection(projection: Mapping[str, Any]) -> bytes:
    """Return RFC8785-equivalent bytes for the frozen restricted projection domain.

    The profile permits only fixed ASCII keys and string/integer/null values.  With
    ensure_ascii=False, compact separators, and sorted keys, Python JSON serialization
    produces the frozen JCS bytes for this restricted domain.  Frozen test vectors are
    the conformance authority.
    """

    validated = _validate_projection(projection)
    text = json.dumps(
        validated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8")


def fingerprint_projection(projection: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonicalize_projection(projection)).hexdigest()


def compute_fingerprint_from_record(record: Mapping[str, Any]) -> str:
    return fingerprint_projection(projection_from_record(record))


def recompute_evidence_fingerprint(evidence: Any) -> str:
    """Independently recompute from Evidence fields; stored metadata is never read."""

    return fingerprint_projection(projection_from_evidence(evidence))