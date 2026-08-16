"""ION PEL Replay Comparability Prerequisite — ReplayExecutionDescriptor
identity and digest primitives.

Pure functions only. No filesystem I/O, no app dependency, no t4
dependency, no network. Implements exactly the identity/digest rules
frozen in ``ION_PEL_REPLAY_EXECUTION_DESCRIPTOR_CONTRACT_FREEZE_v0.1.md``
(sections 6-9) and its completeness addendum.
"""

from __future__ import annotations

import json

from .integrity import sha256_bytes
from .normalized_identity import serialize_deterministic_json

#: Frozen contract section 9. An independent identity for this object --
#: not derived from parser_version, output_contract_id, or any
#: normalization-layer identity.
REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID = (
    "https://ion.local/schemas/pel_replay_execution_descriptor_v0_1.schema.json"
)

__all__ = [
    "REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID",
    "compute_replay_execution_descriptor_id",
    "compute_replay_execution_descriptor_schema_id_digest",
    "serialize_deterministic_json",
]


def compute_replay_execution_descriptor_id(
    *, run_id: str, replay_execution_descriptor_schema_id: str
) -> str:
    """Frozen contract section 7: the 2-component canonical identity tuple.

    JSON-array structural encoding (not delimiter concatenation); no
    trailing newline participates. Content fields (model_family,
    provider_settings, etc.) are deliberately excluded -- they are this
    object's payload, not its identity, mirroring how Phase 2B.2's
    normalized_artifact_id excludes judgment content.
    """
    canonical_bytes = json.dumps(
        [run_id, replay_execution_descriptor_schema_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(canonical_bytes)


def compute_replay_execution_descriptor_schema_id_digest(
    replay_execution_descriptor_schema_id: str,
) -> str:
    """Frozen contract section 15: a filesystem-safe stand-in for the
    schema ``$id`` (a URI, not itself a safe single path component)."""
    return sha256_bytes(replay_execution_descriptor_schema_id.encode("utf-8"))
