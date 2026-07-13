from __future__ import annotations

from app.core.models import Evidence
from app.modules.mive import MIVEComparator
from app.modules.renderer import DeterministicRenderer
from tests.fakes import synthetic_report


def _setup():
    a = synthetic_report("gemini", "gemini", claims=[
        {"claim_id": "a1", "statement": "money is a medium of exchange",
         "evidence_document_ids": ["doc1"], "confidence": 0.8},
        {"claim_id": "a2", "statement": "banks create money",
         "evidence_document_ids": ["doc2"], "confidence": 0.6}])
    b = synthetic_report("openai", "openai", claims=[
        {"claim_id": "b1", "statement": "money serves as a medium of exchange",
         "evidence_document_ids": ["doc1"], "confidence": 0.8},
        {"claim_id": "b2", "statement": "banks do not create money",
         "evidence_document_ids": ["doc2"], "confidence": 0.5}])
    mive = MIVEComparator().compare([a, b])
    evidence = [
        Evidence("doc1", "s1", "Exchange", "money is a medium of exchange used in trade", 0.9),
        Evidence("doc2", "s2", "Banking", "commercial banks create money via lending", 0.8),
    ]
    return a, b, mive, evidence


def test_render_contains_all_required_sections():
    a, b, mive, evidence = _setup()
    out = DeterministicRenderer().render(
        question="What is money?", mive_result=mive, reports=[a, b],
        evidence=evidence, metrics_dict={"request_id": "r1"})
    for key in ("question", "primary_answer", "mive_assessment", "uncertainty",
                "evidence", "operational_metrics", "disclaimer"):
        assert key in out
    assert out["mive_assessment"]["overall_status"] == mive.overall_status


def test_conflicts_are_not_hidden():
    a, b, mive, evidence = _setup()
    out = DeterministicRenderer().render(
        question="q", mive_result=mive, reports=[a, b],
        evidence=evidence, metrics_dict={})
    assert len(out["mive_assessment"]["disagreements"]) == 1
    assert "disagree" in out["primary_answer"].lower()


def test_evidence_rows_link_to_present_documents():
    a, b, mive, evidence = _setup()
    out = DeterministicRenderer().render(
        question="q", mive_result=mive, reports=[a, b],
        evidence=evidence, metrics_dict={})
    ids = {row["document_id"] for row in out["evidence"]}
    assert ids <= {"doc1", "doc2"}
    assert out["evidence"]  # at least one linked excerpt
