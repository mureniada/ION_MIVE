"""Phase 2 tests: the bounded Conversation Context model and builder.

Amendment OD22-08-A1 / D6 (docs/ION_PHASE2_CONVERSATION_CONTEXT_AMENDMENT_v1.md).
Pure unit tests: no Core, no provider, no network.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules import conversation_context as cc
from app.modules.conversation_context import (
    INTERPRETATION_CHAR_CAP,
    MAX_PRIOR_TURNS,
    QUESTION_CHAR_CAP,
    TOTAL_CHAR_CAP,
    TRUNCATION_MARK,
    UNCERTAINTY_CHAR_CAP,
    UNCERTAINTY_ITEM_CAP,
    ConversationContext,
    ConversationContextError,
    PriorTurnContext,
    build_conversation_context,
    canonical_context_bytes,
    cap_text,
    context_sha256,
    prior_turn_from_ask_result,
    retrieval_query_for,
)

PACKAGE_DIR = Path(cc.__file__).resolve().parent


def _result(abstract="The interpretation.", uncertainty=("Open point.",), reports=None):
    if reports is None:
        reports = [{"abstract": abstract, "uncertainty": list(uncertainty),
                    "claims": [{"evidence_document_ids": ["EV-1"]}]}]
    return SimpleNamespace(
        ive_reports=reports,
        rendered={"primary_answer": "COMPOSED TEXT MUST NOT BE REMEMBERED"},
    )


def _turn(turn_id="T-1", question="What is ION?", interpretation="An answer.", uncertainty=()):
    return PriorTurnContext(
        turn_id=turn_id, question=question, interpretation=interpretation,
        uncertainty=tuple(uncertainty),
    )


# --------------------------------------------------------------------- #
# D6 limits are exactly the approved values
# --------------------------------------------------------------------- #
def test_d6_limits_are_exact():
    assert MAX_PRIOR_TURNS == 2
    assert QUESTION_CHAR_CAP == 500
    assert INTERPRETATION_CHAR_CAP == 1200
    assert UNCERTAINTY_ITEM_CAP == 3
    assert UNCERTAINTY_CHAR_CAP == 300
    assert TOTAL_CHAR_CAP == 4000
    assert TRUNCATION_MARK == "…"
    assert cc.CONVERSATION_CONTEXT_CONTRACT_ID == "ION_CONVERSATION_CONTEXT_V0_1"
    assert cc.CONVERSATION_CONTEXT_VERSION == "0.1"


def test_prior_turn_has_exactly_four_facts_and_no_evidence_field():
    assert {f.name for f in dataclasses.fields(PriorTurnContext)} == {
        "turn_id", "question", "interpretation", "uncertainty",
    }
    assert {f.name for f in dataclasses.fields(ConversationContext)} == {
        "prior_turns", "context_sha256", "context_contract_id", "context_version",
    }
    for cls in (PriorTurnContext, ConversationContext):
        for name in (f.name for f in dataclasses.fields(cls)):
            for token in ("evidence", "claim", "document", "citation", "session",
                          "composed", "rendered", "answer"):
                assert token not in name, (cls.__name__, name)


# --------------------------------------------------------------------- #
# deterministic truncation
# --------------------------------------------------------------------- #
def test_cap_text_is_exact_at_the_boundary():
    assert cap_text("x" * 500, 500) == "x" * 500
    capped = cap_text("x" * 501, 500)
    assert len(capped) == 500
    assert capped == "x" * 499 + TRUNCATION_MARK
    assert cap_text("  padded  ", 500) == "padded"
    # deterministic: same input, same output
    assert cap_text("y" * 2000, 1200) == cap_text("y" * 2000, 1200)


def test_prior_turn_from_ask_result_caps_every_field():
    result = _result(
        abstract="a" * 5000,
        uncertainty=["u" * 1000, "v", "w", "fourth dropped", "fifth dropped"],
    )
    prior = prior_turn_from_ask_result(turn_id="T-9", question="q" * 900, ask_result=result)
    assert prior.turn_id == "T-9"
    assert len(prior.question) == QUESTION_CHAR_CAP
    assert prior.question.endswith(TRUNCATION_MARK)
    assert len(prior.interpretation) == INTERPRETATION_CHAR_CAP
    assert prior.uncertainty == ("u" * 299 + TRUNCATION_MARK, "v", "w")


def test_prior_turn_reads_the_ive_abstract_never_the_composed_text():
    prior = prior_turn_from_ask_result(turn_id="T-1", question="Q", ask_result=_result())
    assert prior.interpretation == "The interpretation."
    assert "COMPOSED" not in repr(prior)
    # evidence identities present in the report never enter the context
    assert "EV-1" not in repr(prior)


@pytest.mark.parametrize("reports", [[], [{"abstract": ""}], [{"abstract": "a"}, {"abstract": "b"}],
                                     ["not a dict"], None])
def test_unrememberable_results_yield_none(reports):
    result = SimpleNamespace(ive_reports=reports)
    assert prior_turn_from_ask_result(turn_id="T-1", question="Q", ask_result=result) is None


# --------------------------------------------------------------------- #
# construction invariants, fail closed
# --------------------------------------------------------------------- #
def test_prior_turn_rejects_oversized_or_malformed_fields():
    with pytest.raises(ConversationContextError):
        _turn(question="q" * 501)
    with pytest.raises(ConversationContextError):
        _turn(interpretation="i" * 1201)
    with pytest.raises(ConversationContextError):
        _turn(uncertainty=("a", "b", "c", "d"))
    with pytest.raises(ConversationContextError):
        _turn(uncertainty=("u" * 301,))
    with pytest.raises(ConversationContextError):
        _turn(turn_id="")
    with pytest.raises(ConversationContextError):
        _turn(question=" padded ")


def test_context_rejects_tampered_hash_too_many_turns_and_duplicates():
    one, two, three = _turn("T-1"), _turn("T-2"), _turn("T-3")
    with pytest.raises(ConversationContextError):
        ConversationContext(prior_turns=(one,), context_sha256="0" * 64)
    with pytest.raises(ConversationContextError):
        ConversationContext(
            prior_turns=(one, two, three),
            context_sha256=context_sha256((one, two, three)),
        )
    with pytest.raises(ConversationContextError):
        ConversationContext(prior_turns=(one, one), context_sha256=context_sha256((one, one)))
    with pytest.raises(ConversationContextError):
        ConversationContext(prior_turns=(), context_sha256=context_sha256(()))


def test_canonical_bytes_and_hash_are_stable_golden():
    turn = _turn("T-1", "Q1", "I1", ("U1",))
    expected = json.dumps(
        [{"interpretation": "I1", "question": "Q1", "turn_id": "T-1", "uncertainty": ["U1"]}],
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    assert canonical_context_bytes((turn,)) == expected
    assert canonical_context_bytes((turn,)) == (
        b'[{"interpretation":"I1","question":"Q1","turn_id":"T-1","uncertainty":["U1"]}]'
    )
    assert context_sha256((turn,)) == hashlib.sha256(expected).hexdigest()


# --------------------------------------------------------------------- #
# window -> context, bounded, no summarization
# --------------------------------------------------------------------- #
def test_empty_window_gives_no_context():
    assert build_conversation_context(()) is None


def test_total_cap_drops_the_oldest_turn_never_summarizes():
    big_a = _turn("T-1", "q" * 500, "a" * 1200, ("u" * 300,) * 3)   # 2600 chars
    big_b = _turn("T-2", "r" * 500, "b" * 1200, ("v" * 300,) * 3)   # 2600 chars
    ctx = build_conversation_context((big_a, big_b))
    assert ctx.prior_turns == (big_b,)       # 5200 > 4000: oldest dropped whole
    assert ctx.context_sha256 == context_sha256((big_b,))

    small_a, small_b = _turn("T-1"), _turn("T-2")
    ctx = build_conversation_context((small_a, small_b))
    assert ctx.prior_turns == (small_a, small_b)  # oldest first, both fit


def test_retrieval_query_rule_is_exact():
    assert retrieval_query_for("Current?", None) == "Current?"
    q = "Current?"
    assert retrieval_query_for(q, None) is q
    ctx = build_conversation_context((_turn("T-1", "First Q"), _turn("T-2", "Second Q")))
    assert retrieval_query_for("Tell me more", ctx) == "Second Q\nTell me more"


# --------------------------------------------------------------------- #
# import boundary: standard library only
# --------------------------------------------------------------------- #
def test_package_imports_standard_library_only():
    allowed = {"__future__", "dataclasses", "hashlib", "json", "typing"}
    for path in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in allowed, (path.name, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module.split(".")[0] in allowed, (path.name, node.module)
