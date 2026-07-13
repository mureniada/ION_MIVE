from __future__ import annotations

from app.core.models import Evidence
from app.modules.context_pack import ContextPackBuilder
from app.validation import validate_context_pack
from tests.util import raises
from app.core.errors import ContextPackError


def _evidence(n=3, size=100):
    return [
        Evidence(document_id=f"d{i}", source_id=f"s{i}", title=f"T{i}",
                 content="x" * size, score=1.0 - i * 0.1, page=i, chunk_id=f"d{i}::c0")
        for i in range(n)
    ]


def test_builds_valid_pack_with_stable_ids():
    b = ContextPackBuilder(char_budget=10000)
    pack = b.build("What is money?", _evidence())
    d = pack.to_dict()
    validate_context_pack(d)                          # schema-valid
    assert [doc["document_id"] for doc in d["documents"]] == ["d0", "d1", "d2"]
    assert pack.context_pack_id.startswith("cp_")
    # identical inputs -> identical pack id (reproducibility)
    assert b.build("What is money?", _evidence()).context_pack_id == pack.context_pack_id


def test_truncation_is_explicit_and_recorded():
    b = ContextPackBuilder(char_budget=150)             # only ~1 doc of size 100 fits
    pack = b.build("q", _evidence(n=3, size=100))
    assert pack.metadata["truncated"] is True
    assert pack.metadata["included_documents"] < pack.metadata["evidence_count"]


def test_no_evidence_raises():
    with raises(ContextPackError):
        ContextPackBuilder().build("q", [])
