"""Qdrant retrieval adapter (RetrievalPort) — the product vector store (ADR-005).

Lazy-imports `qdrant_client` so importing this module needs no client/network.
Deployment: Qdrant runs as its own Docker Compose service; this adapter connects
over `VECTOR_STORE_URL`. Payload contract mirrors docs/CORPUS_REGISTER expectations:
document_id, source_id, title, content, page, chunk_id, checksum, ingestion_version.
"""

from __future__ import annotations

import uuid

from ...core.models import Evidence
from ...core.ports import EmbeddingPort


class QdrantRetrieval:
    def __init__(
        self,
        embedder: EmbeddingPort,
        *,
        url: str,
        collection: str,
        api_key: str | None = None,
    ) -> None:
        self._embedder = embedder
        self._url = url
        self._collection = collection
        self._api_key = api_key
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

    def index(self, documents: list[dict]) -> int:
        client = self._ensure_client()
        m = self._models
        self.ensure_collection()
        contents = [d["content"] for d in documents]
        vectors = self._embedder.embed(contents) if contents else []
        points = []
        for d, vec in zip(documents, vectors):
            points.append(
                m.PointStruct(
                    id=str(uuid.uuid4()),
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
        if points:
            client.upsert(collection_name=self._collection, points=points)
        return len(points)

    def rebuild(self, documents: list[dict]) -> int:
        """Deterministic rebuild: drop + recreate the collection, then index."""
        self.ensure_collection(recreate=True)
        return self.index(documents)

    def count(self) -> int:
        client = self._ensure_client()
        return int(client.count(collection_name=self._collection).count)

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
