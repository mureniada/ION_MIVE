"""Governed Evidence Output: the Product view of one completed governance run.

The export list below is deliberately closed. It carries no governance internal,
no promotion / authority / receipt name, and no Core Adapter type, because this
package imports none of them: it depends on the standard library only. Product
code therefore cannot reach governance mutation authority through here, and this
package cannot reach back into Core.

v0.1 is a pure materialization module. It is NOT wired into `Core.ask()` and
changes no live orchestrator behaviour.
"""

from .materializer import (
    MATERIALIZER_ID,
    MATERIALIZER_VERSION,
    materialize_governed_evidence_set,
)
from .models import (
    ACCOUNTING_STATE_NOT_SUBMITTED,
    GOVERNANCE_COMPLETE,
    GOVERNED_EVIDENCE_SET_ID,
    GOVERNED_EVIDENCE_SET_VERSION,
    CandidateAccounting,
    CandidateAccountingEntry,
    GovernanceDisposition,
    GovernedEvidenceEntry,
    GovernedEvidenceMaterializationError,
    GovernedEvidenceSet,
    MaterializationInput,
)

__all__ = [
    "ACCOUNTING_STATE_NOT_SUBMITTED",
    "GOVERNANCE_COMPLETE",
    "GOVERNED_EVIDENCE_SET_ID",
    "GOVERNED_EVIDENCE_SET_VERSION",
    "MATERIALIZER_ID",
    "MATERIALIZER_VERSION",
    "CandidateAccounting",
    "CandidateAccountingEntry",
    "GovernanceDisposition",
    "GovernedEvidenceEntry",
    "GovernedEvidenceMaterializationError",
    "GovernedEvidenceSet",
    "MaterializationInput",
    "materialize_governed_evidence_set",
]
