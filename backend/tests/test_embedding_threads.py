"""E1 (VOE-LATENCY): local-embedding intra-op thread selection.

Deterministic, no model download, no torch required: the resolver is pure and
the LocalEmbedder wiring is checked with a fake sentence-transformers module.
"""

from __future__ import annotations

import os
import sys
import tempfile
import types

from app.modules.retrieval import embeddings as emb


def _cpu_max(text: str) -> str:
    fd, path = tempfile.mkstemp()
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(text)
    return path


def test_finite_quota_selects_quota():
    path = _cpu_max("800000 100000\n")
    assert emb.cgroup_cpu_quota(path) == 8
    assert emb.resolve_embedding_threads({}, path, cpu_count=48) == (8, "cgroup")


def test_fractional_quota_rounds_up_and_minimum_is_one():
    assert emb.cgroup_cpu_quota(_cpu_max("150000 100000")) == 2
    assert emb.cgroup_cpu_quota(_cpu_max("1000 100000")) == 1


def test_quota_is_capped_at_visible_cpus():
    path = _cpu_max("800000 100000")
    assert emb.resolve_embedding_threads({}, path, cpu_count=4) == (4, "cgroup")


def test_unlimited_quota_leaves_torch_default():
    path = _cpu_max("max 100000")
    assert emb.cgroup_cpu_quota(path) is None
    assert emb.resolve_embedding_threads({}, path, cpu_count=48) == (None, "unchanged")


def test_missing_or_malformed_cpu_max_leaves_torch_default():
    assert emb.resolve_embedding_threads({}, "/nonexistent/cpu.max", cpu_count=48) == (
        None, "unchanged",
    )
    for text in ("", "garbage", "800000", "a b", "0 100000", "800000 0"):
        assert emb.cgroup_cpu_quota(_cpu_max(text)) is None, text


def test_explicit_override_wins_over_quota():
    path = _cpu_max("800000 100000")
    env = {emb.EMBEDDING_NUM_THREADS_ENV: " 4 "}
    assert emb.resolve_embedding_threads(env, path, cpu_count=48) == (4, "override")
    env = {emb.EMBEDDING_NUM_THREADS_ENV: "2"}
    assert emb.resolve_embedding_threads(env, "/nonexistent", cpu_count=48) == (2, "override")


def test_invalid_override_falls_back_to_quota():
    path = _cpu_max("800000 100000")
    for bad in ("0", "-3", "eight", "8.5"):
        env = {emb.EMBEDDING_NUM_THREADS_ENV: bad}
        assert emb.resolve_embedding_threads(env, path, cpu_count=48) == (
            8, "cgroup-invalid-override",
        ), bad


def test_invalid_override_without_quota_leaves_torch_default():
    env = {emb.EMBEDDING_NUM_THREADS_ENV: "zero"}
    assert emb.resolve_embedding_threads(env, "/nonexistent", cpu_count=48) == (
        None, "unchanged-invalid-override",
    )


def test_empty_override_is_treated_as_unset():
    path = _cpu_max("800000 100000")
    env = {emb.EMBEDDING_NUM_THREADS_ENV: "   "}
    assert emb.resolve_embedding_threads(env, path, cpu_count=48) == (8, "cgroup")


def test_local_embedder_applies_threads_once_before_model_load():
    calls: list[str] = []

    class FakeModel:
        def __init__(self, name):
            calls.append(f"load:{name}")

        def get_sentence_embedding_dimension(self):
            return 3

        def encode(self, texts, normalize_embeddings):
            assert normalize_embeddings is True
            return [[1.0, 0.0, 0.0] for _ in texts]

    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = FakeModel
    saved_module = sys.modules.get("sentence_transformers")
    saved_apply = emb._apply_embedding_threads
    sys.modules["sentence_transformers"] = fake_st
    emb._apply_embedding_threads = lambda: calls.append("threads")
    try:
        e = emb.LocalEmbedder("some-model")
        assert e.embed(["q"]) == [[1.0, 0.0, 0.0]]
        assert e.dimension == 3
        e.embed(["q2"])
    finally:
        emb._apply_embedding_threads = saved_apply
        if saved_module is None:
            sys.modules.pop("sentence_transformers", None)
        else:
            sys.modules["sentence_transformers"] = saved_module
    assert calls == ["threads", "load:some-model"]
