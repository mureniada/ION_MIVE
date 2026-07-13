"""Composition root: wires concrete adapters into the Core at runtime.

This is the ONLY place that knows about concrete adapters. Construction is lazy
(called at runtime), so importing this module reads no secrets and opens no
connections. Provider SDK clients are created inside the adapters on first call.
"""

from __future__ import annotations

from .core.clock import SystemClock
from .core.config import Settings
from .core.orchestrator import Core
from .core.ports import EmbeddingPort
from .modules.context_pack import ContextPackBuilder
from .modules.gemini_ive import GeminiIVE
from .modules.mive import MIVEComparator
from .modules.openai_ive import OpenAIIVE
from .modules.renderer import DeterministicRenderer
from .modules.retrieval.embeddings import HashingEmbedder, LocalEmbedder, OpenAIEmbedder
from .modules.retrieval.qdrant_store import QdrantRetrieval
from .modules.telemetry import PricingTable


def build_embedder(settings: Settings) -> EmbeddingPort:
    backend = settings.embedding_backend.lower()
    if backend == "fake":
        return HashingEmbedder()
    if backend == "openai":
        return OpenAIEmbedder(settings.embedding_model or "text-embedding-3-small")
    # default: local
    return LocalEmbedder(settings.embedding_model)


def build_retrieval(settings: Settings, embedder: EmbeddingPort) -> QdrantRetrieval:
    return QdrantRetrieval(
        embedder,
        url=settings.qdrant_url,
        collection=settings.qdrant_collection,
        upsert_batch_size=settings.qdrant_upsert_batch_size,
    )


def build_core(settings: Settings) -> Core:
    """Production wiring: real Qdrant + real provider backends (lazy SDKs)."""
    from .modules.gemini_ive.backend import GeminiBackend
    from .modules.openai_ive.backend import OpenAIBackend

    embedder = build_embedder(settings)
    retrieval = build_retrieval(settings, embedder)

    gemini = GeminiIVE(GeminiBackend(settings.gemini_model), model=settings.gemini_model)
    openai = OpenAIIVE(OpenAIBackend(settings.openai_model), model=settings.openai_model)

    return Core(
        retrieval=retrieval,
        context_pack_builder=ContextPackBuilder(char_budget=settings.context_char_budget),
        gemini_ive=gemini,
        openai_ive=openai,
        mive=MIVEComparator(),
        renderer=DeterministicRenderer(),
        pricing=PricingTable(),
        clock=SystemClock(),
        settings=settings,
    )
