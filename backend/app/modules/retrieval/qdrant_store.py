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
from ...core.models import Evidence
from ...core.ports import EmbeddingPort

# Fixed namespace -> deterministic, stable point IDs across re-ingestion.
_ID_NAMESPACE = uuid.UUID("6f9e3d2a-1c4b-4e8a-9f7d-2b5c8a1e0d33")

DEFAULT_UPSERT_BATCH_SIZE = 128


def point_id_for(document_id: str) -> str:
    """Deterministic Qdrant point ID for a document/chunk id."""
    return str(uuid.uuid5(_ID_NAMESPACE, str(document_id)))


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
        results: list[Evidence] = []
        for h in hits:
            p = h.payload or {}
            results.append(
                Evidence(
                    document_id=str(p.get("document_id", h.id)),
                    source_id=str(p.get("source_id", "unknown")),
                    title=str(p.get("title", "")),
                    content=str(p.get("content", "")),
                    score=float(h.score),
                    page=p.get("page"),
                    chunk_id=p.get("chunk_id"),
                    metadata={
                        k: p.get(k)
                        for k in ("checksum", "ingestion_version")
                        if p.get(k)
                    },
                )
            )
        return results
