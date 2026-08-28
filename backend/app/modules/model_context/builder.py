"""Deterministic, fail-closed assembly of a ModelContextAssembly (v0.1).

Pure: no I/O, no clock, no randomness, no persistence, no network, no provider
call, no environment read. It imports the standard library and this package's
own vocabulary, nothing else.

What it does, exactly: it takes a governed basis that upstream already produced
and a set of plain-value candidate projections, and it exposes to model
execution ONLY those candidates the upstream basis already labelled ADMITTED,
copying their content verbatim.

What it does NOT do, and must not be extended to do without a new
authorization: it does not govern, admit, reject, promote, validate, resolve
provenance, recompute a fingerprint, retrieve, size a context, rank, trim,
rewrite a query, judge sufficiency, judge relevance, or decide a turn kind.

    GOVERNANCE DECIDES ADMISSION.
    MODEL CONTEXT BUILDER ENFORCES EXPOSURE.

The two are never substituted. In particular a projection whose identity is not
ADMITTED is a LEGITIMATE INPUT, not an error: the caller is not required to
pre-filter. Such a projection is simply never exposed, and the Builder never
converts that exclusion into REJECTED, UNKNOWN or NOT_SUBMITTED — those are
upstream governance and accounting semantics that this module neither owns nor
reproduces. There is deliberately no branch here that labels an excluded
projection at all.

The governed basis is read STRUCTURALLY, by attribute, rather than by importing
the type that defines it, so this module stays closed against the governance
vocabulary while still accepting the real object verbatim. It reads exactly
three things from it — `question_id`, `context_pack_id` and `admitted` — and
never touches a `rejected` / `unknown` collection, candidate accounting, or any
native governance object carried inside an entry.

Every check below is fail-closed. A violated invariant raises
`ModelContextBuildError`; none is ever downgraded into a partially populated
assembly, and none is ever recorded as reduced coverage.
"""

from __future__ import annotations

from typing import Any, Sequence

from .models import (
    DISPOSITION_ADMITTED,
    QUESTION_NORMALIZATION_STRIP,
    CandidateContentProjection,
    EvidenceContextItem,
    ModelContextAssembly,
    ModelContextBuildError,
    ModelContextCoverage,
    ModelContextCoverageState,
)

MODEL_CONTEXT_BUILDER_ID = "ION_MODEL_CONTEXT_BUILDER_V0_1"
MODEL_CONTEXT_BUILDER_VERSION = "0.1"

_MISSING = object()
_WHAT_BASIS = "governed basis"


# --------------------------------------------------------------------------- #
# fail-closed primitives
# --------------------------------------------------------------------------- #
def _fail(message: str) -> None:
    raise ModelContextBuildError(message)


def _attr(obj: Any, name: str, what: str) -> Any:
    """Read one field of the governed basis, or refuse. Never defaulted."""
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
    """Require a string content value, taken verbatim. An empty one is legal.

    Type only. Whether a title or a source identity may be empty is a decision
    the submitted material already carries; this module copies, it does not
    police corpus content.
    """
    if not isinstance(value, str):
        _fail(f"{what} must be a string, found {type(value).__name__}")
    return value


