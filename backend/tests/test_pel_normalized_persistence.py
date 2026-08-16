"""ION PEL Phase-2B.2 derived normalized-judgment persistence tests
(persist_normalized_judgment), per
ION_PEL_PHASE2B2_DERIVED_ARTIFACT_PERSISTENCE_CONTRACT_FREEZE_v0.1.md.

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
All test writes remain inside a `tempfile.TemporaryDirectory()`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from pel.evidence import persist_raw_evidence
from pel.integrity import sha256_bytes
from pel.normalization_contract import OUTPUT_CONTRACT_ID, PARSER_ID, PARSER_VERSION
from pel.normalization_models import FieldTrace, NormalizedJudgmentV0_2_2, ParserDiagnostic
from pel.normalized_identity import (
    NORMALIZED_SCHEMA_ID,
    compute_normalized_artifact_id,
    compute_normalized_content_sha256,
    compute_normalized_schema_id_digest,
    serialize_deterministic_json,
)
from pel.normalized_persistence import persist_normalized_judgment
from pel.normalized_persistence_models import NormalizedJudgmentPersistenceResult
from pel.normalized_readback import read_normalized_judgment
from pel.normalized_storage import NormalizedPersistenceError
from pel.receipts import build_raw_frozen_run_record
from pel.validation import (
    validate_normalized_judgment_artifact,
    validate_normalized_judgment_persistence_result,
)

VALID_SHA = "a" * 64
DEFAULT_RAW = b"raw-checker-output"


def _persist_raw(root: Path, *, run_id="run-1", raw_artifact_id="ev-1", raw_bytes=DEFAULT_RAW):
    record = build_raw_frozen_run_record(
        run_id=run_id,
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
        raw_artifact_id=raw_artifact_id,
        raw_bytes=raw_bytes,
        capture_mode="manual_import",
    )
    persist_raw_evidence(
        storage_root=root,
        run_record=record,
        raw_bytes=raw_bytes,
        persisted_at="2026-08-16T00:00:00+00:00",
    )
    return record


def _judgment(**overrides) -> NormalizedJudgmentV0_2_2:
    fields = dict(
        run_id="run-1",
        evidence_id="ev-1",
        source_raw_sha256=sha256_bytes(DEFAULT_RAW),
        output_contract_id=OUTPUT_CONTRACT_ID,
        focus_key="X26_READ",
        parser_id=PARSER_ID,
        parser_version=PARSER_VERSION,
        primary_verdict="YES",
        noticed=True,
        declined_as_borderline=False,
        defect_description_text="some text",
        rule_basis_text="R3",
        confidence="HIGH",
        other_findings_state="NONE",
        other_findings_text=None,
        final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
        field_traces=(
            FieldTrace(
                field_name="primary_verdict",
                trace_kind="EXACT_EXTRACT",
                start_byte=10,
                end_byte=13,
                source_excerpt_sha256=VALID_SHA,
                rule_id=None,
                state="PRESENT",
            ),
        ),
        diagnostics=(
            ParserDiagnostic(
                code="MISSING_REQUIRED_FIELD",
                message="confidence: no source occurrence found",
                start_byte=None,
                end_byte=None,
            ),
        ),
        normalized_at="2026-08-16T00:00:00+00:00",
    )
    fields.update(overrides)
    return NormalizedJudgmentV0_2_2(**fields)


def _setup(root: Path, *, run_id="run-1", raw_artifact_id="ev-1", raw_bytes=DEFAULT_RAW, **overrides):
    _persist_raw(root, run_id=run_id, raw_artifact_id=raw_artifact_id, raw_bytes=raw_bytes)
    judgment_fields = dict(
        run_id=run_id, evidence_id=raw_artifact_id, source_raw_sha256=sha256_bytes(raw_bytes)
    )
    judgment_fields.update(overrides)
    return _judgment(**judgment_fields)


def _artifact_dir(root: Path, judgment: NormalizedJudgmentV0_2_2) -> Path:
    schema_digest = compute_normalized_schema_id_digest(NORMALIZED_SCHEMA_ID)
    return (
        root
        / "normalized"
        / judgment.run_id
        / judgment.output_contract_id
        / judgment.parser_id
        / judgment.parser_version
        / schema_digest
    )


def _expect_code(code, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except NormalizedPersistenceError as exc:
        assert exc.code == code, f"expected code {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected NormalizedPersistenceError({code!r}), nothing was raised")


# --------------------------------------------------------------------------- #
# T01 exact judgment round-trip / T22 receipt readback
# --------------------------------------------------------------------------- #

def test_exact_judgment_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root)
        result = persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        assert isinstance(result, NormalizedJudgmentPersistenceResult)
        assert result.readback_verified is True
        assert result.status == "NORMALIZED_PERSISTED_VERIFIED"

        schema_digest = compute_normalized_schema_id_digest(NORMALIZED_SCHEMA_ID)
        artifact, judgment_bytes = read_normalized_judgment(
            storage_root=root,
            run_id=judgment.run_id,
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,
            normalized_schema_id_digest=schema_digest,
        )
        assert judgment_bytes == serialize_deterministic_json(judgment.to_dict())
        assert artifact.normalized_artifact_id == result.normalized_artifact_id


def test_exact_receipt_readback_and_digest_verification():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-t22")
        result = persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        artifact_dir = _artifact_dir(root, judgment)
        receipt_bytes = (artifact_dir / "receipt.json").read_bytes()
        assert sha256_bytes(receipt_bytes) == result.receipt_sha256
        validate_normalized_judgment_persistence_result(result.to_dict())

        schema_digest = compute_normalized_schema_id_digest(NORMALIZED_SCHEMA_ID)
        artifact, _judgment_bytes = read_normalized_judgment(
            storage_root=root,
            run_id="run-t22",
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,
            normalized_schema_id_digest=schema_digest,
        )
        validate_normalized_judgment_artifact(artifact.to_dict())


# --------------------------------------------------------------------------- #
# T02 / T03 digest verification
# --------------------------------------------------------------------------- #

def test_exact_artifact_byte_digest_verification():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root)
        result = persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        expected = sha256_bytes(serialize_deterministic_json(judgment.to_dict()))
        assert result.artifact_bytes_sha256 == expected


def test_normalized_content_digest_behavior():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root)
        result = persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        expected = compute_normalized_content_sha256(judgment.to_dict())
        assert result.normalized_content_sha256 == expected
        assert result.normalized_content_sha256 != result.artifact_bytes_sha256


# --------------------------------------------------------------------------- #
# T04 / T05 normalized_at exclusion
# --------------------------------------------------------------------------- #

def test_normalized_at_only_difference_changes_artifact_bytes_sha256():
    judgment_a = _judgment(normalized_at="2026-08-16T00:00:00+00:00")
    judgment_b = _judgment(normalized_at="2099-01-01T00:00:00+00:00")
    bytes_a = serialize_deterministic_json(judgment_a.to_dict())
    bytes_b = serialize_deterministic_json(judgment_b.to_dict())
    assert bytes_a != bytes_b
    assert sha256_bytes(bytes_a) != sha256_bytes(bytes_b)


def test_normalized_at_only_difference_does_not_change_content_sha256():
    judgment_a = _judgment(normalized_at="2026-08-16T00:00:00+00:00")
    judgment_b = _judgment(normalized_at="2099-01-01T00:00:00+00:00")
    assert compute_normalized_content_sha256(
        judgment_a.to_dict()
    ) == compute_normalized_content_sha256(judgment_b.to_dict())


# --------------------------------------------------------------------------- #
# T06 / T07 identity
# --------------------------------------------------------------------------- #

def test_normalized_artifact_id_deterministic_reproduction():
    kwargs = dict(
        run_id="run-x",
        output_contract_id=OUTPUT_CONTRACT_ID,
        parser_id=PARSER_ID,
        parser_version=PARSER_VERSION,
        normalized_schema_id=NORMALIZED_SCHEMA_ID,
    )
    assert compute_normalized_artifact_id(**kwargs) == compute_normalized_artifact_id(**kwargs)


def test_identity_component_non_collision():
    base = dict(
        run_id="run-x",
        output_contract_id=OUTPUT_CONTRACT_ID,
        parser_id=PARSER_ID,
        parser_version=PARSER_VERSION,
        normalized_schema_id=NORMALIZED_SCHEMA_ID,
    )
    base_id = compute_normalized_artifact_id(**base)
    for field in ("run_id", "output_contract_id", "parser_id", "parser_version", "normalized_schema_id"):
        varied = dict(base)
        varied[field] = base[field] + "-varied"
        assert compute_normalized_artifact_id(**varied) != base_id


# --------------------------------------------------------------------------- #
# T08-T10 source verification
# --------------------------------------------------------------------------- #

def test_source_run_id_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _judgment(run_id="run-does-not-exist")
        _expect_code(
            "SOURCE_RAW_NOT_FOUND",
            persist_normalized_judgment,
            storage_root=root,
            judgment=judgment,
            persisted_at="2026-08-16T00:00:01+00:00",
        )


def test_source_raw_digest_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist_raw(root)
        judgment = _judgment(source_raw_sha256="b" * 64)
        _expect_code(
            "SOURCE_RAW_DIGEST_MISMATCH",
            persist_normalized_judgment,
            storage_root=root,
            judgment=judgment,
            persisted_at="2026-08-16T00:00:01+00:00",
        )


def test_source_evidence_id_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _persist_raw(root, raw_artifact_id="ev-1")
        judgment = _judgment(evidence_id="ev-does-not-match")
        _expect_code(
            "SOURCE_EVIDENCE_ID_MISMATCH",
            persist_normalized_judgment,
            storage_root=root,
            judgment=judgment,
            persisted_at="2026-08-16T00:00:01+00:00",
        )


# --------------------------------------------------------------------------- #
# T11 duplicate rejection
# --------------------------------------------------------------------------- #

def test_duplicate_normalized_artifact_rejection():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root)
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        _expect_code(
            "NORMALIZED_ALREADY_EXISTS",
            persist_normalized_judgment,
            storage_root=root,
            judgment=judgment,
            persisted_at="2026-08-16T00:00:02+00:00",
        )


# --------------------------------------------------------------------------- #
# T12 / T13 failure cleanup + retry
# --------------------------------------------------------------------------- #

class _FailAfterCreateFile:
    """Delegates to a real, already-created exclusive-create file handle, but
    raises OSError on the first write(). The target file therefore exists on
    disk before the failure occurs -- the same trigger condition Phase 2A's
    bounded persistence remediation regression covers."""

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
    real_open = open

    def patched(path, mode="r", *args, **kwargs):
        if mode == "xb" and str(path).endswith(target_filename):
            real_handle = real_open(path, mode, *args, **kwargs)
            return _FailAfterCreateFile(real_handle)
        return real_open(path, mode, *args, **kwargs)

    return patched


def test_failed_judgment_write_cleanup_and_retry():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-t12")

        with patch("builtins.open", new=_open_that_fails_after_creating("judgment.json")):
            _expect_code(
                "NORMALIZED_WRITE_FAILURE",
                persist_normalized_judgment,
                storage_root=root,
                judgment=judgment,
                persisted_at="2026-08-16T00:00:01+00:00",
            )

        assert not _artifact_dir(root, judgment).exists()

        result = persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:02+00:00"
        )
        assert result.status == "NORMALIZED_PERSISTED_VERIFIED"


def test_failed_receipt_write_cleanup_and_retry():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-t13")

        with patch("builtins.open", new=_open_that_fails_after_creating("receipt.json")):
            _expect_code(
                "NORMALIZED_RECEIPT_WRITE_FAILURE",
                persist_normalized_judgment,
                storage_root=root,
                judgment=judgment,
                persisted_at="2026-08-16T00:00:01+00:00",
            )

        assert not _artifact_dir(root, judgment).exists()

        result = persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:02+00:00"
        )
        assert result.status == "NORMALIZED_PERSISTED_VERIFIED"


# --------------------------------------------------------------------------- #
# T14 / T15 field-trace and diagnostics preservation
# --------------------------------------------------------------------------- #

def test_field_trace_preservation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-t14")
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        schema_digest = compute_normalized_schema_id_digest(NORMALIZED_SCHEMA_ID)
        _artifact, judgment_bytes = read_normalized_judgment(
            storage_root=root,
            run_id="run-t14",
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,
            normalized_schema_id_digest=schema_digest,
        )
        read_back = json.loads(judgment_bytes.decode("utf-8"))
        assert read_back["field_traces"] == [t.to_dict() for t in judgment.field_traces]


def test_diagnostics_preservation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-t15")
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        schema_digest = compute_normalized_schema_id_digest(NORMALIZED_SCHEMA_ID)
        _artifact, judgment_bytes = read_normalized_judgment(
            storage_root=root,
            run_id="run-t15",
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,
            normalized_schema_id_digest=schema_digest,
        )
        read_back = json.loads(judgment_bytes.decode("utf-8"))
        assert read_back["diagnostics"] == [d.to_dict() for d in judgment.diagnostics]


# --------------------------------------------------------------------------- #
# T16 schema failure before filesystem mutation
# --------------------------------------------------------------------------- #

def test_schema_failure_before_filesystem_mutation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-t16")
        _expect_code(
            "NORMALIZED_SCHEMA_VALIDATION_FAILURE",
            persist_normalized_judgment,
            storage_root=root,
            judgment=judgment,
            persisted_at="",
        )
        assert not (root / "normalized").exists()


# --------------------------------------------------------------------------- #
# T17 unsafe storage component rejection
# --------------------------------------------------------------------------- #

def test_unsafe_storage_component_rejection():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _judgment(run_id="../escape")
        _expect_code(
            "STORAGE_ROOT_VIOLATION",
            persist_normalized_judgment,
            storage_root=root,
            judgment=judgment,
            persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert list(root.iterdir()) == []


# --------------------------------------------------------------------------- #
# T18 cross-run collision resistance
# --------------------------------------------------------------------------- #

def test_cross_run_collision_resistance():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment_a = _setup(root, run_id="run-t18-a", raw_artifact_id="ev-a", raw_bytes=b"payload-a")
        judgment_b = _setup(root, run_id="run-t18-b", raw_artifact_id="ev-b", raw_bytes=b"payload-b")
        result_a = persist_normalized_judgment(
            storage_root=root, judgment=judgment_a, persisted_at="2026-08-16T00:00:01+00:00"
        )
        result_b = persist_normalized_judgment(
            storage_root=root, judgment=judgment_b, persisted_at="2026-08-16T00:00:01+00:00"
        )
        assert result_a.normalized_artifact_id != result_b.normalized_artifact_id


# --------------------------------------------------------------------------- #
# T19 / T20 Phase 2A files unchanged
# --------------------------------------------------------------------------- #

def test_phase2a_raw_bin_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-t19")
        raw_path = root / "run-t19" / "raw.bin"
        before = raw_path.read_bytes()
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        assert raw_path.read_bytes() == before


def test_phase2a_receipt_json_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-t20")
        receipt_path = root / "run-t20" / "receipt.json"
        before = receipt_path.read_bytes()
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        assert receipt_path.read_bytes() == before


# --------------------------------------------------------------------------- #
# T21 RunRecord unchanged
# --------------------------------------------------------------------------- #

def test_runrecord_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _persist_raw(root, run_id="run-t21")
        judgment = _judgment(run_id="run-t21")
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        assert record.run_status == "RAW_FROZEN"


# --------------------------------------------------------------------------- #
# F-01 remediation -- read_normalized_judgment() full identity verification
# --------------------------------------------------------------------------- #

def _persisted_receipt_path(root: Path, judgment: NormalizedJudgmentV0_2_2) -> Path:
    return _artifact_dir(root, judgment) / "receipt.json"


def _flip_hex_char(value: str) -> str:
    return ("0" if value[0] != "0" else "1") + value[1:]


def test_read_rejects_self_inconsistent_normalized_artifact_id():
    """F-01a: the receipt's stored normalized_artifact_id does not
    reproduce from recomputation over its own five identity fields."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-f01a")
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        receipt_path = _persisted_receipt_path(root, judgment)
        payload = json.loads(receipt_path.read_bytes().decode("utf-8"))
        payload["normalized_artifact_id"] = _flip_hex_char(payload["normalized_artifact_id"])
        receipt_path.write_bytes(serialize_deterministic_json(payload))

        schema_digest = compute_normalized_schema_id_digest(NORMALIZED_SCHEMA_ID)
        _expect_code(
            "NORMALIZED_IDENTITY_MISMATCH",
            read_normalized_judgment,
            storage_root=root,
            run_id="run-f01a",
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,
            normalized_schema_id_digest=schema_digest,
        )


