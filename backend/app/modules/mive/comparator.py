"""MIVE comparator (MIVEPort).

Compares two independent IVE reports deterministically. It never interprets the
corpus and never calls a third model (docs/06). Engine attribution is preserved;
disagreement is surfaced, not smoothed; unique findings are kept; evidence overlap
strengthens but never proves. Testable with synthetic reports and no API access.
"""

from __future__ import annotations

from ...core.errors import MiveError
from ...core.models import Claim, IVEReport, MIVEResult
from ...validation import validate_mive_result
from .text import content_words, jaccard, negation_parity

AGREE_THRESHOLD = 0.5
PARTIAL_THRESHOLD = 0.25


class MIVEComparator:
    def __init__(
        self, *, agree_threshold: float = AGREE_THRESHOLD,
        partial_threshold: float = PARTIAL_THRESHOLD,
    ) -> None:
        self._agree = agree_threshold
        self._partial = partial_threshold

    def compare(self, reports: list[IVEReport]) -> MIVEResult:
        if len(reports) != 2:
            raise MiveError("MIVE v1 compares exactly two IVE reports.")
        a, b = reports
        ea, eb = a.engine_id, b.engine_id
        if ea == eb:
            raise MiveError("The two IVE reports must come from distinct engines.")

        a_words = [content_words(c.statement) for c in a.claims]
        b_words = [content_words(c.statement) for c in b.claims]

        agreements: list[dict] = []
        partials: list[dict] = []
        conflicts: list[dict] = []

        matched_b: set[int] = set()
        matched_a: set[int] = set()

        for i, ca in enumerate(a.claims):
            best_j, best_sim = -1, 0.0
            for j, cb in enumerate(b.claims):
                if j in matched_b:
                    continue
                sim = jaccard(a_words[i], b_words[j])
                if sim > best_sim:
                    best_j, best_sim = j, sim
            if best_j == -1 or best_sim < self._partial:
                continue
            cb = b.claims[best_j]
            same_polarity = negation_parity(ca.statement) == negation_parity(cb.statement)
            entry = self._pair_entry(ea, ca, eb, cb, best_sim)
            if not same_polarity:
                conflicts.append({**entry, "type": "polarity"})
            elif best_sim >= self._agree:
                agreements.append(entry)
            else:
                partials.append(entry)
            matched_a.add(i)
            matched_b.add(best_j)

        unique_findings: list[dict] = []
        for i, ca in enumerate(a.claims):
            if i not in matched_a:
                unique_findings.append(self._unique_entry(ea, ca))
        for j, cb in enumerate(b.claims):
            if j not in matched_b:
                unique_findings.append(self._unique_entry(eb, cb))

        unsupported_findings: list[dict] = []
        for engine, report in ((ea, a), (eb, b)):
            for c in report.claims:
                if not c.evidence_document_ids:
                    unsupported_findings.append(
                        {
                            "engine": engine,
                            "claim_id": c.claim_id,
                            "statement": c.statement,
                            "reason": "no evidence cited",
                        }
                    )

        shared_uncertainty = self._shared_uncertainty(a.uncertainty, b.uncertainty)

        status = self._status(agreements, partials, conflicts, unique_findings)
        notes = [
            f"{len(agreements)} agreement(s), {len(partials)} partial, "
            f"{len(conflicts)} conflict(s), {len(unique_findings)} unique finding(s).",
            "Evidence overlap strengthens comparison but does not prove truth.",
            f"Engine confidences: {ea}={a.confidence}, {eb}={b.confidence} "
            "(confidence is not proof).",
        ]

        result = MIVEResult(
            question=a.question,
            engine_ids=[ea, eb],
            agreements=agreements,
            partial_agreements=partials,
            conflicts=conflicts,
            unique_findings=unique_findings,
            unsupported_findings=unsupported_findings,
            shared_uncertainty=shared_uncertainty,
            overall_status=status,
            comparison_notes=notes,
        )
        validate_mive_result(result.to_dict())
        return result

    # ----------------------------------------------------------------- #
    @staticmethod
    def _pair_entry(ea: str, ca: Claim, eb: str, cb: Claim, sim: float) -> dict:
        overlap = sorted(set(ca.evidence_document_ids) & set(cb.evidence_document_ids))
        combined = sorted(set(ca.evidence_document_ids) | set(cb.evidence_document_ids))
        return {
            "engines": [ea, eb],
            "claim_ids": {ea: ca.claim_id, eb: cb.claim_id},
            "statements": {ea: ca.statement, eb: cb.statement},
            "similarity": round(sim, 3),
            "evidence_overlap": overlap,
            "combined_evidence": combined,
        }

    @staticmethod
    def _unique_entry(engine: str, c: Claim) -> dict:
        return {
            "engine": engine,
            "claim_id": c.claim_id,
            "statement": c.statement,
            "evidence_document_ids": list(c.evidence_document_ids),
            "confidence": c.confidence,
        }

    @staticmethod
    def _shared_uncertainty(ua: list[str], ub: list[str]) -> list[str]:
        norm_b = {u.strip().lower(): u for u in ub}
        shared: list[str] = []
        for u in ua:
            key = u.strip().lower()
            if key in norm_b:
                shared.append(u)
        return shared

    @staticmethod
    def _status(agreements, partials, conflicts, unique) -> str:
        if agreements and not conflicts and not unique:
            return "strong_agreement"
        if agreements and (conflicts or unique or partials):
            return "partial_agreement"
        if conflicts and not agreements:
            return "conflict"
        if not agreements and not conflicts:
            return "divergent"
        return "partial_agreement"