def _sequence(value: Any, what: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        _fail(f"{what} must be supplied as a tuple or list, found {type(value).__name__}")
    return tuple(value)


def _page(value: Any, what: str) -> str | int | None:
    """Carry the measured `ContextDocument.page` domain verbatim: str | int | None."""
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


def _coverage_state(
    admitted_count: int, included_count: int
) -> ModelContextCoverageState:
    """ADMITTED BASIS INCLUSION COVERAGE, from two counts and nothing else.

    Total over the declared vocabulary so that later lawful sizing has a
    correct derivation to reuse. At v0.1 only COMPLETE is reachable from
    `build_model_context`: an empty admitted basis and an ADMITTED candidate
    with no projection both fail closed before this is ever called, which is
    what keeps NOT_APPLICABLE, NONE and PARTIAL from being fabricated.
    """
    if admitted_count == 0:
        return ModelContextCoverageState.NOT_APPLICABLE
    if included_count == 0:
        return ModelContextCoverageState.NONE
    if included_count == admitted_count:
        return ModelContextCoverageState.COMPLETE
    return ModelContextCoverageState.PARTIAL


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def build_model_context(
    *,
    governed_basis: Any,
    candidate_projections: Sequence[CandidateContentProjection],
    question: str,
) -> ModelContextAssembly:
    """Assemble the Model Context for one turn from an already-governed basis.

    `governed_basis` is read structurally and must expose `question_id`,
    `context_pack_id` and `admitted`; each admitted entry must expose
    `candidate_id` and a `disposition` whose own string value is ADMITTED. A
    real `GovernedEvidenceSet` satisfies this without any adaptation.

    `candidate_projections` are the submitted candidates' model-facing values.
    They MAY include identities that are not admitted; those are excluded from
    the result and are never labelled.

    `question` is the already-normalized user question, carried verbatim.

    Raises `ModelContextBuildError` on every contract violation.
    """
    # --- USER_INPUT: carried verbatim, never rewritten -------------------- #
    if not isinstance(question, str) or not question:
        _fail(f"question must be a non-empty string, found {question!r}")
    # Verify the declared normalization already holds. This checks the
    # caller's contract; it does not APPLY a normalization and performs no
    # query rewriting, expansion or reformulation of any kind.
    if question != question.strip():
        _fail(
            "question is not normalized as contracted "
            f"({QUESTION_NORMALIZATION_STRIP}); the Builder never normalizes"
        )

    # --- the governed basis: exactly three fields are read ---------------- #
    question_id = _identity(
        _attr(governed_basis, "question_id", _WHAT_BASIS), "governed basis question_id"
    )
    context_pack_id = _identity(
        _attr(governed_basis, "context_pack_id", _WHAT_BASIS),
        "governed basis context_pack_id",
    )
    admitted = _sequence(
        _attr(governed_basis, "admitted", _WHAT_BASIS), "governed basis admitted entries"
    )

    # v0.1 law: a Model Context with no admitted basis is refused outright. It
    # is NOT downgraded to a USER_INPUT-only context and NOT recorded as NONE
    # coverage, either of which would enact the unrestricted-generation
    # fallback the contract forbids.
    if admitted == ():
        _fail(
            "the governed basis carries no ADMITTED candidate; v0.1 refuses to "
            "build a Model Context rather than fall back to user input alone"
        )

    admitted_ids: list[str] = []
    seen_admitted: set[str] = set()
    for entry in admitted:
        candidate_id = _identity(
            _attr(entry, "candidate_id", "admitted entry"), "admitted entry candidate_id"
        )
        # Read the label upstream already assigned, by its own string value.
        # This verifies what the basis states; it never assigns or changes a
        # disposition, and no other disposition is mapped, coerced or accepted.
        disposition = _attr(entry, "disposition", "admitted entry")
        if not isinstance(disposition, str) or disposition != DISPOSITION_ADMITTED:
            _fail(
                f"admitted entry {candidate_id} does not carry the "
                f"{DISPOSITION_ADMITTED} disposition, found {disposition!r}"
            )
        if candidate_id in seen_admitted:
            _fail(f"duplicate admitted candidate identity: {candidate_id}")
        seen_admitted.add(candidate_id)
        admitted_ids.append(candidate_id)

    # --- the submitted projections, indexed by their OWN identity --------- #
    projection_by_id: dict[str, CandidateContentProjection] = {}
    for item in _sequence(candidate_projections, "candidate projections"):
        # Requiring the projection type is how governance material is kept out:
        # nothing but the six declared model-facing values can be handed in, so
        # Evidence metadata, provenance packages, fingerprints and native
        # records have no channel into a Model Context at all.
        if not isinstance(item, CandidateContentProjection):
            _fail(
                "each candidate projection must be a CandidateContentProjection, "
                f"found {type(item).__name__}"
            )
        document_id = _identity(item.document_id, "candidate projection document_id")
        if document_id in projection_by_id:
            _fail(f"duplicate candidate projection identity: {document_id}")
        _string(item.content, f"candidate projection {document_id} content")
        _string(item.title, f"candidate projection {document_id} title")
        _string(item.source_identity, f"candidate projection {document_id} source_identity")
        _page(item.page, f"candidate projection {document_id} page")
        _chunk_id(item.chunk_id, f"candidate projection {document_id} chunk_id")
        projection_by_id[document_id] = item

    # --- join by identity VALUE, in the governed basis's own order -------- #
    # List position is never the identity contract, and the admitted order is
    # reproduced exactly rather than re-sorted, re-ranked or re-prioritized.
    evidence: list[EvidenceContextItem] = []
    for candidate_id in admitted_ids:
        projection = projection_by_id.get(candidate_id, _MISSING)
        if projection is _MISSING:
            _fail(
                f"ADMITTED candidate {candidate_id} has no candidate projection; "
                "v0.1 refuses rather than omitting a governed candidate"
            )
        evidence.append(
            EvidenceContextItem(
                candidate_id=candidate_id,
                # verbatim, in every field: no rewriting, summarizing,
                # normalizing, trimming or re-derivation of any kind.
                content=projection.content,
                title=projection.title,
                source_identity=projection.source_identity,
                page=projection.page,
                chunk_id=projection.chunk_id,
            )
        )

    # A projection whose identity was not admitted was never looked up above.
    # It is excluded, and no code path here gives it a label of any kind.

    # --- coverage: from the two identity sets, and nothing else ----------- #
    included_ids = tuple(item.candidate_id for item in evidence)
    included_identities = set(included_ids)
    coverage = ModelContextCoverage(
        state=_coverage_state(len(admitted_ids), len(included_ids)),
        admitted_count=len(admitted_ids),
        included_count=len(included_ids),
        omitted_candidate_ids=tuple(
            candidate_id
            for candidate_id in admitted_ids
            if candidate_id not in included_identities
        ),
    )

    return ModelContextAssembly(
        question=question,
        question_normalization=QUESTION_NORMALIZATION_STRIP,
        question_id=question_id,
        context_pack_id=context_pack_id,
        evidence=tuple(evidence),
        coverage=coverage,
    )
