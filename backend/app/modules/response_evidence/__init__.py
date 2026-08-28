"""Response Evidence: what evidence a response may present, and on whose authority.

The export list below is deliberately closed. It carries no governance
internal, no admission / promotion / authority / receipt name, no Core Adapter
type, no governed-evidence type, no Model Context type, no comparison category
and no provider name, because this package imports none of them: it depends on
the standard library only. Product code therefore cannot reach governance
authority, exposure authority or comparison semantics through here, and this
package cannot reach back into Core.

The authorized basis is accepted STRUCTURALLY, by attribute, so a real Model
Context evidence item is consumed verbatim without this package importing the
module that defines it, and without duplicating one line of exposure or
governance semantics.

v0.1 is a pure projection module. It is NOT wired into `Core.ask()`, the live
`DeterministicRenderer` is unchanged and still renders from the retrieved
evidence list, no HTTP response carries its output, and it changes no live
orchestrator behaviour. Wiring it — and deciding how a response's references are
extracted, which is where the deferred GAP-RENDER-01 category gap has to be
answered — is a later, separately authorized task.
"""

from .models import (
    EXCERPT_PREFIX_CHARS,
    EXCERPT_RULE_PREFIX_CHARS_240_V0_1,
    RESPONSE_EVIDENCE_CONTRACT_ID,
    RESPONSE_EVIDENCE_VERSION,
    UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS,
    EvidenceReferenceRequest,
    RenderedEvidenceItem,
    ResponseEvidenceProjection,
    ResponseEvidenceProjectionError,
    UnresolvedReference,
)
from .projector import (
    RESPONSE_EVIDENCE_PROJECTOR_ID,
    RESPONSE_EVIDENCE_PROJECTOR_VERSION,
    project_response_evidence,
)

__all__ = [
    "EXCERPT_PREFIX_CHARS",
    "EXCERPT_RULE_PREFIX_CHARS_240_V0_1",
    "RESPONSE_EVIDENCE_CONTRACT_ID",
    "RESPONSE_EVIDENCE_PROJECTOR_ID",
    "RESPONSE_EVIDENCE_PROJECTOR_VERSION",
    "RESPONSE_EVIDENCE_VERSION",
    "UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS",
    "EvidenceReferenceRequest",
    "RenderedEvidenceItem",
    "ResponseEvidenceProjection",
    "ResponseEvidenceProjectionError",
    "UnresolvedReference",
    "project_response_evidence",
]