def test_read_rejects_persisted_identity_diverging_from_caller_path():
    """F-01b: the receipt is internally self-consistent (its stored
    normalized_artifact_id correctly reproduces from its own, tampered
    identity fields) but a persisted identity component no longer agrees
    with the caller/path identity the read was requested under -- this
    isolates the path-vs-persisted check from the self-consistency check
    above."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-f01b")
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        receipt_path = _persisted_receipt_path(root, judgment)
        payload = json.loads(receipt_path.read_bytes().decode("utf-8"))
        payload["parser_version"] = payload["parser_version"] + "-tampered"
        payload["normalized_artifact_id"] = compute_normalized_artifact_id(
            run_id=payload["run_id"],
            output_contract_id=payload["output_contract_id"],
            parser_id=payload["parser_id"],
            parser_version=payload["parser_version"],
            normalized_schema_id=payload["normalized_schema_id"],
        )
        receipt_path.write_bytes(serialize_deterministic_json(payload))

        schema_digest = compute_normalized_schema_id_digest(NORMALIZED_SCHEMA_ID)
        _expect_code(
            "NORMALIZED_IDENTITY_MISMATCH",
            read_normalized_judgment,
            storage_root=root,
            run_id="run-f01b",
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,  # caller still asks for the ORIGINAL version
            normalized_schema_id_digest=schema_digest,
        )


# --------------------------------------------------------------------------- #
# F-02 remediation -- normalized_content_sha256 independently verified
# --------------------------------------------------------------------------- #

def test_read_rejects_wrong_normalized_content_sha256_with_correct_byte_digest():
    """Proves byte integrity (artifact_bytes_sha256, judgment.json
    untouched) does not silently validate content-identity metadata:
    only normalized_content_sha256 in the receipt is corrupted."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-f02")
        persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:01+00:00"
        )
        receipt_path = _persisted_receipt_path(root, judgment)
        payload = json.loads(receipt_path.read_bytes().decode("utf-8"))
        payload["normalized_content_sha256"] = _flip_hex_char(payload["normalized_content_sha256"])
        receipt_path.write_bytes(serialize_deterministic_json(payload))

        schema_digest = compute_normalized_schema_id_digest(NORMALIZED_SCHEMA_ID)
        _expect_code(
            "NORMALIZED_IDENTITY_MISMATCH",
            read_normalized_judgment,
            storage_root=root,
            run_id="run-f02",
            output_contract_id=judgment.output_contract_id,
            parser_id=judgment.parser_id,
            parser_version=judgment.parser_version,
            normalized_schema_id_digest=schema_digest,
        )


