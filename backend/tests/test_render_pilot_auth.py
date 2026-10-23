"""Render pilot: fail-closed bearer-token gate (`ION_PILOT_API_TOKEN`), docs
routes removed, `/health` public, and the DEBUG-gated stream still 404.

The `check_bearer` tests need no web framework. Transport tests are skipped
where FastAPI/httpx are absent, like `test_transport_api.py`. The startup tests
launch the real app in a fresh interpreter with no secrets configured. No live
provider calls anywhere.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from app.api import auth
from tests.util import PILOT_TEST_TOKEN

BACKEND_DIR = Path(__file__).resolve().parent.parent
GOOD = {"Authorization": f"Bearer {PILOT_TEST_TOKEN}"}
WRONG = {"Authorization": "Bearer " + "x" * len(PILOT_TEST_TOKEN)}
CONFIGURED = {auth.TOKEN_ENV: PILOT_TEST_TOKEN}


# --------------------------------------------------------------------- #
# check_bearer: pure decision, no framework.
# --------------------------------------------------------------------- #
def test_unset_empty_or_short_token_config_refuses_everything():
    for env in ({}, {auth.TOKEN_ENV: ""}, {auth.TOKEN_ENV: "   "},
                {auth.TOKEN_ENV: "s" * (auth.MIN_TOKEN_LENGTH - 1)}):
        presented = env.get(auth.TOKEN_ENV, "")
        for header in (None, "", f"Bearer {presented}", GOOD["Authorization"]):
            refused = auth.check_bearer(header, env)
            assert refused is not None, (env, header)
            assert refused[0] == 503
            assert refused[1]["error_stage"] == "not_ready"


def test_missing_or_malformed_header_is_401():
    for header in (None, "", "Bearer", "Bearer   ", PILOT_TEST_TOKEN,
                   f"Basic {PILOT_TEST_TOKEN}", f"Token {PILOT_TEST_TOKEN}"):
        refused = auth.check_bearer(header, CONFIGURED)
        assert refused is not None and refused[0] == 401, header
        assert refused[1]["error_stage"] == "unauthorized"


def test_wrong_token_is_401_including_prefix_and_same_length():
    for presented in ("x" * len(PILOT_TEST_TOKEN), PILOT_TEST_TOKEN[:-1],
                      PILOT_TEST_TOKEN + "x", PILOT_TEST_TOKEN.upper()):
        refused = auth.check_bearer(f"Bearer {presented}", CONFIGURED)
        assert refused is not None and refused[0] == 401, presented


def test_configured_token_is_accepted_case_insensitive_scheme():
    for header in (f"Bearer {PILOT_TEST_TOKEN}", f"bearer {PILOT_TEST_TOKEN}",
                   f"  BEARER {PILOT_TEST_TOKEN}  "):
        assert auth.check_bearer(header, CONFIGURED) is None, header
    # Surrounding whitespace in the configured value is not part of the token.
    assert auth.check_bearer(GOOD["Authorization"],
                             {auth.TOKEN_ENV: f"  {PILOT_TEST_TOKEN}\n"}) is None


def test_comparison_goes_through_hmac_compare_digest():
    with mock.patch.object(auth.hmac, "compare_digest", wraps=auth.hmac.compare_digest) as spy:
        assert auth.check_bearer(GOOD["Authorization"], CONFIGURED) is None
        assert auth.check_bearer(WRONG["Authorization"], CONFIGURED) is not None
    assert spy.call_count == 2


def test_refusals_never_echo_either_token():
    presented = "presented-" + "q" * 40
    for env in ({}, CONFIGURED):
        refused = auth.check_bearer(f"Bearer {presented}", env)
        text = repr(refused)
        assert presented not in text
        assert PILOT_TEST_TOKEN not in text


# --------------------------------------------------------------------- #
# Transport: the gate as mounted in app.main.
# --------------------------------------------------------------------- #
def _client():
    if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx") is None:
        raise unittest.SkipTest("fastapi/httpx not installed (present in the Docker image)")
    from fastapi.testclient import TestClient

    import app.main as main
    return TestClient(main.app)


def _guarded(monkeypatch, *, token=PILOT_TEST_TOKEN, debug=None):
    """Configure the token/DEBUG env and make any core construction or
    readiness call observable (and fatal to the test if reached)."""
    import app.main as main

    if token is None:
        monkeypatch.delenv(auth.TOKEN_ENV, raising=False)
    else:
        monkeypatch.setenv(auth.TOKEN_ENV, token)
    if debug is None:
        monkeypatch.delenv("DEBUG", raising=False)
    else:
        monkeypatch.setenv("DEBUG", debug)
    get_core = mock.Mock(side_effect=AssertionError("core must not be built"))
    get_controller = mock.Mock(side_effect=AssertionError("controller must not be built"))
    ready = mock.Mock(side_effect=AssertionError("readiness must not be checked"))
    monkeypatch.setattr(main, "_get_core", get_core)
    monkeypatch.setattr(main, "_get_session_controller", get_controller)
    monkeypatch.setattr(main, "require_ready", ready)
    return get_core, get_controller, ready


def test_health_is_public_and_needs_no_token_config(monkeypatch):
    client = _client()
    get_core, _, ready = _guarded(monkeypatch, token=None)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    get_core.assert_not_called()
    ready.assert_not_called()


def test_docs_routes_are_not_mounted(monkeypatch):
    client = _client()
    _guarded(monkeypatch)
    for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        assert client.get(path).status_code == 404, path
        assert client.get(path, headers=GOOD).status_code == 404, path
    import app.main as main
    assert main.app.openapi_url is None
    assert main.app.docs_url is None
    assert main.app.redoc_url is None


def test_ask_without_token_config_is_refused_before_core(monkeypatch):
    client = _client()
    get_core, _, ready = _guarded(monkeypatch, token=None)
    resp = client.post("/ask", json={"question": "what is money?"}, headers=GOOD)
    assert resp.status_code == 503
    assert resp.json()["error_stage"] == "not_ready"
    get_core.assert_not_called()
    ready.assert_not_called()


def test_ask_with_empty_token_config_is_refused(monkeypatch):
    client = _client()
    _guarded(monkeypatch, token="")
    resp = client.post("/ask", json={"question": "what is money?"}, headers={"Authorization": "Bearer "})
    assert resp.status_code == 503


def test_ask_without_or_with_wrong_token_is_401_before_validation_and_core(monkeypatch):
    client = _client()
    get_core, _, ready = _guarded(monkeypatch)
    for headers in ({}, WRONG, {"Authorization": f"Basic {PILOT_TEST_TOKEN}"}):
        # An invalid body too: auth must answer first, not validation.
        resp = client.post("/ask", json={"question": "  "}, headers=headers)
        assert resp.status_code == 401, headers
        assert resp.headers["www-authenticate"] == "Bearer"
        assert resp.json()["error_stage"] == "unauthorized"
        assert PILOT_TEST_TOKEN not in resp.text
    get_core.assert_not_called()
    ready.assert_not_called()


def test_ask_with_valid_token_reaches_request_validation(monkeypatch):
    client = _client()
    get_core, _, _ = _guarded(monkeypatch)
    resp = client.post("/ask", json={"question": "  "}, headers=GOOD)
    assert resp.status_code == 400
    assert resp.json()["error_stage"] == "invalid_request"
    get_core.assert_not_called()


def test_ask_stream_stays_404_without_debug_whatever_the_auth(monkeypatch):
    client = _client()
    for token in (None, PILOT_TEST_TOKEN):
        get_core, _, ready = _guarded(monkeypatch, token=token)
        for headers in ({}, WRONG, GOOD):
            # Malformed query parameters too: no 422 may leak the route.
            for params in ({"question": "q"}, {}, {"question": "q", "top_k": "abc"}):
                resp = client.get("/ask/stream", params=params, headers=headers)
                assert resp.status_code == 404, (token, headers, params)
        get_core.assert_not_called()
        ready.assert_not_called()


def test_ask_stream_with_debug_validates_parameters_after_auth(monkeypatch):
    client = _client()
    get_core, _, _ = _guarded(monkeypatch, debug="true")
    for params in ({}, {"question": "  "}, {"question": "q", "top_k": "abc"},
                   {"question": "q", "top_k": "0"}):
        resp = client.get("/ask/stream", params=params, headers=GOOD)
        assert resp.status_code == 400, params
        assert resp.json()["error_stage"] == "invalid_request"
    get_core.assert_not_called()


def test_ask_stream_with_debug_still_requires_the_token(monkeypatch):
    client = _client()
    get_core, _, _ = _guarded(monkeypatch, debug="true")
    resp = client.get("/ask/stream", params={"question": "q"})
    assert resp.status_code == 401
    resp = client.get("/ask/stream", params={"question": "q"}, headers=WRONG)
    assert resp.status_code == 401
    get_core.assert_not_called()
    _guarded(monkeypatch, token=None, debug="true")
    resp = client.get("/ask/stream", params={"question": "q"}, headers=GOOD)
    assert resp.status_code == 503


def test_pilot_session_routes_require_the_token(monkeypatch):
    client = _client()
    get_core, get_controller, _ = _guarded(monkeypatch)
    for path, body in (("/pilot/sessions", None),
                       ("/pilot/sessions/s-1/turn", {"question": "What is ION?"}),
                       ("/pilot/sessions/s-1/close", None)):
        for headers in ({}, WRONG):
            resp = client.post(path, json=body, headers=headers)
            assert resp.status_code == 401, (path, headers)
    get_core.assert_not_called()
    get_controller.assert_not_called()


def test_every_route_except_health_is_gated(monkeypatch):
    """A route added later without the gate fails here, not in production."""
    from fastapi.routing import APIRoute

    import app.main as main
    client = _client()
    _guarded(monkeypatch, debug="true")
    routes = [r for r in main.app.routes if isinstance(r, APIRoute)]
    assert {r.path for r in routes} >= {"/health", "/ask", "/ask/stream", "/pilot/sessions"}
    for route in routes:
        if route.path == "/health":
            continue
        path = route.path.replace("{session_id}", "s-1")
        for method in route.methods:
            resp = client.request(method, path, params={"question": "q"}, json={"question": "q"})
            assert resp.status_code == 401, (method, route.path, resp.status_code)


# --------------------------------------------------------------------- #
# Startup: the real app in a fresh interpreter, no secrets configured.
# --------------------------------------------------------------------- #
_SECRET_LIKE = ("GEMINI_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "VECTOR_STORE_API_KEY",
                "DEBUG", auth.TOKEN_ENV)


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in _SECRET_LIKE}
    env.update(extra)
    return env


def test_app_imports_with_no_secrets_and_no_token():
    proc = subprocess.run(
        [sys.executable, "-c",
         "import app.main as m; print(m.app.openapi_url, m.app.docs_url, m.app.redoc_url)"],
        cwd=BACKEND_DIR, env=_clean_env(), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["None", "None", "None"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url, headers=None, method="GET", body=None):
    req = urllib.request.Request(url, headers=headers or {}, method=method, data=body)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _serve(env):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"server exited early: {proc.stdout.read()}")
        try:
            if _get(base + "/health") == 200:
                return proc, base
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.25)
    proc.kill()
    raise AssertionError("server did not become healthy")


def _stop(proc) -> str:
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    return out or ""


def test_served_app_fails_closed_without_token_config():
    if importlib.util.find_spec("uvicorn") is None:
        raise unittest.SkipTest("uvicorn not installed (present in the Docker image)")
    proc, base = _serve(_clean_env())
    try:
        ask = b'{"question": "what is money?"}'
        assert _get(base + "/health") == 200
        assert _get(base + "/ask", GOOD, "POST", ask) == 503
        assert _get(base + "/ask", {}, "POST", ask) == 503
        assert _get(base + "/pilot/sessions", GOOD, "POST", b"{}") == 503
        assert _get(base + "/ask/stream?question=q", GOOD) == 404
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert _get(base + path) == 404, path
    finally:
        _stop(proc)


def test_served_app_gates_on_token_and_never_logs_it():
    if importlib.util.find_spec("uvicorn") is None:
        raise unittest.SkipTest("uvicorn not installed (present in the Docker image)")
    proc, base = _serve(_clean_env(**{auth.TOKEN_ENV: PILOT_TEST_TOKEN}))
    try:
        assert _get(base + "/ask", {}, "POST", b'{"question": "q"}') == 401
        assert _get(base + "/ask", WRONG, "POST", b'{"question": "q"}') == 401
        # Valid token, invalid body: past the gate, refused by validation,
        # before any core construction or provider work.
        assert _get(base + "/ask", GOOD, "POST", b'{"question": "  "}') == 400
        assert _get(base + "/ask/stream?question=q", GOOD) == 404
    finally:
        log = _stop(proc)
    assert "/ask" in log  # the access log was captured at all
    assert PILOT_TEST_TOKEN not in log
    assert WRONG["Authorization"].split()[1] not in log
