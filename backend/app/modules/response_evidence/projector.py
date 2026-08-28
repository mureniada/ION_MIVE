"""Deterministic, fail-closed projection of response evidence (v0.1).

Pure: no I/O, no clock, no randomness, no persistence, no network, no provider
call, no environment read. It imports the standard library and this package's
own vocabulary, nothing else.

What it does, exactly: it takes the authorized Model Context evidence basis —
the record of what was actually exposed to the model — plus the reference
requests a response made, and it presents ONLY those candidates whose identity
the basis already holds, copying their content verbatim.

What it does NOT do, and must not be extended to do without a new
authorization: it does not govern, admit, reject, promote, validate, resolve
provenance, recompute a fingerprint, retrieve, size a context, rank, re-order,
rewrite, judge sufficiency, judge relevance, judge whether a reference is
correct, or decide which comparison categories a response draws references
from.

    GOVERNANCE DECIDES ADMISSION.
    MODEL CONTEXT ENFORCES EXPOSURE.
    RESPONSE EVIDENCE PROJECTION ENFORCES PRESENTATION.

The three are never substituted. In particular a reference the basis does not
hold is NOT an error and NOT a verdict: it is excluded from the evidence and
recorded as an `UnresolvedReference`, so the exclusion is observable rather
than silent, and the rest of the response still projects. Refusing the whole
projection there would let one model reference decide the fate of a response;
labelling it REJECTED, UNKNOWN or NOT_SUBMITTED would invent a governance
conclusion out of a presentation fact. There is deliberately no branch here
that does either.

Two input disciplines, deliberately asymmetric:

    THE AUTHORIZED BASIS is read STRUCTURALLY, by attribute, rather than by
    importing the type that defines it, so a real Model Context evidence item is
    consumed verbatim without this package importing the module that produces
    it, and without duplicating one line of exposure or governance semantics. It
    reads exactly six values from each item — `candidate_id`, `content`,
    `title`, `source_identity`, `page` and `chunk_id` — and reaches for nothing
    else, so no coverage state, assembly field or governance object is reachable
    through a basis item.

    A REFERENCE REQUEST must be the declared `EvidenceReferenceRequest` type.
    Requiring it is how model and comparison material is kept out: nothing but
    the two declared plain values can be handed in, so a report object, a
    comparison entry, a confidence, a score or an engine identity has no channel
    into a projection at all.

Category neutrality is a contract requirement, not an oversight. This module
never names, imports or inspects a comparison category — agreements, partial
agreements, conflicts, unique findings or any other. The caller supplies
category-neutral reference requests. That keeps the known live-renderer
category-selection gap (GAP-RENDER-01) out of this Product contract entirely,
and leaves the question of which categories a response draws references from to
a later, separately authorized reference-extraction step.

Every check below is fail-closed. A violated invariant raises
`ResponseEvidenceProjectionError`; none is ever downgraded into a partially
populated projection.
"""

from __future__ import annotations

from typing import Any, Sequence

from .models import (
    EXCERPT_PREFIX_CHARS,
    EXCERPT_RULE_PREFIX_CHARS_240_V0_1,
    UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS,
    EvidenceReferenceRequest,
    RenderedEvidenceItem,
    ResponseEvidenceProjection,
    ResponseEvidenceProjectionError,
    UnresolvedReference,
)

RESPONSE_EVIDENCE_PROJECTOR_ID = "ION_RESPONSE_EVIDENCE_PROJECTOR_V0_1"
RESPONSE_EVIDENCE_PROJECTOR_VERSION = "0.1"

_MISSING = object()
_WHAT_BASIS = "authorized basis item"


# --------------------------------------------------------------------------- #
# fail-closed primitives
# --------------------------------------------------------------------------- #
def _fail(message: str) -> None:
    raise ResponseEvidenceProjectionError(message)


def _attr(obj: Any, name: str, what: str) -> Any:
    """Read one field of an authorized basis item, or refuse. Never defaulted."""
    value = getattr(obj, name, _MISSING)
    if value is _MISSING:
        _fail(f"{what} does not expose the required field: {name}")
    return value


def _identity(value: Any, what: str) -> str:
    """Require a non-empty string identity, taken verbatim. Nothing is cased."""
    if not isinstance(value, str) or not value:
        _fail(f"{what} must be a non-empty string, found {value!r}")
    return value


def _string(value: Any, what: str) -> str:
    """Require a string value, taken verbatim. An empty one is legal.

    Type only. Whether a title or a source identity may be empty is a decision
    the exposed material already carries; this module copies, it does not police
    corpus content.
    """
    if not isinstance(value, str):
        _fail(f"{what} must be a string, found {type(value).__name__}")
    return value


