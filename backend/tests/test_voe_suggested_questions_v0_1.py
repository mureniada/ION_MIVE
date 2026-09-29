"""Suggested next questions (response composer contract v0.2).

The suggestions ride the EXISTING single composer call (schema-only
extension; the system instruction is byte-identical), are deterministically
filtered, and are presentation/navigation only: never evidence, never
retrieval input, never ConversationContext, never Turn Record — unless a user
actually submits one as an ordinary question. Offline stubs only; no provider.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from app.modules.response_composer import (
    COMPOSER_RESPONSE_SCHEMA,
    RESPONSE_COMPOSER_CONTRACT_ID,
    RESPONSE_COMPOSER_VERSION,
    ComposedResponse,
    ComposerContractError,
    ComposerInput,
    VOEResponseComposer,
    build_composer_system_instruction,
)
from app.modules.response_composer.composer import filter_suggested_questions
from app.modules.session import SessionController
from scripts.voe_g2_stage_a_dry_run import (
    build_voe_enabled_settings,
    committed_voe_bundle_dir,
    load_voe_profile_through_settings,
)
from tests.test_orchestrator_conversation_context_v0_1 import ctx_core, ive_report

# The composer system instruction the G6 L1 evaluator pins
# (scripts/voe_g6_l1_offline_eval.py EXPECTED_SYSTEM_INSTRUCTION_SHA256).
PINNED_SYSTEM_INSTRUCTION_SHA256 = (
    "0524cf8c78d4f1802e74248db9aaaad4245c5b15a27742e0c2227b8d3708f7de"
)
QUESTION = "What is ION and how does it work?"
S1 = "How does ION work in practice?"
S2 = "What are the risks of ION?"
S3 = "How does ION relate to money?"


@pytest.fixture(scope="module")
def profile():
    return load_voe_profile_through_settings(
        build_voe_enabled_settings(committed_voe_bundle_dir())
    )


class StubBackend:
    """Records every generate() call; returns the scripted JSON bodies in order."""

    def __init__(self, bodies):
        self._bodies = list(bodies)
        self.calls = []

    def generate(self, *, system, user, schema):
        from app.modules.ive_common import GenerationResult

        self.calls.append({"system": system, "user": user, "schema": schema})
        body = self._bodies.pop(0)
        text = body if isinstance(body, str) else json.dumps(body)
        return GenerationResult(text=text, usage_is_estimated=True)


def composer_input(profile, question=QUESTION):
    return ComposerInput(
        question=question, report_abstract="An interpretation.", report_highlights=(),
        report_claims=(), report_uncertainty=("Open point.",), report_confidence=0.7,
        voe_profile=profile,
    )


# --------------------------------------------------------------------- #
# contract and schema
# --------------------------------------------------------------------- #
def test_contract_is_v0_2_and_schema_stays_strict_with_one_optional_field():
    assert RESPONSE_COMPOSER_CONTRACT_ID == "ION_RESPONSE_COMPOSER_V0_2"
    assert RESPONSE_COMPOSER_VERSION == "0.2"
    assert COMPOSER_RESPONSE_SCHEMA["required"] == ["composed_text"]
    assert COMPOSER_RESPONSE_SCHEMA["additionalProperties"] is False
    prop = COMPOSER_RESPONSE_SCHEMA["properties"]["suggested_questions"]
    assert prop["type"] == "array" and prop["items"] == {"type": "string"}


def test_system_instruction_is_byte_identical_to_the_pinned_one(profile):
    system = build_composer_system_instruction(profile)
    assert hashlib.sha256(system.encode("utf-8")).hexdigest() == PINNED_SYSTEM_INSTRUCTION_SHA256
    assert "suggest" not in system.lower()


def test_composed_response_accepts_only_zero_or_two_to_three():
    ComposedResponse(composed_text="x")
    ComposedResponse(composed_text="x", suggested_questions=(S1, S2))
    ComposedResponse(composed_text="x", suggested_questions=(S1, S2, S3))
    for bad in ((S1,), (S1, S2, S3, "Four?"), [S1, S2], (S1, "")):
        with pytest.raises(ComposerContractError):
            ComposedResponse(composed_text="x", suggested_questions=bad)


# --------------------------------------------------------------------- #
# deterministic filter
# --------------------------------------------------------------------- #
def test_valid_two_and_three_are_kept():
    assert filter_suggested_questions([S1, S2], QUESTION) == (S1, S2)
    assert filter_suggested_questions([S1, S2, S3], QUESTION) == (S1, S2, S3)
    assert filter_suggested_questions(["  " + S1 + "  ", S2], QUESTION) == (S1, S2)


@pytest.mark.parametrize("raw", [None, "not a list", {"a": 1}, 42, [], [1, 2, 3], [None, S1]])
def test_missing_null_non_list_or_non_string_gives_none(raw):
    assert filter_suggested_questions(raw, QUESTION) == ()


def test_more_than_three_keeps_first_three_valid():
    assert filter_suggested_questions([S1, "bad", S2, S3, "What else is there?"], QUESTION) == (
        S1, S2, S3,
    )


def test_duplicates_are_removed_case_and_whitespace_insensitively():
    assert filter_suggested_questions([S1, S1.upper(), " ".join(S1.split(" ")) + "", S2], QUESTION) \
        == (S1, S2)
    assert filter_suggested_questions([S1, "how  does ION WORK in practice?"], QUESTION) == ()


@pytest.mark.parametrize("bad", [
    "How does ION work in practice",          # no question mark
    "How? does ION work in practice?",        # multiple question marks
    "Is it? Really",                          # ? not final
    "How does ION\nwork in practice?",        # newline
    "What does [TW-OBJ-0008] say?",           # [
    "What does it say about ] this?",         # ]
    "What does readme::c0 say?",              # ::
    "Where is http example?",                 # http
    "Is www.example.org relevant?",           # www.
    "What does the DOI say here?",            # standalone doi (case-insensitive)
    "Why?",                                   # too short (< 8)
    "W" * 120 + "?",                          # too long (> 120)
    QUESTION,                                 # equals current question
    "  what is ion and HOW does it   work?  ",  # equals, case/whitespace-insensitive
])
def test_each_invalid_item_is_rejected(bad):
    assert filter_suggested_questions([bad, S1, S2], QUESTION) == (S1, S2)
    assert filter_suggested_questions([bad, S1], QUESTION) == ()   # < 2 survive -> none


@pytest.mark.parametrize("allowed", [
    "What are we doing next?",
    "How is this avoiding inflation?",
    "What about undoing that step?",
])
def test_ordinary_words_containing_doi_are_allowed(allowed):
    assert filter_suggested_questions([allowed, S1], QUESTION) == (allowed, S1)


@pytest.mark.parametrize("rejected", [
    "What does DOI mean?",
    "See doi:10.1234/example?",
    "What is on doi.org?",
    "What is https://doi.org/10.1234/x?",
    "Is the doi listed anywhere?",
])
def test_citation_like_doi_is_rejected(rejected):
    assert filter_suggested_questions([rejected, S1, S2], QUESTION) == (S1, S2)


def test_length_bounds_are_inclusive():
    eight = "Why ION?"
    assert len(eight) == 8
    one_twenty = "W" * 119 + "?"
    assert filter_suggested_questions([eight, one_twenty], QUESTION) == (eight, one_twenty)


# --------------------------------------------------------------------- #
# compose(): one call, isolation from composed_text
# --------------------------------------------------------------------- #
def test_compose_returns_filtered_suggestions_in_the_same_single_call(profile):
    backend = StubBackend([{"composed_text": "Composed.", "suggested_questions": [S1, S2, "bad"]}])
    result = VOEResponseComposer(backend, provider="stub", requested_model="stub").compose(
        composer_input(profile)
    )
    assert len(backend.calls) == 1
    assert backend.calls[0]["schema"] is COMPOSER_RESPONSE_SCHEMA
    assert result.response.composed_text == "Composed."
    assert result.response.suggested_questions == (S1, S2)


@pytest.mark.parametrize("suggestions", [None, "junk", [1, 2], ["no mark"], [S1], {"x": 1}])
def test_malformed_suggestions_never_discard_a_valid_composed_text(profile, suggestions):
    backend = StubBackend([{"composed_text": "Composed.", "suggested_questions": suggestions}])
    result = VOEResponseComposer(backend, provider="stub", requested_model="stub").compose(
        composer_input(profile)
    )
    assert result.response.composed_text == "Composed."
    assert result.response.suggested_questions == ()


def test_absent_suggestions_key_is_fine(profile):
    backend = StubBackend([{"composed_text": "Composed."}])
    result = VOEResponseComposer(backend, provider="stub", requested_model="stub").compose(
        composer_input(profile)
    )
    assert result.response.suggested_questions == ()


# --------------------------------------------------------------------- #
# Core / session: presentation only; no leakage unless submitted
# --------------------------------------------------------------------- #
def voe_core(monkeypatch, profile, reports, bodies):
    core, engine = ctx_core(monkeypatch, reports)
    backend = StubBackend(bodies)
    core._composer = VOEResponseComposer(backend, provider="stub", requested_model="stub")
    core._voe_runtime_profile = profile
    return core, engine, backend


def test_composed_presentation_carries_suggestions_and_nothing_else_does(monkeypatch, profile):
    core, engine, backend = voe_core(
        monkeypatch, profile, [ive_report()],
        [{"composed_text": "Composed.", "suggested_questions": [S1, S2, S3]}],
    )
    captured = []
    result = core.ask(QUESTION, 3, on_turn_record=captured.append)
    rendered = result.rendered
    assert rendered["presentation"] == {
        "composition_status": "COMPOSED", "suggested_questions": [S1, S2, S3],
    }
    assert len(backend.calls) == 1                           # still one composer call
    elsewhere = json.dumps({k: v for k, v in rendered.items() if k != "presentation"})
    for s in (S1, S2, S3):
        assert s not in elsewhere                            # not in primary_answer/uncertainty/evidence
        assert s not in repr(captured[0])                    # not in the Turn Record
        assert s not in repr(engine.model_inputs[0])         # not in the Model Context
        assert s not in json.dumps(result.ive_reports)       # not in the IVE report


def test_fallback_gives_empty_suggestions(monkeypatch, profile):
    core, _, _ = voe_core(monkeypatch, profile, [ive_report()], ["not json at all"])
    result = core.ask(QUESTION, 3)
    assert result.rendered["presentation"] == {
        "composition_status": "FALLBACK", "suggested_questions": [],
    }


def test_unclicked_suggestions_never_reach_retrieval_or_context(monkeypatch, profile):
    core, engine, _ = voe_core(
        monkeypatch, profile, [ive_report(), ive_report()],
        [{"composed_text": "Composed 1.", "suggested_questions": [S1, S2]},
         {"composed_text": "Composed 2.", "suggested_questions": [S3, S1]}],
    )
    controller = SessionController(core=core)
    session = controller.create_session().session_id
    controller.run_turn(session, QUESTION, top_k=3)
    controller.run_turn(session, "Something typed instead", top_k=3)   # S1/S2 not clicked
    for query in core._retrieval.queries:
        assert S1 not in query and S2 not in query
    memory = repr(engine.model_inputs[1].conversation_memory)
    assert S1 not in memory and S2 not in memory
    state = controller._sessions[session]
    assert S1 not in repr(list(state.context_window)) and S1 not in repr(state.root_question)


def test_a_submitted_suggestion_is_an_ordinary_root_anchored_turn(monkeypatch, profile):
    core, engine, _ = voe_core(
        monkeypatch, profile, [ive_report(), ive_report()],
        [{"composed_text": "Composed 1.", "suggested_questions": [S1, S2]},
         {"composed_text": "Composed 2."}],
    )
    controller = SessionController(core=core)
    session = controller.create_session().session_id
    first = controller.run_turn(session, QUESTION, top_k=3)
    clicked = first.rendered["presentation"]["suggested_questions"][0]
    controller.run_turn(session, clicked, top_k=3)                    # the user submits it
    assert core._retrieval.queries == [QUESTION, QUESTION + "\n" + S1]
    state = controller._sessions[session]
    assert [p.question for p in state.context_window] == [QUESTION, S1]  # after COMPLETED only
    assert state.root_question == QUESTION
