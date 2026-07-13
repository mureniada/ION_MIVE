"""Embedding adapters (EmbeddingPort).

- `HashingEmbedder`  : deterministic, dependency-free (numpy). Used by tests and
                       as a zero-cost default so retrieval never needs an API call.
- `LocalEmbedder`    : real local model via sentence-transformers (lazy import).
- `OpenAIEmbedder`   : real provider embeddings via the OpenAI SDK (lazy import).

Choice is config-driven (`EMBEDDING_BACKEND`). Only the reasoning IVE calls must
cost money; retrieval can stay fully local.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class HashingEmbedder:
    """Deterministic hashing vectorizer. Shared vocabulary -> higher cosine."""

    def __init__(self, dimension: int = 256) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = np.zeros(self._dim, dtype=np.float64)
            for tok in _tokens(text):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                idx = h % self._dim
                sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
                vec[idx] += sign
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            out.append(vec.tolist())
        return out


class LocalEmbedder:
    """Real local embeddings. Lazy-imports sentence-transformers on first use."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None
        self._dim: int | None = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # lazy

            self._model = SentenceTransformer(self._model_name)
            self._dim = int(self._model.get_sentence_embedding_dimension())
        return self._model

    @property
    def dimension(self) -> int:
        self._ensure()
        assert self._dim is not None
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]


class OpenAIEmbedder:
    """Real provider embeddings. Lazy-imports the OpenAI SDK; costs money.

    Not used by tests or by default. Requires OPENAI_API_KEY at call time.
    """

    _DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}

    def __init__(self, model_name: str = "text-embedding-3-small") -> None:
        self._model_name = model_name
        self._client = None

    def _ensure(self):
        if self._client is None:
            from openai import OpenAI  # lazy

            self._client = OpenAI()  # reads OPENAI_API_KEY from env at call time
        return self._client

    @property
    def dimension(self) -> int:
        return self._DIMS.get(self._model_name, 1536)

    def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._ensure()
        resp = client.embeddings.create(model=self._model_name, input=texts)
        return [list(d.embedding) for d in resp.data]
