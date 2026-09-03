"""Candidate materialization and read-only measurement (E3 v0.1).

Covers the materialize-side proofs: candidate-must-not-already-exist,
candidate name cannot equal the active alias or the previous active physical
collection, the expected descriptor must be recomputed and match before any
write, a mismatch fails before any Qdrant write, the candidate build uses a
separate `QdrantRetrieval` (never `.rebuild()`), no collection deletion, the
expected/written count check, that the receipt binds expected fingerprint /
embedding profile / vector schema, and that the active alias is never
touched during build. Also covers `measure_candidate`: full pagination
consumption, pagination-order irrelevance, vectors never requested, reported
vs enumerated counts kept separate, unnamed-schema measurement, and
unsupported multi-named-vector shapes failing closed.

No real Qdrant, no Docker, no network anywhere in this module: every client
is a small in-memory fake injected through `materialize_candidate`'s /
`measure_candidate`'s explicit seams, the same pattern
`tests/test_qdrant_batching.py` already uses against `QdrantRetrieval`.
"""

from __future__ import annotations

import hashlib

from app.modules.content_engine import ContentBuildResult
from app.modules.derived_index import (
    BACKEND_FAKE,
    DISTANCE_COSINE,
    EmbeddingProfile,
    ExpectedDerivedIndexDescriptor,
    VectorSchema,
)
from app.modules.derived_index_lifecycle import DerivedIndexLifecycleError
from app.modules.derived_index_lifecycle.materialize import materialize_candidate, measure_candidate
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.evidence_fingerprint import ALGORITHM as EVIDENCE_FINGERPRINT_ALGORITHM
from app.modules.retrieval.evidence_fingerprint import PROFILE_ID as EVIDENCE_FINGERPRINT_PROFILE_ID
from tests.util import raises

CREATED_AT = "2026-09-03T09:00:00Z"
MATERIALIZED_AT = "2026-09-03T09:05:00Z"
MEASURED_AT = "2026-09-03T09:10:00Z"
PACK_FINGERPRINT = hashlib.sha256(b"pack").hexdigest()
DIMENSION = 8


def _fp(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _record(document_id: str) -> dict:
    return {
        "document_id": document_id,
        "source_id": "alpha",
        "source_version": "1.0.0",
        "title": "alpha",
        "content": f"content for {document_id} about money and debt",
        "page": None,
        "chunk_id": document_id,
        "checksum": _fp(f"checksum-{document_id}"),
        "ingestion_version": "v1",
        "evidence_fingerprint": _fp(document_id),
        "evidence_fingerprint_algorithm": EVIDENCE_FINGERPRINT_ALGORITHM,
        "evidence_fingerprint_profile_id": EVIDENCE_FINGERPRINT_PROFILE_ID,
        "ion_source_provenance": {"source_id": "alpha", "provenance_created_at": CREATED_AT},
        "ion_canonical_provenance": {"evidence_id": document_id},
    }


def _build_result(document_ids=("doc-1", "doc-2")) -> ContentBuildResult:
    return ContentBuildResult(
        content_engine_contract_version="0.1",
        content_engine_version="0.1",
        pack_id="ion_test_pack",
        pack_version="1.0.0",
        pack_canonical_fingerprint=PACK_FINGERPRINT,
        chunk_chars=1200,
        overlap=200,
        provenance_created_at=CREATED_AT,
        records=tuple(_record(d) for d in document_ids),
    )


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        backend=BACKEND_FAKE,
        model_name=None,
        model_revision=None,
        implementation_revision="ion-e3d-fake-impl-2026-09-03",
        dimension=DIMENSION,
        normalization_profile="L2_NORMALIZED_BY_ADAPTER",
    )


def _schema() -> VectorSchema:
    return VectorSchema(dimension=DIMENSION, distance_metric=DISTANCE_COSINE, vector_name=None)


def _expected(build=None) -> ExpectedDerivedIndexDescriptor:
    build = build or _build_result()
    return ExpectedDerivedIndexDescriptor.create(build, _profile(), _schema())


# --------------------------------------------------------------------------- #
# fake Qdrant client/models substrate — mirrors test_qdrant_batching.py
# --------------------------------------------------------------------------- #


class FakePointStruct:
    def __init__(self, id, vector, payload):
        self.id = id
        self.vector = vector
        self.payload = payload


class FakeDistance:
    COSINE = "COSINE"


class FakeModels:
    PointStruct = FakePointStruct
    Distance = FakeDistance

    class VectorParams:
        def __init__(self, size, distance):
            self.size = size
            self.distance = distance


