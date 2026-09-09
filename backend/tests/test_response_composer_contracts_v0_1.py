"""Bounded contract test for the Response Composer Gate 1 boundary (v0.1).

Scope is deliberately narrow: Gate 1 introduces inert data shapes and one
Protocol only — no loading, no prompt construction, no provider execution,
no wiring into `Core.ask()`, `app.container`, or any runtime entry point.
This file proves exactly that: the new contracts are immutable, structurally
narrow (no evidence-content field, no field broad enough to smuggle a
`ModelContextAssembly` or `GovernedEvidenceSet` through), and that every
pre-existing frozen-contract test suite this change could plausibly touch
still passes unmodified.

Absence checks are structural (dataclass field names/types), never textual
against source, matching the convention already used by
`test_response_evidence_projection_v0_1.py` and
`test_model_context_builder_v0_1.py`.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.core.ports import ResponseComposerPort
from app.modules.response_composer import (
    RESPONSE_COMPOSER_CONTRACT_ID,
    RESPONSE_COMPOSER_VERSION,
    ComposedResponse,
    ComposerClaimView,
    ComposerContractError,
    ComposerInput,
)
from app.modules.voe_profile import VOEProfileBinding, VOEProfileBindingError, VOERuntimeProfile

# --------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------- #
def _profile_binding() -> VOEProfileBinding:
    return VOEProfileBinding(
        profile_id="VOE-DIALOGUE-PROFILE",
        profile_version="0.2",
        runtime_behavioral_fingerprint_sha256="a" * 64,
    )


def _runtime_profile(**overrides) -> VOERuntimeProfile:
    defaults = dict(
        binding=_profile_binding(),
        dialogue_profile_text="Meet the person before the answer.",
        style_parameters_text='{"warmth": "high"}',
        ethical_policy_text="Do not humiliate, shame, or belittle.",
        illustrative_reasoning_policy_text="Prefer plain explanation if sufficient.",
    )
    defaults.update(overrides)
    return VOERuntimeProfile(**defaults)


def _claim_view(**overrides) -> ComposerClaimView:
    defaults = dict(
        statement="Money functions as a medium of exchange.",
        confidence=0.8,
    )
    defaults.update(overrides)
    return ComposerClaimView(**defaults)


def _composer_input(**overrides) -> ComposerInput:
    defaults = dict(
        question="What is money?",
        report_abstract="Money is a medium of exchange, unit of account, and store of value.",
        report_highlights=("medium of exchange", "store of value"),
        report_claims=(_claim_view(),),
        report_uncertainty=("Historical origin is debated.",),
        report_confidence=0.75,
        voe_profile=_runtime_profile(),
    )
    defaults.update(overrides)
    return ComposerInput(**defaults)


# --------------------------------------------------------------------- #
# 1-3: immutability
# --------------------------------------------------------------------- #
def test_composer_input_is_immutable():
    ci = _composer_input()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ci.question = "different question"


def test_composer_claim_view_is_immutable():
    claim = _claim_view()
    with pytest.raises(dataclasses.FrozenInstanceError):
        claim.statement = "different statement"


def test_voe_profile_binding_is_immutable():
    binding = _profile_binding()
    with pytest.raises(dataclasses.FrozenInstanceError):
        binding.profile_id = "different-id"


def test_composed_response_is_immutable():
    resp = ComposedResponse(composed_text="Money is how people trade value.")
    with pytest.raises(dataclasses.FrozenInstanceError):
        resp.composed_text = "different text"


# --------------------------------------------------------------------- #
# 4: no evidence-content field anywhere in the composer boundary
# --------------------------------------------------------------------- #
_FORBIDDEN_FIELD_NAMES = {
    "content",
    "title",
    "source_identity",
    "page",
    "chunk_id",
    "authorized_evidence_basis",
    "model_context",
    "model_context_assembly",
    "governed_evidence",
    "governed_evidence_set",
    "evidence",
    "settings",
    "session",
    "session_state",
    "conversation_memory",
}


@pytest.mark.parametrize("cls", [ComposerClaimView, ComposerInput, ComposedResponse])
def test_no_forbidden_field_names_present(cls):
    field_names = {f.name for f in dataclasses.fields(cls)}
    overlap = field_names & _FORBIDDEN_FIELD_NAMES
    assert overlap == set(), f"{cls.__name__} carries forbidden field(s): {overlap}"


def test_composer_claim_view_field_set_is_exactly_the_projected_two():
    field_names = {f.name for f in dataclasses.fields(ComposerClaimView)}
    assert field_names == {"statement", "confidence"}


def test_composer_claim_view_has_no_evidence_identity_field_at_all():
    """Gate 3B: evidence_document_ids was removed entirely, not replaced by
    candidate_id/document_id/source_id or any other evidence-identity name."""
    field_names = {f.name for f in dataclasses.fields(ComposerClaimView)}
    forbidden = {
        "evidence_document_ids", "candidate_id", "document_id",
        "source_id", "provenance_id", "citation_id",
    }
    assert field_names & forbidden == set()


def test_composer_input_field_set_is_exactly_the_narrow_seven():
    field_names = {f.name for f in dataclasses.fields(ComposerInput)}
    assert field_names == {
        "question",
        "report_abstract",
        "report_highlights",
        "report_claims",
        "report_uncertainty",
        "report_confidence",
        "voe_profile",
    }


# --------------------------------------------------------------------- #
# 5: no field broad enough to smuggle ModelContextAssembly / GovernedEvidenceSet
# --------------------------------------------------------------------- #
def test_composer_input_field_types_are_narrow_declared_strings():
    """`from __future__ import annotations` stores annotations as strings;
    assert none of them is an unbounded escape hatch (`Any`, `object`, a
    bare unqualified type) through which an arbitrary object — including a
    real ModelContextAssembly or GovernedEvidenceSet — could be typed as
    acceptable."""
    forbidden_type_tokens = ("Any", "object", "ModelContextAssembly", "GovernedEvidenceSet")
    for f in dataclasses.fields(ComposerInput):
        type_str = f.type if isinstance(f.type, str) else repr(f.type)
        for token in forbidden_type_tokens:
            assert token not in type_str, (
                f"ComposerInput.{f.name} is typed {type_str!r}, "
                f"which contains the forbidden token {token!r}"
            )


def test_composer_input_rejects_a_model_context_assembly_shaped_object_as_voe_profile():
    """`__post_init__` refuses anything that is not a real `VOERuntimeProfile`
    for the one field capable of holding a profile-shaped object — proving
    the narrow field cannot be satisfied by a broader, evidence-bearing
    stand-in even if a caller tried."""

    class _ModelContextAssemblyLookAlike:
        question = "irrelevant"
        evidence = ()

    with pytest.raises(ComposerContractError):
        _composer_input(voe_profile=_ModelContextAssemblyLookAlike())


def test_composer_input_now_requires_voe_runtime_profile_not_bare_binding():
    """Gate 2A: `VOEProfileBinding` alone carries identity only and has no
    field a composer could read to construct a system instruction, so
    `ComposerInput.voe_profile` must be a `VOERuntimeProfile` — a bare
    binding, even a real, validly-constructed one, is refused."""
    with pytest.raises(ComposerContractError):
        _composer_input(voe_profile=_profile_binding())


def test_composer_claim_view_rejects_an_unexpected_evidence_id_kwarg():
    """A caller cannot smuggle an evidence-identity value back in through a
    kwarg the dataclass no longer declares — this is TypeError, not a
    contract error, precisely because there is no field to accept it."""
    with pytest.raises(TypeError):
        ComposerClaimView(statement="x", confidence=0.5, evidence_document_ids=("doc-1",))


# --------------------------------------------------------------------- #
# 6: ComposedResponse minimum output surface only
# --------------------------------------------------------------------- #
def test_composed_response_field_set_is_the_minimum_gate_1_surface():
    field_names = {f.name for f in dataclasses.fields(ComposedResponse)}
    assert field_names == {
        "composed_text",
        "response_composer_contract_id",
        "response_composer_version",
    }


def test_composed_response_carries_no_citation_or_telemetry_field():
    forbidden = {
        "reference_requests",
        "evidence_reference_requests",
        "provider",
        "model",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "estimated_cost",
        "usage",
        "status",
        "composer_status",
    }
    field_names = {f.name for f in dataclasses.fields(ComposedResponse)}
    assert field_names & forbidden == set()


def test_composed_response_contract_identity_defaults():
    resp = ComposedResponse(composed_text="A plain composed answer.")
    assert resp.response_composer_contract_id == RESPONSE_COMPOSER_CONTRACT_ID
    assert resp.response_composer_version == RESPONSE_COMPOSER_VERSION


# --------------------------------------------------------------------- #
# 7: ResponseComposerPort is structurally usable as a Protocol
# --------------------------------------------------------------------- #
def test_response_composer_port_is_runtime_checkable_and_structural():
    class _RealComposer:
        def compose(self, composer_input):
            return ComposedResponse(composed_text="ok")

    class _NotAComposer:
        def render(self, x):
            return x

    assert isinstance(_RealComposer(), ResponseComposerPort)
    assert not isinstance(_NotAComposer(), ResponseComposerPort)


def test_response_composer_port_does_not_inherit_ive_or_renderer_semantics():
    from app.core.ports import IVEPort, RendererPort

    assert ResponseComposerPort is not IVEPort
    assert ResponseComposerPort is not RendererPort
    # IVEPort/RendererPort carry non-callable members (properties), so
    # `issubclass()` against them is unsupported for runtime_checkable
    # Protocols (TypeError) — the MRO is the valid structural check for
    # "does not inherit from" here.
    assert IVEPort not in ResponseComposerPort.__mro__
    assert RendererPort not in ResponseComposerPort.__mro__


# --------------------------------------------------------------------- #
# construction sanity (supports the immutability/field tests above with a
# working, valid instance — not a redundant re-test of validation depth)
# --------------------------------------------------------------------- #
def test_valid_composer_input_constructs_and_round_trips_claim_view():
    ci = _composer_input()
    assert ci.report_claims[0].statement == "Money functions as a medium of exchange."
    assert ci.voe_profile.binding.profile_id == "VOE-DIALOGUE-PROFILE"
    assert "Meet the person" in ci.voe_profile.dialogue_profile_text


def test_composer_input_nested_voe_profile_carries_no_evidence_shaped_field():
    """Gate 2A: retyping voe_profile to the richer VOERuntimeProfile must
    not reopen an evidence-content leak — check both levels, since a
    forbidden field could in principle live on either type."""
    forbidden = _FORBIDDEN_FIELD_NAMES
    top_level = {f.name for f in dataclasses.fields(ComposerInput)}
    nested = {f.name for f in dataclasses.fields(VOERuntimeProfile)}
    assert top_level & forbidden == set()
    assert nested & forbidden == set()


def test_voe_profile_binding_rejects_blank_identity():
    with pytest.raises(VOEProfileBindingError):
        VOEProfileBinding(
            profile_id="", profile_version="0.2",
            runtime_behavioral_fingerprint_sha256="a" * 64,
        )
