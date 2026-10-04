"""Qdrant retrieval adapter (RetrievalPort) — the product vector store (ADR-005).

Lazy-imports `qdrant_client` so importing this module needs no client/network.
Upserts are sent in deterministic, configurable batches to stay under Qdrant's
request-size limit. Point IDs are stable (uuid5 of document_id) so re-ingestion
is reproducible. Payload contract, collection name, dimension, chunking, and the
retrieval contract are unchanged.
"""

from __future__ import annotations

import uuid

from ...core.errors import RetrievalError
from ...core.models import (
    LEXICAL_STATUS_ADDED,
    LEXICAL_STATUS_NO_MATCH,
    LEXICAL_STATUS_NOT_TRIGGERED,
    LEXICAL_STATUS_UNAVAILABLE,
    RETRIEVAL_BRANCH_DENSE,
    RETRIEVAL_BRANCH_LEXICAL,
    Evidence,
    LexicalRetrievalOutcome,
)
from ...core.ports import EmbeddingPort
from .entity_lexical import (
    CacheEntry,
    LexicalCacheError,
    LexicalRuntimeCache,
    detect_entities,
    normalize_epistemic_role,
    rank_matches,
    select_matches,
)

# Fixed namespace -> deterministic, stable point IDs across re-ingestion.
_ID_NAMESPACE = uuid.UUID("6f9e3d2a-1c4b-4e8a-9f7d-2b5c8a1e0d33")

DEFAULT_UPSERT_BATCH_SIZE = 128


def point_id_for(document_id: str) -> str:
    """Deterministic Qdrant point ID for a document/chunk id."""
    return str(uuid.uuid5(_ID_NAMESPACE, str(document_id)))


_CANDIDATE_METADATA_KEYS = (
    "evidence_fingerprint",
    "evidence_fingerprint_algorithm",
    "evidence_fingerprint_profile_id",
    "ion_source_provenance",
    "ion_canonical_provenance",
)

_RETRIEVAL_METADATA_KEYS = (
    "checksum",
    "ingestion_version",
) + _CANDIDATE_METADATA_KEYS


def _candidate_metadata_payload(document: dict) -> dict:
    """Copy only pre-activation candidate metadata without reinterpretation."""

    return {
        key: document[key]
        for key in _CANDIDATE_METADATA_KEYS
        if key in document and document[key] is not None
    }


_LEXICAL_SCROLL_PAGE = 256


def evidence_from_payload(
    point_id, payload: dict | None, *, score: float | None,
    retrieval_branch: str = RETRIEVAL_BRANCH_DENSE,
) -> Evidence:
    """The ONE Evidence construction path for a stored point, dense or lexical."""
    p = payload or {}
    return Evidence(
        document_id=str(p.get("document_id", point_id)),
        source_id=str(p.get("source_id", "unknown")),
        title=str(p.get("title", "")),
        content=str(p.get("content", "")),
        score=score,
        page=p.get("page"),
        chunk_id=p.get("chunk_id"),
        metadata={
            k: p.get(k)
            for k in _RETRIEVAL_METADATA_KEYS
            if p.get(k)
        },
        retrieval_branch=retrieval_branch,
    )

