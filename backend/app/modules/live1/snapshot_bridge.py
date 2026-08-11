"""Canonical LIVE-1 replay snapshot -> ContextPack bridge (v0.1).

Turns an already-produced, hash-frozen canonical Context A/B snapshot (see
the PROBE-A canonicalization procedure) back into the same `ContextPack`
representation `ive_common.build_user_prompt` already consumes -- with no
retrieval, no Qdrant, no embeddings, no source-file access, and no network
anywhere in this module.

The snapshot's own SHA-256 must be supplied by the caller and is checked
against the exact input bytes before anything is parsed. Content is never
transformed: no strip(), no whitespace collapsing, no re-encoding.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ...core.models import ContextDocument, ContextPack

REQUIRED_DOCUMENT_FIELDS = (
    "rank", "document_id", "source", "chunk_id", "page", "title", "content",
)


class SnapshotValidationError(Exception):
    """A canonical replay snapshot failed validation. Never silently repaired."""


def context_pack_from_snapshot(raw: bytes, *, expected_sha256: str) -> ContextPack:
    """Deserialize and validate a canonical snapshot into a ContextPack.

    Raises SnapshotValidationError on any hash mismatch, missing field, or
    ambiguous/duplicate rank ordering. Never guesses, never normalizes text.
    """
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        raise SnapshotValidationError(
            f"snapshot SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    try:
        snapshot = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotValidationError(f"snapshot is not valid UTF-8 JSON: {exc}") from None

    if not isinstance(snapshot, dict):
        raise SnapshotValidationError("snapshot root must be a JSON object.")

    question = snapshot.get("question")
    if not isinstance(question, str) or not question:
        raise SnapshotValidationError("snapshot missing required non-empty 'question'.")

    documents = snapshot.get("documents")
    if not isinstance(documents, list) or not documents:
        raise SnapshotValidationError("snapshot missing required non-empty 'documents' array.")

    for i, doc in enumerate(documents):
        if not isinstance(doc, dict):
            raise SnapshotValidationError(f"documents[{i}] is not an object.")
        missing = [f for f in REQUIRED_DOCUMENT_FIELDS if f not in doc]
        if missing:
            raise SnapshotValidationError(f"documents[{i}] missing required field(s): {missing}")

    ranks = [doc["rank"] for doc in documents]
    if len(set(ranks)) != len(ranks):
        raise SnapshotValidationError(f"duplicate rank values in documents: {ranks}")
    expected_ranks = list(range(1, len(documents) + 1))
    if sorted(ranks) != expected_ranks:
        raise SnapshotValidationError(
            f"ranks are not a contiguous 1..N sequence: got {sorted(ranks)}, expected {expected_ranks}"
        )
    if ranks != expected_ranks:
        raise SnapshotValidationError(
            "documents array order does not match ascending rank order — ambiguous ordering rejected "
            f"(array rank order: {ranks})"
        )

    context_documents = [
        ContextDocument(
            document_id=doc["document_id"],
            title=doc["title"],
            content=doc["content"],
            source=doc["source"],
            page=doc["page"],
            chunk_id=doc["chunk_id"],
        )
        for doc in documents
    ]

    pack_id = snapshot.get("pack_id")
    if not isinstance(pack_id, str) or not pack_id:
        raise SnapshotValidationError("snapshot missing required non-empty 'pack_id'.")

    metadata: dict[str, Any] = {
        "source": "live1_snapshot",
        "snapshot_sha256": actual_sha256,
    }
    if "arm" in snapshot:
        metadata["snapshot_arm"] = snapshot["arm"]
    if "source_run_id" in snapshot:
        metadata["snapshot_source_run_id"] = snapshot["source_run_id"]

    return ContextPack(
        context_pack_id=pack_id,
        question=question,
        documents=context_documents,
        metadata=metadata,
    )
