"""In-memory retrieval TEST DOUBLE (RetrievalPort).

Dependency-free (numpy only). Used by unit tests and local dev so the pipeline
runs with no Qdrant server. NOT a product vector store (ADR-005): the product
store is Qdrant. Same interface, so the core cannot tell the difference.
"""

from __future__ import annotations

import numpy as np

from ...core.models import Evidence
from ...core.ports import EmbeddingPort


class InMemoryRetrieval:
    def __init__(self, embedder: EmbeddingPort) -> None:
        self._embedder = embedder
        self._evidence: list[Evidence] = []
        self._matrix: np.ndarray | None = None

    def index(self, documents: list[dict]) -> int:
        """documents: dicts with document_id, source_id, title, content, page?, chunk_id?, metadata?."""
        contents = [d["content"] for d in documents]
        vectors = self._embedder.embed(contents) if contents else []
        self._evidence = [
            Evidence(
                document_id=str(d["document_id"]),
                source_id=str(d.get("source_id", d.get("source", "unknown"))),
                title=str(d.get("title", "")),
                content=str(d["content"]),
                score=0.0,
                page=d.get("page"),
                chunk_id=d.get("chunk_id"),
                metadata=dict(d.get("metadata", {})),
            )
            for d in documents
        ]
        self._matrix = np.array(vectors, dtype=np.float64) if vectors else None
        return len(self._evidence)

    def retrieve(self, question: str, top_k: int) -> list[Evidence]:
        if self._matrix is None or not self._evidence:
            return []
        qvec = np.array(self._embedder.embed([question])[0], dtype=np.float64)
        # vectors are L2-normalized by the embedder; guard anyway.
        qn = np.linalg.norm(qvec) or 1.0
        scores = (self._matrix @ qvec) / qn
        order = np.argsort(-scores)[: max(1, top_k)]
        results: list[Evidence] = []
        for i in order:
            e = self._evidence[int(i)]
            results.append(
                Evidence(
                    document_id=e.document_id,
                    source_id=e.source_id,
                    title=e.title,
                    content=e.content,
                    score=float(scores[int(i)]),
                    page=e.page,
                    chunk_id=e.chunk_id,
                    metadata=e.metadata,
                )
            )
        return results
