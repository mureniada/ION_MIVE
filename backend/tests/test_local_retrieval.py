"""Local lexical retrieval: relevance, provenance, and rebuildability.

Covers mandate §10 requirements 1, 6 and 11, against the real shipped
`local_materials/` layer rather than a fixture, so the acceptance scenario is
exercised on the actual material.
"""

from __future__ import annotations

import hashlib

from app.modules.local_layer.context_pack import PROVENANCE_FIELDS
from app.modules.local_layer.lexical_index import LexicalIndex
from app.modules.local_layer.pipeline import (
    CONTROL_QUESTION,
    LocalLayerPaths,
    build_index,
    delete_index,
    load_layer,
)
from tests.netguard import guarded

UNRELATED_QUESTION = "xylophone chlorophyll tectonic zebra"


def _paths() -> LocalLayerPaths:
    return LocalLayerPaths.resolve()


def _ranking(index: LexicalIndex, question: str, top_k: int = 5):
    return [(e.document_id, round(e.score, 12)) for e in index.retrieve(question, top_k=top_k)]


# --- §10.1 the shipped material is processed and retrievable ---------------- #
@guarded
def test_control_question_retrieves_the_adaptive_dialogue_material():
    index = build_index(_paths())
    assert len(index) > 0

    hits = index.retrieve(CONTROL_QUESTION, top_k=3)
    assert hits, "control question retrieved nothing"
    assert hits[0].source_id == "adaptive_dialogue_intro"
    assert hits[0].score > 0.0
    # ranked, not merely returned
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


@guarded
def test_top_fragment_actually_answers_the_control_question():
    """Guards against a match that ranks well on stopwords alone."""
    hits = build_index(_paths()).retrieve(CONTROL_QUESTION, top_k=1)
    text = hits[0].content.lower()
    assert "adaptive dialogue" in text


@guarded
def test_unrelated_question_returns_absence_not_a_weak_match():
    hits = build_index(_paths()).retrieve(UNRELATED_QUESTION, top_k=5)
    assert hits == []


@guarded
def test_empty_index_retrieves_nothing():
    assert LexicalIndex.build([]).retrieve(CONTROL_QUESTION, top_k=5) == []


# --- §10.6 retrieved fragments preserve full provenance --------------------- #
@guarded
def test_every_retrieved_fragment_carries_complete_provenance():
    hits = build_index(_paths()).retrieve(CONTROL_QUESTION, top_k=5)
    assert hits

    for hit in hits:
        provenance = hit.metadata.get("provenance")
        assert provenance is not None, f"{hit.document_id} lost its provenance"
        missing = [f for f in PROVENANCE_FIELDS if f not in provenance]
        assert not missing, f"{hit.document_id} missing provenance field(s) {missing}"
        # the ninth mandated element: the fragment text itself
        assert hit.content.strip()
        # provenance is consistent with the evidence it travels on
        assert provenance["fragment_id"] == hit.document_id
        assert provenance["material_id"] == hit.source_id


@guarded
def test_draft_labelling_survives_retrieval():
    hits = build_index(_paths()).retrieve(CONTROL_QUESTION, top_k=5)
    for hit in hits:
        provenance = hit.metadata["provenance"]
        assert provenance["status"] == "draft"
        assert provenance["authority"] == "working_material"
        assert provenance["approved_for_publication"] is False


@guarded
def test_ranking_is_deterministic_across_rebuilds():
    first = _ranking(build_index(_paths()), CONTROL_QUESTION)
    second = _ranking(build_index(_paths()), CONTROL_QUESTION)
    assert first == second


# --- §10.11 the index is deletable and rebuildable, sources unchanged ------- #
def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@guarded
def test_index_can_be_deleted_and_rebuilt_leaving_sources_unchanged():
    paths = _paths()
    registry, load_before = load_layer(paths)

    registry_digest_before = _digest(paths.registry)
    document_digests_before = {
        m.source_file: _digest(paths.documents / m.source_file) for m in registry.materials
    }

    index = LexicalIndex.build(load_before.fragments)
    index.save(paths.index)
    assert paths.index.is_file()

    fingerprint_before = index.fingerprint()
    ranking_before = _ranking(index, CONTROL_QUESTION)

    # delete the derived data
    assert delete_index(paths) is True
    assert not paths.index.exists()
    assert delete_index(paths) is False          # already gone; reports honestly

    # rebuild from registry + source documents alone
    rebuilt = build_index(paths, persist=True)
    assert paths.index.is_file()

    assert rebuilt.fingerprint() == fingerprint_before
    assert _ranking(rebuilt, CONTROL_QUESTION) == ranking_before

    _registry_after, load_after = load_layer(paths)
    assert load_after.source_checksums == load_before.source_checksums
    assert _digest(paths.registry) == registry_digest_before
    assert {
        m.source_file: _digest(paths.documents / m.source_file) for m in registry.materials
    } == document_digests_before

    # a persisted index reloads to the same behaviour
    reloaded = LexicalIndex.load(paths.index)
    assert _ranking(reloaded, CONTROL_QUESTION) == ranking_before

    delete_index(paths)                          # leave no derived artifact behind


@guarded
def test_index_fingerprint_changes_when_material_changes():
    """The fingerprint is a real digest of content, not a constant."""
    _registry, load_result = load_layer(_paths())
    base = LexicalIndex.build(load_result.fragments)

    altered = [dict(f) for f in load_result.fragments]
    altered[0]["content"] = altered[0]["content"] + " appended sentence."
    assert LexicalIndex.build(altered).fingerprint() != base.fingerprint()
