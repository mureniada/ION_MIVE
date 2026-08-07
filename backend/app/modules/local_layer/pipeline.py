"""The Phase 1 minimum vertical, end to end.

    local document -> registry -> local processing -> local retrieval
                   -> provenance-labelled Context Pack

Every step is a file read or a pure computation. There is no client, no socket,
no credential and no SDK anywhere on this path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context_pack import LocalContextPackBuilder
from .lexical_index import LexicalIndex
from .loader import LoadResult, load_fragments
from .registry import Registry, documents_dir, load_registry, local_materials_dir

CONTROL_QUESTION = "What is Adaptive Dialogue in ION?"

INDEX_DIRNAME = ".index"
INDEX_FILENAME = "lexical_index.json"

DEFAULT_TOP_K = 3


@dataclass(frozen=True)
class LocalLayerPaths:
    materials: Path
    documents: Path
    registry: Path
    index: Path

    @classmethod
    def resolve(cls, materials_dir: str | Path | None = None) -> "LocalLayerPaths":
        root = Path(materials_dir) if materials_dir else local_materials_dir()
        return cls(
            materials=root,
            documents=documents_dir(root),
            registry=root / "registry.json",
            index=root / INDEX_DIRNAME / INDEX_FILENAME,
        )


def load_layer(paths: LocalLayerPaths | None = None) -> tuple[Registry, LoadResult]:
    """Registry + processed fragments, with nothing admitted that the registry did not name."""
    p = paths or LocalLayerPaths.resolve()
    registry = load_registry(p.registry)
    return registry, load_fragments(registry, p.documents)


def build_index(paths: LocalLayerPaths | None = None, *, persist: bool = False) -> LexicalIndex:
    """Build the lexical index from source material and registry data alone."""
    p = paths or LocalLayerPaths.resolve()
    _registry, load_result = load_layer(p)
    index = LexicalIndex.build(load_result.fragments)
    if persist:
        index.save(p.index)
    return index


def delete_index(paths: LocalLayerPaths | None = None) -> bool:
    """Delete the derived index. Source material and registry are untouched."""
    p = paths or LocalLayerPaths.resolve()
    return LexicalIndex.delete(p.index)


def build_context_pack(
    question: str,
    *,
    paths: LocalLayerPaths | None = None,
    top_k: int = DEFAULT_TOP_K,
    char_budget: int = 60000,
) -> dict[str, Any]:
    """Run the whole vertical for one question and return a schema-valid Context Pack."""
    p = paths or LocalLayerPaths.resolve()
    registry, load_result = load_layer(p)
    index = LexicalIndex.build(load_result.fragments)

    evidence = index.retrieve(question, top_k=top_k)

    return LocalContextPackBuilder(char_budget=char_budget).build(
        question,
        evidence,
        registry_version=registry.registry_version,
        material_count=len(registry.retrievable),
        index_fingerprint=index.fingerprint(),
    )


def run_control_question(paths: LocalLayerPaths | None = None) -> dict[str, Any]:
    """The Phase 1 acceptance scenario (mandate §9)."""
    return build_context_pack(CONTROL_QUESTION, paths=paths)
