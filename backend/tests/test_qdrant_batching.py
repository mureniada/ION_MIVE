"""Deterministic tests for batched Qdrant upsert (no real Qdrant, no network).

A fake client + fake models let us exercise the batching logic exactly, verifying
sizes, counts, order, stable IDs, and that a failing batch surfaces full context
and is never swallowed.
"""

from __future__ import annotations

from app.core.errors import RetrievalError
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.qdrant_store import QdrantRetrieval, point_id_for


class FakeModels:
    class PointStruct:
        def __init__(self, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload


class FakeClient:
    def __init__(self, fail_on_call: int | None = None):
        self.batches: list[list] = []
        self.calls = 0
        self._fail_on = fail_on_call

    def collection_exists(self, name):
        return True

    def create_collection(self, **kw):
        raise AssertionError("collection should already exist in these tests")

    def delete_collection(self, name):
        pass

    def upsert(self, collection_name, points):
        self.calls += 1
        if self._fail_on is not None and self.calls == self._fail_on:
            raise RuntimeError("simulated qdrant 400 payload too large")
        self.batches.append(list(points))

    def count(self, collection_name):
        class _C:
            pass

        c = _C()
        c.count = sum(len(b) for b in self.batches)
        return c


def _qr(batch_size=128, fail_on=None):
    qr = QdrantRetrieval(HashingEmbedder(8), url="x", collection="c",
                         upsert_batch_size=batch_size)
    qr._client = FakeClient(fail_on_call=fail_on)
    qr._models = FakeModels
    return qr


def _docs(n):
    return [
        {"document_id": f"d{i}", "source_id": "s", "title": "t",
         "content": f"content number {i} about money and debt"}
        for i in range(n)
    ]


def test_zero_records_performs_no_upsert():
    qr = _qr()
    assert qr.index([]) == 0
    assert qr._client.calls == 0 and qr._client.batches == []


def test_fewer_than_batch_is_one_upsert():
    qr = _qr(128)
    assert qr.index(_docs(5)) == 5
    assert len(qr._client.batches) == 1
    assert len(qr._client.batches[0]) == 5


def test_exact_multiple_of_batch_size():
    qr = _qr(128)
    assert qr.index(_docs(256)) == 256
    assert [len(b) for b in qr._client.batches] == [128, 128]


def test_remainder_batch_is_handled():
    qr = _qr(128)
    assert qr.index(_docs(130)) == 130
    assert [len(b) for b in qr._client.batches] == [128, 2]


def test_order_and_stable_ids_preserved():
    docs = _docs(130)
    qr = _qr(128)
    qr.index(docs)
    flat_ids = [p.id for batch in qr._client.batches for p in batch]
    expected = [point_id_for(d["document_id"]) for d in docs]
    assert flat_ids == expected                       # order + deterministic IDs
    qr2 = _qr(128)
    qr2.index(docs)
    assert [p.id for b in qr2._client.batches for p in b] == expected  # stable re-ingest


def test_failed_batch_surfaces_context_and_is_not_swallowed():
    qr = _qr(128, fail_on=2)                           # 2nd batch fails
    try:
        qr.index(_docs(200))
        assert False, "expected RetrievalError"
    except RetrievalError as exc:
        msg = str(exc)
        assert "batch 2/2" in msg
        assert "records 128..199" in msg
        assert "batch_size=128" in msg
        assert exc.stage == "retrieval"
        assert isinstance(exc.__cause__, RuntimeError)  # exception chain preserved
    assert qr._client.calls == 2 and len(qr._client.batches) == 1  # not rolled back/swallowed
