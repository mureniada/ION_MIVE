"""Runtime configuration.

Reading this module never reads secrets or opens connections. `Settings.load()`
reads environment variables when explicitly called (at runtime, in factories).
Secret *presence* is exposed as booleans only — values are never returned or
logged (docs/11).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    debug: bool
    default_top_k: int
    openai_model: str
    gemini_model: str
    embedding_backend: str          # "fake" | "local" | "openai"
    embedding_model: str
    qdrant_url: str
    qdrant_collection: str
    context_char_budget: int        # explicit truncation budget (docs/04)

    @staticmethod
    def load(env: dict[str, str] | None = None) -> "Settings":
        e = env if env is not None else os.environ
        return Settings(
            debug=_as_bool(e.get("DEBUG"), False),
            default_top_k=int(e.get("DEFAULT_TOP_K", "5")),
            openai_model=e.get("OPENAI_MODEL", ""),
            gemini_model=e.get("GEMINI_MODEL", ""),
            embedding_backend=e.get("EMBEDDING_BACKEND", "local"),
            embedding_model=e.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            qdrant_url=e.get("VECTOR_STORE_URL", "http://localhost:6333"),
            qdrant_collection=e.get("VECTOR_COLLECTION", "ion_corpus_v1"),
            context_char_budget=int(e.get("CONTEXT_CHAR_BUDGET", "60000")),
        )


def secret_presence(env: dict[str, str] | None = None) -> dict[str, bool]:
    """Booleans only — never the values (docs/11)."""
    e = env if env is not None else os.environ

    def present(name: str) -> bool:
        v = e.get(name)
        return bool(v and v.strip())

    return {
        "OPENAI_API_KEY": present("OPENAI_API_KEY"),
        "GEMINI_API_KEY": present("GEMINI_API_KEY"),
    }
