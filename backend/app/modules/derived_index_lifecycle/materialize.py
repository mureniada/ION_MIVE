"""Candidate materialization and read-only Qdrant measurement (E3 v0.1).

Two functions live here, not one, because they are the two halves of "what did
the candidate physical collection actually end up holding":

    `materialize_candidate` — WRITES. Builds one fresh candidate physical
    collection via `QdrantRetrieval.index()` (never `.rebuild()`) and returns
    a `CandidateMaterializationReceipt`.

    `measure_candidate` — READS ONLY. Observes an existing candidate physical
    collection through `get_collection` + `scroll` and returns a
    `MeasuredDerivedIndexDescriptor`. No Qdrant write of any kind.

Both are kept in this one file, distinct from `verify.py`, because both touch
Qdrant and both concern the candidate's physical state; `verify.py` touches
neither and is a pure comparison of what these two functions produced.

    BUILD != MEASURE != VERIFY

`qdrant_client` / `qdrant_models` are injectable seams (the same pattern
`tests/test_qdrant_batching.py` already uses against `QdrantRetrieval`): pass
fakes in tests, omit them in production to let `QdrantRetrieval` lazily
construct the real client. `qdrant_store.py` and `RetrievalPort` are reused
verbatim; neither is modified.
"""

from __future__ import annotations

from typing import Any

from ..derived_index import EmbeddingProfile, ExpectedDerivedIndexDescriptor, VectorSchema
from ..retrieval.qdrant_store import QdrantRetrieval
from .models import (
    EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY,
    CandidateMaterializationReceipt,
    DerivedIndexLifecycleError,
    MeasuredDerivedIndexDescriptor,
    MeasuredPointDescriptor,
)

__all__ = ["materialize_candidate", "measure_candidate"]


def _require_clean_collection_name(
    name: Any,
    *,
    active_alias: str | None,
    previous_active_collection: str | None,
) -> str:
    if not isinstance(name, str) or not name:
        raise DerivedIndexLifecycleError(
            f"candidate_physical_collection must be a non-empty string, found {name!r}"
        )
    if name != name.strip():
        raise DerivedIndexLifecycleError(
            f"candidate_physical_collection must carry no leading/trailing whitespace, "
            f"found {name!r}"
        )
    if active_alias is not None and name == active_alias:
        raise DerivedIndexLifecycleError(
            "candidate_physical_collection must not equal the active logical alias "
            f"{active_alias!r}: the active alias address is not a candidate build target"
        )
    if previous_active_collection is not None and name == previous_active_collection:
        raise DerivedIndexLifecycleError(
            "candidate_physical_collection must not equal the previous active physical "
            f"collection {previous_active_collection!r}"
        )
    return name


def materialize_candidate(
    *,
    content_build_result: Any,
    expected_derived_index_descriptor: ExpectedDerivedIndexDescriptor,
    embedding_profile: EmbeddingProfile,
    vector_schema: VectorSchema,
    embedder: Any,
    qdrant_url: str,
    candidate_physical_collection: str,
    materialized_at: str,
    materializer_implementation_revision: str,
    active_alias: str | None = None,
    previous_active_collection: str | None = None,
    qdrant_client: Any = None,
    qdrant_models: Any = None,
) -> CandidateMaterializationReceipt:
    """Build exactly one fresh candidate physical collection.

    Fails closed, before any Qdrant write, unless:
      * `candidate_physical_collection` is clean and collides with neither
        `active_alias` nor `previous_active_collection`;
      * recomputing `ExpectedDerivedIndexDescriptor` from `content_build_result`
        + `embedding_profile` + `vector_schema` yields the same
        `derived_index_fingerprint` already carried by
        `expected_derived_index_descriptor` (this is what stops an unrelated
        build from being materialized under a borrowed expected descriptor);
      * the candidate physical collection does not already exist.

    Never calls `QdrantRetrieval.rebuild()` and never deletes a collection.
    `written_point_count != expected_record_count` raises — no
    `CandidateMaterializationReceipt` is ever returned for a build that did
    not write exactly what was expected (there is no "failed" receipt).
    """
    _require_clean_collection_name(
        candidate_physical_collection,
        active_alias=active_alias,
        previous_active_collection=previous_active_collection,
    )

    try:
        recomputed = ExpectedDerivedIndexDescriptor.create(
            content_build_result, embedding_profile, vector_schema
        )
    except Exception as exc:  # noqa: BLE001 - re-raised closed, not swallowed
        raise DerivedIndexLifecycleError(
            f"content_build_result could not be recomputed into an expected derived-index "
            f"descriptor: {exc}"
        ) from exc

    if recomputed.derived_index_fingerprint != expected_derived_index_descriptor.derived_index_fingerprint:
        raise DerivedIndexLifecycleError(
            "recomputed expected derived-index fingerprint does not match the supplied "
            "descriptor: declared "
            f"{expected_derived_index_descriptor.derived_index_fingerprint!r}, recomputed "
            f"{recomputed.derived_index_fingerprint!r}. Refusing to materialize an unrelated "
            "build under a borrowed expected descriptor."
        )

    if (qdrant_client is None) != (qdrant_models is None):
        raise DerivedIndexLifecycleError(
            "qdrant_client and qdrant_models must be supplied together or not at all"
        )

    retrieval = QdrantRetrieval(embedder, url=qdrant_url, collection=candidate_physical_collection)
    if qdrant_client is not None:
        retrieval._client = qdrant_client  # injected seam, same pattern as test_qdrant_batching.py
        retrieval._models = qdrant_models
        client = qdrant_client
    else:
        client = retrieval._ensure_client()

    if client.collection_exists(candidate_physical_collection):
        raise DerivedIndexLifecycleError(
            f"candidate physical collection {candidate_physical_collection!r} already "
            "exists; a fresh blue/green candidate must not collide with an existing "
            "collection, and E3D never deletes one to make room"
        )

    documents = list(content_build_result.records)
    written_point_count = retrieval.index(documents)

    expected_record_count = expected_derived_index_descriptor.record_count
    if written_point_count != expected_record_count:
        raise DerivedIndexLifecycleError(
            f"candidate materialization wrote {written_point_count} point(s) but "
            f"{expected_record_count} were expected; this is a build failure and no "
            "success receipt is produced"
        )

    return CandidateMaterializationReceipt.create(
        expected_derived_index_fingerprint=expected_derived_index_descriptor.derived_index_fingerprint,
        candidate_physical_collection=candidate_physical_collection,
        embedding_profile=embedding_profile,
        vector_schema=vector_schema,
        expected_record_count=expected_record_count,
        written_point_count=written_point_count,
        materialized_at=materialized_at,
        materializer_implementation_revision=materializer_implementation_revision,
        embedding_execution_binding=EMBEDDING_EXECUTION_BINDING_DECLARED_ONLY,
    )