class QdrantRetrieval:
    def __init__(
        self,
        embedder: EmbeddingPort,
        *,
        url: str,
        collection: str,
        api_key: str | None = None,
        upsert_batch_size: int = DEFAULT_UPSERT_BATCH_SIZE,
    ) -> None:
        if upsert_batch_size < 1:
            raise ValueError("upsert_batch_size must be >= 1")
        self._embedder = embedder
        self._url = url
        self._collection = collection
        self._api_key = api_key
        self._batch_size = upsert_batch_size
        self._client = None
        self._models = None
        # TW2-51 runtime cache: created on the first triggered lexical turn,
        # bound to this instance's one collection for the process lifetime.
        self._lexical_cache: LexicalRuntimeCache | None = None

    def _ensure_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient  # lazy
            from qdrant_client import models as qmodels  # lazy

            self._models = qmodels
            self._client = QdrantClient(url=self._url, api_key=self._api_key)
        return self._client

    def ensure_collection(self, *, recreate: bool = False) -> None:
        client = self._ensure_client()
        m = self._models
        exists = client.collection_exists(self._collection)
        if exists and recreate:
            client.delete_collection(self._collection)
            exists = False
        if not exists:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=m.VectorParams(
                    size=self._embedder.dimension, distance=m.Distance.COSINE
                ),
            )

    # -- write -------------------------------------------------------- #
    def _build_points(self, documents: list[dict]) -> list:
        m = self._models
        contents = [d["content"] for d in documents]
        vectors = self._embedder.embed(contents) if contents else []
        points = []
        for d, vec in zip(documents, vectors):
            points.append(
                m.PointStruct(
                    id=point_id_for(d["document_id"]),
                    vector=vec,
                    payload={
                        "document_id": str(d["document_id"]),
                        "source_id": str(d.get("source_id", "unknown")),
                        "title": str(d.get("title", "")),
                        "content": str(d["content"]),
                        "page": d.get("page"),
                        "chunk_id": d.get("chunk_id"),
                        "checksum": d.get("checksum"),
                        "ingestion_version": d.get("ingestion_version"),
                            **_candidate_metadata_payload(d),
                    },
                )
            )
        return points

    def _upsert_in_batches(self, client, points: list) -> int:
        """Upsert points in deterministic batches. No batch is silently skipped."""
        n = len(points)
        if n == 0:
            return 0
        bs = self._batch_size
        num_batches = (n + bs - 1) // bs
        total = 0
        for b in range(num_batches):
            start = b * bs
            end = min(start + bs, n)
            batch = points[start:end]
            try:
                client.upsert(collection_name=self._collection, points=batch)
            except Exception as exc:
                raise RetrievalError(
                    f"Qdrant upsert failed on batch {b + 1}/{num_batches} "
                    f"(batch_size={self._batch_size}, actual={len(batch)}, "
                    f"records {start}..{end - 1}, collection '{self._collection}'): {exc}",
                    stage="retrieval",
                ) from exc
            total += len(batch)
        return total

    def index(self, documents: list[dict]) -> int:
        client = self._ensure_client()
        self.ensure_collection()
        points = self._build_points(documents)
        return self._upsert_in_batches(client, points)

    def rebuild(self, documents: list[dict]) -> int:
        """Deterministic rebuild: drop + recreate the collection, then index."""
        self.ensure_collection(recreate=True)
        self._ensure_client()
        return self._upsert_in_batches(self._client, self._build_points(documents))

    def count(self) -> int:
        client = self._ensure_client()
        return int(client.count(collection_name=self._collection).count)

    # -- read (unchanged contract) ------------------------------------ #
    def retrieve(self, question: str, top_k: int) -> list[Evidence]:
        client = self._ensure_client()
        qvec = self._embedder.embed([question])[0]
        hits = client.query_points(
            collection_name=self._collection, query=qvec, limit=max(1, top_k)
        ).points
        return [
            evidence_from_payload(h.id, h.payload, score=float(h.score)) for h in hits
        ]

    # -- optional entity lexical branch (OP-DEC-20261004-TW2-51) -------- #
    # Read-only by construction: only count, scroll (unfiltered) and retrieve
    # by point id are called. No filter is sent, so the strict-mode
    # `unindexed_filtering_retrieve: false` setting is never exercised.
    def _lexical_cache_instance(self) -> LexicalRuntimeCache:
        if self._lexical_cache is None:
            self._lexical_cache = LexicalRuntimeCache(
                self._collection, self._load_lexical_entries
            )
        return self._lexical_cache

    def _load_lexical_entries(self) -> tuple[int, list[CacheEntry], int]:
        client = self._ensure_client()
        before = int(client.count(collection_name=self._collection, exact=True).count)
        entries: list[CacheEntry] = []
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=self._collection,
                limit=_LEXICAL_SCROLL_PAGE,
                offset=offset,
                with_payload=["document_id", "content", "ion_content_pack_lineage"],
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                entries.append(
                    CacheEntry(
                        point_id=str(point.id),
                        document_id=str(payload.get("document_id", point.id)),
                        content=str(payload.get("content", "")),
                        epistemic_role=normalize_epistemic_role(payload),
                    )
                )
            if offset is None:
                break
        after = int(client.count(collection_name=self._collection, exact=True).count)
        return before, entries, after

    def _materialize_by_id(self, point_ids: list[str]) -> list[Evidence]:
        client = self._ensure_client()
        records = client.retrieve(
            collection_name=self._collection,
            ids=point_ids,
            with_payload=True,
            with_vectors=False,
        )
        by_id = {str(r.id): r for r in records}
        missing = [pid for pid in point_ids if pid not in by_id]
        if missing:
            raise LexicalCacheError(f"nominated points not found by id: {len(missing)}")
        return [
            evidence_from_payload(
                by_id[pid].id, by_id[pid].payload, score=None,
                retrieval_branch=RETRIEVAL_BRANCH_LEXICAL,
            )
            for pid in point_ids
        ]

    def lexical_candidates(
        self, question: str, *, exclude_document_ids: tuple[str, ...] = (), limit: int = 3
    ) -> LexicalRetrievalOutcome:
        terms = detect_entities(question)
        if not terms:
            return LexicalRetrievalOutcome(status=LEXICAL_STATUS_NOT_TRIGGERED)
        term_text = tuple(t.full_form for t in terms)
        cache = self._lexical_cache_instance()
        try:
            snapshot = cache.snapshot()
        except LexicalCacheError:
            return LexicalRetrievalOutcome(
                status=LEXICAL_STATUS_UNAVAILABLE, terms=term_text,
                cache_collection=cache.collection,
            )
        if snapshot.collection != self._collection:  # never mix collections
            return LexicalRetrievalOutcome(
                status=LEXICAL_STATUS_UNAVAILABLE, terms=term_text,
                cache_collection=snapshot.collection,
            )
        matches = rank_matches(snapshot.entries, terms)
        selected = select_matches(
            matches, exclude_document_ids=exclude_document_ids, limit=limit
        )
        identity = {
            "terms": term_text,
            "candidate_count": len(matches),
            "cache_collection": snapshot.collection,
            "cache_fingerprint": snapshot.fingerprint,
        }
        if not selected:
            return LexicalRetrievalOutcome(status=LEXICAL_STATUS_NO_MATCH, **identity)
        try:
            evidence = self._materialize_by_id([m.point_id for m in selected])
        except Exception:
            return LexicalRetrievalOutcome(status=LEXICAL_STATUS_UNAVAILABLE, **identity)
        return LexicalRetrievalOutcome(
            status=LEXICAL_STATUS_ADDED, evidence=tuple(evidence), **identity
        )
