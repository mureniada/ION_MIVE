"""Compose-contract tests for the persistent embedding cache (M8.1).

Deterministic, no live provider calls. They read docker-compose.yml (found via
ION_COMPOSE_FILE, /app/docker-compose.yml inside the image, or by walking up from
this file) and assert the cache wiring without changing any runtime behavior.
"""

from __future__ import annotations

import os
import pathlib
import unittest


def _find_compose() -> pathlib.Path | None:
    env = os.environ.get("ION_COMPOSE_FILE")
    if env and pathlib.Path(env).is_file():
        return pathlib.Path(env)
    candidates = [pathlib.Path("/app/docker-compose.yml")]
    candidates += [p / "docker-compose.yml" for p in pathlib.Path(__file__).resolve().parents]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _compose_text() -> str:
    c = _find_compose()
    if c is None:
        raise unittest.SkipTest("docker-compose.yml not found in this environment")
    return c.read_text(encoding="utf-8")


def test_backend_mounts_hf_cache_volume():
    assert "hf_cache:/root/.cache/huggingface" in _compose_text()


def test_hf_home_is_set():
    t = _compose_text()
    assert "HF_HOME:" in t and "/root/.cache/huggingface" in t


def test_transformers_cache_is_set():
    t = _compose_text()
    assert "TRANSFORMERS_CACHE:" in t and "/root/.cache/huggingface/transformers" in t


def test_sentence_transformers_home_is_set():
    t = _compose_text()
    assert "SENTENCE_TRANSFORMERS_HOME:" in t
    assert "/root/.cache/huggingface/sentence-transformers" in t


def test_hf_cache_named_volume_declared():
    t = _compose_text()
    # declared under the top-level volumes: block
    vol_block = t.split("\nvolumes:", 1)
    assert len(vol_block) == 2 and "hf_cache:" in vol_block[1]


def test_qdrant_storage_unchanged():
    t = _compose_text()
    assert "qdrant_storage:/qdrant/storage" in t          # still mounted by qdrant
    assert "qdrant_storage:" in t.split("\nvolumes:", 1)[1]  # still declared


def test_corpus_source_remains_read_only():
    assert "./corpus/source:/app/corpus/source:ro" in _compose_text()
