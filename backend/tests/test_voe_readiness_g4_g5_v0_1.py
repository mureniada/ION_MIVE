"""G4 + G5: VOE readiness at the HTTP transport.

G4 — a malformed `VOE_PROFILE_ENABLED` is a controlled not-ready state:
`/ask` and the pilot routes return 503 JSON `not_ready` with a fixed message
(never the malformed value, never a traceback), `/ask/stream` stays hidden
with 404 because DEBUG cannot be confirmed, `/health` stays 200, and nothing
is cached, so a corrected setting recovers without a restart.

G5 — a Core composed while the VOE bundle was invalid is cached without a
composer. Once the bundle becomes valid, readiness must still fail closed
(503, restart required) instead of answering uncomposed; the cached Core is
never rebuilt or mutated.

Offline only: `TestClient` in-process, fake embedder, inert vector store URL,
no provider key except a dummy string where readiness must reach the VOE
check. No test reaches `Core.ask()`.
"""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.core.orchestrator import Core
from app.modules.voe_profile import load_voe_runtime_profile
from app.modules.voe_profile.loader import RUNTIME_BEHAVIORAL_FILES
from tests.voe_pack import COMMITTED_VOE_PACK_DIR

SENTINEL = "maybe-G4-SENTINEL-7f3a"
FIXED_MESSAGE = "Invalid runtime configuration (values never shown)."

_CLEARED_ENV = (
    "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "DEBUG", "VOE_PROFILE_ENABLED", "VOE_PROFILE_BUNDLE_DIR",
    "EXECUTION_PROFILE", "EMBEDDING_BACKEND", "GEMINI_MODEL", "OPENAI_MODEL",
    "VECTOR_STORE_URL",
)


@pytest.fixture
def client(monkeypatch):
    for name in _CLEARED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EXECUTION_PROFILE", "STANDARD_GEMINI")
    monkeypatch.setenv("EMBEDDING_BACKEND", "fake")
    monkeypatch.setenv("GEMINI_MODEL", "g4g5-test-model")
    monkeypatch.setenv("VECTOR_STORE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(main, "_STATE", {})
    return TestClient(main.app, raise_server_exceptions=False)


def _assert_controlled_not_ready(response):
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body == {"status": "error", "error_stage": "not_ready", "message": FIXED_MESSAGE}
    assert SENTINEL not in response.text
    assert "Traceback" not in response.text
    assert "VOE_PROFILE_ENABLED" not in response.text


# --------------------------------------------------------------------- #
# G4
# --------------------------------------------------------------------- #
def test_g4_malformed_flag_gives_controlled_503_on_ask_and_pilot_routes(client, monkeypatch):
    monkeypatch.setenv("VOE_PROFILE_ENABLED", SENTINEL)
    _assert_controlled_not_ready(client.post("/ask", json={"question": "q"}))
    _assert_controlled_not_ready(client.post("/pilot/sessions"))
    _assert_controlled_not_ready(client.post("/pilot/sessions/abc/turn", json={"question": "q"}))
    _assert_controlled_not_ready(client.post("/pilot/sessions/abc/close"))
    assert main._STATE == {}


@pytest.mark.parametrize("debug", ["false", "true"])
def test_g4_malformed_flag_keeps_stream_hidden_with_404(client, monkeypatch, debug):
    monkeypatch.setenv("VOE_PROFILE_ENABLED", SENTINEL)
    monkeypatch.setenv("DEBUG", debug)
    response = client.get("/ask/stream", params={"question": "q"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert SENTINEL not in response.text
    assert main._STATE == {}


def test_g4_malformed_flag_leaves_health_ok(client, monkeypatch):
    monkeypatch.setenv("VOE_PROFILE_ENABLED", SENTINEL)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_g4_corrected_flag_recovers_without_restart(client, monkeypatch):
    monkeypatch.setenv("VOE_PROFILE_ENABLED", SENTINEL)
    _assert_controlled_not_ready(client.post("/ask", json={"question": "q"}))
    assert main._STATE == {}

    monkeypatch.setenv("VOE_PROFILE_ENABLED", "false")
    response = client.post("/ask", json={"question": "q"})
    # Past the settings error, into the normal readiness gate: no key is set.
    assert response.status_code == 503
    body = response.json()
    assert body["error_stage"] == "not_ready"
    assert body["message"].startswith("Missing required configuration")


# --------------------------------------------------------------------- #
# G5
# --------------------------------------------------------------------- #
def _enable_voe_with_empty_bundle(monkeypatch, bundle_dir):
    monkeypatch.setenv("VOE_PROFILE_ENABLED", "true")
    monkeypatch.setenv("VOE_PROFILE_BUNDLE_DIR", str(bundle_dir))
    # Dummy, non-credential value: only so readiness reaches the VOE check.
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-not-a-credential")


def _fill_bundle(bundle_dir):
    for name, _, _ in RUNTIME_BEHAVIORAL_FILES:
        shutil.copyfile(COMMITTED_VOE_PACK_DIR / name, bundle_dir / name)


def test_g5_late_valid_bundle_fails_closed_until_restart(client, monkeypatch, tmp_path):
    _enable_voe_with_empty_bundle(monkeypatch, tmp_path)

    first = client.post("/ask", json={"question": "q"})
    assert first.status_code == 503
    assert first.json()["error_stage"] == "not_ready"
    assert "failed to load" in first.json()["message"]

    core = main._STATE["core"]
    assert core.voe_runtime_profile is None
    assert core._composer is None

    _fill_bundle(tmp_path)

    second = client.post("/ask", json={"question": "q"})
    assert second.status_code == 503
    assert second.json()["error_stage"] == "not_ready"
    assert "composed without it" in second.json()["message"]
    assert "restart" in second.json()["message"]
    assert "dummy-not-a-credential" not in second.text

    # Never rebuilt, never mutated.
    assert main._STATE["core"] is core
    assert core._composer is None
    assert core.voe_runtime_profile is None


def test_g5_late_valid_bundle_fails_closed_on_pilot_turn(client, monkeypatch, tmp_path):
    _enable_voe_with_empty_bundle(monkeypatch, tmp_path)
    assert client.post("/ask", json={"question": "q"}).status_code == 503
    core = main._STATE["core"]

    _fill_bundle(tmp_path)

    response = client.post("/pilot/sessions/abc/turn", json={"question": "q"})
    assert response.status_code == 503
    assert response.json()["error_stage"] == "not_ready"
    assert "composed without it" in response.json()["message"]
    assert main._STATE["core"] is core
    assert core._composer is None


def test_g5_core_voe_runtime_profile_is_read_only():
    profile = load_voe_runtime_profile(COMMITTED_VOE_PACK_DIR)
    core = Core.__new__(Core)
    core._voe_runtime_profile = profile
    assert core.voe_runtime_profile is profile
    with pytest.raises(AttributeError):
        core.voe_runtime_profile = None
    assert core.voe_runtime_profile is profile
