"""Model Context: what structured material may enter model execution for a turn.

The export list below is deliberately closed. It carries no governance
internal, no admission / promotion / authority / receipt name, no Core Adapter
type, no governed-evidence type and no provider name, because this package
imports none of them: it depends on the standard library only. Product code
therefore cannot reach governance authority through here, and this package
cannot reach back into Core.

The governed basis is accepted STRUCTURALLY, by attribute, so a real
`GovernedEvidenceSet` is consumed verbatim without this package importing the
module that defines it, and without duplicating one line of governance
semantics.

v0.1 is a pure assembly module. It is NOT wired into `Core.ask()`, no provider
receives its output, and it changes no live orchestrator behaviour. Wiring it —
and deciding how a provider serializes it — is a later, separately authorized
task.
"""

from .builder import (
    MODEL_CONTEXT_BUILDER_ID,
    MODEL_CONTEXT_BUILDER_VERSION,
    build_model_context,
)
from .models import (
    DEFERRED_SEGMENT_CLASSES,
    DISPOSITION_ADMITTED,
    IMPLEMENTED_SEGMENT_CLASSES,
    MODEL_CONTEXT_CONTRACT_ID,
    MODEL_CONTEXT_VERSION,
    QUESTION_NORMALIZATION_STRIP,
    CandidateContentProjection,
    EvidenceContextItem,
    ModelContextAssembly,
    ModelContextBuildError,
    ModelContextCoverage,
    ModelContextCoverageState,
    ModelContextSegmentClass,
)

__all__ = [
    "DEFERRED_SEGMENT_CLASSES",
    "DISPOSITION_ADMITTED",
    "IMPLEMENTED_SEGMENT_CLASSES",
    "MODEL_CONTEXT_BUILDER_ID",
    "MODEL_CONTEXT_BUILDER_VERSION",
    "MODEL_CONTEXT_CONTRACT_ID",
    "MODEL_CONTEXT_VERSION",
    "QUESTION_NORMALIZATION_STRIP",
    "CandidateContentProjection",
    "EvidenceContextItem",
    "ModelContextAssembly",
    "ModelContextBuildError",
    "ModelContextCoverage",
    "ModelContextCoverageState",
    "ModelContextSegmentClass",
    "build_model_context",
]
