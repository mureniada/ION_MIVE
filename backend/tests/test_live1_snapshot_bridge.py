from __future__ import annotations

import hashlib
import json

from app.modules.live1 import SnapshotValidationError, context_pack_from_snapshot
from tests.netguard import guarded
from tests.util import raises


def _snapshot_bytes(**overrides) -> tuple[bytes, str]:
    snapshot = {
        "arm": "baseline",
        "source_run_id": "B1",
        "question": "is money credit or debt?",
        "pack_id": "cp_test0001",
        "documents": [
            {"rank": 1, "document_id": "d0", "source": "broken_money", "chunk_id": "broken_money::pall::c0",
             "page": None, "title": "Broken Money", "score": 0.9, "content": "money is credit and debt"},
            {"rank": 2, "document_id": "d1", "source": "debunkingeconomics", "chunk_id": "debunkingeconomics::p1::c0",
             "page": 1, "title": "Debunking Economics", "score": 0.8, "content": "a second evidence chunk"},
        ],
    }
    snapshot.update(overrides)
    raw = json.dumps(snapshot, sort_keys=True).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()


@guarded
def test_valid_snapshot_loads_into_context_pack():
    raw, digest = _snapshot_bytes()
    pack = context_pack_from_snapshot(raw, expected_sha256=digest)
    assert pack.question == "is money credit or debt?"
    assert pack.context_pack_id == "cp_test0001"
    assert len(pack.documents) == 2


@guarded
def test_hash_mismatch_is_rejected():
    raw, _real_digest = _snapshot_bytes()
    with raises(SnapshotValidationError):
        context_pack_from_snapshot(raw, expected_sha256="0" * 64)


@guarded
def test_document_order_is_preserved():
    raw, digest = _snapshot_bytes()
    pack = context_pack_from_snapshot(raw, expected_sha256=digest)
    assert [d.document_id for d in pack.documents] == ["d0", "d1"]
    assert [d.chunk_id for d in pack.documents] == ["broken_money::pall::c0", "debunkingeconomics::p1::c0"]


@guarded
def test_full_content_preserved_without_normalization():
    raw, digest = _snapshot_bytes()
    pack = context_pack_from_snapshot(raw, expected_sha256=digest)
    assert pack.documents[0].content == "money is credit and debt"
    assert pack.documents[1].content == "a second evidence chunk"


@guarded
def test_no_retrieval_dependency_is_required():
    """The bridge runs to completion entirely inside the network/cloud-import
    denial guard (netguard), and imports nothing retrieval/embedding/Qdrant-
    related — proven statically in test_live1_boundary_audit.py, and here by
    successfully building a ContextPack with every cloud import and outbound
    socket denied."""
    raw, digest = _snapshot_bytes()
    pack = context_pack_from_snapshot(raw, expected_sha256=digest)
    assert pack is not None
    assert len(pack.documents) == 2


@guarded
def test_missing_required_field_is_rejected():
    snapshot = {
        "question": "q",
        "pack_id": "cp_x",
        "documents": [{"rank": 1, "document_id": "d0", "source": "s"}],  # missing chunk_id/page/title/content
    }
    raw = json.dumps(snapshot, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    with raises(SnapshotValidationError):
        context_pack_from_snapshot(raw, expected_sha256=digest)


@guarded
def test_duplicate_rank_is_rejected():
    raw, digest = _snapshot_bytes(documents=[
        {"rank": 1, "document_id": "d0", "source": "s", "chunk_id": "c0", "page": None, "title": "t", "content": "x"},
        {"rank": 1, "document_id": "d1", "source": "s", "chunk_id": "c1", "page": None, "title": "t", "content": "y"},
    ])
    with raises(SnapshotValidationError):
        context_pack_from_snapshot(raw, expected_sha256=digest)


@guarded
def test_non_contiguous_rank_is_rejected():
    raw, digest = _snapshot_bytes(documents=[
        {"rank": 1, "document_id": "d0", "source": "s", "chunk_id": "c0", "page": None, "title": "t", "content": "x"},
        {"rank": 3, "document_id": "d1", "source": "s", "chunk_id": "c1", "page": None, "title": "t", "content": "y"},
    ])
    with raises(SnapshotValidationError):
        context_pack_from_snapshot(raw, expected_sha256=digest)


@guarded
def test_array_order_disagreeing_with_rank_is_rejected():
    raw, digest = _snapshot_bytes(documents=[
        {"rank": 2, "document_id": "d1", "source": "s", "chunk_id": "c1", "page": None, "title": "t", "content": "y"},
        {"rank": 1, "document_id": "d0", "source": "s", "chunk_id": "c0", "page": None, "title": "t", "content": "x"},
    ])
    with raises(SnapshotValidationError):
        context_pack_from_snapshot(raw, expected_sha256=digest)
