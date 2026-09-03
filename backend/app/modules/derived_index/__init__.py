"""Expected derived-index identity (v0.1) — public package surface.

Answers one question, from declarations alone:

    "What derived retrieval state do we EXPECT from this exact Content Pack,
     build, embedding profile and vector schema?"

It never answers what is actually stored in Qdrant right now.

    EXPECTED DERIVED INDEX IDENTITY != MEASURED MATERIALIZED INDEX IDENTITY
    DECLARED EXPECTATION            != MEASURED STORE STATE
    EXPECTED IDENTITY               != VERIFICATION RECEIPT
    BUILD                           != VERIFY != ACTIVATE

This package must never open a store, construct an embedder, call a provider,
touch the filesystem, read a clock, mint a UUID, write anything, or mutate the
Content Pack, Content Build Result, embedding profile or vector schema it is
given. Measured/materialized identity, point counts, stale-point detection,
collection-schema verification, activation and rollback all belong to E3.

See `models.py` for the contract objects and `identity.py` for the canonical
byte rule and fingerprint.
"""

from __future__ import annotations

from .identity import (
    CANONICALIZATION_IMPLEMENTATION,
    CANONICALIZATION_PROFILE,
    CANONICALIZATION_PROFILE_ID,
    EMBEDDING_PROFILE_KEYS,
    FINGERPRINT_ALGORITHM,
    PAYLOAD_KEYS,
    RECORD_DESCRIPTOR_KEYS,
    VECTOR_SCHEMA_KEYS,
    DerivedIndexIdentityError,
    canonical_bytes,
    canonical_payload,
    canonical_record_set,
    compute_derived_index_fingerprint,
)
from .models import (
    BACKEND_FAKE,
    BACKEND_LOCAL,
    BACKEND_OPENAI,
    DERIVED_INDEX_CONTRACT_ID,
    DERIVED_INDEX_CONTRACT_VERSION,
    DISTANCE_COSINE,
    FORBIDDEN_REVISION_PLACEHOLDERS,
    MODEL_BACKED_BACKENDS,
    NORMALIZATION_L2_BY_ADAPTER,
    NORMALIZATION_PROVIDER_UNVERIFIED,
    PROHIBITED_IDENTITY_FIELDS,
    SUPPORTED_BACKENDS,
    SUPPORTED_CONTRACT_VERSIONS,
    SUPPORTED_DISTANCE_METRICS,
    SUPPORTED_NORMALIZATION_PROFILES,
    DerivedIndexError,
    EmbeddingProfile,
    ExpectedDerivedIndexDescriptor,
    RecordDescriptor,
    VectorSchema,
)

__all__ = [
    "BACKEND_FAKE",
    "BACKEND_LOCAL",
    "BACKEND_OPENAI",
    "CANONICALIZATION_IMPLEMENTATION",
    "CANONICALIZATION_PROFILE",
    "CANONICALIZATION_PROFILE_ID",
    "DERIVED_INDEX_CONTRACT_ID",
    "DERIVED_INDEX_CONTRACT_VERSION",
    "DISTANCE_COSINE",
    "DerivedIndexError",
    "DerivedIndexIdentityError",
    "EMBEDDING_PROFILE_KEYS",
    "EmbeddingProfile",
    "ExpectedDerivedIndexDescriptor",
    "FINGERPRINT_ALGORITHM",
    "FORBIDDEN_REVISION_PLACEHOLDERS",
    "MODEL_BACKED_BACKENDS",
    "NORMALIZATION_L2_BY_ADAPTER",
    "NORMALIZATION_PROVIDER_UNVERIFIED",
    "PAYLOAD_KEYS",
    "PROHIBITED_IDENTITY_FIELDS",
    "RECORD_DESCRIPTOR_KEYS",
    "RecordDescriptor",
    "SUPPORTED_BACKENDS",
    "SUPPORTED_CONTRACT_VERSIONS",
    "SUPPORTED_DISTANCE_METRICS",
    "SUPPORTED_NORMALIZATION_PROFILES",
    "VECTOR_SCHEMA_KEYS",
    "VectorSchema",
    "canonical_bytes",
    "canonical_payload",
    "canonical_record_set",
    "compute_derived_index_fingerprint",
]
