"""Turn Record: what happened during one turn, recorded once, immutably.

The export list below is deliberately closed. It carries no governance
internal, no admission / promotion / authority / receipt name, no Core Adapter
type, no governed-evidence type, no comparison category, no provider name and
no persistence handle, because this package imports none of them: it depends on
the standard library only. Product code therefore cannot reach governance
authority, comparison semantics or storage through here, and this package
cannot reach back into Core.

The governed basis is accepted STRUCTURALLY, by attribute, so a real governed
evidence set is bound verbatim — by identity and counts — without this package
importing the module that defines it, and without duplicating one line of
governance semantics. A Turn Record references upstream artifacts; it never
becomes their authority and is never itself evidence.

v0.1 records COMPLETED turns only. The closure vocabulary declares FAILED
because the runtime genuinely fails, but live failure closure is a later,
separately authorized step and no entry point here can produce a FAILED record
from a real turn.

A materialized record is an EPHEMERAL RUNTIME VALUE at v0.1: nothing in this
package writes, logs, serializes or transports it, and no field of it is
carried into the transport result, the rendered answer or the progress stream.
"""

from .materializer import (
    TURN_RECORD_MATERIALIZER_ID,
    TURN_RECORD_MATERIALIZER_VERSION,
    materialize_turn_record,
)
from .models import (
    QUESTION_NORMALIZATION_STRIP,
    TURN_IDENTITY_BASIS_REQUEST_ID,
    TURN_RECORD_CONTRACT_ID,
    TURN_RECORD_VERSION,
    GovernedEvidenceBinding,
    ModelExecutionBinding,
    TurnClosureState,
    TurnConfigurationBinding,
    TurnFailure,
    TurnRecord,
    TurnRecordMaterializationError,
)

__all__ = [
    "QUESTION_NORMALIZATION_STRIP",
    "TURN_IDENTITY_BASIS_REQUEST_ID",
    "TURN_RECORD_CONTRACT_ID",
    "TURN_RECORD_MATERIALIZER_ID",
    "TURN_RECORD_MATERIALIZER_VERSION",
    "TURN_RECORD_VERSION",
    "GovernedEvidenceBinding",
    "ModelExecutionBinding",
    "TurnClosureState",
    "TurnConfigurationBinding",
    "TurnFailure",
    "TurnRecord",
    "TurnRecordMaterializationError",
    "materialize_turn_record",
]
