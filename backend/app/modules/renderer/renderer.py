"""Deterministic renderer (RendererPort).

Synthesizes the User Output Contract (docs/07) from structured fields only — no
LLM call. It must not hide conflicts. Same inputs always produce the same output.
"""

from __future__ import annotations

from ...core.models import Evidence, IVEReport, MIVEResult

_EXCERPT_CHARS = 240
_MAX_AGREEMENTS_IN_ANSWER = 3


class DeterministicRenderer:
    def render(
        self,
        *,
        question: str,
        mive_result: MIVEResult,
        reports: list[IVEReport],
        evidence: list[Evidence],
        metrics_dict: dict,
    ) -> dict:
        ev_index = {e.document_id: e for e in evidence}
        engines = mive_result.engine_ids

        primary_answer = self._primary_answer(mive_result, engines)

        mive_assessment = {
            "agreements": [self._flatten_pair(a) for a in mive_result.agreements],
            "partial_agreements": [self._flatten_pair(p) for p in mive_result.partial_agreements],
            "disagreements": [self._flatten_pair(c) for c in mive_result.conflicts],
            "unique_findings": mive_result.unique_findings,
            "weakly_supported": mive_result.unsupported_findings,
            "overall_status": mive_result.overall_status,
        }

        evidence_section = self._evidence_section(mive_result, ev_index)

        return {
            "question": question,
            "primary_answer": primary_answer,
            "mive_assessment": mive_assessment,
            "uncertainty": self._uncertainty(mive_result, reports),
            "evidence": evidence_section,
            "operational_metrics": metrics_dict,
            "disclaimer": (
                "Intelligence is not truth. This synthesis reflects a comparison of two "
                "independent model interpretations of the retrieved evidence; it preserves "
                "uncertainty and disagreement rather than resolving them automatically."
            ),
        }

    # ----------------------------------------------------------------- #
    def _primary_answer(self, mive: MIVEResult, engines: list[str]) -> str:
        parts: list[str] = []
        eng_label = " and ".join(engines)
        if mive.agreements:
            parts.append(f"Both engines ({eng_label}) agree on the following:")
            for a in mive.agreements[:_MAX_AGREEMENTS_IN_ANSWER]:
                stmt = next(iter(a.get("statements", {}).values()), "")
                parts.append(f"- {stmt}")
        else:
            parts.append(
                f"The two engines ({eng_label}) produced no strongly overlapping claims "
                "on this question; see unique findings below."
            )
        if mive.conflicts:
            parts.append("They disagree on:")
            for c in mive.conflicts:
                stmts = c.get("statements", {})
                pair = " | ".join(f"{k}: {v}" for k, v in stmts.items())
                parts.append(f"- {pair}")
        if mive.shared_uncertainty:
            parts.append("Both engines flag remaining uncertainty (see Uncertainty).")
        return "\n".join(parts)

    @staticmethod
    def _flatten_pair(entry: dict) -> dict:
        return {
            "engines": entry.get("engines", []),
            "statements": entry.get("statements", {}),
            "similarity": entry.get("similarity"),
            "evidence_overlap": entry.get("evidence_overlap", []),
            "type": entry.get("type"),
        }

    @staticmethod
    def _uncertainty(mive: MIVEResult, reports: list[IVEReport]) -> dict:
        per_engine = {r.engine_id: list(r.uncertainty) for r in reports}
        return {
            "shared": mive.shared_uncertainty,
            "per_engine": per_engine,
            "weakly_supported_claims": mive.unsupported_findings,
        }

    def _evidence_section(self, mive: MIVEResult, ev_index: dict[str, Evidence]) -> list[dict]:
        rows: list[dict] = []
        seen: set[tuple[str, str]] = set()

        def add(doc_id: str, linkage: str) -> None:
            e = ev_index.get(doc_id)
            if e is None:
                return
            key = (doc_id, linkage)
            if key in seen:
                return
            seen.add(key)
            rows.append(
                {
                    "document_id": e.document_id,
                    "title": e.title,
                    "source": e.source_id,
                    "page": e.page,
                    "chunk_id": e.chunk_id,
                    "excerpt": e.content[:_EXCERPT_CHARS].strip(),
                    "claim_linkage": linkage,
                }
            )

        for a in mive.agreements:
            linkage = next(iter(a.get("statements", {}).values()), "agreement")
            for doc_id in a.get("combined_evidence", []):
                add(doc_id, linkage)
        for u in mive.unique_findings:
            for doc_id in u.get("evidence_document_ids", []):
                add(doc_id, u.get("statement", "unique finding"))
        return rows

    # ----------------------------------------------------------------- #
    # SINGLE execution profile path (TASK 20) — comparison not applicable.
    # ----------------------------------------------------------------- #
    def render_single(
        self,
        *,
        question: str,
        report: IVEReport,
        authorized_evidence_basis,
        metrics_dict: dict,
    ) -> dict:
        """Render one engine's report, truthfully, with no comparison claim.

        `authorized_evidence_basis` is accepted structurally — this module
        never imports the package that defines its item type — and is the
        ONLY source consulted when resolving the report's own citations. It
        must be exactly the evidence set the executed engine itself received,
        never a broader retrieved-candidate list: a citation id absent from
        this basis is excluded outright, never looked up elsewhere.

        `mive_assessment` is `None` here, not an empty comparison-shaped
        dict: no comparison ran, and an empty `{"agreements": [], ...}` would
        misstate that one was attempted and found nothing.
        """
        return {
            "question": question,
            "primary_answer": report.abstract,
            "mive_assessment": None,
            "uncertainty": self._single_uncertainty(report),
            "evidence": self._single_evidence_section(report, authorized_evidence_basis),
            "operational_metrics": metrics_dict,
            "disclaimer": (
                f"This response was produced by a single configured model execution "
                f"({report.engine_id}). No second, independent model interpretation "
                "was run for this turn, so no cross-model agreement, disagreement, "
                "or consensus claim applies."
            ),
        }

    @staticmethod
    def _single_uncertainty(report: IVEReport) -> dict:
        return {"reported": list(report.uncertainty)}

    @staticmethod
    def _single_evidence_section(report: IVEReport, authorized_evidence_basis) -> list[dict]:
        # Structural, duck-typed read: each item is expected to carry
        # `candidate_id`, `content`, `title`, `source_identity`, `page` and
        # `chunk_id` — the exact fields the executed engine itself received.
        index = {item.candidate_id: item for item in authorized_evidence_basis}
        rows: list[dict] = []
        seen: set[str] = set()
        for claim in report.claims:
            for doc_id in claim.evidence_document_ids:
                if doc_id in seen:
                    continue
                item = index.get(doc_id)
                if item is None:
                    # Cited by the report but not in the authorized basis —
                    # excluded outright, never resolved against anything wider.
                    continue
                seen.add(doc_id)
                rows.append(
                    {
                        "document_id": item.candidate_id,
                        "title": item.title,
                        "source": item.source_identity,
                        "page": item.page,
                        "chunk_id": item.chunk_id,
                        "excerpt": item.content[:_EXCERPT_CHARS].strip(),
                        "claim_linkage": claim.statement,
                    }
                )
        return rows
