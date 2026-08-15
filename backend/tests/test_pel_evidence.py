"""ION PEL Phase-2A evidence-persistence tests (persist_raw_evidence), plus
the Phase-2A source-boundary check.

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
All test writes remain inside a `tempfile.TemporaryDirectory()`.
"""

from __future__ import annotations

import ast
import dataclasses
import tempfile
from pathlib import Path
from unittest.mock import patch

from pel.evidence import persist_raw_evidence
from pel.evidence_models import PersistenceResult
from pel.integrity import sha256_bytes
from pel.readback import read_raw_evidence
from pel.receipts import build_raw_frozen_run_record
from pel.storage import EvidencePersistenceError
from pel.validation import validate_persistence_result, validate_raw_evidence_artifact

VALID_SHA = "a" * 64

PEL_DIR = Path(__file__).resolve().parents[1] / "pel"

FORBIDDEN_IMPORT_ROOTS = {
    "app",
    "t4",
    "requests",
    "httpx",
    "socket",
    "openai",
    "anthropic",
    "google",
}

FORBIDDEN_SYMBOL_NAMES = {
    "NormalizedJudgment",
    "StabilitySummary",
    "CrossModelComparison",
    "GoldEvaluator",
}

FORBIDDEN_FIELD_OR_ATTR_NAMES = {"winner_model", "majority_vote", "action_right"}


def _run_record(raw_bytes: bytes, **overrides):
    fields = dict(
        run_id="run-1",
        plan_id="plan-1",
        condition_id="cond-1",
        replay_index=0,
        model_family="family",
        model_identifier="model-x",
        adapter_id="adapter-1",
        adapter_version="1.0.0",
        task_sha256=VALID_SHA,
        prompt_sha256=VALID_SHA,
        started_at=None,
        completed_at=None,
        raw_artifact_id="artifact-1",
        raw_bytes=raw_bytes,
        capture_mode="manual_import",
    )
    fields.update(overrides)
    return build_raw_frozen_run_record(**fields)


def _expect_code(code, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except EvidencePersistenceError as exc:
        assert exc.code == code, f"expected code {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected EvidencePersistenceError({code!r}), nothing was raised")


def _persist(root: Path, raw: bytes, **overrides) -> PersistenceResult:
    record = _run_record(raw, **overrides)
    return persist_raw_evidence(
        storage_root=root,
        run_record=record,
        raw_bytes=raw,
        persisted_at="2026-08-15T00:00:00+00:00",
    )


# --------------------------------------------------------------------------- #
# successful persistence
# --------------------------------------------------------------------------- #

def test_persist_exact_non_empty_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        result = _persist(Path(tmp), b"raw-model-output")
        assert isinstance(result, PersistenceResult)
        assert result.readback_verified is True
        assert result.status == "PERSISTED_VERIFIED"


def test_persist_zero_byte_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        result = _persist(Path(tmp), b"")
        assert result.raw_bytes == 0
        assert result.raw_sha256 == sha256_bytes(b"")


def test_crlf_and_lf_remain_byte_distinct():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        crlf_result = _persist(root, b"line\r\nline", run_id="run-crlf")
        lf_result = _persist(root, b"line\nline", run_id="run-lf")
        assert crlf_result.raw_sha256 != lf_result.raw_sha256


def test_raw_sha_matches_exact_source_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        result = _persist(Path(tmp), b"source-bytes")
        assert result.raw_sha256 == sha256_bytes(b"source-bytes")


def test_raw_byte_count_matches_source():
    with tempfile.TemporaryDirectory() as tmp:
        result = _persist(Path(tmp), b"twelve-bytes")
        assert result.raw_bytes == len(b"twelve-bytes")


# --------------------------------------------------------------------------- #
# receipt
# --------------------------------------------------------------------------- #

def test_receipt_is_created():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        assert (root / "run-1" / "receipt.json").is_file()


def test_receipt_validates():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        artifact, _raw = read_raw_evidence(storage_root=root, run_id="run-1")
        validate_raw_evidence_artifact(artifact.to_dict())


def test_receipt_preserves_run_task_prompt_raw_linkage():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(b"payload", task_sha256="b" * 64, prompt_sha256="c" * 64)
        persist_raw_evidence(
            storage_root=root,
            run_record=record,
            raw_bytes=b"payload",
            persisted_at="2026-08-15T00:00:00+00:00",
        )
        artifact, _raw = read_raw_evidence(storage_root=root, run_id=record.run_id)
        assert artifact.run_id == record.run_id
        assert artifact.task_sha256 == record.task_sha256
        assert artifact.prompt_sha256 == record.prompt_sha256
        assert artifact.sha256 == record.raw_sha256
        assert artifact.evidence_id == record.raw_artifact_id
        assert artifact.capture_mode == record.capture_mode


