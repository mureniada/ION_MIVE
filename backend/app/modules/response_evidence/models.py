"""Product Response Evidence vocabulary (v0.1).

A `ResponseEvidenceProjection` is a PRODUCT object. It states what evidence a
response is ALLOWED TO PRESENT, after model execution has already happened. It
is not an epistemic authority: it decides nothing about whether a candidate is
true, admitted, rejected, unknown, authoritative, sufficient or relevant.

Three responsibilities are kept strictly apart and are never substituted for
one another:

    GOVERNANCE            decides admission        (upstream, not here)
    MODEL CONTEXT         enforces exposure        (upstream, not here)
    RESPONSE EVIDENCE     enforces presentation    (here)

Membership in `ResponseEvidenceProjection.evidence` therefore means exactly one
thing: THIS CANDIDATE WAS PRESENT IN THE AUTHORIZED MODEL CONTEXT BASIS AND WAS
REFERENCED BY THE RESPONSE. It is not an admission this module created, not a
statement that the reference is correct, and not a statement that the evidence
supports anything. `RenderedEvidenceItem` carries no disposition, authority,
confidence, sufficiency or score field through which it could be read as one.

The two central laws this vocabulary exists to hold:

    MODEL OUTPUT IS NOT EVIDENCE.
    A MODEL MAY REQUEST A REFERENCE. A MODEL MAY NOT CREATE EVIDENCE IDENTITY.

Both are enforced structurally rather than by convention. Every content field
of a `RenderedEvidenceItem` is copied from the authorized basis, and the only
model-originated values that can enter are `candidate_id` — used solely to look
an existing identity UP, never to mint one — and `claim_linkage`, which is held
in its own field and is never merged into source material.

The authorized basis. The narrowest truthful authority for the statement "this
evidence was actually exposed to the model" is the Model Context evidence
segment, whose items carry `candidate_id`, `content`, `title`,
`source_identity`, `page` and `chunk_id`. The retrieved evidence list, the
Context Pack and the governed ADMITTED set are all deliberately NOT that
authority: each is a superset of, or unrelated to, what a model actually read,
and ADMITTED stops equalling EXPOSED the moment lawful context sizing exists. A
candidate no model read must never be presented as the basis of that model's
response.

Excerpting is presentation, never governance. `source_content` holds the
authorized basis content verbatim and remains the authoritative field.
`excerpt` is an explicitly marked, deterministic, presentation-only derivation
of it, and `excerpt_rule`, `truncated` and `source_length` exist so that a
shortened presentation can never be mistaken for the whole source. Those four
fields are checked against `source_content` at construction, so no construction
path — projector or caller — can publish a rewritten excerpt, a false
`truncated` flag or an undeclared rule.

This module imports the standard library only. No Core, Core Adapter,
governed-evidence, model-context, admission, provenance, retrieval, provider,
MIVE, IVE, renderer, container or transport entry point is reachable from here,
so no governance authority, no comparison semantics and no provider detail can
be reached through Product code by way of this package.

No value in this module is derived from a wall clock, a UUID or a random
source, and no instance identifier is minted: the identity fields below are
fixed contract literals, and every other value is carried verbatim from an
input the caller already holds.
"""

from __future__ import annotations

from dataclasses import dataclass

RESPONSE_EVIDENCE_CONTRACT_ID = "ION_RESPONSE_EVIDENCE_PROJECTION_V0_1"
RESPONSE_EVIDENCE_VERSION = "0.1"

# The single presentation transformation this contract knows at v0.1, named so
# that the rule is STATED on every item rather than implied by its length.
EXCERPT_RULE_PREFIX_CHARS_240_V0_1 = "PREFIX_CHARS_240_V0_1"
EXCERPT_PREFIX_CHARS = 240

# The one exclusion reason this contract can record. It is deliberately narrow
# and deliberately NOT a governance word: a reference that does not resolve says
# something about the RESPONSE, not about the candidate's admission state. The
# governance and accounting vocabularies — REJECTED, UNKNOWN, NOT_SUBMITTED —
# belong upstream and have no representation anywhere in this module.
UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS = "NOT_IN_AUTHORIZED_MODEL_CONTEXT_BASIS"


class ResponseEvidenceProjectionError(ValueError):
    """Raised whenever a response evidence projection cannot be built as contracted.

    A malformed authorized basis, a duplicate or ambiguous basis identity, a
    malformed reference request or an inconsistent excerpt raises here. None is
    ever downgraded into a partially populated projection, and none is ever
    converted into a governance verdict.

    A well-formed reference that simply does not resolve is NOT one of these: it
    is recorded as an `UnresolvedReference` and the projection still completes.
    Refusing the whole response because a model cited one identity it was not
    shown would convert a presentation fact into a verdict.

    This is a module-local error on purpose. The module is unwired at v0.1, so
    it introduces no transport stage and no mapping onto the core error
    taxonomy; that is a later wiring decision, not this contract's business.
    """


