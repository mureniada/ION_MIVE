from __future__ import annotations

from app.core.errors import MiveError
from app.modules.mive import MIVEComparator
from app.validation import validate_mive_result
from tests.fakes import synthetic_report
from tests.util import raises

SHARED_UNC = "Origins of money are debated."


def _reports():
    a = synthetic_report(
        "gemini", "gemini",
        claims=[
            {"claim_id": "a1", "statement": "money is a medium of exchange",
             "evidence_document_ids": ["doc1"], "confidence": 0.8},
            {"claim_id": "a2", "statement": "banks create money",
             "evidence_document_ids": ["doc2"], "confidence": 0.6},
            {"claim_id": "a3", "statement": "gold is hard money",
             "evidence_document_ids": ["doc3"], "confidence": 0.7},
            {"claim_id": "a4", "statement": "inflation erodes purchasing power",
             "evidence_document_ids": [], "confidence": 0.5},
        ],
        uncertainty=[SHARED_UNC],
    )
    b = synthetic_report(
        "openai", "openai",
        claims=[
            {"claim_id": "b1", "statement": "money serves as a medium of exchange",
             "evidence_document_ids": ["doc1"], "confidence": 0.8},
            {"claim_id": "b2", "statement": "banks do not create money",
             "evidence_document_ids": ["doc2"], "confidence": 0.5},
        ],
        uncertainty=[SHARED_UNC],
    )
    return a, b


def test_agreement_conflict_unique_and_unsupported_are_detected():
    a, b = _reports()
    res = MIVEComparator().compare([a, b])
    validate_mive_result(res.to_dict())

    assert res.engine_ids == ["gemini", "openai"]
    assert len(res.agreements) == 1
    assert res.agreements[0]["evidence_overlap"] == ["doc1"]

    assert len(res.conflicts) == 1
    assert res.conflicts[0]["type"] == "polarity"

    unique_engines = {u["engine"] for u in res.unique_findings}
    unique_claims = {u["claim_id"] for u in res.unique_findings}
    assert unique_engines == {"gemini"}          # attribution preserved
    assert {"a3", "a4"} <= unique_claims

    assert any(u["claim_id"] == "a4" for u in res.unsupported_findings)
    assert res.shared_uncertainty == [SHARED_UNC]
    assert res.overall_status == "partial_agreement"


def test_disagreement_is_not_smoothed_into_agreement():
    a, b = _reports()
    res = MIVEComparator().compare([a, b])
    # the banks claim must appear as a conflict, never as an agreement
    agree_ids = [set(x["claim_ids"].values()) for x in res.agreements]
    assert not any({"a2", "b2"} <= s for s in agree_ids)


def test_requires_two_distinct_engines():
    a, b = _reports()
    with raises(MiveError):
        MIVEComparator().compare([a])
    same = synthetic_report("gemini", "gemini", claims=[
        {"claim_id": "x", "statement": "y", "evidence_document_ids": [], "confidence": 0.5}])
    with raises(MiveError):
        MIVEComparator().compare([a, same])
