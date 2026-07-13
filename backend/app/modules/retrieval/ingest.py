"""Corpus ingestion: read files -> chunk -> document records for indexing.

Runtime component (needs the corpus and, for real indexing, an embedder + Qdrant).
Text extraction: .txt read directly; .pdf via pypdf (lazy import), per page so we
can record page numbers. Emits records carrying stable evidence identifiers and
the file checksum (traceability, docs/CORPUS_REGISTER).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .chunker import chunk_text

INGESTION_VERSION = "v1"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _read_pages(path: Path) -> list[tuple[int | None, str]]:
    """Return [(page_or_None, text), ...]. TXT -> one entry; PDF -> per page."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return [(None, path.read_text(encoding="utf-8", errors="replace"))]
    if suffix == ".pdf":
        from pypdf import PdfReader  # lazy

        reader = PdfReader(str(path))
        pages: list[tuple[int | None, str]] = []
        for i, page in enumerate(reader.pages, start=1):
            pages.append((i, page.extract_text() or ""))
        return pages
    raise ValueError(f"Unsupported file type: {path.name}")


def build_records(
    source_dir: str | Path,
    *,
    chunk_chars: int = 1200,
    overlap: int = 200,
) -> list[dict]:
    """Produce indexable document records for every file in `source_dir`."""
    directory = Path(source_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Corpus source dir not found: {directory}")

    records: list[dict] = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {".txt", ".pdf"} or not path.is_file():
            continue
        source_id = _slug(path.stem)
        checksum = _sha256(path)
        title = path.stem.replace("_", " ").strip()
        for page, page_text in _read_pages(path):
            for j, chunk in enumerate(chunk_text(page_text, chunk_chars=chunk_chars, overlap=overlap)):
                page_tag = "all" if page is None else str(page)
                chunk_id = f"{source_id}::p{page_tag}::c{j}"
                records.append(
                    {
                        "document_id": chunk_id,
                        "source_id": source_id,
                        "title": title,
                        "content": chunk,
                        "source": path.name,
                        "page": page,
                        "chunk_id": chunk_id,
                        "checksum": checksum,
                        "ingestion_version": INGESTION_VERSION,
                    }
                )
    return records