class _Record:
    def __init__(self, id, payload):
        self.id = id
        self.payload = payload


class FakeVectorParams:
    def __init__(self, size, distance):
        self.size = size
        self.distance = distance


class _CollectionInfo:
    def __init__(self, *, points_count, vectors):
        self.points_count = points_count
        self.config = _Config(vectors)


class _Config:
    def __init__(self, vectors):
        self.params = _Params(vectors)


class _Params:
    def __init__(self, vectors):
        self.vectors = vectors


class FakeQdrantClient:
    """In-memory double covering exactly the surface materialize.py/measure use."""

    def __init__(self, *, existing_collections=None):
        self.collections: dict[str, list] = dict(existing_collections or {})
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.upsert_calls = 0

    def collection_exists(self, name):
        return name in self.collections

    def create_collection(self, collection_name, vectors_config):
        self.created.append(collection_name)
        self.collections[collection_name] = []
        self._vectors_config = getattr(self, "_vectors_config", {})
        self._vectors_config[collection_name] = vectors_config

    def delete_collection(self, name):
        self.deleted.append(name)
        self.collections.pop(name, None)

    def upsert(self, collection_name, points):
        self.upsert_calls += 1
        self.collections[collection_name].extend(points)

    def count(self, collection_name):
        class _C:
            pass

        c = _C()
        c.count = len(self.collections.get(collection_name, []))
        return c

    def get_collection(self, collection_name):
        vc = getattr(self, "_vectors_config", {}).get(
            collection_name, FakeVectorParams(DIMENSION, "COSINE")
        )
        return _CollectionInfo(
            points_count=len(self.collections.get(collection_name, [])), vectors=vc
        )

    def scroll(self, collection_name, with_payload, with_vectors, limit, offset):
        assert with_payload is True
        assert with_vectors is False
        points = self.collections.get(collection_name, [])
        start = offset or 0
        batch = points[start : start + limit]
        records = [_Record(id=p.id, payload=p.payload) for p in batch]
        next_offset = start + limit if start + limit < len(points) else None
        return records, next_offset


def _client_kwargs(client):
    return dict(qdrant_client=client, qdrant_models=FakeModels)


# --------------------------------------------------------------------------- #
# materialize_candidate
# --------------------------------------------------------------------------- #
def test_candidate_must_not_already_exist():
    client = FakeQdrantClient(existing_collections={"ion_candidate_blue": []})
    expected = _expected()
    with raises(DerivedIndexLifecycleError):
        materialize_candidate(
            content_build_result=_build_result(),
            expected_derived_index_descriptor=expected,
            embedding_profile=_profile(),
            vector_schema=_schema(),
            embedder=HashingEmbedder(DIMENSION),
            qdrant_url="http://fake",
            candidate_physical_collection="ion_candidate_blue",
            materialized_at=MATERIALIZED_AT,
            materializer_implementation_revision="ion-e3d-materializer-v0-1",
            **_client_kwargs(client),
        )
    assert client.upsert_calls == 0


def test_candidate_name_cannot_equal_active_alias():
    client = FakeQdrantClient()
    expected = _expected()
    with raises(DerivedIndexLifecycleError):
        materialize_candidate(
            content_build_result=_build_result(),
            expected_derived_index_descriptor=expected,
            embedding_profile=_profile(),
            vector_schema=_schema(),
            embedder=HashingEmbedder(DIMENSION),
            qdrant_url="http://fake",
            candidate_physical_collection="ion_retrieval_active",
            materialized_at=MATERIALIZED_AT,
            materializer_implementation_revision="ion-e3d-materializer-v0-1",
            active_alias="ion_retrieval_active",
            **_client_kwargs(client),
        )


def test_candidate_name_cannot_equal_previous_active_physical_collection():
    client = FakeQdrantClient()
    expected = _expected()
    with raises(DerivedIndexLifecycleError):
        materialize_candidate(
            content_build_result=_build_result(),
            expected_derived_index_descriptor=expected,
            embedding_profile=_profile(),
            vector_schema=_schema(),
            embedder=HashingEmbedder(DIMENSION),
            qdrant_url="http://fake",
            candidate_physical_collection="ion_candidate_blue",
            materialized_at=MATERIALIZED_AT,
            materializer_implementation_revision="ion-e3d-materializer-v0-1",
            previous_active_collection="ion_candidate_blue",
            **_client_kwargs(client),
        )


