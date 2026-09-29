"""Phase 2 tests: Core.ask() with and without a bounded conversation context.

Amendments RQ-A1, MC-A1, TR-A1, CG-A1
(docs/ION_PHASE2_CONVERSATION_CONTEXT_AMENDMENT_v1.md). A REAL Core over the
same stand-in ports `test_session_controller_v0_1.py` uses, with a scripted
engine that returns real `IVEReport` objects and records the exact
`ModelContextAssembly` and prompt each turn produced. No provider SDK, no
network, no credentials.
"""

from __future__ import annotations

import pytest

from app.core import errors
from app.core.models import Claim, IVEReport, Relation, Usage
from app.modules import ive_common
from app.modules.conversation_context import (
    PriorTurnContext,
    build_conversation_context,
)
from app.modules.model_gateway import ModelGateway
from app.modules.renderer.renderer import DeterministicRenderer
from tests.test_session_controller_v0_1 import GEMINI_MODEL, _core, _patch_gate

SUBMITTED = ("EV-1", "EV-2")


def ive_report(
    *, question="Question", abstract="The interpretation.", uncertainty=("Open point.",),
    claim_ids=("EV-1",), relation_ids=(),
):
    return IVEReport(
        engine_id="gemini", provider="gemini", model=GEMINI_MODEL, question=question,
        abstract=abstract, highlights=[],
        claims=[Claim(claim_id="C1", statement="A claim.",
                      evidence_document_ids=list(claim_ids), confidence=0.8)],
        concepts=[],
        relations=(
            [Relation(source="a", relation="r", target="b",
                      evidence_document_ids=list(relation_ids))]
            if relation_ids else []
        ),
        evidence_mapping={"C1": list(claim_ids)}, uncertainty=list(uncertainty),
        confidence=0.7,
        usage=Usage(input_tokens=11, output_tokens=5, latency_ms=1.5),
    )


class ScriptedEngine:
    """Returns the queued reports in order; records model input and prompt."""

    def __init__(self, reports):
        self._reports = list(reports)
        self.model_inputs = []
        self.prompts = []
        self.provider = "gemini"
        self.model = GEMINI_MODEL

    @property
    def engine_id(self):
        return "gemini"

    def run(self, model_input):
        self.model_inputs.append(model_input)
        self.prompts.append(ive_common.build_model_input_prompt(model_input))
        return self._reports.pop(0)


class RecordingRetrieval:
    def __init__(self, candidate_ids=("EV-1", "EV-2", "EV-3")):
        self._ids = tuple(candidate_ids)
        self.queries = []

    def retrieve(self, question, top_k):
        from types import SimpleNamespace

        self.queries.append(question)
        return [SimpleNamespace(document_id=cid, content="body") for cid in self._ids]


def ctx_core(monkeypatch, reports, *, retrieval=None):
    core = _core(submitted=SUBMITTED)
    engine = ScriptedEngine(reports)
    core._model_gateway = ModelGateway({"gemini": engine})
    core._retrieval = retrieval if retrieval is not None else RecordingRetrieval()
    core._renderer = DeterministicRenderer()
    _patch_gate(monkeypatch, SUBMITTED)
    return core, engine


def context_of(*turns):
    return build_conversation_context(tuple(turns))


PRIOR = PriorTurnContext(
    turn_id="PRIOR-TURN-1", question="What is ION?",
    interpretation="PRIOR INTERPRETATION TEXT", uncertainty=("PRIOR UNCERTAINTY",),
)


# --------------------------------------------------------------------- #
# RQ-A1 retrieval query
# --------------------------------------------------------------------- #
def test_no_context_retrieval_query_is_the_question_itself(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report()])
    core.ask("Question", 3)
    assert core._retrieval.queries == ["Question"]