def test_receipt_relative_path_matches_actual_raw_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        artifact, _raw = read_raw_evidence(storage_root=root, run_id="run-1")
        assert (root / artifact.relative_path).resolve() == (
            root / "run-1" / "raw.bin"
        ).resolve()


def test_receipt_serialization_is_deterministic_for_same_artifact():
    raw = b"same-payload"
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        root_a, root_b = Path(tmp_a), Path(tmp_b)
        _persist(root_a, raw, run_id="run-det")
        _persist(root_b, raw, run_id="run-det")
        receipt_a = (root_a / "run-det" / "receipt.json").read_bytes()
        receipt_b = (root_b / "run-det" / "receipt.json").read_bytes()
        assert receipt_a == receipt_b


# --------------------------------------------------------------------------- #
# PersistenceResult
# --------------------------------------------------------------------------- #

def test_persistence_result_validates():
    with tempfile.TemporaryDirectory() as tmp:
        result = _persist(Path(tmp), b"payload")
        validate_persistence_result(result.to_dict())


def test_persistence_result_readback_verified_true():
    with tempfile.TemporaryDirectory() as tmp:
        result = _persist(Path(tmp), b"payload")
        assert result.readback_verified is True


# --------------------------------------------------------------------------- #
# no-overwrite / duplicate refusal
# --------------------------------------------------------------------------- #

def test_duplicate_run_evidence_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(b"payload")
        persist_raw_evidence(
            storage_root=root,
            run_record=record,
            raw_bytes=b"payload",
            persisted_at="2026-08-15T00:00:00+00:00",
        )
        _expect_code(
            "EVIDENCE_ALREADY_EXISTS",
            persist_raw_evidence,
            storage_root=root,
            run_record=record,
            raw_bytes=b"payload",
            persisted_at="2026-08-15T00:00:01+00:00",
        )


def test_existing_run_directory_never_overwritten():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        persist_raw_evidence(
            storage_root=root,
            run_record=_run_record(b"payload", run_id="run-dup"),
            raw_bytes=b"payload",
            persisted_at="2026-08-15T00:00:00+00:00",
        )
        raw_path = root / "run-dup" / "raw.bin"
        original_bytes = raw_path.read_bytes()

        _expect_code(
            "EVIDENCE_ALREADY_EXISTS",
            persist_raw_evidence,
            storage_root=root,
            run_record=_run_record(b"different-payload", run_id="run-dup"),
            raw_bytes=b"different-payload",
            persisted_at="2026-08-15T00:00:01+00:00",
        )
        assert raw_path.read_bytes() == original_bytes


# --------------------------------------------------------------------------- #
# pre-write refusals
# --------------------------------------------------------------------------- #

def test_wrong_raw_digest_refused_before_write():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(b"payload")
        _expect_code(
            "RAW_DIGEST_MISMATCH",
            persist_raw_evidence,
            storage_root=root,
            run_record=record,
            raw_bytes=b"tampered-payload",
            persisted_at="2026-08-15T00:00:00+00:00",
        )
        assert list(root.iterdir()) == []


def test_wrong_raw_byte_count_refused_before_write():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(b"payload")
        stale_record = dataclasses.replace(record, raw_bytes=record.raw_bytes + 1)
        _expect_code(
            "RAW_BYTE_COUNT_MISMATCH",
            persist_raw_evidence,
            storage_root=root,
            run_record=stale_record,
            raw_bytes=b"payload",
            persisted_at="2026-08-15T00:00:00+00:00",
        )
        assert list(root.iterdir()) == []


def test_non_raw_frozen_run_record_refused_before_write():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(b"payload")
        planned_record = dataclasses.replace(record, run_status="PLANNED")
        _expect_code(
            "SCHEMA_VALIDATION_FAILURE",
            persist_raw_evidence,
            storage_root=root,
            run_record=planned_record,
            raw_bytes=b"payload",
            persisted_at="2026-08-15T00:00:00+00:00",
        )
        assert list(root.iterdir()) == []


def test_unsafe_run_id_refused_before_write():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(b"payload", run_id="../escape")
        _expect_code(
            "STORAGE_ROOT_VIOLATION",
            persist_raw_evidence,
            storage_root=root,
            run_record=record,
            raw_bytes=b"payload",
            persisted_at="2026-08-15T00:00:00+00:00",
        )
        assert list(root.iterdir()) == []


def test_pre_write_failures_leave_storage_root_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(b"payload")
        for bad_bytes in (b"tampered", b""):
            try:
                persist_raw_evidence(
                    storage_root=root,
                    run_record=record,
                    raw_bytes=bad_bytes,
                    persisted_at="2026-08-15T00:00:00+00:00",
                )
            except EvidencePersistenceError:
                pass
        assert list(root.iterdir()) == []


# --------------------------------------------------------------------------- #
# write-failure cleanup and same-run retry (bounded remediation regression --
# ION_PEL_PHASE2A_BOUNDED_PERSISTENCE_REMEDIATION_MANDATE_v0.1)
# --------------------------------------------------------------------------- #

