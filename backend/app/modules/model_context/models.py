"""Product Model Context vocabulary (v0.1).

A `ModelContextAssembly` is a PRODUCT object. It states what structured
material is ALLOWED TO ENTER model execution for one turn, after governance has
already run. It is not an epistemic authority: it decides nothing about whether
a candidate is true, admitted, rejected, unknown, authoritative or sufficient.

Two responsibilities are kept strictly apart and are never substituted for one
another:

    GOVERNANCE            decides admission        (upstream, not here)
    MODEL CONTEXT         enforces exposure        (here)

Membership in `ModelContextAssembly.evidence` therefore means exactly one
thing: THIS CANDIDATE WAS ADMITTED UPSTREAM AND INCLUDED IN MODEL CONTEXT. It
is not an admission the Builder created, and `EvidenceContextItem` carries no
disposition, authority, confidence or score field through which it could be
read as one.

Segment vocabulary. The canonical contract names five conceptual segment
classes. At v0.1 only two have a payload here — EVIDENCE and USER_INPUT — and
the other three have NO FIELD ANYWHERE IN THIS MODULE, so they cannot be
carried, defaulted or fabricated. MODEL_OUTPUT in particular is structurally
impossible as same-turn input: the assembly is built strictly before model
execution and has nowhere to put a model answer. The full vocabulary is
declared so the partition is recorded rather than implied, and the two tuples
below state which half is implemented and which half is deferred.

This module imports the standard library only. No Core, Core Adapter,
governed-evidence, admission, provenance, retrieval, provider, renderer,
container or transport entry point is reachable from here, so no governance
authority and no provider detail can be reached through Product code by way of
this package. The one governance value it needs — the disposition label that
permits exposure — is held below as a plain string and only ever compared, so
this module never imports the vocabulary that defines it.

No value in this module is derived from a wall clock, a UUID or a random
source, and no instance identifier is minted: the identity fields below are
fixed contract literals, and every other value is carried verbatim from an
input the caller already holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MODEL_CONTEXT_CONTRACT_ID = "ION_MODEL_CONTEXT_ASSEMBLY_V0_1"
MODEL_CONTEXT_VERSION = "0.1"

# The single normalization the Product already applies to the user question
# before this module ever sees it. Recorded as a fixed contract literal so the
# rule is STATED rather than assumed. The Builder verifies that the supplied
# question already satisfies it; it never applies it, and never rewrites a query.
QUESTION_NORMALIZATION_STRIP = "STRIP"

# The upstream Product disposition that alone permits exposure. Held as a plain
# string so this module never imports the governance vocabulary that defines it;
# the upstream enum subclasses `str`, so equality reads its value directly.
DISPOSITION_ADMITTED = "ADMITTED"


class ModelContextBuildError(ValueError):
    """Raised whenever a Model Context cannot be assembled as contracted.

    Every failure is closed. A missing projection for an ADMITTED candidate, a
    duplicate identity, an empty admitted basis or a malformed input raises
    here; none of them is ever downgraded into a partially populated assembly,
    and none is ever converted into a governance verdict.

    This is a module-local error on purpose. The module is unwired at v0.1, so
    it introduces no transport stage and no mapping onto the core error
    taxonomy; that is a later wiring decision, not this contract's business.
    """


class ModelContextSegmentClass(str, Enum):
    """The canonical segment vocabulary, complete.

    Declaring all five records the partition; it does not implement it. See
    `IMPLEMENTED_SEGMENT_CLASSES` / `DEFERRED_SEGMENT_CLASSES` below, and note
    that no dataclass in this module has a field for any deferred class.
    """

    EVIDENCE = "EVIDENCE"
    USER_INPUT = "USER_INPUT"
    DIALOGUE_INSTRUCTION = "DIALOGUE_INSTRUCTION"
    CONVERSATION_MEMORY = "CONVERSATION_MEMORY"
    MODEL_OUTPUT = "MODEL_OUTPUT"


# The two classes that carry a payload at v0.1, because a runtime input for each
# actually exists: the ADMITTED governed basis, and the normalized question.
IMPLEMENTED_SEGMENT_CLASSES = (
    ModelContextSegmentClass.EVIDENCE,
    ModelContextSegmentClass.USER_INPUT,
)

# Deferred because no runtime input exists to fill them, not because they are
# unwanted: there is no Adaptive Dialogue, no session state and no conversation
# history in the current request path, and a model answer does not exist yet at
# the point this assembly is built. Fabricating any of them would invent
# material the turn never produced.
DEFERRED_SEGMENT_CLASSES = (
    ModelContextSegmentClass.DIALOGUE_INSTRUCTION,
    ModelContextSegmentClass.CONVERSATION_MEMORY,
    ModelContextSegmentClass.MODEL_OUTPUT,
)


class ModelContextCoverageState(str, Enum):
    """ADMITTED BASIS INCLUSION COVERAGE — nothing else.

    This states only whether the upstream ADMITTED basis was fully included in
    this assembly. It is NOT evidence sufficiency, answerability, authority,
    confidence or relevance, and it must never be read as any of them.

    PARTIAL, NONE and NOT_APPLICABLE are declared so the vocabulary is complete
    for later lawful sizing or direct-response work. At v0.1 the Builder emits
    COMPLETE only: it performs no sizing, and both causes of a lesser value —
    an empty admitted basis, and an ADMITTED candidate with no projection —
    fail closed before coverage is ever computed.
    """

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NONE = "NONE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, kw_only=True)
class CandidateContentProjection:
    """One submitted candidate's model-facing values, as plain data.

    This is the ONLY channel through which content reaches a Model Context. It
    carries exactly the fields a model is shown and nothing else: no Evidence
    metadata, no provenance package, no fingerprint, no native governance
    object, no `EvidenceRecord.claim`. Those are governance material, and a
    binding claim is not source text — neither has any field here to enter
    through.

    Field types mirror the measured `ContextDocument` shape verbatim, including
    `page` being either a string or an integer, so the caller projects rather
    than converts.

    The caller is NOT required to pre-filter these to the admitted set. A
    projection whose `document_id` is not ADMITTED is a legitimate input that
    is simply never exposed.
    """

    document_id: str
    content: str
    title: str
    source_identity: str
    page: str | int | None = None
    chunk_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class EvidenceContextItem:
    """One EVIDENCE-segment item: an ADMITTED candidate, exposed verbatim.

    `candidate_id` is the upstream governed identity. The remaining fields are
    byte-for-byte copies of the matching projection — never rewritten,
    summarized, normalized, truncated or re-derived into a different claim.

    There is deliberately no disposition, authority, confidence or score field.
    Membership in `ModelContextAssembly.evidence` is the whole statement, and
    it is a statement about what upstream governance already decided.
    """

    candidate_id: str
    content: str
    title: str
    source_identity: str
    page: str | int | None = None
    chunk_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class ModelContextCoverage:
    """How much of the ADMITTED basis this assembly includes. Counts only.

    Every field here is derived from two identity sets — admitted and included.
    Nothing is read from the question, from scores, from claims, from provider
    output or from any model output to compute it, and there is no field in
    which a sufficiency judgement could be recorded.
    """

    state: ModelContextCoverageState
    admitted_count: int
    included_count: int
    omitted_candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ModelContextAssembly:
    """The complete, provider-neutral Model Context for one turn.

    Immutable, deterministic, and free of any runtime-generated identifier: the
    two identity fields are fixed contract literals, not a per-instance id.

    USER_INPUT and EVIDENCE are separate fields of different types, so the user
    question can never be read as evidence and no evidence item can be read as
    user input.

    Deliberately absent, with no field to carry them: model output, provider
    prompts, provider messages, the system prompt, dialogue instructions,
    conversation memory, retrieval metadata, native governance objects and
    AskResult data. Provider serialization is a downstream concern; this
    assembly is provider-neutral and names no provider.
    """

    question: str
    question_normalization: str
    question_id: str
    context_pack_id: str
    evidence: tuple[EvidenceContextItem, ...]
    coverage: ModelContextCoverage
    model_context_contract_id: str = MODEL_CONTEXT_CONTRACT_ID
    model_context_version: str = MODEL_CONTEXT_VERSION

    def __post_init__(self) -> None:
        # v0.1 law, enforced structurally rather than by convention: no
        # construction path — Builder or caller — can produce a USER_INPUT-only
        # Model Context. On a retrieval-required factual turn that would be the
        # silent fallback to unrestricted factual generation the contract
        # forbids, and the current runtime cannot identify any other turn kind.
        if self.evidence == ():
            raise ModelContextBuildError(
                "v0.1 forbids a Model Context with no evidence: a USER_INPUT-only "
                "assembly is not a lawful model context for this runtime"
            )
