"""Registry is the admission gate: what it refuses must be refused visibly.

Covers mandate §10 requirements 1-5.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.modules.local_layer.loader import find_unregistered, load_fragments
from app.modules.local_layer.registry import (
    REQUIRED_FIELDS,
    LocalRegistryError,
    MissingSourceFileError,
    _validate_record,
    load_registry,
)
from tests.netguard import guarded
from tests.util import raises

DOC_TEXT = "Adaptive Dialogue adapts the shape of inquiry to the state of the evidence. " * 12


def _material(**overrides):
    base = {
        "id": "material_one",
        "title": "Material One",
        "source_file": "one.md",
        "version": "0.1.0",
        "status": "draft",
        "authority": "working_material",
        "retrieval_enabled": True,
        "approved_for_publication": False,
    }
    base.update(overrides)
    return base


@contextmanager
def temp_layer(materials, files):
    """A throwaway local_materials/ tree: registry + documents on disk."""
    root = Path(tempfile.mkdtemp(prefix="ion_local_registry_"))
    try:
        docs = root / "documents"
        docs.mkdir()
        for name, text in files.items():
            (docs / name).write_text(text, encoding="utf-8")
        (root / "registry.json").write_text(
            json.dumps({"registry_version": "1", "materials": materials}),
            encoding="utf-8",
        )
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _message(fn) -> str:
    try:
        fn()
    except LocalRegistryError as exc:
        return str(exc)
    raise AssertionError("expected LocalRegistryError, nothing was raised")


# --- §10.1 a valid registered material can be processed --------------------- #
@guarded
def test_valid_registered_material_is_processed():
    with temp_layer([_material()], {"one.md": DOC_TEXT}) as root:
        registry = load_registry(root / "registry.json")
        result = load_fragments(registry, root / "documents")

        assert registry.registry_version == "1"
        assert [m.id for m in registry.materials] == ["material_one"]
        assert result.fragment_count > 0
        assert {f["material_id"] for f in result.fragments} == {"material_one"}
        # the source was actually read, not merely referenced
        assert "Adaptive Dialogue" in result.fragments[0]["content"]


# --- §10.2 an unregistered file is not silently ingested -------------------- #
@guarded
def test_unregistered_file_is_excluded_and_reported():
    files = {"one.md": DOC_TEXT, "stranger.md": "Never registered, never ingested."}
    with temp_layer([_material()], files) as root:
        registry = load_registry(root / "registry.json")
        result = load_fragments(registry, root / "documents")

        # excluded from the corpus...
        assert {f["material_id"] for f in result.fragments} == {"material_one"}
        assert all("Never registered" not in f["content"] for f in result.fragments)
        # ...and refused visibly rather than dropped in silence
        assert result.unregistered == ("stranger.md",)
        assert find_unregistered(registry, root / "documents") == ("stranger.md",)


# --- §10.3 retrieval_enabled: false is excluded ----------------------------- #
@guarded
def test_retrieval_disabled_material_is_excluded_from_fragments():
    materials = [
        _material(),
        _material(id="material_two", source_file="two.md", retrieval_enabled=False),
    ]
    with temp_layer(materials, {"one.md": DOC_TEXT, "two.md": "Withheld text."}) as root:
        registry = load_registry(root / "registry.json")
        result = load_fragments(registry, root / "documents")

        assert {m.id for m in registry.materials} == {"material_one", "material_two"}
        assert {m.id for m in registry.retrievable} == {"material_one"}
        assert {f["material_id"] for f in result.fragments} == {"material_one"}
        assert all("Withheld" not in f["content"] for f in result.fragments)
        assert result.excluded_material_ids == ("material_two",)
        # the file was still checksummed — excluded from retrieval, not from accounting
        assert set(result.source_checksums) == {"material_one", "material_two"}


# --- §10.4 missing or invalid metadata causes a clear failure --------------- #
@guarded
def test_each_missing_required_field_is_named_in_the_error():
    for field in REQUIRED_FIELDS:
        incomplete = _material()
        del incomplete[field]
        with temp_layer([incomplete], {"one.md": DOC_TEXT}) as root:
            message = _message(lambda r=root: load_registry(r / "registry.json"))
            assert field in message, f"error for missing '{field}' did not name it: {message}"


@guarded
def test_boolean_field_given_a_string_is_rejected():
    bad = _material(retrieval_enabled="true")
    with temp_layer([bad], {"one.md": DOC_TEXT}) as root:
        message = _message(lambda: load_registry(root / "registry.json"))
        assert "retrieval_enabled" in message


@guarded
def test_unknown_field_is_rejected():
    with temp_layer([_material(approved_by="nobody")], {"one.md": DOC_TEXT}) as root:
        message = _message(lambda: load_registry(root / "registry.json"))
        assert "approved_by" in message


@guarded
def test_duplicate_material_id_is_rejected():
    materials = [_material(), _material(source_file="two.md")]
    with temp_layer(materials, {"one.md": DOC_TEXT, "two.md": DOC_TEXT}) as root:
        message = _message(lambda: load_registry(root / "registry.json"))
        assert "duplicate id" in message


@guarded
def test_record_level_validation_names_the_field_independently():
    """The second validation layer works on its own, not only behind jsonschema."""
    incomplete = _material()
    del incomplete["authority"]
    message = _message(lambda: _validate_record(incomplete, 0))
    assert "material_one" in message and "authority" in message


@guarded
def test_malformed_json_registry_is_rejected():
    root = Path(tempfile.mkdtemp(prefix="ion_local_registry_"))
    try:
        (root / "documents").mkdir()
        (root / "registry.json").write_text("{not json", encoding="utf-8")
        message = _message(lambda: load_registry(root / "registry.json"))
        assert "not valid JSON" in message
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- §10.5 a record referencing a missing source file: documented policy ----- #
@guarded
def test_missing_source_file_fails_fast():
    """Documented policy is fail-fast, not skip. See local_materials/README.md."""
    with temp_layer([_material()], {}) as root:          # registry names one.md; it is absent
        registry = load_registry(root / "registry.json")
        with raises(MissingSourceFileError):
            load_fragments(registry, root / "documents")


@guarded
def test_missing_source_file_error_names_material_and_path():
    with temp_layer([_material()], {}) as root:
        registry = load_registry(root / "registry.json")
        message = _message(lambda: load_fragments(registry, root / "documents"))
        assert "material_one" in message and "one.md" in message


@guarded
def test_missing_source_file_fails_even_when_retrieval_is_disabled():
    """A registry entry is a claim the file exists; disabling retrieval does not excuse it."""
    disabled = _material(retrieval_enabled=False)
    with temp_layer([disabled], {}) as root:
        registry = load_registry(root / "registry.json")
        with raises(MissingSourceFileError):
            load_fragments(registry, root / "documents")