def test_recompute_mismatch_fails_before_any_qdrant_write():
    client = FakeQdrantClient()
    expected = _expected()
    other_build = _build_result(document_ids=("doc-9", "doc-10"))
    with raises(DerivedIndexLifecycleError):
        materialize_candidate(
            content_build_result=other_build,
            expected_derived_index_descriptor=expected,
            embedding_profile=_profile(),
            vector_schema=_schema(),
            embedder=HashingEmbedder(DIMENSION),
            qdrant_url="http://fake",
            candidate_physical_collection="ion_candidate_blue",
            materialized_at=MATERIALIZED_AT,
            materializer_implementation_revision="ion-e3d-materializer-v0-1",
            **_client_kwargs(client),
        )
    assert client.upsert_calls == 0
    assert client.created == []


def test_successful_materialization_uses_index_not_rebuild_and_binds_receipt():
    client = FakeQdrantClient()
    build = _build_result()
    expected = _expected(build)
    receipt = materialize_candidate(
        content_build_result=build,
        expected_derived_index_descriptor=expected,
        embedding_profile=_profile(),
        vector_schema=_schema(),
        embedder=HashingEmbedder(DIMENSION),
        qdrant_url="http://fake",
        candidate_physical_collection="ion_candidate_blue",
        materialized_at=MATERIALIZED_AT,
        materializer_implementation_revision="ion-e3d-materializer-v0-1",
        active_alias="ion_retrieval_active",
        **_client_kwargs(client),
    )
    assert client.deleted == []  # no rebuild, no deletion
    assert client.created == ["ion_candidate_blue"]
    assert receipt.written_point_count == 2
    assert receipt.expected_record_count == 2
    assert receipt.expected_derived_index_fingerprint == expected.derived_index_fingerprint
    assert receipt.embedding_profile == expected.embedding_profile
    assert receipt.vector_schema == expected.vector_schema
    assert receipt.success is True
    assert "ion_retrieval_active" not in client.collections  # active alias untouched


class _ShortEmbedder:
    """Wraps HashingEmbedder but drops one vector, simulating a write shortfall
    (`QdrantRetrieval._build_points` zips documents with vectors, so fewer
    vectors than documents silently yields fewer points than expected)."""

    def __init__(self, dimension):
        self._inner = HashingEmbedder(dimension)

    @property
    def dimension(self):
        return self._inner.dimension

    def embed(self, texts):
        vectors = self._inner.embed(texts)
        return vectors[:-1] if vectors else vectors


def test_write_count_mismatch_fails_and_produces_no_receipt():
    client = FakeQdrantClient()
    build = _build_result()
    expected = _expected(build)
    with raises(DerivedIndexLifecycleError):
        materialize_candidate(
            content_build_result=build,
            expected_derived_index_descriptor=expected,
            embedding_profile=_profile(),
            vector_schema=_schema(),
            embedder=_ShortEmbedder(DIMENSION),
            qdrant_url="http://fake",
            candidate_physical_collection="ion_candidate_blue",
            materialized_at=MATERIALIZED_AT,
            materializer_implementation_revision="ion-e3d-materializer-v0-1",
            **_client_kwargs(client),
        )


def test_paired_client_and_models_required_together():
    build = _build_result()
    expected = _expected(build)
    client = FakeQdrantClient()
    with raises(DerivedIndexLifecycleError):
        materialize_candidate(
            content_build_result=build,
            expected_derived_index_descriptor=expected,
            embedding_profile=_profile(),
            vector_schema=_schema(),
            embedder=HashingEmbedder(DIMENSION),
            qdrant_url="http://fake",
            candidate_physical_collection="ion_candidate_blue",
            materialized_at=MATERIALIZED_AT,
            materializer_implementation_revision="ion-e3d-materializer-v0-1",
            qdrant_client=client,
            qdrant_models=None,
        )


def test_empty_candidate_collection_name_fails_closed():
    build = _build_result()
    expected = _expected(build)
    client = FakeQdrantClient()
    with raises(DerivedIndexLifecycleError):
        materialize_candidate(
            content_build_result=build,
            expected_derived_index_descriptor=expected,
            embedding_profile=_profile(),
            vector_schema=_schema(),
            embedder=HashingEmbedder(DIMENSION),
            qdrant_url="http://fake",
            candidate_physical_collection="",
            materialized_at=MATERIALIZED_AT,
            materializer_implementation_revision="ion-e3d-materializer-v0-1",
            **_client_kwargs(client),
        )