def _measured_vector_schema(collection_info: Any) -> VectorSchema:
    vectors = collection_info.config.params.vectors
    if vectors is None:
        raise DerivedIndexLifecycleError(
            "measured collection carries no vectors configuration; unsupported store shape"
        )
    if isinstance(vectors, dict):
        if len(vectors) != 1:
            raise DerivedIndexLifecycleError(
                f"measured collection carries {len(vectors)} named vector(s); this "
                "implementation supports at most the single currently-proven vector "
                "shape and fails closed rather than choosing one"
            )
        (vector_name, params), = vectors.items()
    else:
        vector_name, params = None, vectors

    distance = getattr(params.distance, "name", params.distance)
    try:
        return VectorSchema(dimension=params.size, distance_metric=distance, vector_name=vector_name)
    except Exception as exc:  # noqa: BLE001 - re-raised closed, not swallowed
        raise DerivedIndexLifecycleError(f"measured vector schema is unsupported: {exc}") from exc


def _measured_point(record: Any) -> MeasuredPointDescriptor:
    payload = record.payload or {}
    raw_document_id = payload.get("document_id")
    document_id = raw_document_id if isinstance(raw_document_id, str) else None
    raw_evidence_fingerprint = payload.get("evidence_fingerprint")
    evidence_fingerprint = (
        raw_evidence_fingerprint if isinstance(raw_evidence_fingerprint, str) else None
    )
    return MeasuredPointDescriptor(
        qdrant_point_id=str(record.id),
        document_id=document_id,
        evidence_fingerprint=evidence_fingerprint,
    )


def measure_candidate(
    *,
    candidate_physical_collection: str,
    measured_at: str,
    measurement_implementation_revision: str,
    qdrant_client: Any,
    scroll_page_size: int = 256,
) -> MeasuredDerivedIndexDescriptor:
    """Read-only observation of one candidate physical collection.

    Uses only `get_collection` and `scroll` (`with_payload=True`,
    `with_vectors=False`); no vector bytes are required for
    `STRUCTURAL_V0_1` verification. Pagination is fully consumed and its
    order is discarded — `MeasuredDerivedIndexDescriptor.create` re-sorts by
    `qdrant_point_id` before binding, so pagination order carries no
    identity. Performs no Qdrant write.
    """
    if not isinstance(candidate_physical_collection, str) or not candidate_physical_collection:
        raise DerivedIndexLifecycleError(
            "candidate_physical_collection must be a non-empty string, found "
            f"{candidate_physical_collection!r}"
        )

    info = qdrant_client.get_collection(candidate_physical_collection)
    vector_schema = _measured_vector_schema(info)

    reported_point_count = info.points_count
    if not isinstance(reported_point_count, int) or isinstance(reported_point_count, bool):
        raise DerivedIndexLifecycleError(
            f"measured collection reports a non-integer points_count: {reported_point_count!r}"
        )

    records: list[Any] = []
    offset = None
    while True:
        batch, next_offset = qdrant_client.scroll(
            collection_name=candidate_physical_collection,
            with_payload=True,
            with_vectors=False,
            limit=scroll_page_size,
            offset=offset,
        )
        records.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    measured_points = tuple(_measured_point(record) for record in records)

    return MeasuredDerivedIndexDescriptor.create(
        candidate_physical_collection=candidate_physical_collection,
        vector_schema=vector_schema,
        reported_point_count=reported_point_count,
        enumerated_point_count=len(measured_points),
        measured_points=measured_points,
        measured_at=measured_at,
        measurement_implementation_revision=measurement_implementation_revision,
    )