# --------------------------------------------------------------------------- #
# F-03 -- post-write (both files already written) verification failure
# --------------------------------------------------------------------------- #

def test_post_write_verification_failure_cleans_up_and_allows_retry():
    """Forces the read-back verification step inside
    persist_normalized_judgment to fail only after judgment.json AND
    receipt.json have genuinely, fully been written to disk by the real
    (unpatched) write code -- the class of failure T12/T13 do not cover."""

    def _raise_after_confirming_both_files_written(**kwargs):
        artifact_dir = (
            kwargs["storage_root"]
            / "normalized"
            / kwargs["run_id"]
            / kwargs["output_contract_id"]
            / kwargs["parser_id"]
            / kwargs["parser_version"]
            / kwargs["normalized_schema_id_digest"]
        )
        assert (artifact_dir / "judgment.json").is_file(), (
            "judgment.json must already exist when post-write verification runs"
        )
        assert (artifact_dir / "receipt.json").is_file(), (
            "receipt.json must already exist when post-write verification runs"
        )
        raise NormalizedPersistenceError(
            "NORMALIZED_READBACK_FAILURE",
            "simulated post-write verification failure (both files confirmed written)",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        judgment = _setup(root, run_id="run-f03")

        with patch(
            "pel.normalized_persistence.read_normalized_judgment",
            side_effect=_raise_after_confirming_both_files_written,
        ):
            _expect_code(
                "NORMALIZED_READBACK_FAILURE",
                persist_normalized_judgment,
                storage_root=root,
                judgment=judgment,
                persisted_at="2026-08-16T00:00:01+00:00",
            )

        artifact_dir = _artifact_dir(root, judgment)
        assert not artifact_dir.exists()
        assert not (artifact_dir / "judgment.json").exists()
        assert not (artifact_dir / "receipt.json").exists()

        raw_path = root / "run-f03" / "raw.bin"
        raw_receipt_path = root / "run-f03" / "receipt.json"
        assert raw_path.is_file()
        assert raw_receipt_path.is_file()

        result = persist_normalized_judgment(
            storage_root=root, judgment=judgment, persisted_at="2026-08-16T00:00:02+00:00"
        )
        assert result.status == "NORMALIZED_PERSISTED_VERIFIED"
        assert result.readback_verified is True
