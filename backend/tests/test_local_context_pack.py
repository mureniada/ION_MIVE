"""The Context Pack must carry working-material labelling all the way to the output.

Covers mandate §10 requirements 6 and 7, and demonstrates that the local pack
representation validates against the canonical schema *unmodified*.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import ContextPackError
from app.core.models import Evidence
from app.modules.local_layer.context_pack import PROVENANCE_FIELDS, LocalContextPackBuilder
from app.modules.local_layer.pipeline import CONTROL_QUESTION, run_control_question
from app.validation import validate_context_pack
from tests.netguard import guarded
from tests.util import raises

CANONICAL_TOP_LEVEL_KEYS = {"context_pack_id", "question", "documents", "metadata"}


def _schema_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "schemas" / "context_pack.schema.json"
        if candidate.exists():
            return candidate
    raise AssertionError("schemas/context_pack.schema.json not found")


def _evidence(provenance: dict | None) -> Evidence:
    return Evidence(
        document_id="m::f0",
        source_id="m",
        title="T",
        content="some retrieved text",
        score=1.0,
        chunk_id="m::f0",
        metadata={"provenance": provenance} if provenance is not None else {},
    )


def _full_provenance(**overrides) -> dict:
    base = {
        "material_id": "m",
        "fragment_id": "m::f0",
        "title": "T",
        "source_file": "m.md",
        "version": "0.1.0",
        "status": "draft",
        "authority": "working_material",
        "approved_for_publication": False,
    }
    base.update(overrides)
    return base


def _build(evidence_list, **kwargs):
    defaults = {"registry_version": "1", "material_count": 1, "index_fingerprint": "abc123"}
    defaults.update(kwargs)
    return LocalContextPackBuilder().build(CONTROL_QUESTION, evidence_list, **defaults)


# --- schema compatibility --------------------------------------------------- #
@guarded
def test_local_pack_validates_against_the_unmodified_canonical_schema():
    pack = run_control_question()
    validate_context_pack(pack)                      # the repository's own validator

    # and the schema file itself is genuinely unmodified in the two ways relied upon
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    assert schema["properties"]["documents"]["items"]["additionalProperties"] is True
    assert schema["additionalProperties"] is False


@guarded
def test_top_level_shape_is_exactly_the_canonical_four_keys():
    pack = run_control_question()
    assert set(pack) == CANONICAL_TOP_LEVEL_KEYS


@guarded
def test_pack_id_is_reproducible():
    assert run_control_question()["context_pack_id"] == run_control_question()["context_pack_id"]
    assert run_control_question()["context_pack_id"].startswith("cp_")


# --- §10.6 provenance preserved into the pack ------------------------------- #
@guarded
def test_every_pack_document_carries_complete_provenance():
    pack = run_control_question()
    assert pack["documents"], "control question produced an empty pack"

    for document in pack["documents"]:
        provenance = document.get("provenance")
        assert provenance is not None, f"{document['document_id']} lost its provenance"
        missing = [f for f in PROVENANCE_FIELDS if f not in provenance]
        assert not missing, f"{document['document_id']} missing {missing}"
        assert document["content"].strip()                       # the ninth element
        assert document["source"] == provenance["source_file"]
        assert document["document_id"] == provenance["fragment_id"]


# --- §10.7 draft status stays visible --------------------------------------- #
@guarded
def test_draft_status_and_working_authority_are_visible_in_the_pack():
    pack = run_control_question()
    for document in pack["documents"]:
        provenance = document["provenance"]
        assert provenance["status"] == "draft"
        assert provenance["authority"] == "working_material"
        assert provenance["approved_for_publication"] is False


@guarded
def test_pack_metadata_records_local_origin_and_registry_identity():
    metadata = run_control_question()["metadata"]
    assert metadata["origin"] == "local_working_layer"
    assert metadata["registry_version"] == "1"
    assert metadata["material_count"] >= 1
    assert metadata["index_fingerprint"]


# --- the builder refuses to strip labelling --------------------------------- #
@guarded
def test_evidence_without_provenance_is_refused():
    """A working material may not enter the pack unlabelled."""
    with raises(ContextPackError):
        _build([_evidence(None)])


@guarded
def test_evidence_with_partial_provenance_names_the_missing_fields():
    partial = _full_provenance()
    del partial["status"]
    del partial["authority"]
    try:
        _build([_evidence(partial)])
        raise AssertionError("expected ContextPackError")
    except ContextPackError as exc:
        assert "status" in str(exc) and "authority" in str(exc)


@guarded
def test_no_evidence_raises():
    with raises(ContextPackError):
        _build([])


@guarded
def test_truncation_is_explicit_and_recorded():
    evidence = [
        Evidence(
            document_id=f"m::f{i}",
            source_id="m",
            title="T",
            content="x" * 100,
            score=1.0 - i * 0.1,
            chunk_id=f"m::f{i}",
            metadata={"provenance": _full_provenance(fragment_id=f"m::f{i}")},
        )
        for i in range(3)
    ]
    pack = LocalContextPackBuilder(char_budget=150).build(
        CONTROL_QUESTION,
        evidence,
        registry_version="1",
        material_count=1,
        index_fingerprint="abc123",
    )
    assert pack["metadata"]["truncated"] is True
    assert pack["metadata"]["included_documents"] < pack["metadata"]["evidence_count"]
    validate_context_pack(pack)
