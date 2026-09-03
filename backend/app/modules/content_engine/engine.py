"""The Content Engine build boundary (v0.1).

    Content Pack + source_root + relative-path SourceBindings
        -> resolve_and_verify
        -> existing source reader
        -> existing chunker
        -> existing evidence fingerprint
        -> existing source provenance binding
        -> existing canonical provenance materialization
        -> ContentBuildResult
        -> STOP

No embedding. No Qdrant write. No index identity. No clock, UUID or random
source: `provenance_created_at` is an explicit build input, supplied by the
caller and taken verbatim, exactly as the frozen provenance contract requires of
its own builder.

Reuse, not reimplementation
---------------------------
Chunking, fingerprinting, provenance construction, provenance binding and
canonical materialization are the repository's existing frozen implementations,
imported and called. None of their logic is reproduced here, and none of their
modules is modified.

`retrieval.ingest._read_pages` is reused read-only as the TXT/PDF reader. It is a
private name, and this is recorded as a bounded seam:

    PRIVATE REUSE SEAM / NO OWNERSHIP TRANSFER

It was reused, not copied, because duplicating PDF/TXT extraction would create a
second reader that could silently drift from the one the existing corpus was
ingested with. It takes a path and returns pages; it derives no identity, and
nothing about `retrieval/ingest.py` was changed to permit this.

Origin, identity and location
-----------------------------
`source_origin` is built here, by this module, from the DECLARED RELATIVE POSIX
SOURCE PATH:

    source_origin = "corpus-file://" + relative_source_path

The caller never supplies a URI, and `source_id` is never repurposed as an
origin claim:

    SOURCE ORIGIN != SOURCE IDENTITY
    SOURCE ROOT   != CONTENT PACK IDENTITY

The machine's `source_root` is stripped by construction — only the relative path
survives into provenance — so the same pack, the same relative layout and the
same bytes produce identical provenance and identical fingerprints under any
root, on any machine.

Title
-----
`title` is the declared `source_id`. `title` sits inside the frozen seven-field
fingerprint projection, and the canonical Content Pack has no independent title
field, so a filename-derived title would silently make evidence identity depend
on what a file happened to be called. This is a deterministic technical title,
not a claim that `source_id` is a human display title; a display-title field
would require a Content Pack contract change and is not in this scope.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..retrieval.chunker import chunk_text
from ..retrieval.evidence_fingerprint import ALGORITHM as EVIDENCE_FINGERPRINT_ALGORITHM
from ..retrieval.evidence_fingerprint import PROFILE_ID as EVIDENCE_FINGERPRINT_PROFILE_ID
from ..retrieval.evidence_fingerprint import compute_fingerprint_from_record
from ..retrieval.canonical_provenance_materializer import (
    CanonicalProvenanceMaterializationError,
    materialize_canonical_provenance,
)
from ..retrieval.ingest import INGESTION_VERSION, _read_pages  # private reuse seam
from ..retrieval.source_provenance import (
    KNOWN,
    SOURCE_ORIGIN_SCHEME,
    bind_source_provenance,
    build_source_provenance,
)
from .models import (
    CONTENT_ENGINE_CONTRACT_VERSION,
    CONTENT_ENGINE_VERSION,
    ContentBuildResult,
    ContentEngineError,
)
from .resolver import resolve_and_verify

DEFAULT_CHUNK_CHARS = 1200
DEFAULT_OVERLAP = 200

__all__ = [
    "DEFAULT_CHUNK_CHARS",
    "DEFAULT_OVERLAP",
    "build_content",
    "source_origin_for",
]


def source_origin_for(relative_source_path: str) -> str:
    """The frozen-scheme origin for a source's declared relative POSIX path.

    Built from the relative location, never from `source_id` and never from an
    absolute machine path. The frozen provenance contract validates the result.
    """
    return SOURCE_ORIGIN_SCHEME + relative_source_path


def _provenance_for(
    verified: Any,
    *,
    collector: str | None,
    collected_at: str | None,
    collected_at_status: str,
    provenance_created_at: str,
) -> dict[str, Any]:
    try:
        return build_source_provenance(
            source_id=verified.source_id,
            source_origin=source_origin_for(verified.relative_source_path),
            source_file_sha256=verified.source_sha256,
            collector=collector,
            collected_at=collected_at,
            collected_at_status=collected_at_status,
            provenance_created_at=provenance_created_at,
            provenance_created_at_status=KNOWN,
        )
    except ValueError as exc:
        raise ContentEngineError(
            f"source provenance could not be built for {verified.source_id!r}: {exc}"
        ) from exc


def build_content(
    pack: Any,
    bindings: Mapping[str, Any],
    *,
    source_root: Any,
    provenance_created_at: str,
    collector: str | None = None,
    collected_at: str | None = None,
    collected_at_status: str = "UNKNOWN",
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> ContentBuildResult:
    """Build one Content Pack into a verified, provenance-carrying record set.

    `pack` is consumed read-only and is never modified; its
    `canonical_fingerprint` is carried into the result verbatim, not recomputed.
    `bindings` maps each declared `source_id` to a relative POSIX path beneath
    `source_root`.

    Provenance is MANDATORY here, not an optional flag a caller can forget: every
    successful record carries a validated `ion_source_provenance` and a
    materialized `ion_canonical_provenance`. `provenance_created_at` must be an
    explicit RFC3339 UTC timestamp supplied by the caller — this module reads no
    clock — and its status is therefore always KNOWN, which is exactly what
    canonical materialization requires. It is the provenance-materialization time
    of this build: not a source file's creation time, not the pack's version
    time, and not an activation time.

    Raises `ContentEngineError` on any failure, including a source that yields no
    chunk at all: a declared source that contributes nothing to the build is a
    fact the caller must see, not a silent omission.
    """
    pack_id = getattr(pack, "pack_id", None)
    pack_version = getattr(pack, "pack_version", None)
    pack_fingerprint = getattr(pack, "canonical_fingerprint", None)
    if pack_id is None or pack_version is None or pack_fingerprint is None:
        raise ContentEngineError(
            "pack must carry pack_id, pack_version and canonical_fingerprint"
        )

    verified_sources = resolve_and_verify(pack, bindings, source_root=source_root)

    records: list[dict[str, Any]] = []
    for verified in verified_sources:
        provenance = _provenance_for(
            verified,
            collector=collector,
            collected_at=collected_at,
            collected_at_status=collected_at_status,
            provenance_created_at=provenance_created_at,
        )

        try:
            bound_provenance = bind_source_provenance(
                provenance,
                source_id=verified.source_id,
                source_origin=source_origin_for(verified.relative_source_path),
                source_file_sha256=verified.source_sha256,
            )
        except ValueError as exc:  # pragma: no cover - unreachable by construction
            raise ContentEngineError(
                f"source provenance did not bind for {verified.source_id!r}: {exc}"
            ) from exc

        try:
            pages = _read_pages(verified.path)
        except Exception as exc:
            raise ContentEngineError(
                f"declared source {verified.source_id!r} could not be read: {exc}"
            ) from exc

        produced = 0
        for page, page_text in pages:
            page_tag = "all" if page is None else str(page)
            for ordinal, chunk in enumerate(
                chunk_text(page_text, chunk_chars=chunk_chars, overlap=overlap)
            ):
                chunk_id = f"{verified.source_id}::p{page_tag}::c{ordinal}"
                record: dict[str, Any] = {
                    "document_id": chunk_id,
                    "source_id": verified.source_id,
                    "source_version": verified.source_version,
                    "title": verified.source_id,
                    "content": chunk,
                    "page": page,
                    "chunk_id": chunk_id,
                    "checksum": verified.source_sha256,
                    "ingestion_version": INGESTION_VERSION,
                }
                record["evidence_fingerprint"] = compute_fingerprint_from_record(record)
                record["evidence_fingerprint_algorithm"] = EVIDENCE_FINGERPRINT_ALGORITHM
                record["evidence_fingerprint_profile_id"] = EVIDENCE_FINGERPRINT_PROFILE_ID
                record["ion_source_provenance"] = dict(bound_provenance)

                try:
                    record["ion_canonical_provenance"] = materialize_canonical_provenance(
                        record
                    )
                except CanonicalProvenanceMaterializationError as exc:
                    raise ContentEngineError(
                        f"canonical provenance could not be materialized for "
                        f"{chunk_id!r}: {exc}"
                    ) from exc

                records.append(record)
                produced += 1

        if produced == 0:
            raise ContentEngineError(
                f"declared source {verified.source_id!r} produced no derived record; "
                "a declared source that contributes nothing is refused, not skipped"
            )

    return ContentBuildResult(
        content_engine_contract_version=CONTENT_ENGINE_CONTRACT_VERSION,
        content_engine_version=CONTENT_ENGINE_VERSION,
        pack_id=pack_id,
        pack_version=pack_version,
        pack_canonical_fingerprint=pack_fingerprint,
        chunk_chars=chunk_chars,
        overlap=overlap,
        provenance_created_at=provenance_created_at,
        records=tuple(records),
    )
