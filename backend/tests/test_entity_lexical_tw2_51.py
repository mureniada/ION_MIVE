"""OP-DEC-20261004-TW2-51: entity lexical fallback + Turn Record TR-A2.

Three layers, all offline (no provider SDK, no network, no credentials):

- the pure selection policy (`entity_lexical`): detector, matching tiers,
  ordering, de-duplication, cap, cache verification and fingerprint;
- the Qdrant adapter over an in-memory `qdrant_client` collection, wrapped in
  a client proxy that refuses every non-read call;
- a REAL `Core` over the stand-ins the session/conversation tests use, with
  the real Context Pack builder, Core Adapter, governed-evidence gate, Model
  Context Builder and Turn Record materializer.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
import uuid
from types import SimpleNamespace

import pytest

import app.core.orchestrator as orch
from app.core.models import (
    LEXICAL_STATUS_ADDED,
    LEXICAL_STATUS_NO_MATCH,
    LEXICAL_STATUS_NOT_TRIGGERED,
    LEXICAL_STATUS_UNAVAILABLE,
    RETRIEVAL_BRANCH_DENSE,
    RETRIEVAL_BRANCH_LEXICAL,
    Evidence,
    LexicalRetrievalOutcome,
)
from app.core.config import Settings, SettingsError
from app.modules import ive_common
from app.modules.context_pack import ContextPackBuilder
from app.modules.conversation_context import PriorTurnContext, build_conversation_context
from app.modules.execution_profile import STANDARD_GEMINI
from app.modules.model_gateway import ModelGateway
from app.modules.renderer.renderer import DeterministicRenderer
from app.modules.retrieval import entity_lexical as el
from app.modules.retrieval.embeddings import HashingEmbedder
from app.modules.retrieval.qdrant_store import QdrantRetrieval, point_id_for
from app.modules.turn_record import (
    TURN_RECORD_CONTRACT_ID,
    RetrievalAccountingBinding,
    TurnClosureState,
    TurnRecordMaterializationError,
)
from tests.test_orchestrator_conversation_context_v0_1 import ScriptedEngine, ive_report
from tests.test_session_controller_v0_1 import (
    _Bridge,
    _Clock,
    _Mive,
    _Pricing,
    _adapter,
    _patch_gate,
)

# --------------------------------------------------------------------- #
# corpus fixture: the citation forms "Oomen" actually takes in v4
# --------------------------------------------------------------------- #
CORPUS = {
    "TW-OBJ-0465::c0": "Deviations in Sound Waves Authors P. Oomen a R. Geffen a Company a The Works Research Institute",
    "TW-OBJ-0435::c0": "In vitro study Authors D. Gentile a N. Atassi a B. Farran a P. Oomen a The Works Research Institute",
    "TW-OBJ-0462::c13": "References [63] P. Oomen, P. Holleman, L. De Klerk, 4DSOUND: A New Approach",
    "TW-OBJ-0206::c0": "Citation: Csanad, M.; Val Baker, A.K.F.; Oomen, P. A Frequency-Independent Phase Shifter.",
    "TW-OBJ-0053::c0": "Experimental results. Paul Oomen, Rona Geffen, Daniela Gentile, Nour Atassi",
    "TW-OBJ-0477::c0": "amplitude difference and phase shift, according to Oomen et al [41].",
    "TW-OBJ-0999::c0": "Spatial sound affects wellbeing; no named author in this unit.",
    "TW-OBJ-0998::c0": "Oomenite is a different word and must not match the surname tier.",
    "TW-OBJ-0997::c0": "What is ION and how does it work? ION is a wavelet framing.",
}
# Stored `ion_content_pack_lineage.epistemic_role`, mirroring the v4 metadata of
# these units; None = the unit carries no lineage at all (like a legacy point).
ROLES = {
    "TW-OBJ-0465::c0": "DATA_DESCRIPTION",
    "TW-OBJ-0435::c0": "DATA_DESCRIPTION",
    "TW-OBJ-0462::c13": "SOURCE_AUTHOR_CLAIM",
    "TW-OBJ-0206::c0": "DATA_DESCRIPTION",
    "TW-OBJ-0053::c0": "DATA_DESCRIPTION",
    "TW-OBJ-0477::c0": "METHOD_OR_MODEL",
    "TW-OBJ-0999::c0": "SCIENTIFIC_EMPIRICAL_FINDING",
    "TW-OBJ-0998::c0": None,
    "TW-OBJ-0997::c0": "THE_WORKS_SELF_DESCRIPTION",
}
ORDERED_OOMEN = (
    # tier 1 (full form "P. Oomen"): DATA_DESCRIPTION by offset, then SOURCE_AUTHOR_CLAIM
    "TW-OBJ-0465::c0", "TW-OBJ-0435::c0", "TW-OBJ-0462::c13",
    # tier 2 (whole-word surname "Oomen"): DATA_DESCRIPTION by offset, then the middle role
    "TW-OBJ-0053::c0", "TW-OBJ-0206::c0", "TW-OBJ-0477::c0",
)


def _payload(did):
    role = ROLES[did]
    return {} if role is None else {"ion_content_pack_lineage": {"epistemic_role": role}}


def _entries():
    return [
        el.CacheEntry(point_id=point_id_for(did), document_id=did, content=text,
                      epistemic_role=el.normalize_epistemic_role(_payload(did)))
        for did, text in CORPUS.items()
    ]


def _expected_order():
    """The adopted TW2-52 order, derived independently from fixture text + ROLES."""
    prio = {"DATA_DESCRIPTION": 0, "SOURCE_AUTHOR_CLAIM": 2}
    keys = []
    for did, text in CORPUS.items():
        full = re.search(r"(?<![^\W\d_])P\.\s*Oomen(?![^\W\d_])", text)
        sur = re.search(r"(?<![^\W\d_])Oomen(?![^\W\d_])", text)
        role = prio.get(ROLES[did], 1)
        if full:
            keys.append((1, role, full.start(), did))
        elif sur:
            keys.append((2, role, sur.start(), did))
    return tuple(k[-1] for k in sorted(keys))


# --------------------------------------------------------------------- #
# 1. detector (items 3, 5) — phase 1 only
# --------------------------------------------------------------------- #
def test_who_is_p_oomen_triggers():
    assert el.detect_entities("Who is P. Oomen?") == (el.EntityTerm("P", "Oomen"),)
    assert el.detect_entities("What does the material say about P. Oomen?")[0].full_form == "P. Oomen"
    assert el.detect_entities("Who is P.Oomen?") == (el.EntityTerm("P", "Oomen"),)


@pytest.mark.parametrize("question", [
    "What is ION and how does it work?",
    "Who are some of the key people involved with ION?",
    "Who is Oomen?",                      # surname-only: not adopted
    "Who is Paul Oomen?",                 # multi-token name: not adopted
    "What did the U.S. Army study?",      # abbreviation chain
    "e.g. Oomen", "Dr. Smith", "Fig. 9A shows it",
    "Are Faraday Wave patterns reproducible?",  # capitalized pair: not adopted
])
def test_detector_does_not_trigger_outside_phase_one(question):
    assert el.detect_entities(question) == ()


def test_detector_is_unicode_aware():
    assert el.detect_entities("Was it M. Csanád?") == (el.EntityTerm("M", "Csanád"),)


# --------------------------------------------------------------------- #
# 2. matching, ordering, de-duplication, cap (items 6-9)
# --------------------------------------------------------------------- #
def test_lexical_lookup_reproduces_all_oomen_units_in_adopted_order():
    matches = el.rank_matches(_entries(), el.detect_entities("Who is P. Oomen?"))
    assert tuple(m.document_id for m in matches) == ORDERED_OOMEN == _expected_order()
    assert [m.tier for m in matches] == [1, 1, 1, 2, 2, 2]
    assert [m.role_priority for m in matches] == [0, 0, 2, 0, 0, 1]
    assert "TW-OBJ-0998::c0" not in {m.document_id for m in matches}  # "Oomenite"


def test_ordering_is_stable_under_input_permutation():
    terms = el.detect_entities("Who is P. Oomen?")
    forward = el.rank_matches(_entries(), terms)
    backward = el.rank_matches(list(reversed(_entries())), terms)
    assert forward == backward


def test_entity_whose_full_form_is_absent_yields_nothing():
    # "I. Then" is detected, but the full form occurs nowhere: no surname-tier sweep.
    entries = _entries() + [el.CacheEntry("p-x", "X::c0", "Then the study ended.", "DATA_DESCRIPTION")]
    assert el.rank_matches(entries, el.detect_entities("part I. Then what?")) == ()


def test_duplicates_already_retrieved_densely_are_removed():
    matches = el.rank_matches(_entries(), el.detect_entities("Who is P. Oomen?"))
    picked = el.select_matches(matches, exclude_document_ids={"TW-OBJ-0465::c0"}, limit=3)
    assert [m.document_id for m in picked] == ["TW-OBJ-0435::c0", "TW-OBJ-0462::c13", "TW-OBJ-0053::c0"]


def test_at_most_limit_lexical_additions():
    matches = el.rank_matches(_entries(), el.detect_entities("Who is P. Oomen?"))
    assert len(el.select_matches(matches, exclude_document_ids=(), limit=3)) == 3
    assert len(el.select_matches(matches, exclude_document_ids=(), limit=1)) == 1


# --------------------------------------------------------------------- #
# 3. runtime cache (items 15, 16)
# --------------------------------------------------------------------- #
def test_cache_fingerprint_is_deterministic_and_order_independent():
    a = el.cache_fingerprint(_entries())
    assert a == el.cache_fingerprint(list(reversed(_entries())))
    assert a.startswith("sha256:") and len(a) == 71
    changed = _entries()
    changed[0] = dataclasses.replace(changed[0], content=changed[0].content + "!")
    assert el.cache_fingerprint(changed) != a


def test_cache_builds_once_and_is_bound_to_one_collection():
    calls = []

    def loader():
        calls.append(1)
        return len(CORPUS), _entries(), len(CORPUS)

    cache = el.LexicalRuntimeCache("coll_a", loader)
    first, second = cache.snapshot(), cache.snapshot()
    assert first is second and len(calls) == 1
    assert first.collection == "coll_a" and first.point_count == len(CORPUS)


@pytest.mark.parametrize("loaded", [
    lambda: (5, _entries(), 6),                     # count changed during build
    lambda: (99, _entries(), 99),                   # scrolled fewer than reported
    lambda: (2, [el.CacheEntry("p", "A", "x", el.NO_EPISTEMIC_ROLE)] * 2, 2),  # duplicate ids
    lambda: (1, [el.CacheEntry("p", "A", "x", "")], 1),  # role must never be empty
])
def test_cache_verification_failure_raises_cache_error(loaded):
    with pytest.raises(el.LexicalCacheError):
        el.LexicalRuntimeCache("coll_a", loaded).snapshot()


def test_cache_load_exception_is_wrapped_and_not_cached():
    attempts = []

    def loader():
        attempts.append(1)
        raise ConnectionError("store down")

    cache = el.LexicalRuntimeCache("coll_a", loader)
    for _ in range(2):
        with pytest.raises(el.LexicalCacheError):
            cache.snapshot()
    assert len(attempts) == 2  # a failed build is never cached


# --------------------------------------------------------------------- #
# 4. Qdrant adapter over an in-memory collection (items 11-14, 20)
# --------------------------------------------------------------------- #
_READ_METHODS = {"count", "scroll", "retrieve", "query_points"}


class ReadOnlyClient:
    """Forwards only the read calls the adapter may make; records them."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = []

    def __getattr__(self, name):
        if name not in _READ_METHODS:
            raise AssertionError(f"non-read Qdrant call attempted: {name}")
        self.calls.append(name)
        return getattr(self._inner, name)