def test_context_retrieval_query_is_prior_user_question_then_current(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report()])
    core.ask("Tell me more", 3, conversation_context=context_of(PRIOR))
    assert core._retrieval.queries == ["What is ION?\nTell me more"]
    # prior model text never reaches retrieval
    assert "PRIOR INTERPRETATION TEXT" not in core._retrieval.queries[0]
    assert "PRIOR UNCERTAINTY" not in core._retrieval.queries[0]


def test_invalid_context_type_fails_before_retrieval(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report()])
    with pytest.raises(errors.IonError) as info:
        core.ask("Question", 3, conversation_context={"prior_turns": []})
    assert info.value.stage == errors.STAGE_CONFIGURATION
    assert core._retrieval.queries == []


# --------------------------------------------------------------------- #
# MC-A1 model context and prompt; prior text never becomes evidence
# --------------------------------------------------------------------- #
def test_no_context_model_input_and_prompt_are_the_v0_1_shape(monkeypatch):
    core, engine = ctx_core(monkeypatch, [ive_report()])
    core.ask("Question", 3)
    model_input = engine.model_inputs[0]
    assert model_input.conversation_memory is None
    prompt = engine.prompts[0]
    assert "PRIOR CONVERSATION" not in prompt
    expected = "\n".join([
        "QUESTION:\nQuestion",
        "",
        "CONTEXT DOCUMENTS:",
        "[EV-1] Title-EV-1 — source: SRC-EV-1",
        "body",
        "",
        "[EV-2] Title-EV-2 — source: SRC-EV-2",
        "body",
        "",
        "Produce the JSON object. Use the bracketed document_id values above as "
        "evidence_document_ids. If evidence is missing for a claim, say so in "
        "`uncertainty` rather than inventing support.",
    ])
    assert prompt == expected


def test_context_turn_prompt_block_is_exact(monkeypatch):
    core, engine = ctx_core(monkeypatch, [ive_report()])
    core.ask("Tell me more", 3, conversation_context=context_of(PRIOR))
    prompt = engine.prompts[0]
    block = "\n".join([
        "QUESTION:\nTell me more",
        "",
        "PRIOR CONVERSATION (NOT EVIDENCE):",
        "These are earlier turns of this conversation, shown only so you can "
        "understand what the QUESTION refers to. They are not context documents and "
        "not evidence. Do not cite them, do not treat their content as established "
        "fact, and do not repeat a claim from them unless a CONTEXT DOCUMENT below "
        "supports it.",
        "Prior turn 1:",
        "User question: What is ION?",
        "Interpretation given: PRIOR INTERPRETATION TEXT",
        "Uncertainty noted: PRIOR UNCERTAINTY",
        "",
        "CONTEXT DOCUMENTS:",
    ])
    assert prompt.startswith(block + "\n[EV-1] ")
    # the block holds no square brackets: nothing in it looks citable
    prior_section = prompt[: prompt.index("CONTEXT DOCUMENTS:")]
    assert "[" not in prior_section and "]" not in prior_section


def test_prior_text_never_enters_evidence_or_rendered_evidence(monkeypatch):
    core, engine = ctx_core(monkeypatch, [ive_report()])
    result = core.ask("Tell me more", 3, conversation_context=context_of(PRIOR))
    model_input = engine.model_inputs[0]
    for item in model_input.evidence:
        for value in (item.content, item.title, item.source_identity, item.candidate_id):
            assert "PRIOR" not in value
    assert [item.candidate_id for item in model_input.evidence] == list(SUBMITTED)
    assert model_input.conversation_memory.turns[0].interpretation == "PRIOR INTERPRETATION TEXT"
    assert model_input.question == "Tell me more"
    for row in result.rendered["evidence"]:
        assert "PRIOR" not in repr(row)
    assert "PRIOR-TURN-1" not in repr(model_input)   # no prior identity reaches the model