def _sequence(value: Any, what: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        _fail(f"{what} must be supplied as a tuple or list, found {type(value).__name__}")
    return tuple(value)


def _page(value: Any, what: str) -> str | int | None:
    """Carry the exposed page domain verbatim: str | int | None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    _fail(f"{what} must be a string, an integer or null, found {type(value).__name__}")
    return None


def _chunk_id(value: Any, what: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    _fail(f"{what} must be a string or null, found {type(value).__name__}")
    return None


# --------------------------------------------------------------------------- #
# projection
# --------------------------------------------------------------------------- #
def project_response_evidence(
    *,
    authorized_basis: Sequence[Any],
    reference_requests: Sequence[EvidenceReferenceRequest],
) -> ResponseEvidenceProjection:
    """Project the evidence one response may present.

    `authorized_basis` is the Model Context evidence segment for the turn that
    produced the response — the record of what was ACTUALLY EXPOSED TO THE
    MODEL. Each item is read structurally and must expose `candidate_id`,
    `content`, `title`, `source_identity`, `page` and `chunk_id`; a real Model
    Context evidence item satisfies this without any adaptation. The retrieved
    evidence list, the Context Pack and the governed ADMITTED set are NOT this
    basis and must not be passed as one: each can contain a candidate no model
    read, and presenting one as the ground of a model's answer is exactly what
    this contract exists to prevent.

    `reference_requests` are the identities the response asked to present,
    paired with the response text each reference is associated with. They MAY
    name identities the basis does not hold; those produce no evidence and are
    recorded instead.

    Presentation rows are identified by `(candidate_id, claim_linkage)`: one
    exposed candidate may legitimately support several distinct linkages and
    then appears once per linkage, while an exact repeat of a request is
    collapsed to its first occurrence. Request order is preserved throughout —
    nothing here re-orders, ranks or prioritizes.

    Raises `ResponseEvidenceProjectionError` on every contract violation. A
    well-formed but unresolvable reference is not one.
    """
    # --- the authorized basis, indexed by its OWN identity ---------------- #
    basis_by_id: dict[str, dict[str, Any]] = {}
    for item in _sequence(authorized_basis, "authorized basis"):
        candidate_id = _identity(
            _attr(item, "candidate_id", _WHAT_BASIS), "authorized basis candidate_id"
        )
        # A repeated identity makes the join ambiguous: two different exposed
        # bodies would answer to one name, and any choice between them would be
        # this module silently deciding which source a response rests on.
        if candidate_id in basis_by_id:
            _fail(
                f"duplicate authorized basis identity: {candidate_id}; the "
                "identity join would be ambiguous"
            )
        what = f"{_WHAT_BASIS} {candidate_id}"
        basis_by_id[candidate_id] = {
            "content": _string(_attr(item, "content", what), f"{what} content"),
            "title": _string(_attr(item, "title", what), f"{what} title"),
            "source_identity": _string(
                _attr(item, "source_identity", what), f"{what} source_identity"
            ),
            "page": _page(_attr(item, "page", what), f"{what} page"),
            "chunk_id": _chunk_id(_attr(item, "chunk_id", what), f"{what} chunk_id"),
        }

    # --- the reference requests, resolved by identity VALUE --------------- #
    # List position is never the identity contract, in either direction.
    evidence: list[RenderedEvidenceItem] = []
    unresolved: list[UnresolvedReference] = []
    seen: set[tuple[str, str]] = set()

    for request in _sequence(reference_requests, "reference requests"):
        if not isinstance(request, EvidenceReferenceRequest):
            _fail(
                "each reference request must be an EvidenceReferenceRequest, "
                f"found {type(request).__name__}"
            )
        candidate_id = _identity(
            request.candidate_id, "reference request candidate_id"
        )
        claim_linkage = _string(
            request.claim_linkage, f"reference request {candidate_id} claim_linkage"
        )

        row_key = (candidate_id, claim_linkage)
        if row_key in seen:
            continue
        seen.add(row_key)

        exposed = basis_by_id.get(candidate_id, _MISSING)
        if exposed is _MISSING:
            # Excluded and recorded. Never dropped, never an error, and never
            # given a governance label: this states something about the
            # response, not about the candidate.
            unresolved.append(
                UnresolvedReference(
                    candidate_id=candidate_id,
                    claim_linkage=claim_linkage,
                    reason=UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS,
                )
            )
            continue

        source_content = exposed["content"]
        evidence.append(
            RenderedEvidenceItem(
                # taken from the BASIS, never from the request: a reference
                # resolves an identity, it does not create one.
                candidate_id=candidate_id,
                # verbatim, in every field: no rewriting, summarizing,
                # normalizing, stripping or re-derivation of any kind.
                title=exposed["title"],
                source_identity=exposed["source_identity"],
                page=exposed["page"],
                chunk_id=exposed["chunk_id"],
                source_content=source_content,
                # presentation only, and explicitly marked as such.
                excerpt=source_content[:EXCERPT_PREFIX_CHARS],
                excerpt_rule=EXCERPT_RULE_PREFIX_CHARS_240_V0_1,
                truncated=len(source_content) > EXCERPT_PREFIX_CHARS,
                source_length=len(source_content),
                # model-originated text, kept in its own field.
                claim_linkage=claim_linkage,
            )
        )

    # An exposed candidate the response never referenced was never looked up
    # above. It is simply not presented, and no code path here labels it.

    return ResponseEvidenceProjection(
        evidence=tuple(evidence),
        unresolved_references=tuple(unresolved),
    )
