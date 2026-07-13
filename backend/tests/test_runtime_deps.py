"""Deterministic runtime dependency / config tests for the local embedder.

These verify the *packaging contract* without downloading or executing any model
and without any provider call:

- `build_embedder` selects the configured backend and constructs the adapter
  lazily (no model download at construction).
- The approved local embedding runtime (sentence-transformers) is installed in the
  built image; when absent (e.g. the thin CI sandbox) the presence check SKIPS
  rather than failing, so the suite stays deterministic everywhere.
"""

from __future__ import annotations

import importlib.util
import unittest

from app.container import build_embedder
from app.core.config import Settings
from app.modules.retrieval.embeddings import HashingEmbedder, LocalEmbedder, OpenAIEmbedder


def test_build_embedder_selects_configured_backend_without_download():
    local = build_embedder(
        Settings.load({"EMBEDDING_BACKEND": "local",
                       "EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2"})
    )
    assert isinstance(local, LocalEmbedder)
    assert local._model is None                      # constructed lazily, no download
    assert hasattr(local, "embed")
    assert isinstance(type(local).dimension, property)  # not evaluated (would download)

    assert isinstance(build_embedder(Settings.load({"EMBEDDING_BACKEND": "fake"})), HashingEmbedder)
    assert isinstance(build_embedder(Settings.load({"EMBEDDING_BACKEND": "openai"})), OpenAIEmbedder)


def test_local_embedding_dependency_installed_in_image():
    if importlib.util.find_spec("sentence_transformers") is None:
        raise unittest.SkipTest(
            "sentence-transformers not installed here (must be present in the built Docker image)"
        )
    emb = build_embedder(Settings.load({"EMBEDDING_BACKEND": "local"}))
    assert isinstance(emb, LocalEmbedder)
    assert emb._model is None                        # instantiated without a model download
