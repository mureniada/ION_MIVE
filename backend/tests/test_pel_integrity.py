"""ION PEL Phase-1 integrity-module tests: sha256_bytes, is_sha256_hex,
require_sha256_hex, freeze_task, build_raw_frozen_run_record.

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
"""

from __future__ import annotations

import hashlib

from pel.integrity import is_sha256_hex, require_sha256_hex, sha256_bytes
from pel.receipts import build_raw_frozen_run_record
from pel.task_freeze import freeze_task
from tests.util import raises

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
VALID_SHA_A = "a" * 64
VALID_SHA_B = "b" * 64


# --------------------------------------------------------------------------- #
# sha256_bytes
# --------------------------------------------------------------------------- #

def test_sha256_bytes_is_deterministic():
    data = b"the quick brown fox"
    assert sha256_bytes(data) == sha256_bytes(data)


def test_sha256_bytes_matches_hashlib():
    data = b"ion pel phase 1"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_one_byte_change_changes_digest():
    assert sha256_bytes(b"abc") != sha256_bytes(b"abd")


def test_empty_bytes_digest_is_correct():
    assert sha256_bytes(b"") == EMPTY_SHA256


# --------------------------------------------------------------------------- #
# is_sha256_hex / require_sha256_hex
# --------------------------------------------------------------------------- #

def test_is_sha256_hex_accepts_valid_lowercase_64_hex():
    assert is_sha256_hex(VALID_SHA_A) is True


def test_is_sha256_hex_rejects_uppercase():
    assert is_sha256_hex("A" * 64) is False


def test_is_sha256_hex_rejects_wrong_length():
    assert is_sha256_hex("a" * 63) is False
    assert is_sha256_hex("a" * 65) is False


def test_is_sha256_hex_rejects_non_hex():
    assert is_sha256_hex("g" * 64) is False


def test_require_sha256_hex_returns_valid_digest():
    assert require_sha256_hex(VALID_SHA_A, field_name="x") == VALID_SHA_A


def test_require_sha256_hex_raises_on_invalid_digest():
    with raises(ValueError):
        require_sha256_hex("not-a-digest", field_name="x")


# --------------------------------------------------------------------------- #
# freeze_task
# --------------------------------------------------------------------------- #

def _freeze(bundle_bytes: bytes, prompt_bytes: bytes):
    return freeze_task(
        task_id="task-1",
        task_version="v1",
        task_class="probe",
        semantic_boundary=None,
        bundle_filename="bundle.json",
        bundle_bytes=bundle_bytes,
        prompt_id="prompt-1",
        prompt_bytes=prompt_bytes,
        output_contract_id="contract-1",
        created_at="2026-08-15T00:00:00+00:00",
        provenance=("operator",),
    )


def test_freeze_task_hashes_exact_bundle_bytes():
    spec = _freeze(b"bundle-content", b"prompt-content")
    assert spec.bundle_sha256 == sha256_bytes(b"bundle-content")


def test_freeze_task_hashes_exact_prompt_bytes():
    spec = _freeze(b"bundle-content", b"prompt-content")
    assert spec.prompt_sha256 == sha256_bytes(b"prompt-content")


def test_freeze_task_preserves_byte_lengths():
    spec = _freeze(b"bundle-content", b"prompt-content-longer")
    assert spec.bundle_bytes == len(b"bundle-content")
    assert spec.prompt_bytes == len(b"prompt-content-longer")


def test_freeze_task_sets_frozen():
    spec = _freeze(b"bundle-content", b"prompt-content")
    assert spec.status == "FROZEN"


def test_freeze_task_does_not_normalize_crlf_lf():
    crlf_spec = _freeze(b"line-one\r\nline-two", b"prompt-content")
    lf_spec = _freeze(b"line-one\nline-two", b"prompt-content")
    assert crlf_spec.bundle_sha256 != lf_spec.bundle_sha256
    assert crlf_spec.bundle_bytes != lf_spec.bundle_bytes


def test_freeze_task_is_deterministic_for_same_inputs():
    spec_a = _freeze(b"bundle-content", b"prompt-content")
    spec_b = _freeze(b"bundle-content", b"prompt-content")
    assert spec_a.bundle_sha256 == spec_b.bundle_sha256
    assert spec_a.prompt_sha256 == spec_b.prompt_sha256


# --------------------------------------------------------------------------- #
# build_raw_frozen_run_record
# --------------------------------------------------------------------------- #

def _receipt(raw: bytes, *, task_sha256=VALID_SHA_A, prompt_sha256=VALID_SHA_B):
    return build_raw_frozen_run_record(
        run_id="run-1",
        plan_id="plan-1",
        condition_id="cond-1",
        replay_index=0,
        model_family="family",
        model_identifier="model-x",
        adapter_id="adapter-1",
        adapter_version="1.0.0",
        task_sha256=task_sha256,
        prompt_sha256=prompt_sha256,
        started_at=None,
        completed_at=None,
        raw_artifact_id="artifact-1",
        raw_bytes=raw,
        capture_mode="manual_import",
    )


def test_build_raw_frozen_run_record_hashes_exact_raw_bytes():
    record = _receipt(b"raw-output")
    assert record.raw_sha256 == sha256_bytes(b"raw-output")


def test_receipt_records_raw_length():
    record = _receipt(b"raw-output-content")
    assert record.raw_bytes == len(b"raw-output-content")


def test_receipt_sets_raw_frozen():
    record = _receipt(b"raw-output")
    assert record.run_status == "RAW_FROZEN"


def test_receipt_rejects_malformed_task_digest():
    with raises(ValueError):
        _receipt(b"raw-output", task_sha256="not-a-digest")


def test_receipt_rejects_malformed_prompt_digest():
    with raises(ValueError):
        _receipt(b"raw-output", prompt_sha256="not-a-digest")
