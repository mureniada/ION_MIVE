"""Expected derived-index contract vocabulary (v0.1) — declaration objects only.

An `ExpectedDerivedIndexDescriptor` states what derived retrieval state is
EXPECTED from one Content Pack, one build, one declared embedding profile and
one declared vector schema:

    IT DECLARES AN EXPECTATION.
    IT DOES NOT MEASURE, WRITE, VERIFY OR ACTIVATE ANYTHING.

Boundaries this contract keeps
------------------------------
    EXPECTED DERIVED INDEX IDENTITY != MEASURED MATERIALIZED INDEX IDENTITY
    DECLARED EXPECTATION            != MEASURED STORE STATE
    EXPECTED IDENTITY               != VERIFICATION RECEIPT
    PACK IDENTITY                   != INDEX IDENTITY
    CONTENT BUILD RESULT            != INDEX IDENTITY
    COLLECTION NAME                 != CANONICAL DERIVED INDEX IDENTITY
    BUILD                           != VERIFY != ACTIVATE

A descriptor is NOT proof that Qdrant exists, that any point was written, that
no stale point remains, that counts match, that vectors match, that a live
collection's schema matches, or that anything is active. Those proofs are E3's.

Model revision and implementation revision
------------------------------------------
Vectors depend on two independent things, and both are declared:

    EMBEDDING BACKEND != EMBEDDING IMPLEMENTATION REVISION
    MODEL REVISION    != EMBEDDING IMPLEMENTATION REVISION
    MODEL IDENTITY    != ADAPTER / ALGORITHM IDENTITY

For a model-backed backend, `model_revision` is a REQUIRED EXPLICIT IMMUTABLE
BINDING. Placeholders — UNKNOWN, UNPINNED, LATEST, DEFAULT, CURRENT, UNRESOLVED
— are refused, because a model name without an immutable revision cannot support
a canonical expected identity:

    MODEL NAME != MODEL REVISION

`implementation_revision` is REQUIRED for EVERY backend, model-backed or not: it
identifies the implementation/runtime envelope whose behaviour determines vector
generation. Without it, a materially changed embedding implementation could keep
the same expected index identity over different vectors. It is declared by the
caller — never defaulted, and never inferred from Git, the filesystem, a package
manager or the environment.

This repository currently pins no revision for its default local
sentence-transformers model, and proves no immutable revision for a provider
model. Such a runtime configuration therefore cannot construct a descriptor here
until explicit immutable revisions are supplied. That is a refusal, not a repair:
nothing about dependency locking or the embedding runtime is changed, and no
revision value is ever fabricated.

The `fake` backend is the repository's dependency-free `HashingEmbedder`. It has
no external model artifact, so it declares `model_name = None` and
`model_revision = None` truthfully rather than carrying an invented revision —
but it must still declare an `implementation_revision`, because its algorithm IS
its identity and a changed algorithm must change the expected index.

    EXPECTED PROFILE != PROVEN RUNTIME PROFILE

A descriptor does not prove that the declared model revision was loaded, that
the declared implementation revision was executed, or that the actual vectors
correspond to either declaration. Those are runtime/materialization questions,
and E3 owns them.

This module imports the standard library and its sibling `identity` module. No
Core, container, Settings, retrieval, Qdrant, embedder, content-engine mutation
path, session or turn-record entry point is reachable from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from .identity import (
    FINGERPRINT_ALGORITHM,
    DerivedIndexIdentityError,
    compute_derived_index_fingerprint,
)

DERIVED_INDEX_CONTRACT_ID = "ION_DERIVED_INDEX_V0_1"
DERIVED_INDEX_CONTRACT_VERSION = "0.1"

SUPPORTED_CONTRACT_VERSIONS: tuple[str, ...] = (DERIVED_INDEX_CONTRACT_VERSION,)

#: The embedding backends this repository actually composes, named with its own
#: configuration vocabulary (`EMBEDDING_BACKEND`).
BACKEND_FAKE = "fake"
BACKEND_LOCAL = "local"
BACKEND_OPENAI = "openai"
SUPPORTED_BACKENDS: tuple[str, ...] = (BACKEND_FAKE, BACKEND_LOCAL, BACKEND_OPENAI)

#: Backends whose output depends on an external model artifact. These require an
#: explicit immutable revision; the others must not invent one.
MODEL_BACKED_BACKENDS: frozenset[str] = frozenset({BACKEND_LOCAL, BACKEND_OPENAI})

#: Values that look like a binding but are not one. Compared case-insensitively.
FORBIDDEN_REVISION_PLACEHOLDERS: frozenset[str] = frozenset(
    {"unknown", "unpinned", "latest", "default", "current", "unresolved", "none", "null"}
)

#: Normalization semantics as the adapters actually implement them:
#: `HashingEmbedder` and `LocalEmbedder` normalize in the adapter; the OpenAI
#: adapter returns provider vectors untouched and this repository proves nothing
#: about their normalization.
NORMALIZATION_L2_BY_ADAPTER = "L2_NORMALIZED_BY_ADAPTER"
NORMALIZATION_PROVIDER_UNVERIFIED = "PROVIDER_SUPPLIED_UNVERIFIED"
SUPPORTED_NORMALIZATION_PROFILES: tuple[str, ...] = (
    NORMALIZATION_L2_BY_ADAPTER,
    NORMALIZATION_PROVIDER_UNVERIFIED,
)

#: The only distance metric this repository configures (`Distance.COSINE`).
#: Nothing else is claimed, because nothing else is used.
DISTANCE_COSINE = "COSINE"
SUPPORTED_DISTANCE_METRICS: tuple[str, ...] = (DISTANCE_COSINE,)

#: Named here only so the prohibition is testable rather than argued. None of
#: these may appear as a field at v0.1 — E3 owns every one of them.
PROHIBITED_IDENTITY_FIELDS: tuple[str, ...] = (
    "activated_at",
    "activation_state",
    "activation_timestamp",
    "actual_point_count",
    "collection",
    "measured_index_fingerprint",
    "measured_point_count",
    "point_count",
    "provenance_created_at",
    "qdrant_collection",
    "rollback_id",
    "source_root",
    "verification_status",
    "verified_at",
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

__all__ = [
    "BACKEND_FAKE",
    "BACKEND_LOCAL",
    "BACKEND_OPENAI",
    "DERIVED_INDEX_CONTRACT_ID",
    "DERIVED_INDEX_CONTRACT_VERSION",
    "DISTANCE_COSINE",
    "DerivedIndexError",
    "EmbeddingProfile",
    "ExpectedDerivedIndexDescriptor",
    "FORBIDDEN_REVISION_PLACEHOLDERS",
    "MODEL_BACKED_BACKENDS",
    "NORMALIZATION_L2_BY_ADAPTER",
    "NORMALIZATION_PROVIDER_UNVERIFIED",
    "PROHIBITED_IDENTITY_FIELDS",
    "RecordDescriptor",
    "SUPPORTED_BACKENDS",
    "SUPPORTED_CONTRACT_VERSIONS",
    "SUPPORTED_DISTANCE_METRICS",
    "SUPPORTED_NORMALIZATION_PROFILES",
    "VectorSchema",
]


class DerivedIndexError(ValueError):
    """Raised whenever an expected derived-index object cannot be constructed.

    Every failure is closed. A missing declaration, a placeholder revision, a
    dimension disagreement, a duplicated document id or a fingerprint that does
    not match recomputation raises here; none is repaired.

    Module-local on purpose, in the same spirit as the Content Pack and Content
    Engine contracts: no transport stage, no mapping onto the core error taxonomy.
    """


def _shape_checked_text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise DerivedIndexError(f"{what} must be a non-empty string, found {value!r}")
    if value != value.strip():
        raise DerivedIndexError(
            f"{what} must carry no leading/trailing whitespace, found {value!r}"
        )
    return value


def _sha256_hex(value: Any, what: str) -> str:
    _shape_checked_text(value, what)
    if not _SHA256_HEX.fullmatch(value):
        raise DerivedIndexError(
            f"{what} must be 64 lowercase hexadecimal characters "
            f"({FINGERPRINT_ALGORITHM}), found {value!r}"
        )
    return value


def _positive_int(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DerivedIndexError(f"{what} must be an integer, found {value!r}")
    if value <= 0:
        raise DerivedIndexError(f"{what} must be > 0, found {value!r}")
    return value


@dataclass(frozen=True, kw_only=True)
class RecordDescriptor:
    """One derived record, as it enters expected index identity.

    Two fields only. The evidence fingerprint already binds the identity-bearing
    content projection, so the full record payload is deliberately not carried
    here merely because it is available.
    """

    document_id: str
    evidence_fingerprint: str

    def __post_init__(self) -> None:
        _shape_checked_text(self.document_id, "document_id")
        _sha256_hex(self.evidence_fingerprint, "evidence_fingerprint")

    def canonical_mapping(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "evidence_fingerprint": self.evidence_fingerprint,
        }


@dataclass(frozen=True, kw_only=True)
class EmbeddingProfile:
    """A DECLARED embedding configuration. Never read from the environment.

    Nothing here instantiates an embedder, loads a model, calls a provider, or
    inspects Git, the filesystem, a package manager or the environment: the
    profile states what the caller declares, and every field participates in
    expected derived-index identity because every one of them can change the
    vectors an index would hold.

    `implementation_revision` is required for every backend — the model and the
    implementation that runs it are two different things, and either can change
    the vectors on its own.
    """

    backend: str
    model_name: str | None
    model_revision: str | None
    implementation_revision: str
    dimension: int
    normalization_profile: str

    def __post_init__(self) -> None:
        _shape_checked_text(self.backend, "backend")
        if self.backend not in SUPPORTED_BACKENDS:
            raise DerivedIndexError(
                f"backend must be one of {list(SUPPORTED_BACKENDS)}, found {self.backend!r}"
            )

        _shape_checked_text(self.implementation_revision, "implementation_revision")
        if self.implementation_revision.lower() in FORBIDDEN_REVISION_PLACEHOLDERS:
            raise DerivedIndexError(
                f"implementation_revision {self.implementation_revision!r} is a "
                "placeholder, not an immutable binding; the embedding implementation "
                "envelope must be declared explicitly, never defaulted or inferred"
            )

        _positive_int(self.dimension, "dimension")

        _shape_checked_text(self.normalization_profile, "normalization_profile")
        if self.normalization_profile not in SUPPORTED_NORMALIZATION_PROFILES:
            raise DerivedIndexError(
                "normalization_profile must be one of "
                f"{list(SUPPORTED_NORMALIZATION_PROFILES)}, "
                f"found {self.normalization_profile!r}"
            )

        if self.backend in MODEL_BACKED_BACKENDS:
            _shape_checked_text(self.model_name, "model_name")
            _shape_checked_text(self.model_revision, "model_revision")
            if self.model_revision.lower() in FORBIDDEN_REVISION_PLACEHOLDERS:
                raise DerivedIndexError(
                    f"model_revision {self.model_revision!r} is a placeholder, not an "
                    "immutable binding; a model name without an immutable revision "
                    "cannot support a canonical expected derived-index identity"
                )
        else:
            if self.model_name is not None or self.model_revision is not None:
                raise DerivedIndexError(
                    f"backend {self.backend!r} has no external model artifact; its "
                    "implementation, dimension and normalization are its algorithmic "
                    "identity, so model_name and model_revision must both be None "
                    "rather than carrying an invented value. Declare the algorithm "
                    "through implementation_revision instead."
                )

    def canonical_mapping(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "implementation_revision": self.implementation_revision,
            "dimension": self.dimension,
            "normalization_profile": self.normalization_profile,
        }


@dataclass(frozen=True, kw_only=True)
class VectorSchema:
    """A DECLARED vector-collection schema.

    `vector_name = None` is the explicit representation of the single unnamed
    vector this repository configures today. Named and unnamed are different
    schemas and produce different expected identities.

    The collection NAME is deliberately absent: it is runtime/deployment
    configuration, not canonical derived-index identity.
    """

    dimension: int
    distance_metric: str
    vector_name: str | None = None

    def __post_init__(self) -> None:
        _positive_int(self.dimension, "dimension")

        _shape_checked_text(self.distance_metric, "distance_metric")
        if self.distance_metric not in SUPPORTED_DISTANCE_METRICS:
            raise DerivedIndexError(
                f"distance_metric must be one of {list(SUPPORTED_DISTANCE_METRICS)}, "
                f"found {self.distance_metric!r}"
            )

        if self.vector_name is not None:
            _shape_checked_text(self.vector_name, "vector_name")

    def canonical_mapping(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "distance_metric": self.distance_metric,
            "vector_name": self.vector_name,
        }


@dataclass(frozen=True, kw_only=True)
class ExpectedDerivedIndexDescriptor:
    """One immutable declaration of an expected derived index.

    Pack and content-engine identity are carried verbatim from the
    `ContentBuildResult` the descriptor was created from and are never
    recomputed. `derived_index_fingerprint` is measured, never trusted: `create`
    computes it, and `__post_init__` recomputes and requires exact equality on
    every construction path.

    Deliberately absent, with no field to carry them: `provenance_created_at`
    (build metadata that cannot affect retrieval), the Qdrant collection name,
    source roots, binding paths and absolute paths, point ids and counts,
    verification status, activation state, rollback identity, and any measured
    index fingerprint.
    """

    derived_index_contract_version: str
    pack_id: str
    pack_version: str
    pack_canonical_fingerprint: str
    content_engine_contract_version: str
    content_engine_version: str
    chunk_chars: int
    overlap: int
    record_set: tuple[RecordDescriptor, ...]
    embedding_profile: EmbeddingProfile
    vector_schema: VectorSchema
    derived_index_fingerprint: str

    def __post_init__(self) -> None:
        _shape_checked_text(
            self.derived_index_contract_version, "derived_index_contract_version"
        )
        if self.derived_index_contract_version not in SUPPORTED_CONTRACT_VERSIONS:
            raise DerivedIndexError(
                "derived_index_contract_version must be one of "
                f"{list(SUPPORTED_CONTRACT_VERSIONS)}, "
                f"found {self.derived_index_contract_version!r}"
            )

        _shape_checked_text(self.pack_id, "pack_id")
        _shape_checked_text(self.pack_version, "pack_version")
        _sha256_hex(self.pack_canonical_fingerprint, "pack_canonical_fingerprint")
        _shape_checked_text(
            self.content_engine_contract_version, "content_engine_contract_version"
        )
        _shape_checked_text(self.content_engine_version, "content_engine_version")

        _positive_int(self.chunk_chars, "chunk_chars")
        if not isinstance(self.overlap, int) or isinstance(self.overlap, bool):
            raise DerivedIndexError("overlap must be an integer")
        if self.overlap < 0 or self.overlap >= self.chunk_chars:
            raise DerivedIndexError("overlap must satisfy 0 <= overlap < chunk_chars")

        if not isinstance(self.record_set, tuple):
            raise DerivedIndexError(
                f"record_set must be supplied as a tuple, "
                f"found {type(self.record_set).__name__}"
            )
        if not self.record_set:
            raise DerivedIndexError(
                "record_set must be non-empty: an index expected to hold nothing "
                "is not an index"
            )
        for position, entry in enumerate(self.record_set):
            if not isinstance(entry, RecordDescriptor):
                raise DerivedIndexError(
                    f"record_set[{position}] must be a RecordDescriptor, "
                    f"found {type(entry).__name__}"
                )

        document_ids = [entry.document_id for entry in self.record_set]
        seen: set[str] = set()
        for document_id in document_ids:
            if document_id in seen:
                raise DerivedIndexError(f"duplicate document_id in record_set: {document_id!r}")
            seen.add(document_id)
        if document_ids != sorted(document_ids):
            raise DerivedIndexError(
                "record_set must stand in canonical order (lexicographic by "
                "document_id). Use ExpectedDerivedIndexDescriptor.create to order "
                "an arbitrary record set."
            )

        if not isinstance(self.embedding_profile, EmbeddingProfile):
            raise DerivedIndexError("embedding_profile must be an EmbeddingProfile")
        if not isinstance(self.vector_schema, VectorSchema):
            raise DerivedIndexError("vector_schema must be a VectorSchema")
        if self.vector_schema.dimension != self.embedding_profile.dimension:
            raise DerivedIndexError(
                "vector_schema.dimension must equal embedding_profile.dimension; "
                f"found {self.vector_schema.dimension} and "
                f"{self.embedding_profile.dimension}"
            )

        _shape_checked_text(self.derived_index_fingerprint, "derived_index_fingerprint")
        measured = self._measure(
            derived_index_contract_version=self.derived_index_contract_version,
            pack_id=self.pack_id,
            pack_version=self.pack_version,
            pack_canonical_fingerprint=self.pack_canonical_fingerprint,
            content_engine_contract_version=self.content_engine_contract_version,
            content_engine_version=self.content_engine_version,
            chunk_chars=self.chunk_chars,
            overlap=self.overlap,
            record_set=self.record_set,
            embedding_profile=self.embedding_profile,
            vector_schema=self.vector_schema,
        )
        if self.derived_index_fingerprint != measured:
            raise DerivedIndexError(
                "derived_index_fingerprint does not match the identity measured from "
                f"this descriptor's own declarations: declared "
                f"{self.derived_index_fingerprint!r}, measured {measured!r}"
            )

    @staticmethod
    def _measure(
        *,
        derived_index_contract_version: str,
        pack_id: str,
        pack_version: str,
        pack_canonical_fingerprint: str,
        content_engine_contract_version: str,
        content_engine_version: str,
        chunk_chars: int,
        overlap: int,
        record_set: Sequence[RecordDescriptor],
        embedding_profile: EmbeddingProfile,
        vector_schema: VectorSchema,
    ) -> str:
        try:
            return compute_derived_index_fingerprint(
                derived_index_contract_version=derived_index_contract_version,
                pack_id=pack_id,
                pack_version=pack_version,
                pack_canonical_fingerprint=pack_canonical_fingerprint,
                content_engine_contract_version=content_engine_contract_version,
                content_engine_version=content_engine_version,
                chunk_chars=chunk_chars,
                overlap=overlap,
                record_set=[entry.canonical_mapping() for entry in record_set],
                embedding_profile=embedding_profile.canonical_mapping(),
                vector_schema=vector_schema.canonical_mapping(),
            )
        except DerivedIndexIdentityError as exc:
            raise DerivedIndexError(
                f"expected derived-index identity could not be measured: {exc}"
            ) from exc

    @classmethod
    def create(
        cls,
        content_build_result: Any,
        embedding_profile: EmbeddingProfile,
        vector_schema: VectorSchema,
        *,
        derived_index_contract_version: str = DERIVED_INDEX_CONTRACT_VERSION,
    ) -> "ExpectedDerivedIndexDescriptor":
        """Declare the expected index for one build under one declared configuration.

        Pack and engine identity, and the chunk parameters, are read from
        `content_build_result` — a caller cannot restate them independently and
        so cannot state a conflicting value. The build result is read only; it is
        never modified, and its `provenance_created_at` is deliberately not read
        into identity.

        There is no `derived_index_fingerprint` parameter: the fingerprint is
        measured here, never supplied.
        """
        try:
            pack_id = content_build_result.pack_id
            pack_version = content_build_result.pack_version
            pack_canonical_fingerprint = content_build_result.pack_canonical_fingerprint
            engine_contract_version = (
                content_build_result.content_engine_contract_version
            )
            engine_version = content_build_result.content_engine_version
            chunk_chars = content_build_result.chunk_chars
            overlap = content_build_result.overlap
            records = content_build_result.records
        except AttributeError as exc:
            raise DerivedIndexError(
                f"content_build_result is missing a required field: {exc}"
            ) from exc

        descriptors: list[RecordDescriptor] = []
        for position, record in enumerate(records):
            try:
                descriptors.append(
                    RecordDescriptor(
                        document_id=record["document_id"],
                        evidence_fingerprint=record["evidence_fingerprint"],
                    )
                )
            except (KeyError, TypeError) as exc:
                raise DerivedIndexError(
                    f"records[{position}] is missing a required identity field: {exc}"
                ) from exc

        ordered = tuple(sorted(descriptors, key=lambda entry: entry.document_id))

        return cls(
            derived_index_contract_version=derived_index_contract_version,
            pack_id=pack_id,
            pack_version=pack_version,
            pack_canonical_fingerprint=pack_canonical_fingerprint,
            content_engine_contract_version=engine_contract_version,
            content_engine_version=engine_version,
            chunk_chars=chunk_chars,
            overlap=overlap,
            record_set=ordered,
            embedding_profile=embedding_profile,
            vector_schema=vector_schema,
            derived_index_fingerprint=cls._measure(
                derived_index_contract_version=derived_index_contract_version,
                pack_id=pack_id,
                pack_version=pack_version,
                pack_canonical_fingerprint=pack_canonical_fingerprint,
                content_engine_contract_version=engine_contract_version,
                content_engine_version=engine_version,
                chunk_chars=chunk_chars,
                overlap=overlap,
                record_set=ordered,
                embedding_profile=embedding_profile,
                vector_schema=vector_schema,
            ),
        )

    @property
    def record_count(self) -> int:
        """Expected record count. A declaration, never a measured point count."""
        return len(self.record_set)
