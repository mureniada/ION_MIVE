"""Local document processing: registry-permitted files -> provenance-carrying fragments.

Two properties matter more than anything else here:

* the registry is the only admission gate. A file sitting in `documents/` that no
  record names is never read into a fragment; it is reported in `LoadResult.unregistered`
  so it is refused *visibly* rather than dropped in silence.
* provenance is attached at cut time. Each fragment leaves this module already
  carrying its material's identity, version, status and authority, so no later
  stage has to re-derive them.

Chunking reuses the repository's existing deterministic `chunk_text`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..retrieval.chunker import chunk_text
from .registry import MaterialRecord, Registry, resolve_source_path

SUPPORTED_SUFFIXES = frozenset({".md", ".txt"})

DEFAULT_CHUNK_CHARS = 900
DEFAULT_OVERLAP = 150


@dataclass(frozen=True)
class LoadResult:
    """Everything the load decided, including what it refused and why."""

    fragments: tuple[dict[str, Any], ...] = ()
    unregistered: tuple[str, ...] = ()
    excluded_material_ids: tuple[str, ...] = ()
    source_checksums: dict[str, str] = field(default_factory=dict)

    @property
    def fragment_count(self) -> int:
        return len(self.fragments)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _fragments_for(
    record: MaterialRecord,
    path: Path,
    *,
    chunk_chars: int,
    overlap: int,
) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunk_text(text, chunk_chars=chunk_chars, overlap=overlap)):
        fragment_id = f"{record.id}::f{i}"
        out.append(
            {
                "fragment_id": fragment_id,
                "material_id": record.id,
                "title": record.title,
                "source_file": record.source_file,
                "content": chunk,
                "provenance": record.provenance(fragment_id=fragment_id),
            }
        )
    return out


def find_unregistered(registry: Registry, docs_dir: str | Path) -> tuple[str, ...]:
    """Supported files present on disk that no registry record names."""
    directory = Path(docs_dir)
    if not directory.is_dir():
        return ()
    registered = {m.source_file for m in registry.materials}
    return tuple(
        sorted(
            p.name
            for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
            and p.name not in registered
        )
    )


def load_fragments(
    registry: Registry,
    docs_dir: str | Path,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> LoadResult:
    """Cut every retrieval-enabled material into provenance-carrying fragments.

    Every registered material's source file must exist, whether or not retrieval is
    enabled for it — a registry entry is a claim that the file is there. A broken
    claim raises `MissingSourceFileError` (fail-fast policy).
    """
    directory = Path(docs_dir)

    checksums: dict[str, str] = {}
    for record in registry.materials:
        path = resolve_source_path(record, directory)   # fail-fast on absence
        checksums[record.id] = _sha256(path)

    fragments: list[dict[str, Any]] = []
    for record in registry.retrievable:
        path = directory / record.source_file
        fragments.extend(
            _fragments_for(record, path, chunk_chars=chunk_chars, overlap=overlap)
        )

    excluded = tuple(m.id for m in registry.materials if not m.retrieval_enabled)

    return LoadResult(
        fragments=tuple(fragments),
        unregistered=find_unregistered(registry, directory),
        excluded_material_ids=excluded,
        source_checksums=checksums,
    )