def _qdrant(collection="tw_unified_test"):
    from qdrant_client import QdrantClient, models

    embedder = HashingEmbedder(dimension=64)
    inner = QdrantClient(location=":memory:")
    inner.create_collection(
        collection, vectors_config=models.VectorParams(size=64, distance=models.Distance.COSINE)
    )
    inner.upsert(collection, points=[
        models.PointStruct(
            id=point_id_for(did), vector=embedder.embed([text])[0],
            payload={"document_id": did, "source_id": did.split("::")[0], "title": "",
                     "content": text, "page": None, "chunk_id": did,
                     "checksum": "c-" + did, "ingestion_version": "v", **_payload(did)},
        )
        for did, text in CORPUS.items()
    ])
    store = QdrantRetrieval(embedder, url="memory://", collection=collection)
    store._client = ReadOnlyClient(inner)
    store._models = models
    return store, store._client


def test_dense_retrieve_unchanged_and_marked_dense():
    store, _ = _qdrant()
    hits = store.retrieve("Who is P. Oomen?", 5)
    assert len(hits) == 5
    assert all(h.retrieval_branch == RETRIEVAL_BRANCH_DENSE for h in hits)
    assert all(isinstance(h.score, float) for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert all(h.metadata == {"checksum": "c-" + h.document_id, "ingestion_version": "v"} for h in hits)


def test_lexical_candidates_materialize_by_point_id_with_no_score():
    store, client = _qdrant()
    outcome = store.lexical_candidates("Who is P. Oomen?", exclude_document_ids=(), limit=3)
    assert outcome.status == LEXICAL_STATUS_ADDED
    assert outcome.terms == ("P. Oomen",) and outcome.candidate_count == 6
    assert [e.document_id for e in outcome.evidence] == list(ORDERED_OOMEN[:3])
    assert all(e.score is None and e.retrieval_branch == RETRIEVAL_BRANCH_LEXICAL for e in outcome.evidence)
    assert all(e.content == CORPUS[e.document_id] for e in outcome.evidence)
    assert "retrieve" in client.calls  # point-by-id materialization
    assert outcome.cache_collection == "tw_unified_test"
    assert outcome.cache_fingerprint == el.cache_fingerprint(_entries())


def test_lexical_not_triggered_never_touches_the_store():
    store, client = _qdrant()
    outcome = store.lexical_candidates("What is ION and how does it work?", exclude_document_ids=(), limit=3)
    assert outcome == LexicalRetrievalOutcome(status=LEXICAL_STATUS_NOT_TRIGGERED)
    assert client.calls == []


def test_all_matches_already_dense_is_no_match_with_cache_identity():
    store, _ = _qdrant()
    outcome = store.lexical_candidates("Who is P. Oomen?", exclude_document_ids=ORDERED_OOMEN, limit=3)
    assert outcome.status == LEXICAL_STATUS_NO_MATCH
    assert outcome.evidence == () and outcome.candidate_count == 6
    assert outcome.cache_fingerprint is not None


def test_cache_failure_in_adapter_is_unavailable():
    store, client = _qdrant()
    client._inner.count = lambda **kw: (_ for _ in ()).throw(ConnectionError("down"))
    outcome = store.lexical_candidates("Who is P. Oomen?", exclude_document_ids=(), limit=3)
    assert outcome.status == LEXICAL_STATUS_UNAVAILABLE and outcome.evidence == ()


def test_lexical_path_has_no_qdrant_write_capability():
    src = inspect.getsource(el)
    assert not re.search(r"\b(upsert|delete|create_collection|recreate|update|set_payload|"
                         r"overwrite_payload|create_payload_index|qdrant_client)\b", src)
    from app.modules.retrieval import qdrant_store

    for name in ("lexical_candidates", "_load_lexical_entries", "_materialize_by_id",
                 "_lexical_cache_instance"):
        body = inspect.getsource(getattr(qdrant_store.QdrantRetrieval, name))
        assert not re.search(r"\.(upsert|delete\w*|create_\w+|recreate\w*|update\w*|set_payload|"
                             r"overwrite_payload)\(", body), name


# --------------------------------------------------------------------- #
# 5. Evidence score semantics (items 12-14)
# --------------------------------------------------------------------- #
def test_evidence_score_and_branch_pairing_is_enforced():
    Evidence("A", "S", "", "x", 0.4)  # DENSE default with a score
    Evidence("A", "S", "", "x", None, retrieval_branch=RETRIEVAL_BRANCH_LEXICAL)
    with pytest.raises(ValueError):
        Evidence("A", "S", "", "x", None)  # dense without score
    with pytest.raises(ValueError):
        Evidence("A", "S", "", "x", 0.4, retrieval_branch=RETRIEVAL_BRANCH_LEXICAL)
    with pytest.raises(ValueError):
        Evidence("A", "S", "", "x", 0.4, retrieval_branch="HYBRID")


# --------------------------------------------------------------------- #
# 6. real Core (items 1-4, 10, 16-19)
# --------------------------------------------------------------------- #
def _ev(did, score=0.5):
    return Evidence(document_id=did, source_id=did.split("::")[0], title="",
                    content=CORPUS.get(did, "dense body " + did), score=score, chunk_id=did)


def _lex(did):
    return Evidence(document_id=did, source_id=did.split("::")[0], title="",
                    content=CORPUS[did], score=None, chunk_id=did,
                    retrieval_branch=RETRIEVAL_BRANCH_LEXICAL)


class StubRetrieval:
    """Dense stand-in plus an optional lexical branch, recording what it saw."""

    def __init__(self, dense_ids=("TW-OBJ-0999::c0", "TW-OBJ-0997::c0"), lexical=None,
                 lexical_error=None, has_lexical=True):
        self.dense_ids = tuple(dense_ids)
        self.dense_queries, self.lexical_questions = [], []
        self._lexical, self._lexical_error = lexical, lexical_error
        if not has_lexical:
            self.lexical_candidates = None

    def retrieve(self, question, top_k):
        self.dense_queries.append(question)
        return [_ev(d, 0.9 - i / 10) for i, d in enumerate(self.dense_ids[:top_k])]

    def lexical_candidates(self, question, *, exclude_document_ids, limit):
        self.lexical_questions.append(question)
        if self._lexical_error is not None:
            raise self._lexical_error
        if self._lexical is not None:
            return self._lexical
        terms = el.detect_entities(question)
        if not terms:
            return LexicalRetrievalOutcome(status=LEXICAL_STATUS_NOT_TRIGGERED)
        matches = el.rank_matches(_entries(), terms)
        picked = el.select_matches(matches, exclude_document_ids=exclude_document_ids, limit=limit)
        common = dict(terms=tuple(t.full_form for t in terms), candidate_count=len(matches),
                      cache_collection="ion_corpus_v1", cache_fingerprint=el.cache_fingerprint(_entries()))
        if not picked:
            return LexicalRetrievalOutcome(status=LEXICAL_STATUS_NO_MATCH, **common)
        return LexicalRetrievalOutcome(status=LEXICAL_STATUS_ADDED,
                                       evidence=tuple(_lex(m.document_id) for m in picked), **common)


def _real_core(monkeypatch, *, retrieval, enabled, admitted=None, reports=None, top_k=5):
    core = orch.Core.__new__(orch.Core)
    core._settings = SimpleNamespace(default_top_k=top_k, context_char_budget=60000,
                                     qdrant_collection="ion_corpus_v1",
                                     entity_lexical_enabled=enabled, entity_lexical_max=3)
    core._clock = _Clock()
    core._retrieval = retrieval
    core._build = ContextPackBuilder(char_budget=60000)
    core._core_adapter = _adapter(_Bridge())
    core._execution_profile = STANDARD_GEMINI
    engine = ScriptedEngine(reports or [ive_report(claim_ids=(retrieval.dense_ids[0],))])
    core._model_gateway = ModelGateway({"gemini": engine})
    core._mive = _Mive()
    core._renderer = DeterministicRenderer()
    core._pricing = _Pricing()
    core._composer = None
    core._voe_runtime_profile = None
    seen = {}
    real_govern = core._core_adapter.govern

    def govern(request):
        seen["candidates"] = tuple(c.document_id for c in request.candidates)
        return real_govern(request)

    core._core_adapter.govern = govern

    class AdmitAllSubmitted:
        def __call__(self, **kwargs):
            ids = admitted if admitted is not None else seen["candidates"]
            from tests.test_session_controller_v0_1 import _native_for
            return _native_for(ids)

    import app.modules.core_adapter.facade as facade
    monkeypatch.setattr(facade, "run_runtime_admission_gate", AdmitAllSubmitted())
    return core, engine, seen


def _ask(core, question, **kw):
    records = []
    result = core.ask(question, on_turn_record=records.append, **kw)
    return result, records[0]


def test_flag_off_dense_path_unchanged(monkeypatch):
    on_retrieval = StubRetrieval()
    off_retrieval = StubRetrieval()
    core_off, engine_off, seen_off = _real_core(monkeypatch, retrieval=off_retrieval, enabled=False)
    _, record_off = _ask(core_off, "Who is P. Oomen?")
    assert off_retrieval.lexical_questions == []          # never called
    assert record_off.retrieval_accounting is None        # TR-A2 binding absent
    assert seen_off["candidates"] == off_retrieval.dense_ids
    assert record_off.governed_evidence.retrieved_count == 2
    assert record_off.turn_record_contract_id == TURN_RECORD_CONTRACT_ID == "ION_TURN_RECORD_V0_3"
    # same dense evidence and model input as a turn with the flag missing entirely
    core_missing, engine_missing, _ = _real_core(monkeypatch, retrieval=on_retrieval, enabled=False)
    del core_missing._settings.entity_lexical_enabled
    _ask(core_missing, "Who is P. Oomen?")
    assert engine_off.prompts == engine_missing.prompts


def test_detector_not_triggered_dense_path_unchanged(monkeypatch):
    on = StubRetrieval()
    core_on, engine_on, seen_on = _real_core(monkeypatch, retrieval=on, enabled=True)
    _, record = _ask(core_on, "What is ION and how does it work?")
    off = StubRetrieval()
    core_off, engine_off, _ = _real_core(monkeypatch, retrieval=off, enabled=False)
    _ask(core_off, "What is ION and how does it work?")
    assert seen_on["candidates"] == on.dense_ids
    assert engine_on.prompts == engine_off.prompts
    acc = record.retrieval_accounting
    assert acc.lexical_status == "NOT_TRIGGERED" and acc.lexical_triggered is False
    assert acc.dense_retrieved == 2 and acc.lexical_added_document_ids == ()


def test_fresh_oomen_turn_adds_lexical_candidates_through_governance(monkeypatch):
    stub = StubRetrieval()
    core, engine, seen = _real_core(monkeypatch, retrieval=stub, enabled=True)
    _, record = _ask(core, "Who is P. Oomen?")
    added = ORDERED_OOMEN[:3]
    assert stub.lexical_questions == ["Who is P. Oomen?"]
    # lexical candidates reach governance with the dense ones
    assert seen["candidates"] == stub.dense_ids + added
    # and, once admitted, reach the model context like any other evidence
    assert [i.candidate_id for i in engine.model_inputs[0].evidence] == list(stub.dense_ids + added)
    acc = record.retrieval_accounting
    assert acc.lexical_status == "ADDED" and acc.lexical_terms == ("P. Oomen",)
    assert acc.lexical_candidates == 6 and acc.lexical_added_document_ids == added
    assert record.governed_evidence.retrieved_count == acc.dense_retrieved + len(added)
    assert record.configuration.effective_top_k == 5  # dense top-k only


def test_unverified_lexical_candidate_fails_closed_and_never_reaches_a_model(monkeypatch):
    """Governance at v0.1 is set-level and fail-closed: a candidate the gate
    does not verify fails the turn before any Model Context exists. A lexical
    candidate gets no exemption — it can never bypass admission."""
    from app.core import errors

    stub = StubRetrieval()
    admitted = stub.dense_ids + ("TW-OBJ-0465::c0",)  # 0435::c0 and 0462::c13 unverified
    core, engine, seen = _real_core(monkeypatch, retrieval=stub, enabled=True, admitted=admitted)
    records = []
    with pytest.raises(errors.ContextPackError):
        core.ask("Who is P. Oomen?", on_turn_record=records.append)
    assert "TW-OBJ-0462::c13" in seen["candidates"]   # it WAS submitted to governance
    assert engine.model_inputs == []                    # and no model ever saw anything
    assert records[0].closure_state is TurnClosureState.FAILED
    assert records[0].retrieval_accounting.lexical_status == "ADDED"


def test_warm_session_root_question_does_not_trigger_lexical(monkeypatch):
    stub = StubRetrieval()
    core, _, seen = _real_core(monkeypatch, retrieval=stub, enabled=True)
    prior = PriorTurnContext(turn_id="T-1", question="Who is P. Oomen?",
                             interpretation="An interpretation.", uncertainty=())
    ctx = build_conversation_context((prior,), root_question="Who is P. Oomen?")
    _, record = _ask(core, "What did the study measure?", conversation_context=ctx)
    assert stub.dense_queries == ["Who is P. Oomen?\nWhat did the study measure?"]
    assert stub.lexical_questions == ["What did the study measure?"]  # current question only
    assert record.retrieval_accounting.lexical_status == "NOT_TRIGGERED"
    assert seen["candidates"] == stub.dense_ids


def test_warm_session_current_question_triggers_independently(monkeypatch):
    stub = StubRetrieval(dense_ids=("TW-OBJ-0465::c0", "TW-OBJ-0999::c0"))
    core, _, seen = _real_core(monkeypatch, retrieval=stub, enabled=True)
    prior = PriorTurnContext(turn_id="T-1", question="What did the sound study find?",
                             interpretation="An interpretation.", uncertainty=())
    ctx = build_conversation_context((prior,), root_question="What did the sound study find?")
    _, record = _ask(core, "Who is P. Oomen?", conversation_context=ctx)
    assert stub.lexical_questions == ["Who is P. Oomen?"]
    acc = record.retrieval_accounting
    # 0465::c0 was already dense: de-duplicated, three NEW lexical additions
    assert acc.lexical_added_document_ids == ("TW-OBJ-0435::c0", "TW-OBJ-0462::c13", "TW-OBJ-0053::c0")
    assert record.governed_evidence.retrieved_count == 5


@pytest.mark.parametrize("stub_kwargs", [
    {"lexical_error": ConnectionError("cache build failed")},
    {"has_lexical": False},
    {"lexical": LexicalRetrievalOutcome(status=LEXICAL_STATUS_ADDED,
                                        evidence=tuple(_lex(d) for d in ORDERED_OOMEN))},  # over cap
    {"lexical": "not an outcome"},
])
def test_lexical_failure_is_unavailable_and_dense_turn_completes(monkeypatch, stub_kwargs):
    stub = StubRetrieval(**stub_kwargs)
    core, engine, seen = _real_core(monkeypatch, retrieval=stub, enabled=True)
    result, record = _ask(core, "Who is P. Oomen?")
    assert result.status == "success" and record.closure_state is TurnClosureState.COMPLETED
    acc = record.retrieval_accounting
    assert acc.lexical_status == "UNAVAILABLE" and acc.lexical_terms == ("P. Oomen",)
    assert acc.lexical_added_document_ids == ()
    assert seen["candidates"] == stub.dense_ids
    assert record.governed_evidence.retrieved_count == acc.dense_retrieved == 2


def test_failed_turn_after_retrieval_keeps_accounting(monkeypatch):
    stub = StubRetrieval()
    core, _, _ = _real_core(monkeypatch, retrieval=stub, enabled=True)
    core._model_gateway = ModelGateway({"gemini": ScriptedEngine([])})  # engine raises on pop
    records = []
    with pytest.raises(Exception):
        core.ask("Who is P. Oomen?", on_turn_record=records.append)
    record = records[0]
    assert record.closure_state is TurnClosureState.FAILED
    assert record.retrieval_accounting.lexical_status == "ADDED"
    assert record.governed_evidence.retrieved_count == 5


def test_bounded_answer_inputs_lexical_mentions_add_no_claims(monkeypatch):
    """Item 19 at the boundary the runtime controls: a lexical candidate enters
    the model input as its unit text only — no synthesized profile, role or
    biography text, no entity annotation, and the question is unchanged. (What
    the model then writes is not testable offline; see the offline replay.)"""
    stub = StubRetrieval()
    core, engine, _ = _real_core(monkeypatch, retrieval=stub, enabled=True)
    _ask(core, "Who is P. Oomen?")
    model_input = engine.model_inputs[0]
    lexical_items = [i for i in model_input.evidence if i.candidate_id in ORDERED_OOMEN]
    assert lexical_items and all(i.content == CORPUS[i.candidate_id] for i in lexical_items)
    assert model_input.question == "Who is P. Oomen?"
    prompt = engine.prompts[0]
    for marker in ("LEXICAL", "retrieval_branch", "biography", "profile of"):
        assert marker not in prompt
    assert ive_common.build_model_input_prompt(model_input) == prompt


# --------------------------------------------------------------------- #
# 7. Turn Record TR-A2 (items 17, 18)
# --------------------------------------------------------------------- #
def _acc(**overrides):
    base = dict(dense_retrieved=5, lexical_triggered=True, lexical_terms=("P. Oomen",),
                lexical_candidates=6, lexical_added_document_ids=("A", "B"),
                lexical_cache_collection="c", lexical_cache_fingerprint="sha256:x",
                lexical_status="ADDED")
    base.update(overrides)
    return base


@pytest.mark.parametrize("overrides", [
    {"lexical_status": "MAYBE"},
    {"lexical_status": "ADDED", "lexical_added_document_ids": ()},
    {"lexical_status": "NO_MATCH"},  # with additions
    {"lexical_status": "UNAVAILABLE"},  # with additions
    {"lexical_status": "NOT_TRIGGERED"},  # with terms/additions
    {"lexical_candidates": 1},  # fewer candidates than additions
    {"lexical_added_document_ids": ("A", "A")},
    {"lexical_status": "ADDED", "lexical_cache_fingerprint": None},
    {"dense_retrieved": -1},
])
def test_accounting_binding_refuses_inconsistent_status(overrides):
    with pytest.raises(TurnRecordMaterializationError):
        RetrievalAccountingBinding(**_acc(**overrides))


def test_accounting_binding_accepts_each_consistent_status():
    RetrievalAccountingBinding(**_acc())
    RetrievalAccountingBinding(**_acc(lexical_status="NO_MATCH", lexical_added_document_ids=()))
    RetrievalAccountingBinding(**_acc(lexical_status="UNAVAILABLE", lexical_added_document_ids=(),
                                      lexical_cache_collection=None, lexical_cache_fingerprint=None,
                                      lexical_candidates=0))
    RetrievalAccountingBinding(**_acc(lexical_status="NOT_TRIGGERED", lexical_triggered=False,
                                      lexical_terms=(), lexical_candidates=0,
                                      lexical_added_document_ids=(), lexical_cache_collection=None,
                                      lexical_cache_fingerprint=None))


def test_turn_record_enforces_retrieved_count_invariant(monkeypatch):
    stub = StubRetrieval()
    core, _, _ = _real_core(monkeypatch, retrieval=stub, enabled=True)
    _, record = _ask(core, "Who is P. Oomen?")
    bad = RetrievalAccountingBinding(**{
        f.name: getattr(record.retrieval_accounting, f.name)
        for f in dataclasses.fields(RetrievalAccountingBinding)
    } | {"dense_retrieved": 1})
    with pytest.raises(TurnRecordMaterializationError):
        dataclasses.replace(record, retrieval_accounting=bad)


# --------------------------------------------------------------------- #
# 8. configuration
# --------------------------------------------------------------------- #
def test_settings_default_off_and_strict():
    s = Settings.load({})
    assert s.entity_lexical_enabled is False and s.entity_lexical_max == 3
    assert Settings.load({"ENTITY_LEXICAL_ENABLED": "true"}).entity_lexical_enabled is True
    for bad in ("maybe", "2"):
        with pytest.raises(SettingsError):
            Settings.load({"ENTITY_LEXICAL_ENABLED": bad})
    for bad in ("0", "-1", "x"):
        with pytest.raises(SettingsError):
            Settings.load({"ENTITY_LEXICAL_MAX": bad})


def test_point_ids_are_the_deterministic_uuid5_of_document_ids():
    assert point_id_for("TW-OBJ-0465::c0") == "f55f2dbe-a26a-5d63-b278-6b9a7755cd7c"
    assert uuid.UUID(point_id_for("x")).version == 5


# --------------------------------------------------------------------- #
# 9. OP-DEC-20261004-TW2-52 amendment: role-aware ordering, projection,
#    fingerprint, full-form gating, NO_MATCH semantics.
#    ADMISSION_ALL_OR_NOTHING = VERIFIED and unchanged (see the fail-closed
#    test above); nothing here touches admission.
# --------------------------------------------------------------------- #
def _e(did, text, role):
    return el.CacheEntry(point_id="p-" + did, document_id=did, content=text, epistemic_role=role)


P_OOMEN = el.detect_entities("Who is P. Oomen?")


def _order(entries):
    return [m.document_id for m in el.rank_matches(entries, P_OOMEN)]


def test_tw2_52_data_description_before_source_author_claim_same_tier():
    entries = [_e("A", "P. Oomen ref", "SOURCE_AUTHOR_CLAIM"),
               _e("B", "xxxxxxxxxx P. Oomen byline", "DATA_DESCRIPTION")]
    assert _order(entries) == ["B", "A"]  # role beats an earlier offset


def test_tw2_52_other_roles_and_sentinel_sort_between():
    entries = [_e("S", "P. Oomen", "SOURCE_AUTHOR_CLAIM"),
               _e("M", "P. Oomen", "METHOD_OR_MODEL"),
               _e("N", "P. Oomen", el.NO_EPISTEMIC_ROLE),
               _e("D", "P. Oomen", "DATA_DESCRIPTION")]
    order = _order(entries)
    assert order[0] == "D" and order[-1] == "S"
    assert set(order[1:3]) == {"M", "N"}
    assert el.role_priority("METHOD_OR_MODEL") == el.role_priority(el.NO_EPISTEMIC_ROLE) == 1


def test_tw2_52_match_tier_stronger_than_role():
    entries = [_e("SUR_DD", "Oomen alone, no full form here", "DATA_DESCRIPTION"),
               _e("FULL_SAC", "P. Oomen in a reference", "SOURCE_AUTHOR_CLAIM")]
    assert _order(entries) == ["FULL_SAC", "SUR_DD"]


def test_tw2_52_full_form_ahead_of_surname_tier():
    entries = [_e("SUR", "Oomen", "DATA_DESCRIPTION"), _e("FULL", "zzzz P. Oomen", "DATA_DESCRIPTION")]
    assert [(m.document_id, m.tier) for m in el.rank_matches(entries, P_OOMEN)] == [("FULL", 1), ("SUR", 2)]


def test_tw2_52_earliest_occurrence_then_document_id():
    entries = [_e("B", "aaaa P. Oomen", "DATA_DESCRIPTION"),
               _e("A", "aaaaaaaa P. Oomen", "DATA_DESCRIPTION"),
               _e("C", "aaaa P. Oomen", "DATA_DESCRIPTION")]
    assert _order(entries) == ["B", "C", "A"]  # offset first, then document_id (B < C)


@pytest.mark.parametrize("payload", [
    {},                                                    # no lineage
    {"ion_content_pack_lineage": None},
    {"ion_content_pack_lineage": "DATA_DESCRIPTION"},      # lineage not a mapping
    {"ion_content_pack_lineage": {}},                      # no role
    {"ion_content_pack_lineage": {"epistemic_role": None}},
    {"ion_content_pack_lineage": {"epistemic_role": 7}},   # non-string
    {"ion_content_pack_lineage": {"epistemic_role": ""}},  # empty string
    None,
])
def test_tw2_52_missing_or_unusable_role_is_exact_sentinel(payload):
    assert el.normalize_epistemic_role(payload) == "__NO_EPISTEMIC_ROLE__" == el.NO_EPISTEMIC_ROLE


@pytest.mark.parametrize("stored", ["DATA_DESCRIPTION", " DATA_DESCRIPTION ", "data_description",
                                    "SOURCE_AUTHOR_CLAIM", "THE_WORKS_POSITION"])
def test_tw2_52_stored_role_is_used_verbatim(stored):
    role = el.normalize_epistemic_role({"ion_content_pack_lineage": {"epistemic_role": stored}})
    assert role == stored  # no trim, no case folding
    expected = {"DATA_DESCRIPTION": 0, "SOURCE_AUTHOR_CLAIM": 2}.get(stored, 1)
    assert el.role_priority(role) == expected  # " DATA_DESCRIPTION " is NOT first


def test_tw2_52_role_never_inferred_from_free_text():
    payload = {"ion_content_pack_lineage": {
        "source_location": "PDF p.1: title block (title, authors, affiliations)",
        "category": "SCIENTIFIC_AND_TECHNICAL"},
        "content": "Authors P. Oomen", "title": "Title block"}
    assert el.normalize_epistemic_role(payload) == el.NO_EPISTEMIC_ROLE
    body = inspect.getsource(el.normalize_epistemic_role).split('"""')[-1]
    for field in ('"source_location"', '"content"', '"title"', '"chunk_id"', '"page"'):
        assert field not in body  # only the lineage role key is ever read


def test_tw2_52_source_location_never_affects_adapter_ordering():
    store_a, _ = _qdrant("coll_loc_a")
    store_b, client_b = _qdrant("coll_loc_b")
    # rewrite every unit's free-text locator in collection B only (test fixture setup)
    for did in CORPUS:
        lineage = dict(_payload(did).get("ion_content_pack_lineage", {}))
        lineage["source_location"] = "References [1]-[99] " + did
        client_b._inner.set_payload("coll_loc_b", {"ion_content_pack_lineage": lineage},
                                    points=[point_id_for(did)])
    a = store_a.lexical_candidates("Who is P. Oomen?", exclude_document_ids=(), limit=6)
    b = store_b.lexical_candidates("Who is P. Oomen?", exclude_document_ids=(), limit=6)
    assert [e.document_id for e in a.evidence] == [e.document_id for e in b.evidence] == list(ORDERED_OOMEN)


def test_tw2_52_fingerprint_changes_with_role_and_is_deterministic():
    base = _entries()
    fp = el.cache_fingerprint(base)
    assert fp == el.cache_fingerprint(list(reversed(base)))
    changed = [dataclasses.replace(e, epistemic_role="METHOD_OR_MODEL")
               if e.document_id == "TW-OBJ-0465::c0" else e for e in base]
    assert el.cache_fingerprint(changed) != fp
    sentinel = [dataclasses.replace(e, epistemic_role=el.NO_EPISTEMIC_ROLE) for e in base]
    assert el.cache_fingerprint(sentinel) != fp


def test_tw2_52_adapter_projects_stored_role_and_sentinel():
    store, _ = _qdrant()
    snap = store._lexical_cache_instance().snapshot()
    roles = {e.document_id: e.epistemic_role for e in snap.entries}
    assert roles["TW-OBJ-0465::c0"] == "DATA_DESCRIPTION"
    assert roles["TW-OBJ-0462::c13"] == "SOURCE_AUTHOR_CLAIM"
    assert roles["TW-OBJ-0998::c0"] == "__NO_EPISTEMIC_ROLE__"
    assert snap.fingerprint == el.cache_fingerprint(_entries())


def test_tw2_52_full_form_gating_blocks_surname_expansion():
    # "Oomen" occurs in many units, but "Q. Oomen" occurs nowhere: no expansion.
    terms = el.detect_entities("Who is Q. Oomen?")
    assert terms == (el.EntityTerm("Q", "Oomen"),)
    assert el.rank_matches(_entries(), terms) == ()
    store, _ = _qdrant()
    outcome = store.lexical_candidates("Who is Q. Oomen?", exclude_document_ids=(), limit=3)
    assert outcome.status == LEXICAL_STATUS_NO_MATCH and outcome.candidate_count == 0


def test_tw2_52_no_match_case_a_zero_matches_recorded(monkeypatch):
    stub = StubRetrieval()
    core, _, seen = _real_core(monkeypatch, retrieval=stub, enabled=True)
    _, record = _ask(core, "Who is Q. Oomen?")
    acc = record.retrieval_accounting
    assert acc.lexical_status == "NO_MATCH" and acc.lexical_triggered is True
    assert acc.lexical_candidates == 0 and acc.lexical_added_document_ids == ()
    assert seen["candidates"] == stub.dense_ids


def test_tw2_52_no_match_case_b_all_matches_already_dense(monkeypatch):
    stub = StubRetrieval(dense_ids=ORDERED_OOMEN)
    core, _, seen = _real_core(monkeypatch, retrieval=stub, enabled=True, top_k=6,
                               reports=[ive_report(claim_ids=(ORDERED_OOMEN[0],))])
    _, record = _ask(core, "Who is P. Oomen?")
    acc = record.retrieval_accounting
    assert acc.lexical_status == "NO_MATCH"
    assert acc.lexical_candidates == 6 and acc.lexical_added_document_ids == ()  # case B, auditable
    assert seen["candidates"] == ORDERED_OOMEN
    assert record.governed_evidence.retrieved_count == acc.dense_retrieved == 6
