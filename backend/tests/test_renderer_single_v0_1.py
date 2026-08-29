"""TASK 20 contract test: the SINGLE execution-profile renderer path.

Scope: `DeterministicRenderer.render_single` only. The existing `render(...)`
comparison path (frozen, tested in `test_renderer.py`) is untouched and
remains comparison-only.

Central law under test (D20-20 / §24-27): the SINGLE renderer resolves a
report's citations ONLY against the evidence basis it is explicitly handed —
never a broader retrieved-candidate list — so a candidate the active
governance/Model-Context boundary excluded can never reach rendered output
merely because the underlying report happened to cite it.
"""

from __future__ import annotations

from app.modules.model_context import EvidenceContextItem
from app.modules.renderer import DeterministicRenderer
from tests.fakes import synthetic_report


def _basis(*items: EvidenceContextItem) -> tuple[EvidenceContextItem, ...]:
    return tuple(items)


def _item(candidate_id: str, *, content: str, title: str, source_identity: str) -> EvidenceContextItem:
    return EvidenceContextItem(
        candidate_id=candidate_id, content=content, title=title,
        source_identity=source_identity, page=None, chunk_id=None,
    )


def _report_citing(*doc_ids: str) -> "synthetic_report":
    return synthetic_report(
        "gemini", "gemini",
        claims=[
            {"claim_id": "c1", "statement": "a claim citing everything it saw",
             "evidence_document_ids": list(doc_ids), "confidence": 0.8},
        ],
        uncertainty=["Origins of money are debated."],
    )


# --------------------------------------------------------------------- #
# structural shape
# --------------------------------------------------------------------- #
def test_render_single_contains_all_required_sections():
    report = _report_citing("A")
    basis = _basis(_item("A", content="alpha content", title="Alpha", source_identity="src-a"))
    out = DeterministicRenderer().render_single(
        question="What is money?", report=report, authorized_evidence_basis=basis,
        metrics_dict={"request_id": "r1"},
    )
    for key in ("question", "primary_answer", "mive_assessment", "uncertainty",
                "evidence", "operational_metrics", "disclaimer"):
        assert key in out


def test_render_single_mive_assessment_is_none_not_an_empty_comparison_shape():
    report = _report_citing("A")
    basis = _basis(_item("A", content="c", title="t", source_identity="s"))
    out = DeterministicRenderer().render_single(
        question="q", report=report, authorized_evidence_basis=basis, metrics_dict={},
    )
    assert out["mive_assessment"] is None


def test_render_single_primary_answer_is_the_reports_own_abstract():
    report = _report_citing("A")
    basis = _basis(_item("A", content="c", title="t", source_identity="s"))
    out = DeterministicRenderer().render_single(
        question="q", report=report, authorized_evidence_basis=basis, metrics_dict={},
    )
    assert out["primary_answer"] == report.abstract


def test_render_single_uncertainty_is_the_reports_own_only():
    report = _report_citing("A")
    basis = _basis(_item("A", content="c", title="t", source_identity="s"))
    out = DeterministicRenderer().render_single(
        question="q", report=report, authorized_evidence_basis=basis, metrics_dict={},
    )
    assert out["uncertainty"] == {"reported": report.uncertainty}
    assert "shared" not in out["uncertainty"]
    assert "per_engine" not in out["uncertainty"]


def test_render_single_operational_metrics_is_passed_through_verbatim():
    report = _report_citing("A")
    basis = _basis(_item("A", content="c", title="t", source_identity="s"))
    metrics = {"request_id": "r1", "total_estimated_cost": 0.01}
    out = DeterministicRenderer().render_single(
        question="q", report=report, authorized_evidence_basis=basis, metrics_dict=metrics,
    )
    assert out["operational_metrics"] is metrics


