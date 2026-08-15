"""ION PEL Phase-1 domain-model tests (TaskSpec, ExecutionCondition,
ExecutionPlan, RunRecord).

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
"""

from __future__ import annotations

import dataclasses

from pel.models import ExecutionCondition, ExecutionPlan, RunRecord, TaskSpec
from tests.util import raises

VALID_SHA = "a" * 64

# Prohibited semantic-authority vocabulary (mandate section 3.6 / 16-A5),
# checked here against dataclass field *names* only.
FORBIDDEN_FIELD_NAMES = {
    "true",
    "ground_truth",
    "validated",
    "canonical",
    "authorized",
    "action_right",
    "winner_model",
    "majority_truth",
    "majority",
}


def _task_spec(**overrides):
    fields = dict(
        task_id="task-1",
        task_version="v1",
        task_class="probe",
        semantic_boundary=None,
        bundle_filename="bundle.json",
        bundle_sha256=VALID_SHA,
        bundle_bytes=10,
        prompt_id="prompt-1",
        prompt_sha256=VALID_SHA,
        prompt_bytes=5,
        output_contract_id="contract-1",
        created_at="2026-08-15T00:00:00+00:00",
        status="FROZEN",
        provenance=("operator",),
    )
    fields.update(overrides)
    return TaskSpec(**fields)


def _condition(**overrides):
    fields = dict(
        condition_id="cond-1",
        model_family="family",
        model_identifier="model-x",
        adapter_id="adapter-1",
        adapter_version="1.0.0",
        expected_replays=3,
        provider_settings=(("temperature", "UNKNOWN"),),
    )
    fields.update(overrides)
    return ExecutionCondition(**fields)


def _plan(**overrides):
    fields = dict(
        plan_id="plan-1",
        task_id="task-1",
        conditions=(_condition(),),
        session_policy="isolated",
        execution_order=None,
        stop_rule="fixed_replay_count",
        gold_access_policy="NO_GOLD",
        status="DRAFT",
    )
    fields.update(overrides)
    return ExecutionPlan(**fields)


def _run_record(**overrides):
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
        raw_sha256=VALID_SHA,
        raw_bytes=10,
        capture_mode="manual_import",
        run_status="RAW_FROZEN",
    )
    fields.update(overrides)
    return RunRecord(**fields)


# --------------------------------------------------------------------------- #
# frozen-ness
# --------------------------------------------------------------------------- #

def test_task_spec_is_frozen():
    spec = _task_spec()
    with raises(dataclasses.FrozenInstanceError):
        spec.task_id = "other"


def test_execution_condition_is_frozen():
    condition = _condition()
    with raises(dataclasses.FrozenInstanceError):
        condition.condition_id = "other"


def test_execution_plan_is_frozen():
    plan = _plan()
    with raises(dataclasses.FrozenInstanceError):
        plan.plan_id = "other"


def test_run_record_is_frozen():
    record = _run_record()
    with raises(dataclasses.FrozenInstanceError):
        record.run_id = "other"


# --------------------------------------------------------------------------- #
# to_dict() shape
# --------------------------------------------------------------------------- #

def test_task_spec_to_dict_is_json_compatible_and_provenance_is_a_list():
    d = _task_spec().to_dict()
    assert d["provenance"] == ["operator"]
    assert isinstance(d["provenance"], list)
    assert d["bundle_bytes"] == 10
    assert d["semantic_boundary"] is None


def test_execution_condition_to_dict_serializes_provider_settings_as_object():
    d = _condition().to_dict()
    assert d["provider_settings"] == {"temperature": "UNKNOWN"}
    assert isinstance(d["provider_settings"], dict)


def test_execution_plan_to_dict_serializes_conditions_and_order():
    plan = _plan(execution_order=("cond-1",))
    d = plan.to_dict()
    assert isinstance(d["conditions"], list)
    assert d["conditions"][0]["condition_id"] == "cond-1"
    assert d["execution_order"] == ["cond-1"]


def test_execution_plan_to_dict_preserves_none_execution_order():
    d = _plan(execution_order=None).to_dict()
    assert d["execution_order"] is None


def test_run_record_to_dict_returns_primitives():
    d = _run_record().to_dict()
    assert d["run_id"] == "run-1"
    assert d["replay_index"] == 0
    assert d["run_status"] == "RAW_FROZEN"


# --------------------------------------------------------------------------- #
# ExecutionCondition validation
# --------------------------------------------------------------------------- #

def test_execution_condition_rejects_expected_replays_below_one():
    with raises(ValueError):
        _condition(expected_replays=0)


def test_execution_condition_rejects_duplicate_provider_setting_keys():
    with raises(ValueError):
        _condition(
            provider_settings=(("temperature", "UNKNOWN"), ("temperature", "0.0"))
        )


# --------------------------------------------------------------------------- #
# ExecutionPlan validation
# --------------------------------------------------------------------------- #

def test_execution_plan_rejects_zero_conditions():
    with raises(ValueError):
        _plan(conditions=())


def test_execution_plan_rejects_duplicate_condition_id_values():
    with raises(ValueError):
        _plan(
            conditions=(
                _condition(condition_id="cond-1"),
                _condition(condition_id="cond-1"),
            )
        )


def test_execution_plan_rejects_unknown_execution_order_condition_ids():
    with raises(ValueError):
        _plan(
            conditions=(_condition(condition_id="cond-1"),),
            execution_order=("cond-unknown",),
        )


# --------------------------------------------------------------------------- #
# RunRecord validation
# --------------------------------------------------------------------------- #

def test_run_record_rejects_negative_replay_index():
    with raises(ValueError):
        _run_record(replay_index=-1)


def test_run_record_rejects_negative_raw_bytes():
    with raises(ValueError):
        _run_record(raw_bytes=-1)


def test_run_record_rejects_malformed_sha_values():
    with raises(ValueError):
        _run_record(task_sha256="not-a-digest")
    with raises(ValueError):
        _run_record(prompt_sha256="not-a-digest")
    with raises(ValueError):
        _run_record(raw_sha256="not-a-digest")


# --------------------------------------------------------------------------- #
# No semantic-authority surface
# --------------------------------------------------------------------------- #

def test_no_forbidden_semantic_authority_field_on_any_public_dataclass():
    for cls in (TaskSpec, ExecutionCondition, ExecutionPlan, RunRecord):
        names = {f.name.lower() for f in dataclasses.fields(cls)}
        forbidden = names & FORBIDDEN_FIELD_NAMES
        assert not forbidden, f"{cls.__name__} carries forbidden field(s): {forbidden}"