# --------------------------------------------------------------------------- #
# measure_candidate
# --------------------------------------------------------------------------- #
def _seed_measured_collection(client, name, n=5):
    client.collections[name] = []
    client.create_collection(name, FakeVectorParams(DIMENSION, "COSINE"))
    points = [
        FakePointStruct(
            id=f"pt-{i}",
            vector=[0.0] * DIMENSION,
            payload={"document_id": f"doc-{i}", "evidence_fingerprint": _fp(f"doc-{i}")},
        )
        for i in range(n)
    ]
    client.collections[name] = points
    return points


def test_measurement_consumes_full_pagination():
    client = FakeQdrantClient()
    _seed_measured_collection(client, "ion_candidate_blue", n=5)
    descriptor = measure_candidate(
        candidate_physical_collection="ion_candidate_blue",
        measured_at=MEASURED_AT,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
        qdrant_client=client,
        scroll_page_size=2,
    )
    assert descriptor.enumerated_point_count == 5
    assert descriptor.reported_point_count == 5
    assert len(descriptor.measured_points) == 5


def test_measurement_pagination_order_is_irrelevant():
    client_a = FakeQdrantClient()
    _seed_measured_collection(client_a, "ion_candidate_blue", n=4)
    a = measure_candidate(
        candidate_physical_collection="ion_candidate_blue",
        measured_at=MEASURED_AT,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
        qdrant_client=client_a,
        scroll_page_size=1,
    )
    client_b = FakeQdrantClient()
    _seed_measured_collection(client_b, "ion_candidate_blue", n=4)
    b = measure_candidate(
        candidate_physical_collection="ion_candidate_blue",
        measured_at=MEASURED_AT,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
        qdrant_client=client_b,
        scroll_page_size=100,
    )
    assert a.measured_state_fingerprint == b.measured_state_fingerprint


def test_measurement_never_requests_vectors():
    client = FakeQdrantClient()
    _seed_measured_collection(client, "ion_candidate_blue", n=2)
    # FakeQdrantClient.scroll asserts with_vectors is False; a passing run is the proof.
    measure_candidate(
        candidate_physical_collection="ion_candidate_blue",
        measured_at=MEASURED_AT,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
        qdrant_client=client,
    )


def test_reported_and_enumerated_counts_kept_separate_on_mismatch():
    class MiscountingClient(FakeQdrantClient):
        def get_collection(self, collection_name):
            info = super().get_collection(collection_name)
            info.points_count = 999
            return info

    miscounting = MiscountingClient()
    _seed_measured_collection(miscounting, "ion_candidate_blue", n=3)
    descriptor = measure_candidate(
        candidate_physical_collection="ion_candidate_blue",
        measured_at=MEASURED_AT,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
        qdrant_client=miscounting,
    )
    assert descriptor.reported_point_count == 999
    assert descriptor.enumerated_point_count == 3
    assert descriptor.reported_point_count != descriptor.enumerated_point_count


def test_unnamed_vector_schema_measured_correctly():
    client = FakeQdrantClient()
    _seed_measured_collection(client, "ion_candidate_blue", n=1)
    descriptor = measure_candidate(
        candidate_physical_collection="ion_candidate_blue",
        measured_at=MEASURED_AT,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
        qdrant_client=client,
    )
    assert descriptor.vector_schema.vector_name is None
    assert descriptor.vector_schema.dimension == DIMENSION
    assert descriptor.vector_schema.distance_metric == DISTANCE_COSINE


def test_multiple_named_vectors_fail_closed():
    client = FakeQdrantClient()
    _seed_measured_collection(client, "ion_candidate_blue", n=1)
    client._vectors_config["ion_candidate_blue"] = {
        "dense": FakeVectorParams(DIMENSION, "COSINE"),
        "sparse": FakeVectorParams(DIMENSION, "COSINE"),
    }
    with raises(DerivedIndexLifecycleError):
        measure_candidate(
            candidate_physical_collection="ion_candidate_blue",
            measured_at=MEASURED_AT,
            measurement_implementation_revision="ion-e3d-measurer-v0-1",
            qdrant_client=client,
        )


def test_measurement_performs_no_write():
    client = FakeQdrantClient()
    _seed_measured_collection(client, "ion_candidate_blue", n=2)
    created_before, deleted_before = list(client.created), list(client.deleted)
    measure_candidate(
        candidate_physical_collection="ion_candidate_blue",
        measured_at=MEASURED_AT,
        measurement_implementation_revision="ion-e3d-measurer-v0-1",
        qdrant_client=client,
    )
    assert client.upsert_calls == 0
    assert client.created == created_before  # measurement created nothing new
    assert client.deleted == deleted_before  # measurement deleted nothing