class _FailAfterCreateFile:
    """Delegates to a real, already-created exclusive-create file handle, but
    raises OSError on the first write(). The target file therefore exists on
    disk -- created by the real `open(..., "xb")` -- before the failure
    occurs, which is exactly the confirmed defect's trigger condition (a
    write/flush/close failure *after* successful exclusive creation)."""

    def __init__(self, real_handle):
        self._real = real_handle

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._real.__exit__(exc_type, exc, tb)
        return False

    def write(self, data):
        raise OSError("simulated write failure after real file creation")

    def flush(self):
        pass

    def fileno(self):
        return self._real.fileno()


def _open_that_fails_after_creating(target_filename: str):
    """A drop-in replacement for `builtins.open` that only fails the
    exclusive-create write for `target_filename`; every other open (including
    the other of raw.bin/receipt.json) behaves normally."""
    real_open = open

    def patched(path, mode="r", *args, **kwargs):
        if mode == "xb" and str(path).endswith(target_filename):
            real_handle = real_open(path, mode, *args, **kwargs)
            return _FailAfterCreateFile(real_handle)
        return real_open(path, mode, *args, **kwargs)

    return patched


def test_raw_write_failure_after_real_file_creation_cleans_up_and_allows_retry():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = b"remediation-probe-bytes"
        record = _run_record(raw, run_id="run-remediation-raw")

        with patch("builtins.open", new=_open_that_fails_after_creating("raw.bin")):
            _expect_code(
                "WRITE_FAILURE",
                persist_raw_evidence,
                storage_root=root,
                run_record=record,
                raw_bytes=raw,
                persisted_at="2026-08-15T00:00:00+00:00",
            )

        # zero partial artifact remains: no run directory, no raw.bin, no receipt.json
        assert list(root.iterdir()) == []
        assert not (root / "run-remediation-raw").exists()

        # same run_id, same valid RunRecord, same raw bytes -- must now succeed
        result = persist_raw_evidence(
            storage_root=root,
            run_record=record,
            raw_bytes=raw,
            persisted_at="2026-08-15T00:00:01+00:00",
        )
        assert result.status == "PERSISTED_VERIFIED"
        assert result.readback_verified is True


def test_receipt_write_failure_after_real_file_creation_cleans_up_and_allows_retry():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = b"remediation-probe-bytes-2"
        record = _run_record(raw, run_id="run-remediation-receipt")

        with patch("builtins.open", new=_open_that_fails_after_creating("receipt.json")):
            _expect_code(
                "RECEIPT_WRITE_FAILURE",
                persist_raw_evidence,
                storage_root=root,
                run_record=record,
                raw_bytes=raw,
                persisted_at="2026-08-15T00:00:00+00:00",
            )

        # zero partial artifact remains: raw.bin (written successfully before
        # the receipt write failed) must also be gone, along with the
        # run directory and any stray receipt.json.
        assert list(root.iterdir()) == []
        assert not (root / "run-remediation-receipt").exists()

        # same run, restored real I/O -- must now succeed
        result = persist_raw_evidence(
            storage_root=root,
            run_record=record,
            raw_bytes=raw,
            persisted_at="2026-08-15T00:00:01+00:00",
        )
        assert result.status == "PERSISTED_VERIFIED"
        assert result.readback_verified is True


# --------------------------------------------------------------------------- #
# no semantic parsing
# --------------------------------------------------------------------------- #

def test_no_semantic_parsing_occurs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = bytes(range(256))  # arbitrary binary content, not UTF-8 text
        record = _run_record(raw)
        persist_raw_evidence(
            storage_root=root,
            run_record=record,
            raw_bytes=raw,
            persisted_at="2026-08-15T00:00:00+00:00",
        )
        _artifact, read_back = read_raw_evidence(storage_root=root, run_id=record.run_id)
        assert read_back == raw


# --------------------------------------------------------------------------- #
# source-boundary check (mandate section 19)
# --------------------------------------------------------------------------- #

def _pel_source_files():
    return sorted(PEL_DIR.glob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_pel_source_has_no_forbidden_imports():
    violations = []
    for path in _pel_source_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if root in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(
                            f"{path.name}: from {node.module} import ..."
                        )
    assert not violations, f"forbidden imports found: {violations}"


def test_pel_source_has_no_forbidden_semantic_symbols_or_fields():
    violations = []
    for path in _pel_source_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in FORBIDDEN_SYMBOL_NAMES:
                    violations.append(f"{path.name}: symbol {node.name}")
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in FORBIDDEN_FIELD_OR_ATTR_NAMES:
                    violations.append(f"{path.name}: field {node.target.id}")
            if (
                isinstance(node, ast.Attribute)
                and node.attr in FORBIDDEN_FIELD_OR_ATTR_NAMES
            ):
                violations.append(f"{path.name}: attribute .{node.attr}")
    assert not violations, f"forbidden semantic-authority surface found: {violations}"
