"""Local working layer for new ION materials (Phase 1).

Entirely local. Nothing in this package imports a cloud SDK, constructs a cloud
client, reads a cloud credential, or opens a network connection. The protected
Qdrant Cloud corpus is out of reach by construction, not by convention: retrieval
here is a deterministic lexical index over files on disk.

Materials live under `local_materials/` and are admitted only through the
registry — a file present on disk but absent from the registry is never ingested.
"""

from .context_pack import LocalContextPackBuilder
from .lexical_index import LexicalIndex
from .loader import LoadResult, load_fragments
from .registry import (
    LocalRegistryError,
    MaterialRecord,
    MissingSourceFileError,
    Registry,
    load_registry,
)

__all__ = [
    "LexicalIndex",
    "LoadResult",
    "LocalContextPackBuilder",
    "LocalRegistryError",
    "MaterialRecord",
    "MissingSourceFileError",
    "Registry",
    "load_fragments",
    "load_registry",
]
