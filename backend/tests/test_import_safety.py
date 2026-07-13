"""Importing the package must need no secrets and open no connections (docs/11)."""

from __future__ import annotations

import importlib


def test_core_and_modules_import_without_secrets():
    for mod in [
        "app",
        "app.core.config",
        "app.core.models",
        "app.core.ports",
        "app.core.orchestrator",
        "app.container",
        "app.modules.context_pack.builder",
        "app.modules.mive.comparator",
        "app.modules.renderer.renderer",
        "app.modules.telemetry.pricing",
        "app.modules.retrieval.memory_index",
        "app.modules.retrieval.qdrant_store",
        "app.modules.gemini_ive.adapter",
        "app.modules.openai_ive.adapter",
    ]:
        importlib.import_module(mod)


def test_hashing_embedder_is_dependency_light():
    from app.modules.retrieval.embeddings import HashingEmbedder

    emb = HashingEmbedder(dimension=64)
    vecs = emb.embed(["money is debt", "money is debt"])
    assert vecs[0] == vecs[1]  # deterministic
    assert emb.dimension == 64
