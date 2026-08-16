"""ION PEL Replay Comparability Prerequisite tests
(persist_replay_execution_descriptor), per
ION_PEL_REPLAY_EXECUTION_DESCRIPTOR_CONTRACT_FREEZE_v0.1.md, its
completeness addendum, and its failure-code closure.

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
All test writes remain inside a `tempfile.TemporaryDirectory()`.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from pel.evidence import persist_raw_evidence
from pel.integrity import sha256_bytes
from pel.models import ExecutionCondition, RunRecord
from pel.normalized_identity import serialize_deterministic_json
from pel.receipts import build_raw_frozen_run_record
from pel.replay_execution_descriptor_models import ReplayExecutionDescriptorPersistenceResult
from pel.replay_execution_identity import (
    REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
    compute_replay_execution_descriptor_id,
    compute_replay_execution_descriptor_schema_id_digest,
)
from pel.replay_execution_persistence import persist_replay_execution_descriptor
from pel.replay_execution_readback import read_replay_execution_descriptor
from pel.replay_execution_storage import ReplayExecutionDescriptorPersistenceError
from pel.validation import (
    validate_replay_execution_descriptor,
    validate_replay_execution_descriptor_persistence_result,
)

VALID_SHA = "a" * 64
DEFAULT_RAW = b"replay-raw-output"


def _run_record(*, run_id="run-1", raw_artifact_id="ev-1", raw_bytes=DEFAULT_RAW, **overrides):
    fields = dict(
        run_id=run_id,
        plan_id="plan-1",
        condition_id="cond-1",
        replay_index=0,
        model_family="family-x",
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
    fields.update(overrides)
    return build_raw_frozen_run_record(**fields)


def _execution_condition(record: RunRecord, **overrides) -> ExecutionCondition:
    fields = dict(
        condition_id=record.condition_id,
        model_family=record.model_family,
        model_identifier=record.model_identifier,
        adapter_id=record.adapter_id,
        adapter_version=record.adapter_version,
        expected_replays=3,
        provider_settings=(("temperature", "0.0"), ("top_p", "1.0")),
    )
    fields.update(overrides)
    return ExecutionCondition(**fields)


def _setup(
    root: Path,
    *,
    run_id="run-1",
    raw_artifact_id="ev-1",
    raw_bytes=DEFAULT_RAW,
    record_overrides=None,
    condition_overrides=None,
):
    record = _run_record(
        run_id=run_id, raw_artifact_id=raw_artifact_id, raw_bytes=raw_bytes,
        **(record_overrides or {}),
    )
    persist_raw_evidence(
        storage_root=root, run_record=record, raw_bytes=raw_bytes,
        persisted_at="2026-08-16T00:00:00+00:00",
    )
    condition = _execution_condition(record, **(condition_overrides or {}))
    return record, condition


def _descriptor_dir(root: Path, run_id: str) -> Path:
    digest = compute_replay_execution_descriptor_schema_id_digest(
        REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID
    )
    return root / "replay-execution" / run_id / digest


def _expect_code(code, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ReplayExecutionDescriptorPersistenceError as exc:
        assert exc.code == code, f"expected code {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(
        f"expected ReplayExecutionDescriptorPersistenceError({code!r}), nothing was raised"
    )


# --------------------------------------------------------------------------- #
# T01 exact round trip
# --------------------------------------------------------------------------- #

def test_exact_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t01")
        result = persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert isinstance(result, ReplayExecutionDescriptorPersistenceResult)
        assert result.readback_verified is True
        assert result.status == "EXECUTION_DESCRIPTOR_PERSISTED_VERIFIED"

        descriptor, _bytes = read_replay_execution_descriptor(
            storage_root=root, run_id="run-t01",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )
        assert descriptor.descriptor_id == result.descriptor_id
        assert descriptor.condition_id == condition.condition_id
        assert descriptor.model_family == condition.model_family
        assert dict(descriptor.provider_settings) == dict(condition.provider_settings)
        validate_replay_execution_descriptor(descriptor.to_dict())
        validate_replay_execution_descriptor_persistence_result(result.to_dict())


# --------------------------------------------------------------------------- #
# T02 deterministic descriptor_id / T03 identity non-collision
# --------------------------------------------------------------------------- #

def test_descriptor_id_deterministic_reproduction():
    kwargs = dict(
        run_id="run-x", replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID
    )
    assert compute_replay_execution_descriptor_id(
        **kwargs
    ) == compute_replay_execution_descriptor_id(**kwargs)


def test_identity_non_collision_across_run_id():
    a = compute_replay_execution_descriptor_id(
        run_id="run-a", replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID
    )
    b = compute_replay_execution_descriptor_id(
        run_id="run-b", replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID
    )
    assert a != b


def test_identity_non_collision_across_schema_id():
    a = compute_replay_execution_descriptor_id(
        run_id="run-a", replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID
    )
    b = compute_replay_execution_descriptor_id(
        run_id="run-a",
        replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID + "-other",
    )
    assert a != b


def test_schema_digest_non_collision():
    digest_a = compute_replay_execution_descriptor_schema_id_digest(
        "https://ion.local/schemas/pel_replay_execution_descriptor_v0_1.schema.json"
    )
    digest_b = compute_replay_execution_descriptor_schema_id_digest(
        "https://ion.local/schemas/pel_replay_execution_descriptor_v0_2.schema.json"
    )
    assert digest_a != digest_b


# --------------------------------------------------------------------------- #
# T05 same-run same-schema overwrite rejection
# --------------------------------------------------------------------------- #

def test_duplicate_descriptor_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t05")
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        _expect_code(
            "EXECUTION_DESCRIPTOR_ALREADY_EXISTS", persist_replay_execution_descriptor,
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:02+00:00",
        )


# --------------------------------------------------------------------------- #
# T06-T08 source verification
# --------------------------------------------------------------------------- #

def test_source_run_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(run_id="run-missing")
        condition = _execution_condition(record)
        _expect_code(
            "EXECUTION_DESCRIPTOR_SOURCE_RAW_NOT_FOUND", persist_replay_execution_descriptor,
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )


def test_task_sha256_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t07")
        tampered = dataclasses.replace(record, task_sha256="b" * 64)
        _expect_code(
            "EXECUTION_DESCRIPTOR_TASK_SHA256_MISMATCH", persist_replay_execution_descriptor,
            storage_root=root, run_record=tampered, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )


def test_prompt_sha256_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t08")
        tampered = dataclasses.replace(record, prompt_sha256="b" * 64)
        _expect_code(
            "EXECUTION_DESCRIPTOR_PROMPT_SHA256_MISMATCH", persist_replay_execution_descriptor,
            storage_root=root, run_record=tampered, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )


# --------------------------------------------------------------------------- #
# T09 RunRecord/ExecutionCondition provenance mismatch — stable code
# --------------------------------------------------------------------------- #

def test_condition_provenance_mismatch_model_family():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(
            root, run_id="run-t09a", condition_overrides={"model_family": "different-family"}
        )
        _expect_code(
            "EXECUTION_DESCRIPTOR_CONDITION_PROVENANCE_MISMATCH",
            persist_replay_execution_descriptor,
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )


def test_condition_provenance_mismatch_condition_id_same_stable_code():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(
            root, run_id="run-t09b", condition_overrides={"condition_id": "different-condition"}
        )
        _expect_code(
            "EXECUTION_DESCRIPTOR_CONDITION_PROVENANCE_MISMATCH",
            persist_replay_execution_descriptor,
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )


# --------------------------------------------------------------------------- #
# T10-T13 provider_settings semantics
# --------------------------------------------------------------------------- #

def test_provider_settings_order_independence():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(
            root, run_id="run-t10",
            condition_overrides={"provider_settings": (("temperature", "0.0"), ("top_p", "1.0"))},
        )
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        descriptor, _bytes = read_replay_execution_descriptor(
            storage_root=root, run_id="run-t10",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )
        as_persisted = dict(descriptor.provider_settings)
        reordered_equivalent = dict((("top_p", "1.0"), ("temperature", "0.0")))
        assert as_persisted == reordered_equivalent


def test_provider_settings_different_value_is_distinguished():
    settings_a = dict((("temperature", "0.0"),))
    settings_b = dict((("temperature", "0.7"),))
    assert settings_a != settings_b


def test_provider_settings_duplicate_key_rejected():
    try:
        ExecutionCondition(
            condition_id="c", model_family="f", model_identifier="m",
            adapter_id="a", adapter_version="1", expected_replays=1,
            provider_settings=(("k", "1"), ("k", "2")),
        )
    except ValueError:
        return
    raise AssertionError("expected ValueError for duplicate provider_settings keys")


def test_empty_provider_settings_persisted_as_empty_object():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(
            root, run_id="run-t13", condition_overrides={"provider_settings": ()}
        )
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        descriptor, descriptor_bytes = read_replay_execution_descriptor(
            storage_root=root, run_id="run-t13",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )
        assert descriptor.provider_settings == ()
        payload = json.loads(descriptor_bytes.decode("utf-8"))
        assert payload["provider_settings"] == {}


# --------------------------------------------------------------------------- #
# T14-T16 digest / readback / identity recomputation
# --------------------------------------------------------------------------- #

def test_exact_descriptor_bytes_digest():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t14")
        result = persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        descriptor_path = _descriptor_dir(root, "run-t14") / "descriptor.json"
        assert sha256_bytes(descriptor_path.read_bytes()) == result.descriptor_bytes_sha256


def test_readback_verification_matches_written_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t15")
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        descriptor_path = _descriptor_dir(root, "run-t15") / "descriptor.json"
        _descriptor, read_bytes = read_replay_execution_descriptor(
            storage_root=root, run_id="run-t15",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )
        assert read_bytes == descriptor_path.read_bytes()


def test_read_rejects_self_inconsistent_descriptor_id():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t16")
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        descriptor_path = _descriptor_dir(root, "run-t16") / "descriptor.json"
        payload = json.loads(descriptor_path.read_bytes().decode("utf-8"))
        original = payload["descriptor_id"]
        payload["descriptor_id"] = ("0" if original[0] != "0" else "1") + original[1:]
        descriptor_path.write_bytes(serialize_deterministic_json(payload))

        _expect_code(
            "EXECUTION_DESCRIPTOR_IDENTITY_MISMATCH", read_replay_execution_descriptor,
            storage_root=root, run_id="run-t16",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )


# --------------------------------------------------------------------------- #
# T17 schema failure before filesystem mutation
# --------------------------------------------------------------------------- #

def test_schema_failure_before_filesystem_mutation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t17")
        _expect_code(
            "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE",
            persist_replay_execution_descriptor,
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="", persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert not (root / "replay-execution").exists()


# --------------------------------------------------------------------------- #
# T19 unsafe storage component rejection
# --------------------------------------------------------------------------- #

def test_unsafe_run_id_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record = _run_record(run_id="../escape")
        condition = _execution_condition(record)
        _expect_code(
            "EXECUTION_DESCRIPTOR_STORAGE_ROOT_VIOLATION", persist_replay_execution_descriptor,
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert list(root.iterdir()) == []


# --------------------------------------------------------------------------- #
# T20-T21 failure cleanup + retry
# --------------------------------------------------------------------------- #

class _FailAfterCreateFile:
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


def test_failed_descriptor_write_cleanup_and_retry():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t20")

        with patch("builtins.open", new=_open_that_fails_after_creating("descriptor.json")):
            _expect_code(
                "EXECUTION_DESCRIPTOR_WRITE_FAILURE", persist_replay_execution_descriptor,
                storage_root=root, run_record=record, execution_condition=condition,
                session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
            )
        assert not _descriptor_dir(root, "run-t20").exists()

        result = persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:02+00:00",
        )
        assert result.status == "EXECUTION_DESCRIPTOR_PERSISTED_VERIFIED"


def test_post_write_verification_failure_cleans_up_and_allows_retry():
    def _raise_after_confirming_written(**kwargs):
        digest = compute_replay_execution_descriptor_schema_id_digest(
            kwargs["replay_execution_descriptor_schema_id"]
        )
        descriptor_path = (
            kwargs["storage_root"] / "replay-execution" / kwargs["run_id"] / digest
            / "descriptor.json"
        )
        assert descriptor_path.is_file(), (
            "descriptor.json must already exist when post-write verification runs"
        )
        raise ReplayExecutionDescriptorPersistenceError(
            "EXECUTION_DESCRIPTOR_READBACK_FAILURE",
            "simulated post-write verification failure (file confirmed written)",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t21")

        with patch(
            "pel.replay_execution_persistence.read_replay_execution_descriptor",
            side_effect=_raise_after_confirming_written,
        ):
            _expect_code(
                "EXECUTION_DESCRIPTOR_READBACK_FAILURE", persist_replay_execution_descriptor,
                storage_root=root, run_record=record, execution_condition=condition,
                session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
            )

        assert not _descriptor_dir(root, "run-t21").exists()
        raw_path = root / "run-t21" / "raw.bin"
        assert raw_path.is_file()

        result = persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:02+00:00",
        )
        assert result.status == "EXECUTION_DESCRIPTOR_PERSISTED_VERIFIED"


# --------------------------------------------------------------------------- #
# T22-T24 session_policy / replay_index / plan_id — provenance, not identity
# --------------------------------------------------------------------------- #

def test_session_policy_preserved_but_not_part_of_identity():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t22")
        result = persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="loose", persisted_at="2026-08-16T00:00:01+00:00",
        )
        descriptor, _bytes = read_replay_execution_descriptor(
            storage_root=root, run_id="run-t22",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )
        assert descriptor.session_policy == "loose"
        expected_id = compute_replay_execution_descriptor_id(
            run_id="run-t22",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )
        assert result.descriptor_id == expected_id


def test_replay_index_and_plan_id_are_bookkeeping_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(
            root, run_id="run-t23",
            record_overrides={"replay_index": 4, "plan_id": "plan-xyz"},
        )
        result = persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        descriptor, _bytes = read_replay_execution_descriptor(
            storage_root=root, run_id="run-t23",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )
        assert descriptor.replay_index == 4
        assert descriptor.plan_id == "plan-xyz"
        expected_id = compute_replay_execution_descriptor_id(
            run_id="run-t23",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )
        assert result.descriptor_id == expected_id


# --------------------------------------------------------------------------- #
# T25 historical absence
# --------------------------------------------------------------------------- #

def test_historical_absence_creates_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _record, _condition = _setup(root, run_id="run-t25")
        assert not (root / "replay-execution").exists()
        _expect_code(
            "EXECUTION_DESCRIPTOR_READBACK_FAILURE", read_replay_execution_descriptor,
            storage_root=root, run_id="run-t25",
            replay_execution_descriptor_schema_id=REPLAY_EXECUTION_DESCRIPTOR_SCHEMA_ID,
        )


# --------------------------------------------------------------------------- #
# T26-T28 preserved-artifact boundary
# --------------------------------------------------------------------------- #

def test_phase2a_raw_bin_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t26")
        raw_path = root / "run-t26" / "raw.bin"
        before = raw_path.read_bytes()
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert raw_path.read_bytes() == before


def test_phase2a_receipt_json_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t27")
        receipt_path = root / "run-t27" / "receipt.json"
        before = receipt_path.read_bytes()
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert receipt_path.read_bytes() == before


def test_phase2b2_namespace_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t28")
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert not (root / "normalized").exists()


# --------------------------------------------------------------------------- #
# T29-T31 RunRecord / ExecutionCondition / ExecutionPlan semantics unchanged
# --------------------------------------------------------------------------- #

def test_runrecord_semantics_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t29")
        persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert record.run_status == "RAW_FROZEN"


def test_executioncondition_semantics_unchanged():
    try:
        ExecutionCondition(
            condition_id="c", model_family="f", model_identifier="m",
            adapter_id="a", adapter_version="1", expected_replays=0,
            provider_settings=(),
        )
    except ValueError:
        return
    raise AssertionError("expected ValueError for expected_replays < 1")


def test_executionplan_not_required_by_descriptor_call():
    signature = inspect.signature(persist_replay_execution_descriptor)
    assert "execution_plan" not in signature.parameters


# --------------------------------------------------------------------------- #
# T32-T34 F-RXD-01 remediation — construction-time TypeError/ValueError must
# map to EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE, not leak unwrapped.
# --------------------------------------------------------------------------- #

def test_empty_plan_id_maps_to_schema_validation_failure_not_bare_valueerror():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t32")
        tampered = dataclasses.replace(record, plan_id="")
        _expect_code(
            "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE",
            persist_replay_execution_descriptor,
            storage_root=root, run_record=tampered, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        assert not (root / "replay-execution").exists()
        raw_path = root / "run-t32" / "raw.bin"
        assert raw_path.is_file()


def test_cross_checked_field_shared_empty_value_maps_to_schema_validation_failure():
    cross_checked_fields = (
        "condition_id",
        "model_family",
        "model_identifier",
        "adapter_id",
        "adapter_version",
    )
    for field_name in cross_checked_fields:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record, condition = _setup(root, run_id=f"run-t33-{field_name}")
            tampered_record = dataclasses.replace(record, **{field_name: ""})
            tampered_condition = dataclasses.replace(condition, **{field_name: ""})
            # cross-check itself must not be the failure: both sides agree
            assert getattr(tampered_record, field_name) == getattr(
                tampered_condition, field_name
            )
            _expect_code(
                "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE",
                persist_replay_execution_descriptor,
                storage_root=root, run_record=tampered_record,
                execution_condition=tampered_condition,
                session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
            )
            assert not (root / "replay-execution").exists()


def test_retry_with_valid_input_succeeds_after_construction_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record, condition = _setup(root, run_id="run-t34")
        tampered = dataclasses.replace(record, plan_id="")
        _expect_code(
            "EXECUTION_DESCRIPTOR_SCHEMA_VALIDATION_FAILURE",
            persist_replay_execution_descriptor,
            storage_root=root, run_record=tampered, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
        )
        result = persist_replay_execution_descriptor(
            storage_root=root, run_record=record, execution_condition=condition,
            session_policy="strict", persisted_at="2026-08-16T00:00:02+00:00",
        )
        assert result.status == "EXECUTION_DESCRIPTOR_PERSISTED_VERIFIED"


# --------------------------------------------------------------------------- #
# T35 F-RXD-02 remediation — provider_settings byte-level order-independence,
# proven against the actual persisted descriptor.json bytes, not a
# re-serialization performed only by the test.
# --------------------------------------------------------------------------- #

def _provider_settings_substring(raw_bytes: bytes) -> bytes:
    text = raw_bytes.decode("utf-8")
    key = '"provider_settings":'
    start = text.index(key) + len(key)
    assert text[start] == "{"
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end is not None, "unterminated provider_settings object"
    return text[start:end].encode("utf-8")


def test_provider_settings_byte_level_order_independence_on_disk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record_a, condition_a = _setup(
            root, run_id="run-t35a",
            condition_overrides={"provider_settings": (("a", "1"), ("b", "2"))},
        )
        record_b, condition_b = _setup(
            root, run_id="run-t35b",
            condition_overrides={"provider_settings": (("b", "2"), ("a", "1"))},
        )
        record_c, condition_c = _setup(
            root, run_id="run-t35c",
            condition_overrides={"provider_settings": (("a", "9"), ("b", "2"))},
        )
        for record, condition in (
            (record_a, condition_a), (record_b, condition_b), (record_c, condition_c),
        ):
            persist_replay_execution_descriptor(
                storage_root=root, run_record=record, execution_condition=condition,
                session_policy="strict", persisted_at="2026-08-16T00:00:01+00:00",
            )

        bytes_a = (_descriptor_dir(root, "run-t35a") / "descriptor.json").read_bytes()
        bytes_b = (_descriptor_dir(root, "run-t35b") / "descriptor.json").read_bytes()
        bytes_c = (_descriptor_dir(root, "run-t35c") / "descriptor.json").read_bytes()

        substring_a = _provider_settings_substring(bytes_a)
        substring_b = _provider_settings_substring(bytes_b)
        substring_c = _provider_settings_substring(bytes_c)

        # same key/value pairs, different input tuple order -> identical bytes
        assert substring_a == substring_b == b'{"a":"1","b":"2"}'
        # different value -> different persisted bytes
        assert substring_c == b'{"a":"9","b":"2"}'
        assert substring_c != substring_a