def test_context_does_not_change_admitted_evidence_ids(monkeypatch):
    retrieval_a, retrieval_b = RecordingRetrieval(), RecordingRetrieval()
    core_a, engine_a = ctx_core(monkeypatch, [ive_report()], retrieval=retrieval_a)
    core_b, engine_b = ctx_core(monkeypatch, [ive_report()], retrieval=retrieval_b)
    core_a.ask("Tell me more", 3)
    core_b.ask("Tell me more", 3, conversation_context=context_of(PRIOR))
    ids_a = [i.candidate_id for i in engine_a.model_inputs[0].evidence]
    ids_b = [i.candidate_id for i in engine_b.model_inputs[0].evidence]
    assert ids_a == ids_b == list(SUBMITTED)
    assert engine_a.model_inputs[0].coverage == engine_b.model_inputs[0].coverage


# --------------------------------------------------------------------- #
# TR-A1 turn record binding and deterministic reconstruction
# --------------------------------------------------------------------- #
def test_completed_context_turn_record_binds_context_verbatim(monkeypatch):
    ctx = context_of(PRIOR)
    core, _ = ctx_core(monkeypatch, [ive_report()])
    captured = []
    core.ask("Tell me more", 3, conversation_context=ctx, on_turn_record=captured.append)
    [record] = captured
    binding = record.conversation_context
    assert record.turn_record_contract_id == "ION_TURN_RECORD_V0_2"
    assert record.question == "Tell me more"
    assert binding.context_sha256 == ctx.context_sha256
    assert binding.context_contract_id == "ION_CONVERSATION_CONTEXT_V0_1"
    assert binding.retrieval_query == "What is ION?\nTell me more"
    [prior] = binding.prior_turns
    assert (prior.turn_id, prior.question, prior.interpretation, prior.uncertainty) == (
        PRIOR.turn_id, PRIOR.question, PRIOR.interpretation, PRIOR.uncertainty,
    )


def test_no_context_turn_record_has_no_binding(monkeypatch):
    core, _ = ctx_core(monkeypatch, [ive_report()])
    captured = []
    core.ask("Question", 3, on_turn_record=captured.append)
    assert captured[0].conversation_context is None


def test_turn_is_reconstructable_byte_for_byte_from_its_record(monkeypatch):
    from app.modules.conversation_context import ConversationContext, context_sha256
    from app.modules.model_context import build_model_context

    ctx = context_of(
        PriorTurnContext(turn_id="T-1", question="Q1", interpretation="I1", uncertainty=()),
        PRIOR,
    )
    core, engine = ctx_core(monkeypatch, [ive_report()])
    captured = []
    core.ask("Tell me more", 3, conversation_context=ctx, on_turn_record=captured.append)
    record = captured[0]
    original_prompt = engine.prompts[0]
    original_input = engine.model_inputs[0]

    # rebuild the context from the RECORD alone and check its hash
    rebuilt_turns = tuple(
        PriorTurnContext(turn_id=t.turn_id, question=t.question,
                         interpretation=t.interpretation, uncertainty=t.uncertainty)
        for t in record.conversation_context.prior_turns
    )
    assert context_sha256(rebuilt_turns) == record.conversation_context.context_sha256
    rebuilt_ctx = ConversationContext(
        prior_turns=rebuilt_turns,
        context_sha256=record.conversation_context.context_sha256,
    )
    # same question + same admitted basis + rebuilt context -> identical prompt
    rebuilt_input = build_model_context(
        governed_basis=type("B", (), {
            "question_id": original_input.question_id,
            "context_pack_id": original_input.context_pack_id,
            "admitted": tuple(
                type("E", (), {"candidate_id": i.candidate_id, "disposition": "ADMITTED"})()
                for i in original_input.evidence
            ),
        })(),
        candidate_projections=[
            __import__("app.modules.model_context", fromlist=["x"]).CandidateContentProjection(
                document_id=i.candidate_id, content=i.content, title=i.title,
                source_identity=i.source_identity, page=i.page, chunk_id=i.chunk_id,
            )
            for i in original_input.evidence
        ],
        question=record.question,
        conversation_context=rebuilt_ctx,
    )
    assert ive_common.build_model_input_prompt(rebuilt_input) == original_prompt
    assert rebuilt_input == original_input