# --------------------------------------------------------------------- #
# truthfulness: no cross-model comparison language
# --------------------------------------------------------------------- #
def test_render_single_disclaimer_never_claims_a_comparison():
    """The disclaimer may truthfully NEGATE comparison claims (e.g. "no
    cross-model agreement... applies") — that is not a fabrication, it is
    the whole point of this disclaimer. What must never appear is an
    AFFIRMATIVE claim that a comparison happened."""
    report = _report_citing("A")
    basis = _basis(_item("A", content="c", title="t", source_identity="s"))
    out = DeterministicRenderer().render_single(
        question="q", report=report, authorized_evidence_basis=basis, metrics_dict={},
    )
    lowered = out["disclaimer"].lower()
    for forbidden_claim in (
        "both engines agree", "engines agree", "reached consensus",
        "in consensus", "cross-model confirmation", "engines confirm",
        "both engines disagree",
    ):
        assert forbidden_claim not in lowered, forbidden_claim
    assert report.engine_id in out["disclaimer"]


def test_render_single_no_cross_model_language_anywhere_in_output():
    report = _report_citing("A")
    basis = _basis(_item("A", content="c", title="t", source_identity="s"))
    out = DeterministicRenderer().render_single(
        question="q", report=report, authorized_evidence_basis=basis, metrics_dict={},
    )
    blob = str(out).lower()
    for forbidden_claim in ("both engines agree", "engines agree", "reached consensus"):
        assert forbidden_claim not in blob


# --------------------------------------------------------------------- #
# D20-20 / §27 — the mixed A/B/C evidence-authority proof
# --------------------------------------------------------------------- #
_A_SENTINEL = "ALPHA-CONTENT-9f31"
_B_SENTINEL = "BRAVO-CONTENT-2e77"
_C_SENTINEL = "CHARLIE-CONTENT-c410"


def test_response_cited_is_a_subset_of_model_context_included():
    """Retrieved candidates: A, B, C. ModelContext (authorized) basis: A, C
    only — B was retrieved but excluded upstream. The provider report cites
    all three (A, B, C), exactly as an engine might if its own reasoning
    referenced something outside what it was authorized to see. Rendered
    evidence MUST contain A and C, and MUST NOT contain B — proving
    RESPONSE-CITED ⊆ MODEL-CONTEXT-INCLUDED, never resolved against the
    full retrieval collection.
    """
    report = _report_citing("CAND-A", "CAND-B", "CAND-C")
    authorized_basis = _basis(
        _item("CAND-A", content=_A_SENTINEL, title="Alpha", source_identity="src-a"),
        _item("CAND-C", content=_C_SENTINEL, title="Charlie", source_identity="src-c"),
        # CAND-B is deliberately ABSENT from the authorized basis: it exists
        # only in a hypothetical broader retrieval set this renderer must
        # never consult.
    )

    out = DeterministicRenderer().render_single(
        question="mixed basis?", report=report,
        authorized_evidence_basis=authorized_basis, metrics_dict={},
    )

    rendered_ids = {row["document_id"] for row in out["evidence"]}
    assert rendered_ids == {"CAND-A", "CAND-C"}
    assert "CAND-B" not in rendered_ids

    # B's unique content sentinel must be absent from rendered output entirely
    blob = str(out)
    assert _B_SENTINEL not in blob
    assert _A_SENTINEL in blob
    assert _C_SENTINEL in blob


def test_excluded_candidate_is_silently_dropped_not_errored():
    """A citation absent from the authorized basis is excluded outright —
    never raised as an error, never substituted, never looked up elsewhere."""
    report = _report_citing("CAND-A", "CAND-B")
    authorized_basis = _basis(
        _item("CAND-A", content=_A_SENTINEL, title="Alpha", source_identity="src-a"),
    )

    out = DeterministicRenderer().render_single(
        question="q", report=report, authorized_evidence_basis=authorized_basis,
        metrics_dict={},
    )

    assert {row["document_id"] for row in out["evidence"]} == {"CAND-A"}


def test_render_single_never_touches_a_broader_retrieval_collection():
    """Structural proof: `authorized_evidence_basis` is the ONLY source
    consulted — passing an empty basis yields zero evidence rows even though
    the report cites real ids, proving no fallback lookup exists anywhere."""
    report = _report_citing("CAND-A", "CAND-B", "CAND-C")
    out = DeterministicRenderer().render_single(
        question="q", report=report, authorized_evidence_basis=(), metrics_dict={},
    )
    assert out["evidence"] == []
