"""LIVE-1 coherence pure feature extraction, v0.2 infrastructure only.

Deterministic StageARubricAssessment -> CoherenceFeatureVector mapping.
Reads only fields already present on StageARubricAssessment; never
inspects provenance, group/arm identity, Stage B, or source answer text
(S8) -- there is no such field to read in the first place. No
changed_count is computed (S7): only the six mechanically unambiguous R2
counts (per-status counts plus non_preserved, the self-defining
complement of preserved).

No network. No provider SDK import. Not wired into container.py/Core.ask().
"""

from __future__ import annotations

from ...core.models import CoherenceFeatureVector, StageARubricAssessment


def extract_coherence_features(assessment: StageARubricAssessment) -> CoherenceFeatureVector:
    claims = assessment.material_claims
    total = len(claims)
    preserved = sum(1 for c in claims if c.status == "PRESERVED")
    added = sum(1 for c in claims if c.status == "ADDED")
    removed = sum(1 for c in claims if c.status == "REMOVED")
    modified = sum(1 for c in claims if c.status == "MODIFIED")
    contradicted = sum(1 for c in claims if c.status == "CONTRADICTED")
    return CoherenceFeatureVector(
        r1=assessment.core_conclusion,
        r4=assessment.epistemic_stance,
        r5=assessment.material_contradiction,
        total_claim_count=total,
        preserved_count=preserved,
        added_count=added,
        removed_count=removed,
        modified_count=modified,
        contradicted_count=contradicted,
        non_preserved_count=total - preserved,
        observed_r6=assessment.overall_semantic_effect,
    )
