"""Corpus ingestion: read files -> chunk -> document records for indexing.

Runtime component (needs the corpus and, for real indexing, an embedder + Qdrant).
Text extraction: .txt read directly; .pdf via pypdf (lazy import), per page so we
can record page numbers. Emits records carrying stable evidence identifiers and
the file checksum (traceability, docs/CORPUS_REGISTER).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .canonical_provenance_materializer import materialize_canonical_provenance
from .evidence_fingerprint import ALGORITHM as EVIDENCE_FINGERPRINT_ALGORITHM
from .evidence_fingerprint import PROFILE_ID as EVIDENCE_FINGERPRINT_PROFILE_ID
from .evidence_fingerprint import compute_fingerprint_from_record
from .source_provenance import bind_source_provenance
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
    source_provenance_by_source: Mapping[str, Mapping[str, Any]] | None = None,
    materialize_canonical: bool = False,
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
                record = {
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
                record["evidence_fingerprint"] = compute_fingerprint_from_record(record)
                record["evidence_fingerprint_algorithm"] = EVIDENCE_FINGERPRINT_ALGORITHM
                record["evidence_fingerprint_profile_id"] = EVIDENCE_FINGERPRINT_PROFILE_ID

                if source_provenance_by_source is not None and source_id in source_provenance_by_source:
                    expected_origin = "corpus-file://" + path.relative_to(directory).as_posix()
                    record["ion_source_provenance"] = bind_source_provenance(
                        source_provenance_by_source[source_id],
                        source_id=source_id,
                        source_origin=expected_origin,
                        source_file_sha256=checksum,
                    )

                if materialize_canonical:
                    if source_provenance_by_source is None or source_id not in source_provenance_by_source:
                        raise ValueError(
                            "canonical materialization requires an explicit source provenance binding"
                        )
                    if "ion_source_provenance" not in record:
                        raise ValueError(
                            "canonical materialization requires validated source provenance"
                        )
                    record["ion_canonical_provenance"] = materialize_canonical_provenance(
                        record
                    )

                records.append(record)
    return records