@dataclass(frozen=True, kw_only=True)
class EvidenceReferenceRequest:
    """One request to PRESENT an already-existing evidence identity.

    This is the only channel through which model or comparison output reaches a
    projection, and it carries exactly two plain values.

    `candidate_id` is a REQUEST TO RESOLVE, never a creation. Nothing downstream
    treats it as evidence identity until it has been matched, by value, against
    the authorized basis.

    `claim_linkage` is response text associated with the reference. IT IS NOT
    EVIDENCE. It is never parsed epistemically, never read for authority, never
    matched against source material and never merged into it.

    The contract is deliberately neutral about where a reference came from. It
    carries no comparison category, no engine identity, no claim identifier and
    no confidence, so the category-selection policy of any particular caller
    cannot be baked into this Product contract.
    """

    candidate_id: str
    claim_linkage: str


@dataclass(frozen=True, kw_only=True)
class RenderedEvidenceItem:
    """One presentable evidence row: an exposed candidate, referenced by a response.

    `candidate_id` is the upstream identity, copied from the authorized basis
    rather than from the reference request, so a request can never introduce an
    identity the basis does not already hold.

    `title`, `source_identity`, `page`, `chunk_id` and `source_content` are
    byte-for-byte copies of the authorized basis item — never rewritten,
    summarized, normalized, re-derived or repaired.

    `claim_linkage` is the only model-originated text here and lives in its own
    field, structurally separate from `source_content`.

    There is deliberately no disposition, authority, sufficiency, confidence,
    relevance, score, provenance or fingerprint field. Membership in a
    projection's `evidence` is the whole statement, and it is a statement about
    exposure and reference, not about truth.
    """

    candidate_id: str
    title: str
    source_identity: str
    source_content: str
    excerpt: str
    excerpt_rule: str
    truncated: bool
    source_length: int
    claim_linkage: str
    page: str | int | None = None
    chunk_id: str | None = None

    def __post_init__(self) -> None:
        # v0.1 law, enforced structurally rather than by convention: the excerpt
        # is a marked, deterministic derivation of `source_content` and nothing
        # else. No construction path can publish a rewritten excerpt, a false
        # `truncated` flag, a wrong `source_length` or an undeclared rule, so an
        # excerpt can never be passed off as the whole source.
        if self.excerpt_rule != EXCERPT_RULE_PREFIX_CHARS_240_V0_1:
            raise ResponseEvidenceProjectionError(
                f"v0.1 knows one excerpt rule, {EXCERPT_RULE_PREFIX_CHARS_240_V0_1}; "
                f"found {self.excerpt_rule!r}"
            )
        if self.source_length != len(self.source_content):
            raise ResponseEvidenceProjectionError(
                f"source_length {self.source_length} does not match the "
                f"{len(self.source_content)} characters of source_content"
            )
        if self.excerpt != self.source_content[:EXCERPT_PREFIX_CHARS]:
            raise ResponseEvidenceProjectionError(
                "excerpt is not the contracted prefix of source_content; "
                "rendering may shorten a presentation, never rewrite the source"
            )
        if self.truncated != (len(self.source_content) > EXCERPT_PREFIX_CHARS):
            raise ResponseEvidenceProjectionError(
                f"truncated {self.truncated!r} misstates whether source_content "
                f"({len(self.source_content)} characters) exceeds "
                f"{EXCERPT_PREFIX_CHARS}"
            )


@dataclass(frozen=True, kw_only=True)
class UnresolvedReference:
    """A reference the authorized basis does not hold. Presentation accounting only.

    This records that a response asked to present an identity it was not shown,
    so the exclusion is observable instead of silent. It is NOT a verdict about
    the candidate: `reason` is a presentation fact, and this type has no field in
    which a governance disposition could be recorded.

    In particular this is never REJECTED, UNKNOWN, NOT_SUBMITTED or UNADMITTED.
    Those are upstream governance and accounting states, they describe something
    this module cannot observe, and they are absent from this module entirely.
    """

    candidate_id: str
    claim_linkage: str
    reason: str = UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS


@dataclass(frozen=True, kw_only=True)
class ResponseEvidenceProjection:
    """The complete, provider-neutral response evidence projection for one response.

    Immutable, deterministic, and free of any runtime-generated identifier: the
    two identity fields are fixed contract literals, not a per-instance id.

    `evidence` and `unresolved_references` are separate fields of different
    types, so a reference that resolved can never be read as one that did not,
    and neither can be read as the other's opposite verdict.

    Deliberately absent, with no field to carry them: model output objects,
    comparison results, report objects, provider prompts, provider identity,
    the governed evidence set, the Model Context assembly itself, retrieval
    metadata, scores, and AskResult or API data. Transport serialization is a
    downstream concern; this projection is provider- and transport-neutral and
    names no provider.
    """

    evidence: tuple[RenderedEvidenceItem, ...]
    unresolved_references: tuple[UnresolvedReference, ...]
    response_evidence_contract_id: str = RESPONSE_EVIDENCE_CONTRACT_ID
    response_evidence_version: str = RESPONSE_EVIDENCE_VERSION
