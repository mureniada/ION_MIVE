"""ION PEL Phase-1 JSON Schema contract tests, plus static boundary checks:
no forbidden imports, no runtime filesystem-write primitives.

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from pel.models import ExecutionCondition, ExecutionPlan, RunRecord, TaskSpec
from pel.validation import (
    PELValidationError,
    validate_execution_plan,
    validate_run_record,
    validate_task_spec,
)
from tests.util import raises

VALID_SHA = "a" * 64

PEL_DIR = Path(__file__).resolve().parents[1] / "pel"

# mandate section 13.3 / 16-A3
FORBIDDEN_IMPORT_ROOTS = {
    "app",
    "t4",
    "requests",
    "httpx",
    "socket",
    "openai",
    "anthropic",
    "google",  # covers google.generativeai and google.genai
}


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _valid_task_spec_payload() -> dict:
    return TaskSpec(
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
    ).to_dict()


def _valid_execution_plan_payload() -> dict:
    condition = ExecutionCondition(
        condition_id="cond-1",
        model_family="family",
        model_identifier="model-x",
        adapter_id="adapter-1",
        adapter_version="1.0.0",
        expected_replays=3,
        provider_settings=(("temperature", "UNKNOWN"),),
    )
    return ExecutionPlan(
        plan_id="plan-1",
        task_id="task-1",
        conditions=(condition,),
        session_policy="isolated",
        execution_order=None,
        stop_rule="fixed_replay_count",
        gold_access_policy="NO_GOLD",
        status="DRAFT",
    ).to_dict()


def _valid_run_record_payload() -> dict:
    return RunRecord(
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
    ).to_dict()


# --------------------------------------------------------------------------- #
# valid payloads validate
# --------------------------------------------------------------------------- #

def test_valid_task_spec_validates():
    validate_task_spec(_valid_task_spec_payload())


def test_valid_execution_plan_validates():
    validate_execution_plan(_valid_execution_plan_payload())


def test_valid_run_record_validates():
    validate_run_record(_valid_run_record_payload())


# --------------------------------------------------------------------------- #
# TaskSpec schema
# --------------------------------------------------------------------------- #

def test_task_spec_schema_rejects_unknown_additional_property():
    payload = _valid_task_spec_payload()
    payload["unexpected_field"] = "x"
    with raises(PELValidationError):
        validate_task_spec(payload)


def test_task_spec_schema_rejects_missing_required_field():
    payload = _valid_task_spec_payload()
    del payload["created_at"]
    with raises(PELValidationError):
        validate_task_spec(payload)


def test_task_spec_schema_rejects_malformed_sha():
    payload = _valid_task_spec_payload()
    payload["bundle_sha256"] = "not-a-digest"
    with raises(PELValidationError):
        validate_task_spec(payload)


def test_task_spec_schema_rejects_negative_byte_count():
    payload = _valid_task_spec_payload()
    payload["bundle_bytes"] = -1
    with raises(PELValidationError):
        validate_task_spec(payload)


def test_task_spec_schema_rejects_invalid_status():
    payload = _valid_task_spec_payload()
    payload["status"] = "UNKNOWN_STATUS"
    with raises(PELValidationError):
        validate_task_spec(payload)


# --------------------------------------------------------------------------- #
# ExecutionPlan schema
# --------------------------------------------------------------------------- #

def test_execution_plan_schema_rejects_unknown_additional_property():
    payload = _valid_execution_plan_payload()
    payload["unexpected_field"] = "x"
    with raises(PELValidationError):
        validate_execution_plan(payload)


def test_execution_plan_schema_rejects_missing_required_field():
    payload = _valid_execution_plan_payload()
    del payload["stop_rule"]
    with raises(PELValidationError):
        validate_execution_plan(payload)


def test_execution_plan_schema_rejects_empty_conditions():
    payload = _valid_execution_plan_payload()
    payload["conditions"] = []
    with raises(PELValidationError):
        validate_execution_plan(payload)


def test_execution_plan_schema_rejects_expected_replays_zero():
    payload = _valid_execution_plan_payload()
    payload["conditions"][0]["expected_replays"] = 0
    with raises(PELValidationError):
        validate_execution_plan(payload)


def test_execution_plan_schema_rejects_invalid_gold_access_policy():
    payload = _valid_execution_plan_payload()
    payload["gold_access_policy"] = "SHOW_GOLD"
    with raises(PELValidationError):
        validate_execution_plan(payload)


def test_execution_plan_schema_rejects_invalid_status():
    payload = _valid_execution_plan_payload()
    payload["status"] = "UNKNOWN_STATUS"
    with raises(PELValidationError):
        validate_execution_plan(payload)


# --------------------------------------------------------------------------- #
# RunRecord schema
# --------------------------------------------------------------------------- #

def test_run_record_schema_rejects_unknown_additional_property():
    payload = _valid_run_record_payload()
    payload["unexpected_field"] = "x"
    with raises(PELValidationError):
        validate_run_record(payload)


def test_run_record_schema_rejects_missing_required_field():
    payload = _valid_run_record_payload()
    del payload["raw_sha256"]
    with raises(PELValidationError):
        validate_run_record(payload)


def test_run_record_schema_rejects_malformed_sha():
    payload = _valid_run_record_payload()
    payload["raw_sha256"] = "not-a-digest"
    with raises(PELValidationError):
        validate_run_record(payload)


def test_run_record_schema_rejects_negative_replay_index():
    payload = _valid_run_record_payload()
    payload["replay_index"] = -1
    with raises(PELValidationError):
        validate_run_record(payload)


def test_run_record_schema_rejects_negative_raw_bytes():
    payload = _valid_run_record_payload()
    payload["raw_bytes"] = -1
    with raises(PELValidationError):
        validate_run_record(payload)


def test_run_record_schema_rejects_invalid_run_status():
    payload = _valid_run_record_payload()
    payload["run_status"] = "UNKNOWN_STATUS"
    with raises(PELValidationError):
        validate_run_record(payload)


# --------------------------------------------------------------------------- #
# static boundary checks (mandate sections 3.2, 3.3, 3.4, 3.5, 16-A3, 16-A4)
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


def test_pel_source_has_no_runtime_write_primitives():
    violations = []
    for path in _pel_source_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in (
                "write_text",
                "write_bytes",
            ):
                violations.append(f"{path.name}: .{func.attr}(...)")
            if isinstance(func, ast.Name) and func.id == "open":
                mode_arg = None
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    mode_arg = node.args[1].value
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode_arg = kw.value.value
                if isinstance(mode_arg, str) and ("w" in mode_arg or "a" in mode_arg):
                    violations.append(f"{path.name}: open(..., mode={mode_arg!r})")
    assert not violations, f"runtime write primitives found: {violations}"
