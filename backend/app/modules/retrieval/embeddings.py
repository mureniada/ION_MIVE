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
import math
import os
import re
import sys

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")

# E1 (VOE-LATENCY): PyTorch sizes its intra-op pool from the host's visible
# CPUs, not the container's cgroup quota. On staging that is 48 threads under an
# 8-CPU quota, which throttles a single query encode from ~9 ms to ~3 s. The cap
# changes only how many threads compute the SAME vector (bitwise identical at
# N=8 in the E1 A/B); model, tokenizer, precision and inputs are untouched.
EMBEDDING_NUM_THREADS_ENV = "EMBEDDING_NUM_THREADS"
_CGROUP_CPU_MAX = "/sys/fs/cgroup/cpu.max"


def cgroup_cpu_quota(cpu_max_path: str = _CGROUP_CPU_MAX) -> int | None:
    """Whole CPUs granted by a cgroup v2 `cpu.max` ("<quota> <period>"),
    rounded up; None when the file is absent, unparsable, or "max" (unlimited)."""
    try:
        fields = open(cpu_max_path, encoding="ascii").read().split()
    except OSError:
        return None
    if len(fields) != 2 or fields[0] == "max":
        return None
    try:
        quota, period = int(fields[0]), int(fields[1])
    except ValueError:
        return None
    if quota <= 0 or period <= 0:
        return None
    return max(1, math.ceil(quota / period))


def resolve_embedding_threads(
    env=None, cpu_max_path: str = _CGROUP_CPU_MAX, cpu_count: int | None = None
) -> tuple[int | None, str]:
    """Intra-op thread count for local embedding, and where it came from.

    1. A valid `EMBEDDING_NUM_THREADS` (integer >= 1) wins: source "override".
    2. Otherwise the cgroup quota, capped at the visible CPU count: "cgroup".
       An invalid override is ignored here (source "cgroup-invalid-override")
       rather than failing retrieval: it is a performance knob, not a gate.
    3. No finite quota: None ("unchanged") -- PyTorch keeps its own default.
    """
    env = os.environ if env is None else env
    raw = (env.get(EMBEDDING_NUM_THREADS_ENV) or "").strip()
    invalid_override = False
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value >= 1:
            return value, "override"
        invalid_override = True

    quota = cgroup_cpu_quota(cpu_max_path)
    if quota is None:
        return None, "unchanged-invalid-override" if invalid_override else "unchanged"
    visible = os.cpu_count() if cpu_count is None else cpu_count
    if visible:
        quota = min(quota, visible)
    return quota, "cgroup-invalid-override" if invalid_override else "cgroup"


def _apply_embedding_threads() -> None:
    """Set PyTorch's process-wide intra-op thread count once, before the first
    model load, and log the outcome once. Inter-op threads are left as they are."""
    import torch  # lazy: sentence-transformers already depends on it

    threads, source = resolve_embedding_threads()
    if threads is not None:
        torch.set_num_threads(threads)
    print(
        f"[embedding] intra_op_threads={torch.get_num_threads()} source={source} "
        f"interop_threads={torch.get_num_interop_threads()} "
        f"cgroup_quota={cgroup_cpu_quota()} visible_cpus={os.cpu_count()}",
        file=sys.stderr,
        flush=True,
    )


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

            _apply_embedding_threads()
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
