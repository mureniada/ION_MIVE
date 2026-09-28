"""VOE G2 Stage B (B1) — offline tests for `scripts/voe_g2_stage_b_real_gemini.py`.

No test here makes a provider call, constructs the real `GeminiBackend`, or
reads a real credential: every environment is an explicit dict of dummy
values, and every backend is a fake injected through `backend_factory`.
Tests that run a turn run under `netguard`'s `guarded` decorator (cloud SDK
imports and outbound sockets denied, provider credentials removed).
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from app.modules.ive_common import GenerationResult
from app.modules.telemetry import PricingTable
from scripts import voe_g2_stage_b_real_gemini as harness
from scripts.task21_governed_turn import discover_repo_root, read_repository_head
from tests.netguard import guarded

HARNESS_SOURCE = Path(harness.__file__).read_text(encoding="utf-8")
REPO_ROOT = discover_repo_root(Path(harness.__file__).resolve().parent)

DUMMY_KEY = "dummy-offline-test-value-not-a-credential-0123456789"
PRICED_MODEL = "gemini-3.1-flash-lite"


def _env(**overrides):
    env = {"GEMINI_API_KEY": DUMMY_KEY, "GEMINI_MODEL": PRICED_MODEL}
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


class _FakeGeminiBackend:
    """Stands in for `GeminiBackend`: same constructor and `generate` shape."""

    def __init__(self, model, *, mode="success", echo=None):
        self.model = model
        self.mode = mode
        self.echo = echo
        self.calls = 0

    def generate(self, *, system, user, schema):
        self.calls += 1
        if self.mode == "raise":
            raise RuntimeError("fake provider failure")
        abstract = json.loads(user)["abstract"]
        text = "Composed (fake): " + abstract + (self.echo or "")
        if self.mode == "no_usage":
            return GenerationResult(text=json.dumps({"composed_text": text}), usage_is_estimated=True)
        return GenerationResult(
            text=json.dumps({"composed_text": text}),
            input_tokens=5200,
            output_tokens=300,
            usage_is_estimated=False,
        )


class _Factory:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.built = []

    def __call__(self, model):
        backend = _FakeGeminiBackend(model, **self.kwargs)
        self.built.append(backend)
        return backend


@pytest.fixture
def ready(monkeypatch):
    """SDK locatable and a clean tree, without touching either for real."""
    monkeypatch.setattr(harness, "_sdk_probe", lambda: True)
    monkeypatch.setattr(harness, "read_worktree_status", lambda repo_root: "")
    return read_repository_head(REPO_ROOT)


def _run(head, factory, env=None, **kwargs):
    return harness.run_stage_b(
        env=env or _env(), expected_head=head, run_id="test", backend_factory=factory, **kwargs
    )


# --------------------------------------------------------------------- #
# Environment preflight (booleans only)
# --------------------------------------------------------------------- #
def test_environment_passes_with_one_credential_and_a_priced_model(monkeypatch):
    monkeypatch.setattr(harness, "_sdk_probe", lambda: True)
    check = harness.check_environment(_env())
    assert check.problems == []
    assert check.model_priced is True
    assert check.credential_header_safe is True


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"GOOGLE_API_KEY": DUMMY_KEY}, "both GEMINI_API_KEY and GOOGLE_API_KEY"),
        ({"GEMINI_API_KEY": None}, "neither GEMINI_API_KEY nor GOOGLE_API_KEY"),
        ({"OPENAI_API_KEY": DUMMY_KEY}, "OPENAI_API_KEY is present"),
        ({"GEMINI_MODEL": None}, "GEMINI_MODEL is not present"),
        ({"GEMINI_MODEL": " " + PRICED_MODEL}, "whitespace"),
        ({"GEMINI_MODEL": "gemini-unpriced-model"}, "not priced"),
        ({"GEMINI_API_KEY": "has space"}, "not header-safe"),
    ],
)
def test_environment_problems_are_refused(monkeypatch, overrides, fragment):
    monkeypatch.setattr(harness, "_sdk_probe", lambda: True)
    problems = harness.check_environment(_env(**overrides)).problems
    assert any(fragment in p for p in problems), problems


def test_unpriced_model_is_allowed_only_when_explicitly_allowed(monkeypatch):
    monkeypatch.setattr(harness, "_sdk_probe", lambda: True)
    check = harness.check_environment(_env(GEMINI_MODEL="gemini-unpriced-model"), allow_unpriced_model=True)
    assert check.problems == []
    assert check.model_priced is False


@guarded
def test_missing_sdk_is_a_preflight_problem():
    # Under netguard the SDK import is denied, so the probe reports it absent.
    assert "google-genai SDK is not locatable (google.genai)" in harness.check_environment(_env()).problems


def test_environment_report_never_contains_a_value(monkeypatch):
    monkeypatch.setattr(harness, "_sdk_probe", lambda: True)
    check = harness.check_environment(_env(GOOGLE_API_KEY=DUMMY_KEY))
    serialized = json.dumps({"report": check.to_receipt(), "problems": check.problems})
    assert DUMMY_KEY not in serialized
    assert PRICED_MODEL not in serialized


# --------------------------------------------------------------------- #
# Committed-blob source identity (D2)
# --------------------------------------------------------------------- #
def test_committed_blob_matches_the_approved_sha_and_the_working_copy_is_untouched():
    readme = REPO_ROOT / "corpus" / "README.md"
    before = (readme.stat().st_mtime_ns, hashlib.sha256(readme.read_bytes()).hexdigest())

    blob = harness.read_committed_source_blob(REPO_ROOT)

    assert hashlib.sha256(blob).hexdigest() == harness.APPROVED_SOURCE_SHA256
    assert b"\r" not in blob
    assert (readme.stat().st_mtime_ns, hashlib.sha256(readme.read_bytes()).hexdigest()) == before


@guarded
def test_source_mismatch_aborts_without_constructing_a_backend(ready, monkeypatch):
    monkeypatch.setattr(harness, "APPROVED_SOURCE_SHA256", "0" * 64)
    factory = _Factory()
    receipt = _run(ready, factory)
    assert receipt["outcome"] == harness.OUTCOME_ABORTED
    assert receipt["source"]["matches_approved"] is False
    assert factory.built == []


# --------------------------------------------------------------------- #
# Repository gates
# --------------------------------------------------------------------- #
@guarded
def test_dirty_tree_aborts_without_constructing_a_backend(ready, monkeypatch):
    monkeypatch.setattr(harness, "read_worktree_status", lambda repo_root: "?? stray.txt\n")
    factory = _Factory()
    receipt = _run(ready, factory)
    assert receipt["outcome"] == harness.OUTCOME_ABORTED
    assert "working tree is not clean" in receipt["preflight_problems"]
    assert factory.built == []


@guarded
def test_head_mismatch_aborts_without_constructing_a_backend(ready):
    factory = _Factory()
    receipt = _run("0" * 40, factory)
    assert receipt["outcome"] == harness.OUTCOME_ABORTED
    assert "HEAD does not equal the expected HEAD" in receipt["preflight_problems"]
    assert factory.built == []


@guarded
def test_environment_problem_aborts_without_constructing_a_backend(ready):
    factory = _Factory()
    receipt = _run(ready, factory, env=_env(OPENAI_API_KEY=DUMMY_KEY))
    assert receipt["outcome"] == harness.OUTCOME_ABORTED
    assert receipt["real_provider_executed"] is False
    assert receipt["execution_counts"] == {"real_provider_calls_forwarded": 0}
    assert factory.built == []


# --------------------------------------------------------------------- #
# The B1 turn with a fake backend
# --------------------------------------------------------------------- #
@guarded
def test_b1_success_path_forwards_exactly_one_call(ready):
    factory = _Factory()
    receipt = _run(ready, factory)

    assert receipt["outcome"] == harness.OUTCOME_PASS
    assert receipt["variant"] == "B1"
    assert all(receipt["checks"].values()), receipt["checks"]
    assert len(factory.built) == 1 and factory.built[0].calls == 1
    assert factory.built[0].model == PRICED_MODEL
    counts = receipt["execution_counts"]
    assert counts["real_provider_calls_forwarded"] == 1
    assert counts["composer_generate_attempts"] == 1
    assert counts["ive_engine"] == 1 and counts["ive_engine_provider"] == "CONTROLLED_FAKE"
    assert counts["openai"] == 0 and counts["mive"] == 0
    assert receipt["composition"]["status"] == "COMPOSED"
    assert receipt["composition"]["provider"] == "gemini"
    assert receipt["composition"]["estimated_cost"] == PricingTable().estimate_cost(PRICED_MODEL, 5200, 300)
    assert receipt["source"]["identity_basis"] == "COMMITTED_BLOB_AT_HEAD"
    assert receipt["human_review"]["status"] == "PENDING"


@guarded
def test_fake_backend_is_never_reported_as_a_real_provider_execution(ready):
    receipt = _run(ready, _Factory())
    assert receipt["composer_backend_class"] == "_FakeGeminiBackend"
    assert receipt["real_provider_executed"] is False


@guarded
def test_backend_failure_is_a_safe_fallback(ready):
    receipt = _run(ready, _Factory(mode="raise"))
    assert receipt["outcome"] == harness.OUTCOME_SAFE_FAIL
    assert receipt["composition"]["status"] == "FALLBACK_PROVIDER_ERROR"
    assert receipt["answers"]["primary_answer_replaced"] is False
    assert receipt["execution_counts"]["real_provider_calls_forwarded"] == 1


@guarded
def test_unreported_usage_fails_the_automated_checks(ready):
    receipt = _run(ready, _Factory(mode="no_usage"))
    assert receipt["outcome"] == harness.OUTCOME_CHECK_FAILED
    assert receipt["checks"]["tokens_reported"] is False
    assert receipt["checks"]["usage_not_estimated"] is False


@guarded
def test_a_receipt_containing_a_credential_value_is_withheld(ready):
    with pytest.raises(harness.SecretLeakError):
        _run(ready, _Factory(echo=DUMMY_KEY))


# --------------------------------------------------------------------- #
# The one-call limit
# --------------------------------------------------------------------- #
def test_one_call_wrapper_never_forwards_a_second_call():
    real = _FakeGeminiBackend(PRICED_MODEL)
    wrapper = harness.OneCallComposerBackend(real)
    payload = json.dumps({"abstract": "a"})
    wrapper.generate(system="s", user=payload, schema={})

    with pytest.raises(harness.ProviderCallBudgetExceeded):
        wrapper.generate(system="s", user=payload, schema={})
    assert real.calls == 1
    assert wrapper.forwarded_count == 1
    assert wrapper.attempt_count == 2


# --------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------- #
@guarded
def test_default_mode_is_preflight_only_and_never_constructs_a_backend(ready, capsys):
    factory = _Factory()
    exit_code = harness.main(["--expected-head", ready], env=_env(), backend_factory=factory)
    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["mode"] == "PREFLIGHT_ONLY"
    assert report["provider_call_made"] is False
    assert factory.built == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--execute-one-real-call"],
        ["--execute-one-real-call", "--expected-head", "abc"],
        ["--execute-one-real-call", "--receipt", "r.json"],
    ],
)
def test_execute_requires_expected_head_and_receipt(argv):
    with pytest.raises(SystemExit) as excinfo:
        harness.main(argv, env=_env(), backend_factory=_Factory())
    assert excinfo.value.code == 2


@guarded
def test_execute_writes_the_receipt(ready, tmp_path, capsys):
    receipt_path = tmp_path / "receipt.json"
    exit_code = harness.main(
        ["--execute-one-real-call", "--expected-head", ready, "--receipt", str(receipt_path), "--run-id", "t"],
        env=_env(),
        backend_factory=_Factory(),
    )
    capsys.readouterr()
    written = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert written["run_id"] == "t"
    assert written["outcome"] == harness.OUTCOME_PASS
    assert DUMMY_KEY not in receipt_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("flag", ["--question", "--variant", "--repeat", "--retries", "--model"])
def test_cli_offers_no_scope_changing_switch(flag):
    with pytest.raises(SystemExit) as excinfo:
        harness.main([flag, "x"], env=_env(), backend_factory=_Factory())
    assert excinfo.value.code == 2


# --------------------------------------------------------------------- #
# Static isolation
# --------------------------------------------------------------------- #
def _imported_module_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize(
    "prefix", ["app.container", "app.modules.openai_ive", "qdrant_client", "openai", "google"]
)
def test_harness_imports_no_other_provider_or_store(prefix):
    for name in _imported_module_names(HARNESS_SOURCE):
        assert not (name == prefix or name.startswith(prefix + ".")), name


def test_harness_constructs_no_real_ive_engine():
    called = {
        node.func.id
        for node in ast.walk(ast.parse(HARNESS_SOURCE))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "GeminiIVE" not in called
    assert "ControlledDeterministicEngine" in called
