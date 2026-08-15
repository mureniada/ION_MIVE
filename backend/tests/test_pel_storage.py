"""ION PEL Phase-2A storage-safety tests (require_storage_root,
require_storage_component, evidence_paths).

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
All test writes remain inside a `tempfile.TemporaryDirectory()`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from pel.storage import (
    EvidencePersistenceError,
    evidence_paths,
    require_storage_component,
    require_storage_root,
)
from tests.util import raises


def test_existing_directory_accepted_as_storage_root():
    with tempfile.TemporaryDirectory() as tmp:
        resolved = require_storage_root(Path(tmp))
        assert resolved.is_dir()


def test_missing_root_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "does-not-exist"
        with raises(EvidencePersistenceError):
            require_storage_root(missing)


def test_file_as_root_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "a-file.txt"
        file_path.write_bytes(b"content")
        with raises(EvidencePersistenceError):
            require_storage_root(file_path)


def test_safe_run_id_accepted():
    assert require_storage_component("run-1", field_name="run_id") == "run-1"
    assert require_storage_component("a" * 128, field_name="run_id") == "a" * 128


def test_dot_rejected():
    with raises(EvidencePersistenceError):
        require_storage_component(".", field_name="run_id")


def test_dotdot_rejected():
    with raises(EvidencePersistenceError):
        require_storage_component("..", field_name="run_id")


def test_parent_traversal_forward_slash_rejected():
    with raises(EvidencePersistenceError):
        require_storage_component("../x", field_name="run_id")


def test_parent_traversal_backslash_rejected():
    with raises(EvidencePersistenceError):
        require_storage_component("..\\x", field_name="run_id")


def test_leading_slash_rejected():
    with raises(EvidencePersistenceError):
        require_storage_component("/x", field_name="run_id")


def test_embedded_forward_slash_rejected():
    with raises(EvidencePersistenceError):
        require_storage_component("a/b", field_name="run_id")


def test_embedded_backslash_rejected():
    with raises(EvidencePersistenceError):
        require_storage_component("a\\b", field_name="run_id")


def test_overlength_component_rejected():
    with raises(EvidencePersistenceError):
        require_storage_component("a" * 129, field_name="run_id")


def test_evidence_paths_remain_beneath_exact_root():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_directory, raw_path, receipt_path = evidence_paths(
            storage_root=root, run_id="run-1"
        )
        resolved_root = root.resolve()
        assert run_directory.parent == resolved_root
        assert raw_path.parent == run_directory
        assert receipt_path.parent == run_directory
        assert raw_path.name == "raw.bin"
        assert receipt_path.name == "receipt.json"


def test_run_directory_is_direct_child_of_root():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_directory, _raw_path, _receipt_path = evidence_paths(
            storage_root=root, run_id="run-xyz"
        )
        assert run_directory == root.resolve() / "run-xyz"
