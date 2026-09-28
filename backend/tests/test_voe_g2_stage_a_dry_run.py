"""VOE G2 Stage A — tests for the controlled, network-free composed-turn harness
(`scripts/voe_g2_stage_a_dry_run.py`).

Every test that runs a turn runs under `netguard`'s `guarded` decorator:
cloud SDK imports and outbound sockets are denied and provider credentials
are removed, so a pass here is itself evidence that Stage A made no provider
call. The VOE profile is the real, committed, hash-pinned bundle, loaded
through the real `Settings` -> `resolve_voe_profile` path.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest

from app.modules.voe_profile import (
    EXPECTED_PROFILE_ID,
    EXPECTED_PROFILE_VERSION,
    EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256,
    RUNTIME_BEHAVIORAL_FILES,
    VOEProfileLoadError,
)
from scripts import voe_g2_stage_a_dry_run as harness
from tests.netguard import guarded
from tests.voe_pack import COMMITTED_VOE_PACK_DIR

HARNESS_SOURCE = Path(harness.__file__).read_text(encoding="utf-8")


# --------------------------------------------------------------------- #
# The three composer modes, end to end
# --------------------------------------------------------------------- #
@guarded
def test_success_mode_composes_under_the_real_profile():
    obs = harness.run_voe_dry_turn(composer_mode="success")

    assert obs.composition["status"] == "COMPOSED"
    assert obs.final_primary_answer == harness.COMPOSED_TEXT_PREFIX + obs.base_primary_answer
    assert obs.composition["provider"] == "CONTROLLED_FAKE"
    assert obs.composition["model"] == harness.FAKE_COMPOSER_MODEL
    assert obs.composition["input_tokens"] is None
    assert obs.composition["output_tokens"] is None
    assert obs.composition["estimated_cost"] is None
    assert obs.ive_engine_execution_count == 1
    assert obs.composer_backend_generate_count == 1
    assert obs.openai_execution_count == 0
    assert obs.mive_execution_count == 0
    assert obs.turn_record_model_execution_count == 1
    assert obs.turn_record_closure_state == "COMPLETED"
    assert all(obs.checks.values())


@guarded
def test_provider_error_mode_falls_back_to_the_deterministic_answer():
    obs = harness.run_voe_dry_turn(composer_mode="provider_error")

    assert obs.composition["status"] == "FALLBACK_PROVIDER_ERROR"
    assert obs.final_primary_answer == obs.base_primary_answer
    assert obs.composition["provider"] is None
    assert obs.composition["latency_ms"] is None
    assert obs.composer_backend_generate_count == 1
    assert obs.ask_result_status == "success"


@guarded
def test_malformed_output_mode_falls_back_to_the_deterministic_answer():
    obs = harness.run_voe_dry_turn(composer_mode="malformed_output")

    assert obs.composition["status"] == "FALLBACK_MALFORMED_OUTPUT"
    assert obs.final_primary_answer == obs.base_primary_answer
    assert obs.composer_backend_generate_count == 1
    assert obs.ask_result_status == "success"


def test_unknown_composer_mode_is_rejected_before_any_turn():
    with pytest.raises(ValueError, match="unknown composer mode"):
        harness.run_voe_dry_turn(composer_mode="real")


# --------------------------------------------------------------------- #
# The real VOE profile loading path
# --------------------------------------------------------------------- #
@guarded
def test_profile_identity_is_the_pinned_committed_bundle():
    obs = harness.run_voe_dry_turn(composer_mode="success")

    assert obs.voe_profile_id == EXPECTED_PROFILE_ID
    assert obs.voe_profile_version == EXPECTED_PROFILE_VERSION
    assert obs.voe_runtime_behavioral_fingerprint_sha256 == EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256
    assert obs.voe_bundle_dir == "backend/app/modules/voe_profile/assets"
    assert harness.committed_voe_bundle_dir() == COMMITTED_VOE_PACK_DIR.resolve()


@guarded
def test_profile_is_resolved_through_settings_with_voe_enabled(monkeypatch):
    calls = []
    real_resolve = harness.resolve_voe_profile

    def spying_resolve(*, enabled, bundle_dir):
        calls.append((enabled, bundle_dir))
        return real_resolve(enabled=enabled, bundle_dir=bundle_dir)

    monkeypatch.setattr(harness, "resolve_voe_profile", spying_resolve)
    harness.run_voe_dry_turn(composer_mode="success")

    assert calls == [(True, str(COMMITTED_VOE_PACK_DIR.resolve()))]


def test_settings_are_built_from_an_explicit_dict_not_the_environment(monkeypatch):
    monkeypatch.setenv("VOE_PROFILE_ENABLED", "false")
    monkeypatch.setenv("VOE_PROFILE_BUNDLE_DIR", "/nowhere")
    settings = harness.build_voe_enabled_settings(COMMITTED_VOE_PACK_DIR)

    assert settings.voe_profile_enabled is True
    assert settings.voe_profile_bundle_dir == str(COMMITTED_VOE_PACK_DIR)


@guarded
def test_tampered_bundle_fails_closed_before_any_turn(tmp_path):
    for filename, _, _ in RUNTIME_BEHAVIORAL_FILES:
        shutil.copyfile(COMMITTED_VOE_PACK_DIR / filename, tmp_path / filename)
    target = tmp_path / RUNTIME_BEHAVIORAL_FILES[0][0]
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(VOEProfileLoadError):
        harness.run_voe_dry_turn(composer_mode="success", bundle_dir=tmp_path)


@guarded
def test_missing_bundle_file_fails_closed_before_any_turn(tmp_path):
    for filename, _, _ in RUNTIME_BEHAVIORAL_FILES[1:]:
        shutil.copyfile(COMMITTED_VOE_PACK_DIR / filename, tmp_path / filename)

    with pytest.raises(VOEProfileLoadError, match="missing"):
        harness.run_voe_dry_turn(composer_mode="success", bundle_dir=tmp_path)


# --------------------------------------------------------------------- #
# What the composer received
# --------------------------------------------------------------------- #
@guarded
def test_composer_received_only_the_approved_projection():
    obs = harness.run_voe_dry_turn(composer_mode="success")

    assert obs.composer_user_payload_keys == sorted(
        ["question", "abstract", "highlights", "claims", "uncertainty", "confidence"]
    )
    assert obs.composer_system_instruction_characters > 0
    assert len(obs.composer_system_instruction_sha256) == 64


def test_controlled_backend_refuses_a_second_call():
    backend = harness.ControlledComposerBackend("success")
    payload = json.dumps({"abstract": "a"})
    backend.generate(system="s", user=payload, schema={})

    with pytest.raises(RuntimeError, match="more than once"):
        backend.generate(system="s", user=payload, schema={})


# --------------------------------------------------------------------- #
# Receipt
# --------------------------------------------------------------------- #
@guarded
def test_receipt_states_a_controlled_run_and_carries_no_credential_name():
    obs = harness.run_voe_dry_turn(composer_mode="success")
    receipt = harness.build_receipt(obs, run_id="test-run")

    assert receipt["receipt_schema_id"] == "ION_VOE_G2_STAGE_A_DRY_RECEIPT_V0_1"
    assert receipt["stage"] == "VOE_G2_STAGE_A"
    assert receipt["provider_execution"] == "CONTROLLED_FAKE"
    assert receipt["real_provider_executed"] is False
    assert receipt["credentials_read"] is False
    assert receipt["observed_composition_status"] == receipt["expected_composition_status"]
    assert receipt["answers"]["primary_answer_replaced"] is True
    assert all(receipt["checks"].values())
    assert "API_KEY" not in json.dumps(receipt)


@guarded
def test_main_writes_a_parseable_receipt(tmp_path, capsys):
    receipt_path = tmp_path / "receipt.json"
    exit_code = harness.main(
        ["--composer-mode", "malformed_output", "--run-id", "t", "--receipt", str(receipt_path)]
    )

    assert exit_code == 0
    written = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert written["run_id"] == "t"
    assert written["observed_composition_status"] == "FALLBACK_MALFORMED_OUTPUT"
    assert json.loads(capsys.readouterr().out) == written


@pytest.mark.parametrize("flag", ["--real", "--live", "--provider"])
def test_cli_offers_no_real_provider_switch(flag):
    with pytest.raises(SystemExit) as excinfo:
        harness.main([flag])
    assert excinfo.value.code == 2


# --------------------------------------------------------------------- #
# Static isolation
# --------------------------------------------------------------------- #
_FORBIDDEN_IMPORT_PREFIXES = (
    "app.container",
    "app.modules.gemini_ive",
    "app.modules.openai_ive",
    "qdrant_client",
    "openai",
    "google",
)


def _imported_module_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_harness_imports_no_network_capable_module():
    for name in _imported_module_names(HARNESS_SOURCE):
        assert not any(
            name == prefix or name.startswith(prefix + ".") for prefix in _FORBIDDEN_IMPORT_PREFIXES
        ), name


def test_harness_never_reads_the_process_environment():
    assert "os" not in _imported_module_names(HARNESS_SOURCE)
    attribute_names = {
        node.attr for node in ast.walk(ast.parse(HARNESS_SOURCE)) if isinstance(node, ast.Attribute)
    }
    assert not attribute_names & {"environ", "getenv"}
