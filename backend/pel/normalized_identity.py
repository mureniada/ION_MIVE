"""ION PEL Phase 2B.2 — normalized-artifact identity and digest primitives.

Pure functions only. No filesystem I/O, no app dependency, no t4
dependency, no network. Implements exactly the identity/digest/
serialization rules frozen in
``ION_PEL_PHASE2B2_DERIVED_ARTIFACT_PERSISTENCE_CONTRACT_FREEZE_v0.1.md``,
sections 6, 7, 8, and 11.
"""

from __future__ import annotations

import json

from .integrity import sha256_bytes

#: Frozen contract section 6 -- the $id of
#: schemas/pel_normalized_judgment_v0_2_2.schema.json. Not derived from
#: parser_version: PARSER VERSION != NORMALIZED SCHEMA IDENTITY.
NORMALIZED_SCHEMA_ID = "https://ion.local/schemas/pel_normalized_judgment_v0_2_2.schema.json"

__all__ = [
    "NORMALIZED_SCHEMA_ID",
    "compute_normalized_artifact_id",
    "compute_normalized_content_sha256",
    "compute_normalized_schema_id_digest",
    "serialize_deterministic_json",
]


def compute_normalized_artifact_id(
    *,
    run_id: str,
    output_contract_id: str,
    parser_id: str,
    parser_version: str,
    normalized_schema_id: str,
) -> str:
    """Frozen contract section 7: the 5-component canonical identity tuple.

    JSON-array structural encoding (not delimiter concatenation); no
    trailing newline participates; lowercase hex via ``sha256_bytes``.
    """
    canonical_bytes = json.dumps(
        [run_id, output_contract_id, parser_id, parser_version, normalized_schema_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(canonical_bytes)


def compute_normalized_schema_id_digest(normalized_schema_id: str) -> str:
    """Frozen contract section 10: a filesystem-safe stand-in for the
    schema ``$id`` (a URI, not itself a safe single path component)."""
    return sha256_bytes(normalized_schema_id.encode("utf-8"))


def serialize_deterministic_json(payload: dict) -> bytes:
    """Frozen contract sections 8B, 11: the exact persisted-file
    convention, reused unchanged from Phase 2A's local deterministic
    serialization (not RFC 8785, not a universal canonical JSON standard).
    Used for both ``judgment.json`` and ``receipt.json``.
    """
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
        + b"\n"
    )


def compute_normalized_content_sha256(judgment_dict: dict) -> str:
    """Frozen contract section 8A: logical normalized-content identity.

    ``normalized_at`` is removed entirely (never replaced with null)
    before serialization; no trailing newline participates. Must never be
    used as proof of exact persisted-byte identity -- see
    ``artifact_bytes_sha256`` for that.
    """
    content_dict = dict(judgment_dict)
    content_dict.pop("normalized_at", None)
    content_bytes = json.dumps(
        content_dict, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(content_bytes)
