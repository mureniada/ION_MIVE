"""Expected derived-index identity — the measured half of E2.3.

This module answers one question, from declarations alone:

    "What derived retrieval state do we EXPECT from this exact Content Pack,
     this build, this embedding profile and this vector schema?"

It does not answer what is actually stored anywhere.

    EXPECTED DERIVED INDEX IDENTITY != MEASURED MATERIALIZED INDEX IDENTITY
    DECLARED EXPECTATION            != MEASURED STORE STATE

Nothing here opens a store, constructs an embedder, calls a provider, touches
the filesystem, reads a clock, or mints a UUID. The only inputs are the
arguments passed in, so the same declarations always produce the same bytes and
the same digest on any machine.

Canonicalization profile
------------------------
`CANONICALIZATION_PROFILE_ID` is the INTERNAL deterministic-profile identity
already established and bound by E2.1, reused here rather than reinvented. It is
not a claim of external RFC 8785 conformance; it names the byte rule this
repository commits to, so a later change of implementation is a visible profile
change rather than a silent drift in identity.

What the payload deliberately excludes
--------------------------------------
`provenance_created_at` — it changes provenance-materialization metadata and
nothing else: not content, not chunk identity, not embedding input or output,
not dimension, not distance semantics, not ranking. Two builds of the same
corpus an hour apart must not be two different indexes.

The Qdrant collection name — runtime/deployment configuration, not canonical
identity. Source roots, binding paths and absolute paths — machine facts. Point
ids, point counts, verification status, activation state and any measured
identity — materialization concerns owned by E3.

Ordering
--------
The record set is canonicalized by `document_id`, which is unique within a
build. Caller ordering therefore cannot move the fingerprint. Payload property
names are fixed ASCII, the domain on which the bound serializer's UTF-16
property-name ordering is unambiguous.

Division of responsibility with `models.py`
-------------------------------------------
This module validates only what determinism requires: exact key sets, string and
integer shapes, and unique document ids. Vocabulary governance — which backends
exist, which revisions count as placeholders, which distance metrics are
supported, whether the embedding and vector dimensions agree — belongs to
`models.py` and is not duplicated here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from t4 import jcs

#: Internal deterministic-profile identity, reused from E2.1. NOT an external
#: conformance claim.
CANONICALIZATION_PROFILE = "ION_DERIVED_INDEX_CANONICALIZATION_PROFILE_V0_1"
CANONICALIZATION_PROFILE_ID = "ION_JCS_V0_1"
CANONICALIZATION_IMPLEMENTATION = "t4.jcs.serialize"

FINGERPRINT_ALGORITHM = "SHA256"

#: One entry of the canonical record set. The evidence fingerprint already binds
#: the identity-bearing content projection, so no further record payload is
#: carried here merely because it happens to be available.
RECORD_DESCRIPTOR_KEYS: tuple[str, ...] = ("document_id", "evidence_fingerprint")

#: The declared embedding profile, as it enters identity. `implementation_revision`
#: sits alongside `model_revision` because the vectors depend on BOTH the model
#: artifact and the implementation envelope that runs it:
#:     MODEL REVISION != EMBEDDING IMPLEMENTATION REVISION
EMBEDDING_PROFILE_KEYS: tuple[str, ...] = (
    "backend",
    "model_name",
    "model_revision",
    "implementation_revision",
    "dimension",
    "normalization_profile",
)

#: The declared vector schema, as it enters identity.
VECTOR_SCHEMA_KEYS: tuple[str, ...] = ("dimension", "distance_metric", "vector_name")

#: The identity payload. Exactly these eleven fields — and never the resulting
#: fingerprint itself, which cannot be an input to its own computation.
PAYLOAD_KEYS: tuple[str, ...] = (
    "derived_index_contract_version",
    "pack_id",
    "pack_version",
    "pack_canonical_fingerprint",
    "content_engine_contract_version",
    "content_engine_version",
    "chunk_chars",
    "overlap",
    "record_set",
    "embedding_profile",
    "vector_schema",
)

__all__ = [
    "CANONICALIZATION_IMPLEMENTATION",
    "CANONICALIZATION_PROFILE",
    "CANONICALIZATION_PROFILE_ID",
    "DerivedIndexIdentityError",
    "EMBEDDING_PROFILE_KEYS",
    "FINGERPRINT_ALGORITHM",
    "PAYLOAD_KEYS",
    "RECORD_DESCRIPTOR_KEYS",
    "VECTOR_SCHEMA_KEYS",
    "canonical_bytes",
    "canonical_payload",
    "canonical_record_set",
    "compute_derived_index_fingerprint",
]


class DerivedIndexIdentityError(ValueError):
    """Raised whenever an expected derived-index identity cannot be computed.

    Every failure is closed. A missing field, an unexpected field, a non-string
    or non-integer value, a whitespace-padded value or a duplicated document id
    is refused; none is trimmed, defaulted, deduplicated or coerced into a
    legal-looking value, because a repaired input would yield a digest that
    describes something the caller never declared.

    Module-local on purpose: this introduces no transport stage and no mapping
    onto the core error taxonomy.
    """


def _identity_text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise DerivedIndexIdentityError(
            f"{what} must be a non-empty string, found {value!r}"
        )
    if value != value.strip():
        raise DerivedIndexIdentityError(
            f"{what} must carry no leading/trailing whitespace, found {value!r}"
        )
    return value


def _optional_identity_text(value: Any, what: str) -> str | None:
    """A declared value or an explicit absence. Absence is null, never a placeholder."""
    if value is None:
        return None
    return _identity_text(value, what)


def _positive_int(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DerivedIndexIdentityError(f"{what} must be an integer, found {value!r}")
    if value <= 0:
        raise DerivedIndexIdentityError(f"{what} must be > 0, found {value!r}")
    return value


def _mapping_with_keys(value: Any, keys: tuple[str, ...], what: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DerivedIndexIdentityError(
            f"{what} must be a mapping, found {type(value).__name__}"
        )
    if set(value.keys()) != set(keys):
        raise DerivedIndexIdentityError(
            f"{what} must carry exactly the fields {list(keys)}, found {sorted(value.keys())}"
        )
    return dict(value)


def canonical_record_set(records: Sequence[Any]) -> tuple[dict[str, str], ...]:
    """Return the record descriptors in canonical order: by `document_id`.

    The caller's ordering carries no identity. A duplicated `document_id` fails
    closed rather than resolving to a last-one-wins winner: a record set naming
    one document twice does not describe one index.
    """
    if isinstance(records, (str, bytes, Mapping)):
        raise DerivedIndexIdentityError(
            f"record_set must be a sequence of record descriptors, "
            f"found {type(records).__name__}"
        )

    entries: list[dict[str, str]] = []
    for position, record in enumerate(records):
        where = f"record_set[{position}]"
        raw = _mapping_with_keys(record, RECORD_DESCRIPTOR_KEYS, where)
        entries.append(
            {key: _identity_text(raw[key], f"{where}.{key}") for key in RECORD_DESCRIPTOR_KEYS}
        )

    if not entries:
        raise DerivedIndexIdentityError(
            "record_set must be non-empty: an index expected to hold nothing is not an index"
        )

    seen: set[str] = set()
    for entry in entries:
        document_id = entry["document_id"]
        if document_id in seen:
            raise DerivedIndexIdentityError(
                f"duplicate document_id in record_set: {document_id!r}"
            )
        seen.add(document_id)

    return tuple(sorted(entries, key=lambda entry: entry["document_id"]))


def _canonical_embedding_profile(profile: Any) -> dict[str, Any]:
    raw = _mapping_with_keys(profile, EMBEDDING_PROFILE_KEYS, "embedding_profile")
    return {
        "backend": _identity_text(raw["backend"], "embedding_profile.backend"),
        "model_name": _optional_identity_text(
            raw["model_name"], "embedding_profile.model_name"
        ),
        "model_revision": _optional_identity_text(
            raw["model_revision"], "embedding_profile.model_revision"
        ),
        # Required for every backend, model-backed or not: a changed
        # implementation can produce different vectors from an unchanged model.
        "implementation_revision": _identity_text(
            raw["implementation_revision"], "embedding_profile.implementation_revision"
        ),
        "dimension": _positive_int(raw["dimension"], "embedding_profile.dimension"),
        "normalization_profile": _identity_text(
            raw["normalization_profile"], "embedding_profile.normalization_profile"
        ),
    }


def _canonical_vector_schema(schema: Any) -> dict[str, Any]:
    raw = _mapping_with_keys(schema, VECTOR_SCHEMA_KEYS, "vector_schema")
    return {
        "dimension": _positive_int(raw["dimension"], "vector_schema.dimension"),
        "distance_metric": _identity_text(
            raw["distance_metric"], "vector_schema.distance_metric"
        ),
        # null is the explicit, canonical representation of the unnamed single
        # vector Qdrant is configured with today. Named and unnamed are
        # different schemas and produce different identities.
        "vector_name": _optional_identity_text(
            raw["vector_name"], "vector_schema.vector_name"
        ),
    }


def canonical_payload(
    *,
    derived_index_contract_version: str,
    pack_id: str,
    pack_version: str,
    pack_canonical_fingerprint: str,
    content_engine_contract_version: str,
    content_engine_version: str,
    chunk_chars: int,
    overlap: int,
    record_set: Sequence[Any],
    embedding_profile: Any,
    vector_schema: Any,
) -> dict[str, Any]:
    """The exact structure the fingerprint covers — nothing more, nothing less."""
    if not isinstance(overlap, int) or isinstance(overlap, bool) or overlap < 0:
        raise DerivedIndexIdentityError(f"overlap must be an integer >= 0, found {overlap!r}")
    chunk_chars = _positive_int(chunk_chars, "chunk_chars")
    if overlap >= chunk_chars:
        raise DerivedIndexIdentityError("overlap must satisfy 0 <= overlap < chunk_chars")

    payload = {
        "derived_index_contract_version": _identity_text(
            derived_index_contract_version, "derived_index_contract_version"
        ),
        "pack_id": _identity_text(pack_id, "pack_id"),
        "pack_version": _identity_text(pack_version, "pack_version"),
        "pack_canonical_fingerprint": _identity_text(
            pack_canonical_fingerprint, "pack_canonical_fingerprint"
        ),
        "content_engine_contract_version": _identity_text(
            content_engine_contract_version, "content_engine_contract_version"
        ),
        "content_engine_version": _identity_text(
            content_engine_version, "content_engine_version"
        ),
        "chunk_chars": chunk_chars,
        "overlap": overlap,
        "record_set": [dict(entry) for entry in canonical_record_set(record_set)],
        "embedding_profile": _canonical_embedding_profile(embedding_profile),
        "vector_schema": _canonical_vector_schema(vector_schema),
    }
    # Structural assertion, not decoration: the payload key set IS the contract.
    if set(payload.keys()) != set(PAYLOAD_KEYS):  # pragma: no cover - unreachable
        raise DerivedIndexIdentityError("canonical payload key set does not match the contract")
    return payload


def canonical_bytes(**kwargs: Any) -> bytes:
    """The bytes the digest covers, under `CANONICALIZATION_PROFILE_ID`."""
    return jcs.serialize(canonical_payload(**kwargs))


def compute_derived_index_fingerprint(**kwargs: Any) -> str:
    """SHA-256, lowercase hexadecimal, over the canonical payload bytes."""
    return hashlib.sha256(canonical_bytes(**kwargs)).hexdigest()
