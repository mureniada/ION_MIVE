from __future__ import annotations

from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.memory_index import InMemoryRetrieval


def _docs():
    return [
        {"document_id": "d1", "source_id": "s1", "title": "Debt",
         "content": "money is fundamentally a form of credit and debt relationships"},
        {"document_id": "d2", "source_id": "s2", "title": "Commodity",
         "content": "gold and silver served as commodity money with intrinsic value"},
        {"document_id": "d3", "source_id": "s3", "title": "Whales",
         "content": "the ecological value of whales and ocean carbon capture"},
    ]


def test_retrieval_returns_relevant_evidence_first():
    r = InMemoryRetrieval(HashingEmbedder(dimension=512))
    assert r.index(_docs()) == 3
    hits = r.retrieve("is money credit or debt?", top_k=3)
    assert hits[0].document_id == "d1"
    assert hits[0].score >= hits[-1].score        # sorted by score
    assert hits[0].source_id == "s1"              # evidence metadata preserved


def test_empty_index_returns_nothing():
    r = InMemoryRetrieval(HashingEmbedder())
    assert r.retrieve("anything", top_k=5) == []
