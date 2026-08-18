"""E-05 CanonicalTaskBinding canonical-ingress tests."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace

import pytest

from pel.canonical_task_binding import (
    build_canonical_task_bound_run_record,
    compute_canonical_task_binding_id,
)
from pel.canonical_task_binding_models import (
    CANONICAL_TASK_BINDING_SCHEMA_ID,
)
from pel.canonical_task_identity import compute_canonical_task_sha256
from pel.integrity import sha256_bytes
from pel.task_freeze import freeze_task


def _task():
    return freeze_task(
        task_id="task-e05",
        task_version="1",
        task_class="TEST",
        semantic_boundary="bounded",
        bundle_filename="bundle.bin",
        bundle_bytes=b"bundle-content",
        prompt_id="prompt-label",
        prompt_bytes=b"prompt-content",
        output_contract_id="output-contract-1",
        created_at="2026-08-18T00:00:00+00:00",
    )


def _build(task_spec=None, *, run_id="run-e05"):
    return build_canonical_task_bound_run_record(
        task_spec=task_spec or _task(),
        run_id=run_id,
        plan_id="plan-e05",
        condition_id="condition-e05",
        replay_index=0,
        model_family="family-x",
        model_identifier="model-x",
        adapter_id="adapter-x",
        adapter_version="1.0",
        started_at=None,
        completed_at=None,
        raw_artifact_id="raw-e05",
        raw_bytes=b"raw-output",
        capture_mode="manual_import",
    )


def test_b01_frozen_task_spec_canonical_ingress_succeeds():
    record, binding = _build()

    assert record.run_status == "RAW_FROZEN"
    assert binding.status == "CANONICAL_TASK_BINDING_FROZEN"


def test_b02_draft_task_spec_is_refused():
    spec = replace(_task(), status="DRAFT")

    with pytest.raises(ValueError):
        _build(spec)


def test_b03_superseded_task_spec_is_refused():
    spec = replace(_task(), status="SUPERSEDED")

    with pytest.raises(ValueError):
        _build(spec)


def test_b04_b05_caller_cannot_supply_task_or_prompt_hash_authority():
    params = inspect.signature(
        build_canonical_task_bound_run_record
    ).parameters

    assert "task_sha256" not in params
    assert "prompt_sha256" not in params


def test_b06_run_record_task_hash_is_canonical_digest():
    spec = _task()
    record, _binding = _build(spec)

    assert record.task_sha256 == compute_canonical_task_sha256(spec)


def test_b07_run_record_prompt_hash_is_taskspec_prompt_hash():
    spec = _task()
    record, binding = _build(spec)

    assert record.prompt_sha256 == spec.prompt_sha256
    assert binding.prompt_sha256 == spec.prompt_sha256


def test_b08_binding_is_linked_to_same_run_and_task():
    spec = _task()
    record, binding = _build(spec)

    assert binding.run_id == record.run_id
    assert binding.task_id == spec.task_id
    assert binding.canonical_task_sha256 == record.task_sha256


def test_binding_id_follows_frozen_slot_identity_rule():
    run_id = "run-binding-id"

    expected_bytes = json.dumps(
        [run_id, CANONICAL_TASK_BINDING_SCHEMA_ID],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    assert compute_canonical_task_binding_id(
        run_id=run_id
    ) == sha256_bytes(expected_bytes)


def test_binding_id_changes_with_run_id():
    assert compute_canonical_task_binding_id(
        run_id="run-a"
    ) != compute_canonical_task_binding_id(
        run_id="run-b"
    )

# --- E05 persistence/readback tests ---

from pel.canonical_task_binding_persistence import (
    persist_canonical_task_binding,
)
from pel.canonical_task_binding_readback import (
    read_canonical_task_binding,
)
from pel.canonical_task_binding_storage import (
    CanonicalTaskBindingPersistenceError,
    canonical_task_binding_path,
)
from pel.integrity import sha256_bytes
from pel.normalized_identity import serialize_deterministic_json


def test_b09_binding_source_mismatch_is_rejected(tmp_path):
    spec = _task()
    record, binding = _build(spec)

    bad_binding = replace(
        binding,
        task_id="different-task",
    )

    with pytest.raises(
        CanonicalTaskBindingPersistenceError
    ) as exc_info:
        persist_canonical_task_binding(
            storage_root=tmp_path,
            task_spec=spec,
            run_record=record,
            binding=bad_binding,
        )

    assert (
        exc_info.value.code
        == "CANONICAL_TASK_BINDING_SOURCE_MISMATCH"
    )


def test_b10_binding_persistence_is_write_once(tmp_path):
    spec = _task()
    record, binding = _build(spec)

    result = persist_canonical_task_binding(
        storage_root=tmp_path,
        task_spec=spec,
        run_record=record,
        binding=binding,
    )

    assert result.readback_verified is True

    with pytest.raises(
        CanonicalTaskBindingPersistenceError
    ) as exc_info:
        persist_canonical_task_binding(
            storage_root=tmp_path,
            task_spec=spec,
            run_record=record,
            binding=binding,
        )

    assert (
        exc_info.value.code
        == "CANONICAL_TASK_BINDING_ALREADY_EXISTS"
    )


def test_b11_readback_verifies_exact_binding_bytes(tmp_path):
    spec = _task()
    record, binding = _build(spec)

    result = persist_canonical_task_binding(
        storage_root=tmp_path,
        task_spec=spec,
        run_record=record,
        binding=binding,
    )

    read_binding, read_bytes = read_canonical_task_binding(
        storage_root=tmp_path,
        run_id=record.run_id,
    )

    expected_bytes = serialize_deterministic_json(
        binding.to_dict()
    )

    assert read_binding == binding
    assert read_bytes == expected_bytes
    assert result.binding_bytes_sha256 == sha256_bytes(
        expected_bytes
    )
    assert result.readback_verified is True


def test_b12_failed_readback_cleans_slot_and_permits_retry(
    tmp_path,
    monkeypatch,
):
    import pel.canonical_task_binding_persistence as module

    spec = _task()
    record, binding = _build(spec)

    original_readback = module.read_canonical_task_binding

    def forced_failure(**_kwargs):
        raise CanonicalTaskBindingPersistenceError(
            "CANONICAL_TASK_BINDING_READBACK_FAILURE",
            "forced test failure",
        )

    monkeypatch.setattr(
        module,
        "read_canonical_task_binding",
        forced_failure,
    )

    with pytest.raises(
        CanonicalTaskBindingPersistenceError
    ):
        persist_canonical_task_binding(
            storage_root=tmp_path,
            task_spec=spec,
            run_record=record,
            binding=binding,
        )

    directory, binding_path = canonical_task_binding_path(
        storage_root=tmp_path,
        run_id=record.run_id,
        binding_id=binding.binding_id,
    )

    assert not binding_path.exists()
    assert not directory.exists()

    monkeypatch.setattr(
        module,
        "read_canonical_task_binding",
        original_readback,
    )

    result = persist_canonical_task_binding(
        storage_root=tmp_path,
        task_spec=spec,
        run_record=record,
        binding=binding,
    )

    assert result.readback_verified is True


def test_unsafe_run_id_is_rejected_by_storage_boundary(
    tmp_path,
):
    spec = _task()
    record, binding = _build(
        spec,
        run_id="../escape",
    )

    with pytest.raises(
        CanonicalTaskBindingPersistenceError
    ) as exc_info:
        persist_canonical_task_binding(
            storage_root=tmp_path,
            task_spec=spec,
            run_record=record,
            binding=binding,
        )

    assert (
        exc_info.value.code
        == "CANONICAL_TASK_BINDING_STORAGE_ROOT_VIOLATION"
    )
