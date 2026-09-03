"""E3 derived-index lifecycle contract vocabulary (v0.1) — receipt objects.

This package answers the question `derived_index` (E2.3) deliberately refuses
to answer: what actually happened when an EXPECTED derived index was built,
measured, verified, activated or rolled back.

    EXPECTED IDENTITY   != MEASURED STORE STATE
    BUILD != MEASURE != VERIFY != ACTIVATE != ROLLBACK
    CANDIDATE != ACTIVE
    VERIFIED != ACTIVE
    ROLLBACK != REBUILD

Every receipt here is an immutable, validated, EVENT/AUDIT record: it states
what happened, once, under an explicit caller-supplied RFC3339 UTC timestamp.
No receipt reads a clock, mints a UUID, or infers a revision from Git, the
filesystem, a package manager or the environment. A receipt's own fingerprint
is always MEASURED from its own declared fields and re-checked on every
construction — the same "measured, never trusted" discipline
`derived_index.ExpectedDerivedIndexDescriptor` uses for its own identity.

Selected architecture (operator-approved): blue/green physical Qdrant
collections behind one stable alias. `materialize.py` builds and measures a
candidate physical collection; `verify.py` is a pure comparison of declared
expectation against measured fact; `activation.py` performs the one bounded
alias cutover (and its reverse, rollback).

This module imports the standard library, its sibling `identity` module, and
`derived_index`'s public models (`ExpectedDerivedIndexDescriptor`,
`EmbeddingProfile`, `VectorSchema`) read-only. No Core, container, Settings,
session, turn-record, Qdrant client, embedder or filesystem path is reachable
from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..derived_index import EmbeddingProfile, VectorSchema
from .identity import compute_fingerprint

DERIVED_INDEX_LIFECYCLE_CONTRACT_ID = "ION_DERIVED_INDEX_LIFECYCLE_V0_1"
DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION = "0.1"
SUPPORTED_LIFECYCLE_CONTRACT_VERSIONS: tuple[str, ...] = (
    DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
)

#: The only verification scope this implementation performs or claims:
#: record-set completeness, evidence-fingerprint equality, vector-schema
#: equality and candidate/expected identity binding. It is NOT universal
#: vector-byte reproduction proof.
VERIFICATION_SCOPE_STRUCTURAL_V0_1 = "STRUCTURAL_V0_1"
SUPPORTED_VERIFICATION_SCOPES: tuple[str, ...] = (VERIFICATION_SCOPE_STRUCTURAL_V0_1,)

#: v0.1 never claims more than "an embedder object satisfying the declared
#: profile was invoked"; it never claims the declared model/implementation
#: revision was actually loaded or executed.
EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY = "DECLARED_ONLY"
SUPPORTED_EMBEDDING_EXECUTION_BINDINGS: tuple[str, ...] = (
    EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY,
)

VERIFICATION_STATUS_PASS = "PASS"
VERIFICATION_STATUS_FAIL = "FAIL"
SUPPORTED_VERIFICATION_STATUSES: tuple[str, ...] = (
    VERIFICATION_STATUS_PASS,
    VERIFICATION_STATUS_FAIL,
)

#: Bootstrap: alias absent -> alias created pointing at the first candidate.
#: Cutover: alias moved from one existing physical collection to another, in
#: one `update_collection_aliases` request (delete + create).
ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE = "ALIAS_BOOTSTRAP_CREATE"
ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER = "ALIAS_ATOMIC_CUTOVER"
SUPPORTED_ACTIVATION_METHODS: tuple[str, ...] = (
    ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE,
    ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER,
)

ROLLBACK_RESULT_ROLLED_BACK = "ROLLED_BACK"
SUPPORTED_ROLLBACK_RESULTS: tuple[str, ...] = (ROLLBACK_RESULT_ROLLED_BACK,)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_RFC3339_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)

__all__ = [
    "ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER",
    "ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE",
    "ActivationReceipt",
    "CandidateMaterializationReceipt",
    "DERIVED_INDEX_LIFECYCLE_CONTRACT_ID",
    "DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION",
    "DerivedIndexLifecycleError",
    "EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY",
    "MeasuredDerivedIndexDescriptor",
    "MeasuredPointDescriptor",
    "ROLLBACK_RESULT_ROLLED_BACK",
    "RollbackReceipt",
    "SUPPORTED_ACTIVATION_METHODS",
    "SUPPORTED_EMBEDDING_EXECUTION_BINDINGS",
    "SUPPORTED_LIFECYCLE_CONTRACT_VERSIONS",
    "SUPPORTED_ROLLBACK_RESULTS",
    "SUPPORTED_VERIFICATION_SCOPES",
    "SUPPORTED_VERIFICATION_STATUSES",
    "VERIFICATION_SCOPE_STRUCTURAL_V0_1",
    "VERIFICATION_STATUS_FAIL",
    "VERIFICATION_STATUS_PASS",
    "VerificationReceipt",
]


class DerivedIndexLifecycleError(ValueError):
    """Raised whenever an E3 lifecycle object or operation cannot proceed.

    Every failure is closed: a missing declaration, an out-of-place value, a
    fingerprint that does not match recomputation, a name collision, a
    disallowed store shape, a stale alias prestate or a missing alias
    capability all raise here. Nothing is repaired, defaulted or inferred.

    The one exception type for the whole `derived_index_lifecycle` package, by
    design — this module introduces no transport stage and no mapping onto
    the core error taxonomy.
    """


# --------------------------------------------------------------------------- #
# shape helpers — local on purpose; no shared validation framework
# --------------------------------------------------------------------------- #


def _shape_checked_text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise DerivedIndexLifecycleError(f"{what} must be a non-empty string, found {value!r}")
    if value != value.strip():
        raise DerivedIndexLifecycleError(
            f"{what} must carry no leading/trailing whitespace, found {value!r}"
        )
    return value


def _optional_shape_checked_text(value: Any, what: str) -> str | None:
    if value is None:
        return None
    return _shape_checked_text(value, what)


def _sha256_hex(value: Any, what: str) -> str:
    _shape_checked_text(value, what)
    if not _SHA256_HEX.fullmatch(value):
        raise DerivedIndexLifecycleError(
            f"{what} must be 64 lowercase hexadecimal characters (SHA256), found {value!r}"
        )
    return value


def _positive_int(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DerivedIndexLifecycleError(f"{what} must be an integer, found {value!r}")
    if value <= 0:
        raise DerivedIndexLifecycleError(f"{what} must be > 0, found {value!r}")
    return value


def _non_negative_int(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DerivedIndexLifecycleError(f"{what} must be an integer, found {value!r}")
    if value < 0:
        raise DerivedIndexLifecycleError(f"{what} must be >= 0, found {value!r}")
    return value


def _rfc3339_utc(value: Any, what: str) -> str:
    """Require an explicit, caller-supplied RFC3339 UTC timestamp.

    No system clock is ever consulted here — this only validates the shape of
    a string the caller already supplied.
    """
    if not isinstance(value, str) or not _RFC3339_UTC_RE.fullmatch(value):
        raise DerivedIndexLifecycleError(
            f"{what} must be an explicit RFC3339 UTC timestamp (e.g. "
            f"'2026-09-03T09:00:00Z'), found {value!r}"
        )
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DerivedIndexLifecycleError(f"{what} is not a valid timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise DerivedIndexLifecycleError(f"{what} must be UTC, found {value!r}")
    return value


def _canonical_text_tuple(values: Any, what: str) -> tuple[str, ...]:
    """A caller-declared collection of strings, stored in deterministic order."""
    if not isinstance(values, tuple):
        raise DerivedIndexLifecycleError(
            f"{what} must be supplied as a tuple, found {type(values).__name__}"
        )
    for position, entry in enumerate(values):
        if not isinstance(entry, str) or not entry:
            raise DerivedIndexLifecycleError(
                f"{what}[{position}] must be a non-empty string, found {entry!r}"
            )
    ordered = tuple(sorted(values))
    if ordered != values:
        raise DerivedIndexLifecycleError(
            f"{what} must stand in canonical (sorted) order, found {values!r}"
        )
    return ordered


def _contract_version(value: Any) -> str:
    _shape_checked_text(value, "lifecycle_contract_version")
    if value not in SUPPORTED_LIFECYCLE_CONTRACT_VERSIONS:
        raise DerivedIndexLifecycleError(
            "lifecycle_contract_version must be one of "
            f"{list(SUPPORTED_LIFECYCLE_CONTRACT_VERSIONS)}, found {value!r}"
        )
    return value


def _one_of(value: Any, supported: tuple[str, ...], what: str) -> str:
    _shape_checked_text(value, what)
    if value not in supported:
        raise DerivedIndexLifecycleError(f"{what} must be one of {list(supported)}, found {value!r}")
    return value


# --------------------------------------------------------------------------- #
# candidate materialization
# --------------------------------------------------------------------------- #

_CANDIDATE_RECEIPT_PAYLOAD_KEYS: tuple[str, ...] = (
    "lifecycle_contract_version",
    "expected_derived_index_fingerprint",
    "candidate_physical_collection",
    "embedding_profile",
    "vector_schema",
    "expected_record_count",
    "written_point_count",
    "materialized_at",
    "materializer_implementation_revision",
    "embedding_execution_binding",
)


@dataclass(frozen=True, kw_only=True)
class CandidateMaterializationReceipt:
    """One event: a candidate physical collection was built and written to.

    An EVENT/AUDIT receipt, not canonical derived-index identity — its own
    fingerprint may (and does) bind `materialized_at` and the candidate
    physical collection address, because this receipt states what happened,
    not what is eternally expected:

        CANDIDATE RECEIPT IDENTITY != EXPECTED DERIVED-INDEX IDENTITY

    `written_point_count == expected_record_count` is `success`; the caller
    (`materialize.materialize_candidate`) never constructs this receipt for a
    build that failed that check, so every instance describes a build that
    wrote exactly what was expected.
    """

    lifecycle_contract_version: str
    expected_derived_index_fingerprint: str
    candidate_physical_collection: str
    embedding_profile: EmbeddingProfile
    vector_schema: VectorSchema
    expected_record_count: int
    written_point_count: int
    materialized_at: str
    materializer_implementation_revision: str
    embedding_execution_binding: str
    candidate_receipt_fingerprint: str

    def __post_init__(self) -> None:
        _contract_version(self.lifecycle_contract_version)
        _sha256_hex(self.expected_derived_index_fingerprint, "expected_derived_index_fingerprint")
        _shape_checked_text(self.candidate_physical_collection, "candidate_physical_collection")
        if not isinstance(self.embedding_profile, EmbeddingProfile):
            raise DerivedIndexLifecycleError("embedding_profile must be an EmbeddingProfile")
        if not isinstance(self.vector_schema, VectorSchema):
            raise DerivedIndexLifecycleError("vector_schema must be a VectorSchema")
        _positive_int(self.expected_record_count, "expected_record_count")
        _non_negative_int(self.written_point_count, "written_point_count")
        _rfc3339_utc(self.materialized_at, "materialized_at")
        _shape_checked_text(
            self.materializer_implementation_revision, "materializer_implementation_revision"
        )
        _one_of(
            self.embedding_execution_binding,
            SUPPORTED_EMBEDDING_EXECUTION_BINDINGS,
            "embedding_execution_binding",
        )
        _sha256_hex(self.candidate_receipt_fingerprint, "candidate_receipt_fingerprint")

        measured = self._measure(
            lifecycle_contract_version=self.lifecycle_contract_version,
            expected_derived_index_fingerprint=self.expected_derived_index_fingerprint,
            candidate_physical_collection=self.candidate_physical_collection,
            embedding_profile=self.embedding_profile,
            vector_schema=self.vector_schema,
            expected_record_count=self.expected_record_count,
            written_point_count=self.written_point_count,
            materialized_at=self.materialized_at,
            materializer_implementation_revision=self.materializer_implementation_revision,
            embedding_execution_binding=self.embedding_execution_binding,
        )
        if measured != self.candidate_receipt_fingerprint:
            raise DerivedIndexLifecycleError(
                "candidate_receipt_fingerprint does not match the identity measured "
                f"from this receipt's own fields: declared "
                f"{self.candidate_receipt_fingerprint!r}, measured {measured!r}"
            )

    @property
    def success(self) -> bool:
        return self.written_point_count == self.expected_record_count

    @staticmethod
    def _measure(
        *,
        lifecycle_contract_version: str,
        expected_derived_index_fingerprint: str,
        candidate_physical_collection: str,
        embedding_profile: EmbeddingProfile,
        vector_schema: VectorSchema,
        expected_record_count: int,
        written_point_count: int,
        materialized_at: str,
        materializer_implementation_revision: str,
        embedding_execution_binding: str,
    ) -> str:
        payload = {
            "lifecycle_contract_version": lifecycle_contract_version,
            "expected_derived_index_fingerprint": expected_derived_index_fingerprint,
            "candidate_physical_collection": candidate_physical_collection,
            "embedding_profile": embedding_profile.canonical_mapping(),
            "vector_schema": vector_schema.canonical_mapping(),
            "expected_record_count": expected_record_count,
            "written_point_count": written_point_count,
            "materialized_at": materialized_at,
            "materializer_implementation_revision": materializer_implementation_revision,
            "embedding_execution_binding": embedding_execution_binding,
        }
        assert set(payload.keys()) == set(_CANDIDATE_RECEIPT_PAYLOAD_KEYS)  # pragma: no cover
        return compute_fingerprint(payload)

    @classmethod
    def create(
        cls,
        *,
        expected_derived_index_fingerprint: str,
        candidate_physical_collection: str,
        embedding_profile: EmbeddingProfile,
        vector_schema: VectorSchema,
        expected_record_count: int,
        written_point_count: int,
        materialized_at: str,
        materializer_implementation_revision: str,
        embedding_execution_binding: str = EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY,
        lifecycle_contract_version: str = DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
    ) -> "CandidateMaterializationReceipt":
        fingerprint = cls._measure(
            lifecycle_contract_version=lifecycle_contract_version,
            expected_derived_index_fingerprint=expected_derived_index_fingerprint,
            candidate_physical_collection=candidate_physical_collection,
            embedding_profile=embedding_profile,
            vector_schema=vector_schema,
            expected_record_count=expected_record_count,
            written_point_count=written_point_count,
            materialized_at=materialized_at,
            materializer_implementation_revision=materializer_implementation_revision,
            embedding_execution_binding=embedding_execution_binding,
        )
        return cls(
            lifecycle_contract_version=lifecycle_contract_version,
            expected_derived_index_fingerprint=expected_derived_index_fingerprint,
            candidate_physical_collection=candidate_physical_collection,
            embedding_profile=embedding_profile,
            vector_schema=vector_schema,
            expected_record_count=expected_record_count,
            written_point_count=written_point_count,
            materialized_at=materialized_at,
            materializer_implementation_revision=materializer_implementation_revision,
            embedding_execution_binding=embedding_execution_binding,
            candidate_receipt_fingerprint=fingerprint,
        )


# --------------------------------------------------------------------------- #
# measured store state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, kw_only=True)
class MeasuredPointDescriptor:
    """One point as Qdrant actually reports it — including malformed shapes.

    `document_id` / `evidence_fingerprint` are `None` when the stored payload
    did not carry a well-formed string for that field. Measurement must be
    able to represent invalid or unverifiable store state rather than raise:
    PASS/FAIL is owned entirely by `verify.py`.
    """

    qdrant_point_id: str
    document_id: str | None
    evidence_fingerprint: str | None

    def __post_init__(self) -> None:
        _shape_checked_text(self.qdrant_point_id, "qdrant_point_id")
        if self.document_id is not None and not isinstance(self.document_id, str):
            raise DerivedIndexLifecycleError("document_id must be a string or None")
        if self.evidence_fingerprint is not None and not isinstance(
            self.evidence_fingerprint, str
        ):
            raise DerivedIndexLifecycleError("evidence_fingerprint must be a string or None")

    def canonical_mapping(self) -> dict[str, Any]:
        return {
            "qdrant_point_id": self.qdrant_point_id,
            "document_id": self.document_id,
            "evidence_fingerprint": self.evidence_fingerprint,
        }


_MEASURED_STATE_PAYLOAD_KEYS: tuple[str, ...] = (
    "lifecycle_contract_version",
    "candidate_physical_collection",
    "vector_schema",
    "reported_point_count",
    "enumerated_point_count",
    "measured_points",
)


@dataclass(frozen=True, kw_only=True)
class MeasuredDerivedIndexDescriptor:
    """Actual observed Qdrant store facts for one candidate physical collection.

    Deliberately absent: verification PASS/FAIL, activation state, rollback
    state, and the EXPECTED identity — none of those are measured from
    Qdrant, so none has a field here.

    `measured_state_fingerprint` excludes `measured_at`: two measurements of
    unchanged store state must yield the same measured-state identity, even
    though the measurement EVENTS happened at different times.
    """

    lifecycle_contract_version: str
    candidate_physical_collection: str
    vector_schema: VectorSchema
    reported_point_count: int
    enumerated_point_count: int
    measured_points: tuple[MeasuredPointDescriptor, ...]
    measured_at: str
    measurement_implementation_revision: str
    measured_state_fingerprint: str

    def __post_init__(self) -> None:
        _contract_version(self.lifecycle_contract_version)
        _shape_checked_text(self.candidate_physical_collection, "candidate_physical_collection")
        if not isinstance(self.vector_schema, VectorSchema):
            raise DerivedIndexLifecycleError("vector_schema must be a VectorSchema")
        _non_negative_int(self.reported_point_count, "reported_point_count")
        _non_negative_int(self.enumerated_point_count, "enumerated_point_count")

        if not isinstance(self.measured_points, tuple):
            raise DerivedIndexLifecycleError(
                "measured_points must be supplied as a tuple, "
                f"found {type(self.measured_points).__name__}"
            )
        for position, entry in enumerate(self.measured_points):
            if not isinstance(entry, MeasuredPointDescriptor):
                raise DerivedIndexLifecycleError(
                    f"measured_points[{position}] must be a MeasuredPointDescriptor, "
                    f"found {type(entry).__name__}"
                )
        ids = [entry.qdrant_point_id for entry in self.measured_points]
        if ids != sorted(ids):
            raise DerivedIndexLifecycleError(
                "measured_points must stand in canonical order (sorted by "
                "qdrant_point_id); pagination order carries no identity"
            )

        _rfc3339_utc(self.measured_at, "measured_at")
        _shape_checked_text(
            self.measurement_implementation_revision, "measurement_implementation_revision"
        )
        _sha256_hex(self.measured_state_fingerprint, "measured_state_fingerprint")

        measured = self._measure(
            lifecycle_contract_version=self.lifecycle_contract_version,
            candidate_physical_collection=self.candidate_physical_collection,
            vector_schema=self.vector_schema,
            reported_point_count=self.reported_point_count,
            enumerated_point_count=self.enumerated_point_count,
            measured_points=self.measured_points,
        )
        if measured != self.measured_state_fingerprint:
            raise DerivedIndexLifecycleError(
                "measured_state_fingerprint does not match the identity measured "
                f"from this descriptor's own fields: declared "
                f"{self.measured_state_fingerprint!r}, measured {measured!r}"
            )

    @staticmethod
    def _measure(
        *,
        lifecycle_contract_version: str,
        candidate_physical_collection: str,
        vector_schema: VectorSchema,
        reported_point_count: int,
        enumerated_point_count: int,
        measured_points: tuple[MeasuredPointDescriptor, ...],
    ) -> str:
        payload = {
            "lifecycle_contract_version": lifecycle_contract_version,
            "candidate_physical_collection": candidate_physical_collection,
            "vector_schema": vector_schema.canonical_mapping(),
            "reported_point_count": reported_point_count,
            "enumerated_point_count": enumerated_point_count,
            "measured_points": [entry.canonical_mapping() for entry in measured_points],
        }
        assert set(payload.keys()) == set(_MEASURED_STATE_PAYLOAD_KEYS)  # pragma: no cover
        return compute_fingerprint(payload)

    @classmethod
    def create(
        cls,
        *,
        candidate_physical_collection: str,
        vector_schema: VectorSchema,
        reported_point_count: int,
        enumerated_point_count: int,
        measured_points: tuple[MeasuredPointDescriptor, ...],
        measured_at: str,
        measurement_implementation_revision: str,
        lifecycle_contract_version: str = DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
    ) -> "MeasuredDerivedIndexDescriptor":
        ordered_points = tuple(
            sorted(measured_points, key=lambda entry: entry.qdrant_point_id)
        )
        fingerprint = cls._measure(
            lifecycle_contract_version=lifecycle_contract_version,
            candidate_physical_collection=candidate_physical_collection,
            vector_schema=vector_schema,
            reported_point_count=reported_point_count,
            enumerated_point_count=enumerated_point_count,
            measured_points=ordered_points,
        )
        return cls(
            lifecycle_contract_version=lifecycle_contract_version,
            candidate_physical_collection=candidate_physical_collection,
            vector_schema=vector_schema,
            reported_point_count=reported_point_count,
            enumerated_point_count=enumerated_point_count,
            measured_points=ordered_points,
            measured_at=measured_at,
            measurement_implementation_revision=measurement_implementation_revision,
            measured_state_fingerprint=fingerprint,
        )


# --------------------------------------------------------------------------- #
# structural verification
# --------------------------------------------------------------------------- #

_VERIFICATION_RECEIPT_PAYLOAD_KEYS: tuple[str, ...] = (
    "lifecycle_contract_version",
    "verification_scope",
    "expected_derived_index_fingerprint",
    "candidate_receipt_fingerprint",
    "measured_state_fingerprint",
    "status",
    "expected_record_count",
    "candidate_expected_record_count",
    "candidate_written_point_count",
    "qdrant_reported_point_count",
    "enumerated_point_count",
    "missing_document_ids",
    "unexpected_document_ids",
    "duplicate_document_ids",
    "missing_required_payload_details",
    "evidence_fingerprint_mismatches",
    "bindings_match",
    "schema_match",
    "embedding_execution_binding",
    "verified_at",
    "verifier_implementation_revision",
)


@dataclass(frozen=True, kw_only=True)
class VerificationReceipt:
    """Result of a PURE comparison of declared expectation against measured fact.

    `status` is `PASS` iff every one of `bindings_match`, `schema_match`, the
    four count equalities and the four empty mismatch/missing/unexpected/
    duplicate collections hold. `verification_scope` is always
    `STRUCTURAL_V0_1` at this version: record-set completeness, evidence
    fingerprint equality, vector-schema equality, and candidate/expected
    binding — never a claim of universal vector-byte reproduction.
    """

    lifecycle_contract_version: str
    verification_scope: str
    expected_derived_index_fingerprint: str
    candidate_receipt_fingerprint: str
    measured_state_fingerprint: str
    status: str
    expected_record_count: int
    candidate_expected_record_count: int
    candidate_written_point_count: int
    qdrant_reported_point_count: int
    enumerated_point_count: int
    missing_document_ids: tuple[str, ...]
    unexpected_document_ids: tuple[str, ...]
    duplicate_document_ids: tuple[str, ...]
    missing_required_payload_details: tuple[str, ...]
    evidence_fingerprint_mismatches: tuple[str, ...]
    bindings_match: bool
    schema_match: bool
    embedding_execution_binding: str
    verified_at: str
    verifier_implementation_revision: str
    verification_receipt_fingerprint: str

    def __post_init__(self) -> None:
        _contract_version(self.lifecycle_contract_version)
        _one_of(self.verification_scope, SUPPORTED_VERIFICATION_SCOPES, "verification_scope")
        _sha256_hex(self.expected_derived_index_fingerprint, "expected_derived_index_fingerprint")
        _sha256_hex(self.candidate_receipt_fingerprint, "candidate_receipt_fingerprint")
        _sha256_hex(self.measured_state_fingerprint, "measured_state_fingerprint")
        _one_of(self.status, SUPPORTED_VERIFICATION_STATUSES, "status")
        _positive_int(self.expected_record_count, "expected_record_count")
        _non_negative_int(self.candidate_expected_record_count, "candidate_expected_record_count")
        _non_negative_int(self.candidate_written_point_count, "candidate_written_point_count")
        _non_negative_int(self.qdrant_reported_point_count, "qdrant_reported_point_count")
        _non_negative_int(self.enumerated_point_count, "enumerated_point_count")
        _canonical_text_tuple(self.missing_document_ids, "missing_document_ids")
        _canonical_text_tuple(self.unexpected_document_ids, "unexpected_document_ids")
        _canonical_text_tuple(self.duplicate_document_ids, "duplicate_document_ids")
        _canonical_text_tuple(
            self.missing_required_payload_details, "missing_required_payload_details"
        )
        _canonical_text_tuple(
            self.evidence_fingerprint_mismatches, "evidence_fingerprint_mismatches"
        )
        if not isinstance(self.bindings_match, bool):
            raise DerivedIndexLifecycleError("bindings_match must be a bool")
        if not isinstance(self.schema_match, bool):
            raise DerivedIndexLifecycleError("schema_match must be a bool")
        _one_of(
            self.embedding_execution_binding,
            SUPPORTED_EMBEDDING_EXECUTION_BINDINGS,
            "embedding_execution_binding",
        )
        _rfc3339_utc(self.verified_at, "verified_at")
        _shape_checked_text(
            self.verifier_implementation_revision, "verifier_implementation_revision"
        )
        _sha256_hex(self.verification_receipt_fingerprint, "verification_receipt_fingerprint")

        computed_status = self._compute_status()
        if computed_status != self.status:
            raise DerivedIndexLifecycleError(
                f"status {self.status!r} does not match the outcome measured from this "
                f"receipt's own fields: measured {computed_status!r}"
            )

        measured = self._measure(**self._payload_fields())
        if measured != self.verification_receipt_fingerprint:
            raise DerivedIndexLifecycleError(
                "verification_receipt_fingerprint does not match the identity measured "
                f"from this receipt's own fields: declared "
                f"{self.verification_receipt_fingerprint!r}, measured {measured!r}"
            )

    def _compute_status(self) -> str:
        counts_match = (
            self.candidate_expected_record_count == self.expected_record_count
            and self.candidate_written_point_count == self.expected_record_count
            and self.qdrant_reported_point_count == self.expected_record_count
            and self.enumerated_point_count == self.expected_record_count
        )
        clean = (
            not self.missing_document_ids
            and not self.unexpected_document_ids
            and not self.duplicate_document_ids
            and not self.missing_required_payload_details
            and not self.evidence_fingerprint_mismatches
        )
        passed = self.bindings_match and self.schema_match and counts_match and clean
        return VERIFICATION_STATUS_PASS if passed else VERIFICATION_STATUS_FAIL

    def _payload_fields(self) -> dict[str, Any]:
        return {
            "lifecycle_contract_version": self.lifecycle_contract_version,
            "verification_scope": self.verification_scope,
            "expected_derived_index_fingerprint": self.expected_derived_index_fingerprint,
            "candidate_receipt_fingerprint": self.candidate_receipt_fingerprint,
            "measured_state_fingerprint": self.measured_state_fingerprint,
            "status": self.status,
            "expected_record_count": self.expected_record_count,
            "candidate_expected_record_count": self.candidate_expected_record_count,
            "candidate_written_point_count": self.candidate_written_point_count,
            "qdrant_reported_point_count": self.qdrant_reported_point_count,
            "enumerated_point_count": self.enumerated_point_count,
            "missing_document_ids": self.missing_document_ids,
            "unexpected_document_ids": self.unexpected_document_ids,
            "duplicate_document_ids": self.duplicate_document_ids,
            "missing_required_payload_details": self.missing_required_payload_details,
            "evidence_fingerprint_mismatches": self.evidence_fingerprint_mismatches,
            "bindings_match": self.bindings_match,
            "schema_match": self.schema_match,
            "embedding_execution_binding": self.embedding_execution_binding,
            "verified_at": self.verified_at,
            "verifier_implementation_revision": self.verifier_implementation_revision,
        }

    @staticmethod
    def _measure(**fields: Any) -> str:
        payload = dict(fields)
        payload["missing_document_ids"] = list(payload["missing_document_ids"])
        payload["unexpected_document_ids"] = list(payload["unexpected_document_ids"])
        payload["duplicate_document_ids"] = list(payload["duplicate_document_ids"])
        payload["missing_required_payload_details"] = list(
            payload["missing_required_payload_details"]
        )
        payload["evidence_fingerprint_mismatches"] = list(
            payload["evidence_fingerprint_mismatches"]
        )
        assert set(payload.keys()) == set(_VERIFICATION_RECEIPT_PAYLOAD_KEYS)  # pragma: no cover
        return compute_fingerprint(payload)

    @classmethod
    def create(
        cls,
        *,
        verification_scope: str,
        expected_derived_index_fingerprint: str,
        candidate_receipt_fingerprint: str,
        measured_state_fingerprint: str,
        expected_record_count: int,
        candidate_expected_record_count: int,
        candidate_written_point_count: int,
        qdrant_reported_point_count: int,
        enumerated_point_count: int,
        missing_document_ids: tuple[str, ...],
        unexpected_document_ids: tuple[str, ...],
        duplicate_document_ids: tuple[str, ...],
        missing_required_payload_details: tuple[str, ...],
        evidence_fingerprint_mismatches: tuple[str, ...],
        bindings_match: bool,
        schema_match: bool,
        embedding_execution_binding: str,
        verified_at: str,
        verifier_implementation_revision: str,
        lifecycle_contract_version: str = DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
    ) -> "VerificationReceipt":
        counts_match = (
            candidate_expected_record_count == expected_record_count
            and candidate_written_point_count == expected_record_count
            and qdrant_reported_point_count == expected_record_count
            and enumerated_point_count == expected_record_count
        )
        clean = (
            not missing_document_ids
            and not unexpected_document_ids
            and not duplicate_document_ids
            and not missing_required_payload_details
            and not evidence_fingerprint_mismatches
        )
        status = (
            VERIFICATION_STATUS_PASS
            if (bindings_match and schema_match and counts_match and clean)
            else VERIFICATION_STATUS_FAIL
        )
        fields = dict(
            lifecycle_contract_version=lifecycle_contract_version,
            verification_scope=verification_scope,
            expected_derived_index_fingerprint=expected_derived_index_fingerprint,
            candidate_receipt_fingerprint=candidate_receipt_fingerprint,
            measured_state_fingerprint=measured_state_fingerprint,
            status=status,
            expected_record_count=expected_record_count,
            candidate_expected_record_count=candidate_expected_record_count,
            candidate_written_point_count=candidate_written_point_count,
            qdrant_reported_point_count=qdrant_reported_point_count,
            enumerated_point_count=enumerated_point_count,
            missing_document_ids=missing_document_ids,
            unexpected_document_ids=unexpected_document_ids,
            duplicate_document_ids=duplicate_document_ids,
            missing_required_payload_details=missing_required_payload_details,
            evidence_fingerprint_mismatches=evidence_fingerprint_mismatches,
            bindings_match=bindings_match,
            schema_match=schema_match,
            embedding_execution_binding=embedding_execution_binding,
            verified_at=verified_at,
            verifier_implementation_revision=verifier_implementation_revision,
        )
        fingerprint = cls._measure(**fields)
        return cls(verification_receipt_fingerprint=fingerprint, **fields)


# --------------------------------------------------------------------------- #
# activation / rollback
# --------------------------------------------------------------------------- #

_ACTIVATION_RECEIPT_PAYLOAD_KEYS: tuple[str, ...] = (
    "lifecycle_contract_version",
    "logical_alias",
    "previous_active_collection",
    "new_active_collection",
    "expected_derived_index_fingerprint",
    "verification_receipt_fingerprint",
    "activation_method",
    "activated_at",
    "activator_implementation_revision",
)


@dataclass(frozen=True, kw_only=True)
class ActivationReceipt:
    """One bounded alias cutover. Never a build, a measurement or a verification.

    `previous_active_collection = None` marks a bootstrap activation (alias
    was absent); such a receipt cannot be rolled back (`activation.py`
    enforces this, since there is nothing to roll back to).
    """

    lifecycle_contract_version: str
    logical_alias: str
    previous_active_collection: str | None
    new_active_collection: str
    expected_derived_index_fingerprint: str
    verification_receipt_fingerprint: str
    activation_method: str
    activated_at: str
    activator_implementation_revision: str
    activation_receipt_fingerprint: str

    def __post_init__(self) -> None:
        _contract_version(self.lifecycle_contract_version)
        _shape_checked_text(self.logical_alias, "logical_alias")
        _optional_shape_checked_text(
            self.previous_active_collection, "previous_active_collection"
        )
        _shape_checked_text(self.new_active_collection, "new_active_collection")
        if self.previous_active_collection == self.new_active_collection:
            raise DerivedIndexLifecycleError(
                "new_active_collection must differ from previous_active_collection"
            )
        _sha256_hex(self.expected_derived_index_fingerprint, "expected_derived_index_fingerprint")
        _sha256_hex(self.verification_receipt_fingerprint, "verification_receipt_fingerprint")
        _one_of(self.activation_method, SUPPORTED_ACTIVATION_METHODS, "activation_method")
        if self.activation_method == ACTIVATION_METHOD_ALIAS_BOOTSTRAP_CREATE and (
            self.previous_active_collection is not None
        ):
            raise DerivedIndexLifecycleError(
                "a bootstrap activation must carry previous_active_collection = None"
            )
        if self.activation_method == ACTIVATION_METHOD_ALIAS_ATOMIC_CUTOVER and (
            self.previous_active_collection is None
        ):
            raise DerivedIndexLifecycleError(
                "an atomic-cutover activation must carry a previous_active_collection"
            )
        _rfc3339_utc(self.activated_at, "activated_at")
        _shape_checked_text(
            self.activator_implementation_revision, "activator_implementation_revision"
        )
        _sha256_hex(self.activation_receipt_fingerprint, "activation_receipt_fingerprint")

        measured = self._measure(
            lifecycle_contract_version=self.lifecycle_contract_version,
            logical_alias=self.logical_alias,
            previous_active_collection=self.previous_active_collection,
            new_active_collection=self.new_active_collection,
            expected_derived_index_fingerprint=self.expected_derived_index_fingerprint,
            verification_receipt_fingerprint=self.verification_receipt_fingerprint,
            activation_method=self.activation_method,
            activated_at=self.activated_at,
            activator_implementation_revision=self.activator_implementation_revision,
        )
        if measured != self.activation_receipt_fingerprint:
            raise DerivedIndexLifecycleError(
                "activation_receipt_fingerprint does not match the identity measured "
                f"from this receipt's own fields: declared "
                f"{self.activation_receipt_fingerprint!r}, measured {measured!r}"
            )

    @staticmethod
    def _measure(**fields: Any) -> str:
        payload = dict(fields)
        assert set(payload.keys()) == set(_ACTIVATION_RECEIPT_PAYLOAD_KEYS)  # pragma: no cover
        return compute_fingerprint(payload)

    @classmethod
    def create(
        cls,
        *,
        logical_alias: str,
        previous_active_collection: str | None,
        new_active_collection: str,
        expected_derived_index_fingerprint: str,
        verification_receipt_fingerprint: str,
        activation_method: str,
        activated_at: str,
        activator_implementation_revision: str,
        lifecycle_contract_version: str = DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
    ) -> "ActivationReceipt":
        fields = dict(
            lifecycle_contract_version=lifecycle_contract_version,
            logical_alias=logical_alias,
            previous_active_collection=previous_active_collection,
            new_active_collection=new_active_collection,
            expected_derived_index_fingerprint=expected_derived_index_fingerprint,
            verification_receipt_fingerprint=verification_receipt_fingerprint,
            activation_method=activation_method,
            activated_at=activated_at,
            activator_implementation_revision=activator_implementation_revision,
        )
        fingerprint = cls._measure(**fields)
        return cls(activation_receipt_fingerprint=fingerprint, **fields)


_ROLLBACK_RECEIPT_PAYLOAD_KEYS: tuple[str, ...] = (
    "lifecycle_contract_version",
    "logical_alias",
    "from_collection",
    "to_collection",
    "activation_receipt_fingerprint",
    "rolled_back_at",
    "rollback_implementation_revision",
    "result",
)


@dataclass(frozen=True, kw_only=True)
class RollbackReceipt:
    """One bounded alias cutover reversing exactly one `ActivationReceipt`.

    Never a rebuild, a re-embed or a deletion: it binds the
    `activation_receipt_fingerprint` it reverses so the reversal is
    traceable, and nothing else.
    """

    lifecycle_contract_version: str
    logical_alias: str
    from_collection: str
    to_collection: str
    activation_receipt_fingerprint: str
    rolled_back_at: str
    rollback_implementation_revision: str
    result: str
    rollback_receipt_fingerprint: str

    def __post_init__(self) -> None:
        _contract_version(self.lifecycle_contract_version)
        _shape_checked_text(self.logical_alias, "logical_alias")
        _shape_checked_text(self.from_collection, "from_collection")
        _shape_checked_text(self.to_collection, "to_collection")
        if self.from_collection == self.to_collection:
            raise DerivedIndexLifecycleError("from_collection must differ from to_collection")
        _sha256_hex(self.activation_receipt_fingerprint, "activation_receipt_fingerprint")
        _rfc3339_utc(self.rolled_back_at, "rolled_back_at")
        _shape_checked_text(
            self.rollback_implementation_revision, "rollback_implementation_revision"
        )
        _one_of(self.result, SUPPORTED_ROLLBACK_RESULTS, "result")
        _sha256_hex(self.rollback_receipt_fingerprint, "rollback_receipt_fingerprint")

        measured = self._measure(
            lifecycle_contract_version=self.lifecycle_contract_version,
            logical_alias=self.logical_alias,
            from_collection=self.from_collection,
            to_collection=self.to_collection,
            activation_receipt_fingerprint=self.activation_receipt_fingerprint,
            rolled_back_at=self.rolled_back_at,
            rollback_implementation_revision=self.rollback_implementation_revision,
            result=self.result,
        )
        if measured != self.rollback_receipt_fingerprint:
            raise DerivedIndexLifecycleError(
                "rollback_receipt_fingerprint does not match the identity measured "
                f"from this receipt's own fields: declared "
                f"{self.rollback_receipt_fingerprint!r}, measured {measured!r}"
            )

    @staticmethod
    def _measure(**fields: Any) -> str:
        payload = dict(fields)
        assert set(payload.keys()) == set(_ROLLBACK_RECEIPT_PAYLOAD_KEYS)  # pragma: no cover
        return compute_fingerprint(payload)

    @classmethod
    def create(
        cls,
        *,
        logical_alias: str,
        from_collection: str,
        to_collection: str,
        activation_receipt_fingerprint: str,
        rolled_back_at: str,
        rollback_implementation_revision: str,
        result: str = ROLLBACK_RESULT_ROLLED_BACK,
        lifecycle_contract_version: str = DERIVED_INDEX_LIFECYCLE_CONTRACT_VERSION,
    ) -> "RollbackReceipt":
        fields = dict(
            lifecycle_contract_version=lifecycle_contract_version,
            logical_alias=logical_alias,
            from_collection=from_collection,
            to_collection=to_collection,
            activation_receipt_fingerprint=activation_receipt_fingerprint,
            rolled_back_at=rolled_back_at,
            rollback_implementation_revision=rollback_implementation_revision,
            result=result,
        )
        fingerprint = cls._measure(**fields)
        return cls(rollback_receipt_fingerprint=fingerprint, **fields)
