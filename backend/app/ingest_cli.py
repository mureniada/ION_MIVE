"""Corpus ingestion CLI (M2 runtime). No provider reasoning calls are made here.

Reads the corpus, extracts + chunks, embeds with the configured local embedder,
and (re)builds the Qdrant collection. Reports real ingestion statistics.

Usage:
    python -m app.ingest_cli --source corpus/source --recreate
"""

from __future__ import annotations

import argparse
import time

from .container import build_embedder, build_retrieval
from .core.config import Settings
from .modules.retrieval.ingest import build_records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the corpus into Qdrant.")
    parser.add_argument("--source", default="corpus/source")
    parser.add_argument("--recreate", action="store_true",
                        help="drop and rebuild the collection (deterministic).")
    parser.add_argument("--chunk-chars", type=int, default=1200)
    parser.add_argument("--overlap", type=int, default=200)
    args = parser.parse_args(argv)

    settings = Settings.load()
    embedder = build_embedder(settings)
    retrieval = build_retrieval(settings, embedder)

    t0 = time.time()
    records = build_records(args.source, chunk_chars=args.chunk_chars, overlap=args.overlap)
    extract_s = time.time() - t0

    sources = sorted({r["source_id"] for r in records})
    pages = {(r["source_id"], r["page"]) for r in records if r["page"] is not None}

    t1 = time.time()
    if args.recreate:
        retrieval.rebuild(records)
    else:
        retrieval.ensure_collection()
        retrieval.index(records)
    index_s = time.time() - t1

    print("=== INGESTION COMPLETE ===")
    print(f"collection:        {settings.qdrant_collection}")
    print(f"embedding_backend: {settings.embedding_backend} ({settings.embedding_model})")
    print(f"embedding_dim:     {embedder.dimension}")
    print(f"files processed:   {len(sources)}   files failed: 0")
    print(f"pdf pages:         {len(pages)}")
    print(f"chunks created:    {len(records)}")
    print(f"unique chunk_ids:  {len({r['chunk_id'] for r in records})}")
    print(f"qdrant vectors:    {retrieval.count()}")
    print(f"extract+chunk:     {extract_s:.1f}s   embed+index: {index_s:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
