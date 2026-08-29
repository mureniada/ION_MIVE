"""Product Turn Record vocabulary (v0.1).

A `TurnRecord` is a PRODUCT object. It states WHAT HAPPENED during one turn,
after that turn has closed. It is not an epistemic authority: it decides
nothing about whether a candidate is true, admitted, rejected, unknown,
authoritative, sufficient or relevant, and it is not itself evidence.

Four responsibilities are kept strictly apart and are never substituted for one
another:

    GOVERNANCE            decides admission        (upstream, not here)
    RETRIEVAL             returns candidates       (upstream, not here)
    COMPARISON            compares reports         (upstream, not here)
    TURN RECORD           records closure facts    (here)

The central law this vocabulary exists to hold:

    ONE SUCCESSFULLY COMPLETED TURN = ONE IMMUTABLE TURN RECORD.

Every value in a `TurnRecord` is carried verbatim from a fact the caller
already observed during the turn. Nothing here is computed from source
material, re-derived from a provider answer, or recomputed from an upstream
artifact. In particular the governed basis is bound BY REFERENCE — identity
plus counts — and never copied, so a Turn Record can never become a second
evidence authority.

Structural absence. The two later Product layers that do not execute in a turn
today have NO FIELD ANYWHERE IN THIS MODULE, and neither does session state,
conversation state, a parent turn, a dialogue instruction, an execution policy,
a rendered answer, an event trace or any evidence content. They are absent
rather than nullable on purpose: a permanently-`None` field would assert that a
layer ran and produced nothing, which is not what happened. Absence means
absence.

This module imports the standard library only. No Core, orchestrator, Core
Adapter, governed-evidence, admission, provenance, retrieval, provider, MIVE,
renderer, container, transport or persistence entry point is reachable from
here, so no governance authority, no comparison semantics, no provider detail
and no storage capability can be reached through Product code by way of this
package, and this package cannot reach back into Core.

No value in this module is derived from a wall clock, a UUID or a random
source, and no instance identifier is minted: the identity fields below are
either fixed contract literals or values the caller supplies verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

TURN_RECORD_CONTRACT_ID = "ION_TURN_RECORD_V0_1"
TURN_RECORD_VERSION = "0.1"

# The turn identity rule, recorded as a fixed literal so it is STATED rather
# than assumed. The runtime's `request_id` already uniquely identifies one turn;
# this contract binds to it verbatim and mints nothing of its own.
TURN_IDENTITY_BASIS_REQUEST_ID = "CORE_ASK_REQUEST_ID_V0_1"

# The single normalization the Product already applies to the user question
# before this module ever sees it. Recorded as a fixed contract literal so the
# rule is STATED. The materializer verifies that the supplied question already
# satisfies it; it never applies it, and never rewrites a question.
QUESTION_NORMALIZATION_STRIP = "STRIP"


class TurnRecordMaterializationError(ValueError):
    """Raised whenever a Turn Record cannot be materialized as contracted.

    Every failure is closed. A missing runtime fact, a malformed identity, a
    disagreeing context-pack identity, a duplicate engine identity or an
    inconsistent closure state raises here; none is ever downgraded into a
    partially populated record, and none is ever converted into a governance
    verdict or an evidence state.

    This is a module-local error on purpose. It introduces no transport stage
    and no mapping onto the core error taxonomy; how a caller closes a turn
    whose record cannot be materialized is a later wiring decision, not this
    contract's business.
    """


class TurnClosureState(str, Enum):
    """How one turn ended. Exactly two states, because the runtime has two.

    COMPLETED and FAILED are both truthful for the observed runtime. At v0.1
    only COMPLETED is produced by the materializer: live failure closure is a
    later, separately authorized step, so a FAILED record cannot yet arise from
    a real turn.

    There is deliberately no CLARIFY, WAITING_FOR_USER, DIRECT_RESPONSE or
    ABORTED member. Nothing in the current runtime can produce any of them, and
    declaring one would record a turn outcome the system cannot reach.
    """

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, kw_only=True)
class GovernedEvidenceBinding:
    """The governed basis of one turn, BOUND BY REFERENCE — never duplicated.

    This carries identity and counts only. There is deliberately no field for
    an admitted, rejected or unknown entry, no native record, validation or
    transition, no fingerprint, no disposition and no evidence content, so a
    reader cannot mistake this binding for the governed evidence itself and no
    second evidence authority can be constructed from it.

    There is also no instance identifier. The upstream governed set has none —
    its identity is a deterministic contract identity plus the question and
    context-pack binding below — and minting one here would invent a fact the
    runtime never produced.
    """

    governed_evidence_set_id: str
    governed_evidence_set_version: str
    question_id: str
    context_pack_id: str
    backend_id: str
    mapping_profile_id: str
    adapter_id: str
    adapter_version: str
    retrieved_count: int
    submitted_count: int
    governed_count: int


@dataclass(frozen=True, kw_only=True)
class ModelExecutionBinding:
    """One model execution that actually ran during this turn.

    `requested_model` is the model the Product ASKED FOR. It is never presented
    as the model a provider reported running: the current runtime discards the
    provider-reported identity before it reaches any Product object, so there is
    no field here in which that claim could be made.

    Deliberately absent, with no field to carry them: raw provider output, the
    report body, claims, concepts, relations, evidence identifiers, confidence,
    uncertainty, an execution profile, an arm or policy label, and any retry,
    fallback, dispatch or termination policy. A measurement the runtime did not
    produce stays `None` rather than being estimated into existence.
    """

    engine_id: str
    provider: str
    requested_model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    usage_is_estimated: bool = False
    estimated_cost: float | None = None


@dataclass(frozen=True, kw_only=True)
class TurnConfigurationBinding:
    """The smallest configuration binding that makes one turn auditable.

    This is a closed field set, not a configuration dump. There is deliberately
    no field for a store URL, an API key, an environment mapping or the settings
    object itself, so no secret and no infrastructure endpoint has anywhere to
    enter.

    Provider model names are NOT here. The model a turn actually asked for
    belongs to the execution that asked for it, and lives on
    `ModelExecutionBinding` instead.
    """

    effective_top_k: int
    context_char_budget: int
    retrieval_collection: str
    app_version: str
    pricing_as_of: str


@dataclass(frozen=True, kw_only=True)
class TurnFailure:
    """Why a turn failed. Operational fact only — never an evidence state.

    An operational failure is NOT an evidence UNKNOWN, and this type has no
    field in which a governance disposition, an admission state or a
    sufficiency judgement could be recorded.

    `error_stage` is nullable because the runtime genuinely has failure paths
    that carry no stage; recording one for them would invent it. `error_message`
    is nullable for the same reason and is intended only for already-controlled
    Product text — never a raw provider payload.

    At v0.1 no live turn produces this type: failure closure is deferred. It is
    declared so the Product vocabulary is complete and so the shape is fixed
    before it is wired.
    """

    error_type: str
    error_stage: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, kw_only=True)
class TurnRecord:
    """The complete, immutable, provider- and transport-neutral record of one turn.

    Deterministic: every field is carried verbatim from a fact supplied by the
    caller. The contract identity fields are fixed literals, not a per-instance
    id, and `turn_id` is the runtime's own turn identity rather than anything
    minted here.

    Deliberately absent, with no field to carry them: the rendered answer, the
    transport result, the comparison result object, the report objects, raw
    provider output, evidence content, the governed evidence set itself, the
    progress or event trace, session and conversation identity, a parent turn,
    dialogue instructions, an execution profile, and any binding for a later
    Product layer that does not execute in a turn today.

    `pipeline_latency_ms` is named for exactly what the runtime measures: the
    span the Product already times, which ENDS BEFORE RENDERING. It is not an
    end-to-end or total turn latency and must never be read as one.
    """

    turn_id: str
    question: str
    closure_state: TurnClosureState
    turn_started_at: str
    turn_closed_at: str
    retrieval_latency_ms: float
    comparison_latency_ms: float
    pipeline_latency_ms: float
    context_pack_id: str
    governed_evidence: GovernedEvidenceBinding
    model_executions: tuple[ModelExecutionBinding, ...]
    mive_overall_status: str
    configuration: TurnConfigurationBinding
    failure: TurnFailure | None = None
    turn_identity_basis: str = TURN_IDENTITY_BASIS_REQUEST_ID
    question_normalization: str = QUESTION_NORMALIZATION_STRIP
    turn_record_contract_id: str = TURN_RECORD_CONTRACT_ID
    turn_record_version: str = TURN_RECORD_VERSION

    def __post_init__(self) -> None:
        # v0.1 laws, enforced structurally rather than by convention: no
        # construction path — materializer or caller — can produce a record
        # that misstates how its turn ended, or one whose two context-pack
        # identities disagree.
        if not isinstance(self.closure_state, TurnClosureState):
            raise TurnRecordMaterializationError(
                "closure_state must be a TurnClosureState, "
                f"found {self.closure_state!r}"
            )
        if self.closure_state is TurnClosureState.COMPLETED and self.failure is not None:
            raise TurnRecordMaterializationError(
                "a COMPLETED turn carries no failure; a record stating both "
                "would make success and failure indistinguishable"
            )
        if self.closure_state is TurnClosureState.FAILED and self.failure is None:
            raise TurnRecordMaterializationError(
                "a FAILED turn must carry its failure; a bare FAILED record "
                "would lose the only fact that distinguishes it"
            )
        if self.context_pack_id != self.governed_evidence.context_pack_id:
            raise TurnRecordMaterializationError(
                f"context_pack_id {self.context_pack_id!r} does not match the "
                f"governed basis {self.governed_evidence.context_pack_id!r}; "
                "the turn and its governed basis must name one Context Pack"
            )
