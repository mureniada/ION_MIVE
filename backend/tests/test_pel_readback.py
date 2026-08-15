"""ION PEL Phase-2A read-back verification tests (read_raw_evidence).

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
All test writes remain inside a `tempfile.TemporaryDirectory()`; tampering
tests mutate only files written there by a prior successful persistence call.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pel.evidence import persist_raw_evidence
from pel.evidence_models import RawEvidenceArtifact
from pel.readback import read_raw_evidence
from pel.receipts import build_raw_frozen_run_record
from pel.storage import EvidencePersistenceError

VALID_SHA = "a" * 64


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


def _persist(root: Path, raw: bytes, **overrides) -> None:
    record = _run_record(raw, **overrides)
    persist_raw_evidence(
        storage_root=root,
        run_record=record,
        raw_bytes=raw,
        persisted_at="2026-08-15T00:00:00+00:00",
    )


# --------------------------------------------------------------------------- #
# successful readback
# --------------------------------------------------------------------------- #

def test_readback_returns_exact_original_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = b"exact-original-bytes"
        _persist(root, raw)
        _artifact, read_back = read_raw_evidence(storage_root=root, run_id="run-1")
        assert read_back == raw


def test_readback_returns_validated_raw_evidence_artifact():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        artifact, _raw = read_raw_evidence(storage_root=root, run_id="run-1")
        assert isinstance(artifact, RawEvidenceArtifact)
        assert artifact.run_id == "run-1"
        assert artifact.status == "RAW_FROZEN"


# --------------------------------------------------------------------------- #
# missing files
# --------------------------------------------------------------------------- #

def test_missing_run_directory_is_readback_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _expect_code(
            "READBACK_FAILURE",
            read_raw_evidence,
            storage_root=root,
            run_id="never-persisted",
        )


def test_missing_raw_bin_is_readback_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        (root / "run-1" / "raw.bin").unlink()
        _expect_code(
            "READBACK_FAILURE", read_raw_evidence, storage_root=root, run_id="run-1"
        )


def test_missing_receipt_json_is_readback_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        (root / "run-1" / "receipt.json").unlink()
        _expect_code(
            "READBACK_FAILURE", read_raw_evidence, storage_root=root, run_id="run-1"
        )


# --------------------------------------------------------------------------- #
# malformed / invalid receipt
# --------------------------------------------------------------------------- #

def test_malformed_receipt_json_is_readback_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        (root / "run-1" / "receipt.json").write_bytes(b"{not valid json")
        _expect_code(
            "READBACK_FAILURE", read_raw_evidence, storage_root=root, run_id="run-1"
        )


def test_schema_invalid_receipt_is_schema_validation_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        receipt_path = root / "run-1" / "receipt.json"
        payload = json.loads(receipt_path.read_bytes())
        payload["status"] = "NOT_A_REAL_STATUS"
        receipt_path.write_bytes(json.dumps(payload).encode("utf-8"))
        _expect_code(
            "SCHEMA_VALIDATION_FAILURE",
            read_raw_evidence,
            storage_root=root,
            run_id="run-1",
        )


def test_receipt_run_id_mismatch_is_run_id_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload-a", run_id="run-a")
        _persist(root, b"payload-b", run_id="run-b")
        receipt_a = root / "run-a" / "receipt.json"
        receipt_b = root / "run-b" / "receipt.json"
        receipt_a.write_bytes(receipt_b.read_bytes())
        _expect_code(
            "RUN_ID_MISMATCH", read_raw_evidence, storage_root=root, run_id="run-a"
        )


# --------------------------------------------------------------------------- #
# tampered / truncated raw bytes
# --------------------------------------------------------------------------- #

def test_tampered_raw_byte_is_readback_digest_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        raw_path = root / "run-1" / "raw.bin"
        original = raw_path.read_bytes()
        tampered = original[:-1] + bytes([original[-1] ^ 0xFF])
        assert len(tampered) == len(original)
        raw_path.write_bytes(tampered)
        _expect_code(
            "READBACK_DIGEST_MISMATCH",
            read_raw_evidence,
            storage_root=root,
            run_id="run-1",
        )


def test_truncated_raw_data_detected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload-for-truncation")
        raw_path = root / "run-1" / "raw.bin"
        raw_path.write_bytes(b"payload-for")
        _expect_code(
            "READBACK_FAILURE", read_raw_evidence, storage_root=root, run_id="run-1"
        )


def test_receipt_raw_byte_count_mismatch_detected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        receipt_path = root / "run-1" / "receipt.json"
        payload = json.loads(receipt_path.read_bytes())
        payload["byte_count"] = payload["byte_count"] + 5
        receipt_path.write_bytes(json.dumps(payload).encode("utf-8"))
        _expect_code(
            "READBACK_FAILURE", read_raw_evidence, storage_root=root, run_id="run-1"
        )


# --------------------------------------------------------------------------- #
# no writes during readback
# --------------------------------------------------------------------------- #

def test_readback_performs_no_writes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist(root, b"payload")
        raw_path = root / "run-1" / "raw.bin"
        receipt_path = root / "run-1" / "receipt.json"
        raw_mtime_before = raw_path.stat().st_mtime_ns
        receipt_mtime_before = receipt_path.stat().st_mtime_ns
        raw_bytes_before = raw_path.read_bytes()
        receipt_bytes_before = receipt_path.read_bytes()

        read_raw_evidence(storage_root=root, run_id="run-1")

        assert raw_path.stat().st_mtime_ns == raw_mtime_before
        assert receipt_path.stat().st_mtime_ns == receipt_mtime_before
        assert raw_path.read_bytes() == raw_bytes_before
        assert receipt_path.read_bytes() == receipt_bytes_before
