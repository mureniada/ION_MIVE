"""Offline tests for voe_h2_ab_harness.py (H2 IVE thinking budget 1280, paired IVE A/B). ZERO provider calls.

Sockets are blocked in every test. The provider is a fake that tells the arms
apart only by the request itself (arm B is the request that carries a thinking
config), so arm identity, order and prompt identity are checked on what was
actually sent. One test drives the REAL google-genai 2.28.0 client through an
httpx MockTransport and diffs the two HTTP request bodies.

The turn path is the REAL repository code: Core.ask (with the repo's own
stand-ins from tests/test_core_voe_composition_v0_1.py for retrieval and
governance), ModelGateway, GeminiIVE adapter, GeminiBackend, ive_common, the
H1 Step 0 capture, and the frozen E3 tap, classifier and Phase A orchestrator,
each loaded by sha256.

Run from the repository's backend/ directory with:
    H1_TEST_E3_HARNESS   frozen voe_e3_paired_replay.py   (1134c4f6...65c7)
    H1AB_TEST_CLASSIFIER frozen voe_e3_index17_probe.py   (2b63a7e3...ecb6)
    H1AB_TEST_PA         frozen voe_e3_pa_reconfirm.py    (7f242c00...207c)
    python -m pytest -q -p no:cacheprovider scripts/h2/tests/test_h2_ab_harness.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import platform
import socket
import sys
import uuid
from types import SimpleNamespace

import httpx
import pytest
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

for _var in ("H1_TEST_E3_HARNESS", "H1AB_TEST_CLASSIFIER", "H1AB_TEST_PA"):
    if _var not in os.environ:
        pytest.skip(f"{_var} is not set", allow_module_level=True)

H2_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_PATH = os.path.join(H2_DIR, "voe_h2_ab_harness.py")
CAPTURE_PATH = os.path.join(os.path.dirname(H2_DIR), "h1", "voe_h1_ive_capture.py")   # H1 Step 0, by sha256
SCORER_PATH = os.path.join(H2_DIR, "h2_ab_score.py")
E3_HARNESS_PATH = os.environ["H1_TEST_E3_HARNESS"]
CLASSIFIER_PATH = os.environ["H1AB_TEST_CLASSIFIER"]
PA_PATH = os.environ["H1AB_TEST_PA"]
MODEL = "gemini-2.5-pro"
REAL_CLIENT = genai.Client
QUESTIONS = [f"Question {i}: what does The Works say about ION?" for i in range(27)]
# Identity checks this checkout cannot pass (older VOE bundle, synthetic questions).
CHECKOUT_FAILS = ["s0_fingerprint_ok", "s0_profile_version", "s0_questions_sha256", "s0_system_instruction_ok"]


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*_a, **_k):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


class FakeProvider:
    """Scripted per arm. The arm is read from the request: B carries a thinking config."""

    def __init__(self, clock):
        self.script = {"A": [], "B": []}
        self.latency_s = {"A": 24.0, "B": 23.0}
        self.seen = []
        self.clock = clock

    def generate_content(self, *, model, contents, config):
        arm = "B" if config.thinking_config is not None else "A"
        self.seen.append({"arm": arm, "model": model, "contents": contents, "config": config})
        self.clock.t += self.latency_s[arm]
        if not self.script[arm]:
            raise AssertionError(f"unexpected extra provider call for arm {arm}")
        item = self.script[arm].pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def e(monkeypatch):
    import app.modules.gemini_ive.adapter as gadapter
    import app.modules.gemini_ive.backend as gbm

    monkeypatch.setattr(gbm.GeminiBackend, "_ensure", gbm.GeminiBackend._ensure)
    monkeypatch.setattr(gbm.GeminiBackend, "generate", gbm.GeminiBackend.generate)
    monkeypatch.setattr(gadapter.GeminiIVE, "run", gadapter.GeminiIVE.run)
    tag = uuid.uuid4().hex[:8]
    hm = _load(f"h2ab_{tag}", HARNESS_PATH)
    cap = hm.load_by_path(f"h1cap_{tag}", CAPTURE_PATH, hm.EXPECTED_CAPTURE_SHA256)
    harness = cap.load_by_path(f"e3h_{tag}", E3_HARNESS_PATH, cap.EXPECTED_HARNESS_SHA256)
    runner = hm.load_by_path(f"e3c_{tag}", CLASSIFIER_PATH, hm.EXPECTED_CLASSIFIER_SHA256)
    pa = hm.load_by_path(f"e3pa_{tag}", PA_PATH, hm.EXPECTED_PA_SHA256)
    scorer = _load(f"h2abs_{tag}", SCORER_PATH)
    cap.MAX_IVE_CALLS = hm.MAX_IVE_CALLS
    clock = FakeClock()
    monkeypatch.setattr(harness, "time", SimpleNamespace(monotonic=clock.monotonic))  # the tap's SDK clock
    provider = FakeProvider(clock)
    clients = []

    def client(*_a, **_k):
        clients.append(SimpleNamespace(models=provider))
        return clients[-1]

    monkeypatch.setattr(genai, "Client", client)
    return SimpleNamespace(hm=hm, cap=cap, harness=harness, runner=runner, pa=pa, scorer=scorer, gbm=gbm,
                           gadapter=gadapter, provider=provider, mp=monkeypatch, sleeps=[], clients=clients)


# --------------------------------------------------------------------- #
# payloads and responses
# --------------------------------------------------------------------- #
def payload(i, *, concepts=5, relations=6, claim_ids=("EV-1",), rel_ids=("EV-1",), unc=("Origins debated.",)):
    return {
        "abstract": f"Abstract {i}: money as “credit” — {{braces}} and \"quotes\".",
        "highlights": [f"H{i}a", "Ünïcödé highlight ✓"],
        "claims": [{"claim_id": "c1", "statement": f"Claim {i}: ION’s role", "evidence_document_ids": list(claim_ids),
                    "confidence": 0.8}],
        "concepts": [{"name": f"Concept {k}", "description": "a “wavelet”"} for k in range(concepts)],
        "relations": [{"source": "ION", "relation": f"r{k}", "target": "nature",
                       "evidence_document_ids": list(rel_ids)} for k in range(relations)],
        "uncertainty": list(unc),
        "confidence": 0.7,
    }


def response(body, *, prompt=3100, visible=1400, thoughts=1700, rid="resp"):
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[
            types.Part(text="private reasoning summary", thought=True), types.Part(text=text)]))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt, candidates_token_count=visible,
            thoughts_token_count=thoughts, total_token_count=prompt + visible + thoughts),
        response_id=rid)


def api_error(code, status):
    return genai_errors.APIError(code, {"error": {"code": code, "message": "scripted", "status": status}})


def script_ok(e, n=81, *, start=0):
    e.provider.script["A"].extend(response(payload(i)) for i in range(start, start + n))
    e.provider.script["B"].extend(response(payload(i), visible=1300, thoughts=1000)
                                  for i in range(start, start + n))


# --------------------------------------------------------------------- #
# world
# --------------------------------------------------------------------- #
def make_core(e, *, engine=None):
    from tests.test_core_voe_composition_v0_1 import _RecordingComposer, _core, _patch_gate, _voe_profile
    from app.modules.gemini_ive.adapter import GeminiIVE
    from app.modules.model_gateway import ModelGateway

    composer = _RecordingComposer()
    composer._backend = e.gbm.GeminiBackend(MODEL, telemetry_label="composer", thinking_budget=512)
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    _patch_gate(e.mp)
    engine = engine or GeminiIVE(e.gbm.GeminiBackend(MODEL, telemetry_label="ive"), model=MODEL)
    core._model_gateway = ModelGateway({"gemini": engine})
    return core, composer


def make_info(e, core):
    import app.core.orchestrator as orch
    import app.modules.ive_common as ic

    backend = e.cap._dig(core, "_model_gateway", "_engines", "gemini", "_backend")
    return {
        "google_genai_version": genai.__version__, "python_version": platform.python_version(),
        "file_sha256": {name: e.cap.sha256_file(mod.__file__) for name, mod in (
            ("orchestrator", orch), ("gemini_backend", e.gbm), ("gemini_adapter", e.gadapter), ("ive_common", ic))},
        "ive_system_prompt": e.cap.text_digest(ic.IVE_SYSTEM_PROMPT),
        "ive_response_schema": e.cap.schema_digest(ic.IVE_RESPONSE_SCHEMA),
        "ive_backend_label": e.cap._dig(backend, "_telemetry_label"),
        "ive_backend_thinking_budget": e.cap._dig(backend, "_thinking_budget"),
        "core_class_composer_mentions": inspect.getsource(type(core)).count("self._composer"),
    }


def app_ns():
    import app.modules.ive_common as ic
    from app.core.errors import NormalizationError, ProviderError
    from app.core.models import Usage

    return SimpleNamespace(ic=ic, ProviderError=ProviderError, NormalizationError=NormalizationError,
                           Usage=Usage, APIError=genai_errors.APIError)


def wire(e, *, engine=None, questions=QUESTIONS, **over):
    from app.modules.execution_profile import STANDARD_GEMINI

    core, composer = make_core(e, engine=engine)
    e.harness.install_tap(e.gbm)
    e.cap.install_capture(e.gbm, e.harness)
    h = e.harness
    kw = dict(
        harness=h, gbm=e.gbm,
        settings=SimpleNamespace(gemini_model=MODEL, voe_composer_thinking_budget=512),
        profile=STANDARD_GEMINI, core=core,
        runtime_profile=SimpleNamespace(binding=SimpleNamespace(
            profile_version="0.4", runtime_behavioral_fingerprint_sha256=h.EXPECTED_FINGERPRINT)),
        system_sha=h.EXPECTED_SYSTEM_SHA256, questions=questions,
        questions_sha256=e.cap.EXPECTED_QUESTIONS_SHA256, deployment_id=e.cap.EXPECTED_DEPLOYMENT_ID,
        sources={"core_ask": inspect.getsource(type(core).ask), "core_class": inspect.getsource(type(core)),
                 "gemini_backend_module": inspect.getsource(e.gbm)},
        info=make_info(e, core))
    kw.update(over)
    world = e.cap.World(**kw)
    step0 = e.cap.start_checks(world)
    d, checks = e.hm.assemble(world, e.cap, e.runner, e.pa, e.scorer, e.gadapter, step0, app_ns())
    d.sleep = e.sleeps.append
    return d, checks, composer


def run(e, d, checks, tmp_path, name="out"):
    out = str(tmp_path / name)
    S = e.hm.run_programme(d, e.hm.build_meta(d, checks, "prereg-under-test"), out)
    lines = open(os.path.join(out, "h2ab_ledger.jsonl"), encoding="utf-8").read().splitlines()
    parsed = [(ln.split(" ", 1)[0], json.loads(ln.split(" ", 1)[1])) for ln in lines]
    return S, parsed, os.path.join(out, "h2ab_ledger.jsonl")


def attempts(parsed):
    return [obj for tag, obj in parsed if tag == "H2AB_ATTEMPT"]


def expected_arm_sequence(keys):
    """The preregistered order, re-derived here: slots alternate AB, BA, ... in run order."""
    seq = []
    for p, i in keys:
        seq.extend("AB" if ((p - 1) * 27 + i) % 2 == 0 else "BA")
    return seq


ALL_KEYS = [(p, i) for p in range(1, 4) for i in range(27)]


# --------------------------------------------------------------------- #
# identity and start checks
# --------------------------------------------------------------------- #
def test_frozen_modules_load_only_by_sha(e, tmp_path):
    for path, sha in ((CAPTURE_PATH, e.hm.EXPECTED_CAPTURE_SHA256), (CLASSIFIER_PATH, e.hm.EXPECTED_CLASSIFIER_SHA256),
                      (PA_PATH, e.hm.EXPECTED_PA_SHA256)):
        bad = tmp_path / os.path.basename(path)
        bad.write_bytes(open(path, "rb").read() + b"\n")
        with pytest.raises(e.hm.H2ABStop):
            e.hm.load_by_path(f"bad_{uuid.uuid4().hex[:6]}", str(bad), sha)


def test_scorer_sha_is_pinned_in_the_harness(e):
    assert e.hm.EXPECTED_SCORER_SHA256 == _sha(SCORER_PATH)


def test_start_checks_pass_with_zero_provider_calls(e):
    d, checks, composer = wire(e)
    assert all(checks.values()), [k for k, v in checks.items() if not v]
    assert len([k for k in checks if k.startswith("s0_")]) == 19 and len(checks) == 19 + 19
    assert checks["plan_81_pairs"] and e.hm.MAX_IVE_CALLS == e.scorer.SCHEDULED_PAIRS * 2 * 2 == 324
    assert checks["arm_b_budget_1280"] and checks["arm_b_backend_differs_only_in_budget"]
    assert checks["schema_b_is_the_module_schema"] and checks["margins_set"]
    assert e.provider.seen == [] and e.harness.CALLS == [] and e.cap.CAPTURES == [] and composer.calls == []


def test_start_checks_fail_closed_on_identity(e, monkeypatch):
    import app.modules.ive_common as ic

    d, checks, _ = wire(e, deployment_id="other")
    assert [k for k, v in checks.items() if not v] == ["s0_deployment_id"]
    e.cap.MAX_IVE_CALLS = 27
    assert e.hm.ab_start_checks(d)["ive_call_cap"] is False
    e.cap.MAX_IVE_CALLS = e.hm.MAX_IVE_CALLS
    monkeypatch.setattr(ic, "IVE_SYSTEM_PROMPT", ic.IVE_SYSTEM_PROMPT + " Keep concepts short.")
    d.world.info = make_info(e, d.core)
    failing = [k for k, v in e.hm.ab_start_checks(d).items() if not v]
    assert failing == ["ive_system_prompt"]                    # a prompt change cannot slip through
    d.world.info["file_sha256"] = dict(d.world.info["file_sha256"], ive_common="0" * 64)
    assert e.hm.ab_start_checks(d)["source_files"] is False


def test_a_mutated_module_schema_fails_the_checks(e, monkeypatch):
    import app.modules.ive_common as ic

    mutated = json.loads(json.dumps(ic.IVE_RESPONSE_SCHEMA))
    mutated["properties"]["concepts"]["maxItems"] = 3
    monkeypatch.setattr(ic, "IVE_RESPONSE_SCHEMA", mutated)
    d, checks, _ = wire(e)
    bad = {k for k, v in checks.items() if not v}
    assert {"schema_a_sha", "schema_a_has_no_caps"} <= bad


def test_arm_b_budget_identity_fails_the_checks(e):
    d, checks, _ = wire(e)
    e.scorer.THINKING_BUDGET_B = 1024              # the wrapper was installed with 1280
    bad = {k for k, v in e.hm.ab_start_checks(d).items() if not v}
    assert bad == {"arm_b_budget_1280", "arm_b_backend_differs_only_in_budget"}


def test_a_deployed_ive_thinking_budget_fails_the_checks_and_stops_the_run(e, tmp_path):
    """If the deployed IVE already had a thinking budget, arm A would not be the baseline."""
    from app.modules.gemini_ive.adapter import GeminiIVE

    script_ok(e, 2)
    engine = GeminiIVE(e.gbm.GeminiBackend(MODEL, telemetry_label="ive", thinking_budget=512), model=MODEL)
    d, checks, _ = wire(e, engine=engine)
    bad = {k for k, v in checks.items() if not v}
    assert {"ive_backend_no_thinking_budget", "arm_b_backend_differs_only_in_budget"} <= bad
    S, parsed, ledger = run(e, d, checks, tmp_path)      # even if forced to run, the guard stops it
    assert S["status"] == "STOPPED_HARNESS_GUARD" and len(attempts(parsed)) == 1
    assert "thinking config not as preregistered" in S["stop_reason"]
    assert e.scorer.score(ledger)["verdict"]["sub_reason"] == "HARNESS_INTEGRITY"


def test_arm_b_is_a_copy_that_differs_only_in_the_budget(e):
    d, _, _ = wire(e)
    backend = d.cap._dig(d.core, "_model_gateway", "_engines", "gemini", "_backend")
    b = d.wiring.arm_b_backend(backend)
    assert b is not backend and type(b) is type(backend) and backend._thinking_budget is None
    assert b._thinking_budget == 1280 and b._telemetry_label == backend._telemetry_label == "ive"
    assert b._model == backend._model == MODEL


def test_build_deps_wiring_on_repo_code(e, monkeypatch, tmp_path):
    """The real container path (build_deps -> build_world), with only build_core
    swapped for the stand-in Core. This checkout carries an older VOE bundle and
    synthetic questions, so exactly those Step 0 identity checks fail."""
    import app.container as container
    from tests.voe_pack import COMMITTED_VOE_PACK_DIR

    core, _ = make_core(e)
    monkeypatch.setattr(container, "build_core", lambda settings: core)
    for k, v in {"GEMINI_MODEL": MODEL, "EXECUTION_PROFILE": "STANDARD_GEMINI", "VOE_PROFILE_ENABLED": "true",
                 "VOE_PROFILE_BUNDLE_DIR": str(COMMITTED_VOE_PACK_DIR), "VOE_COMPOSER_THINKING_BUDGET": "512"}.items():
        monkeypatch.setenv(k, v)
    qfile = tmp_path / "q.json"
    qfile.write_text(json.dumps(QUESTIONS), encoding="utf-8")
    env = {"H1_E3_HARNESS_PATH": E3_HARNESS_PATH, "H1_QUESTIONS_PATH": str(qfile),
           "H2AB_CAPTURE_PATH": CAPTURE_PATH, "H2AB_CLASSIFIER_PATH": CLASSIFIER_PATH, "H2AB_PA_PATH": PA_PATH,
           "H2AB_SCORER_PATH": SCORER_PATH, "RAILWAY_DEPLOYMENT_ID": e.cap.EXPECTED_DEPLOYMENT_ID}
    d, checks = e.hm.build_deps(env)
    assert sorted(k for k, v in checks.items() if not v) == CHECKOUT_FAILS
    assert d.cap.MAX_IVE_CALLS == 324 and d.harness.CALLS == [] and e.provider.seen == [] and e.clients == []
    meta = e.hm.build_meta(d, checks, "p")
    assert meta["schema_b_sha256"] == meta["schema_a_sha256"] == e.scorer.EXPECTED_SCHEMA_A_SHA256
    assert meta["thinking_budget_b"] == 1280 and meta["planned"]["pairs"] == 81
    assert meta["planned"]["passes"] == 3 and meta["planned"]["max_ive_calls"] == 324


def test_dry_run_through_main_and_real_wiring_fails_closed_with_zero_calls(e, monkeypatch, capsys, tmp_path):
    """The zero-call dry run exactly as main() runs it in the container (env vars,
    prereg check, build_deps -> build_world on this checkout), with only build_core
    swapped for the stand-in Core. This checkout is not the deployed e6880e7 bundle
    and the questions are synthetic, so the preflight must refuse on exactly those
    identity checks, before any provider call and before any output exists."""
    import app.container as container
    from tests.voe_pack import COMMITTED_VOE_PACK_DIR

    core, _ = make_core(e)
    monkeypatch.setattr(container, "build_core", lambda settings: core)
    qfile = tmp_path / "q.json"
    qfile.write_text(json.dumps(QUESTIONS), encoding="utf-8")
    prereg = tmp_path / "prereg.md"
    prereg.write_text("frozen", encoding="utf-8")
    for k, v in {"GEMINI_MODEL": MODEL, "EXECUTION_PROFILE": "STANDARD_GEMINI", "VOE_PROFILE_ENABLED": "true",
                 "VOE_PROFILE_BUNDLE_DIR": str(COMMITTED_VOE_PACK_DIR), "VOE_COMPOSER_THINKING_BUDGET": "512",
                 "H1_E3_HARNESS_PATH": E3_HARNESS_PATH, "H1_QUESTIONS_PATH": str(qfile),
                 "H2AB_CAPTURE_PATH": CAPTURE_PATH, "H2AB_CLASSIFIER_PATH": CLASSIFIER_PATH, "H2AB_PA_PATH": PA_PATH,
                 "H2AB_SCORER_PATH": SCORER_PATH, "RAILWAY_DEPLOYMENT_ID": e.cap.EXPECTED_DEPLOYMENT_ID,
                 "H2AB_PREREG_PATH": str(prereg), "H2AB_PREREG_SHA256": _sha(str(prereg)),
                 "H2AB_PREFLIGHT_ONLY": "1", "H2AB_OUT_DIR": str(tmp_path / "out")}.items():
        monkeypatch.setenv(k, v)
    assert e.hm.main() == 2
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("H2AB_STOP ")
    stop = json.loads(lines[0].split(" ", 1)[1])
    assert stop["provider_calls"] == 0 and stop["reason"].startswith("start checks failed")
    failed = sorted(json.loads(stop["reason"].split(": ", 1)[1].replace("'", '"')))
    assert failed == CHECKOUT_FAILS
    assert e.provider.seen == [] and e.clients == [] and not (tmp_path / "out").exists()


def test_main_preflight_only_and_stops(e, monkeypatch, capsys, tmp_path):
    d, checks, _ = wire(e)
    monkeypatch.setattr(e.hm, "build_deps", lambda _env: (d, checks))
    prereg = tmp_path / "prereg.md"
    prereg.write_text("frozen", encoding="utf-8")
    monkeypatch.setenv("H2AB_PREREG_PATH", str(prereg))
    monkeypatch.setenv("H2AB_PREREG_SHA256", _sha(str(prereg)))
    monkeypatch.setenv("H2AB_PREFLIGHT_ONLY", "1")
    monkeypatch.setenv("H2AB_OUT_DIR", str(tmp_path / "out"))
    assert e.hm.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("H2AB_PREFLIGHT ") and '"provider_calls": 0' in out
    meta = json.loads(out.split(" ", 1)[1])["meta"]
    assert meta["prereg_sha256"] == _sha(str(prereg)) and meta["schema_b"] == meta["schema_a"]
    assert meta["thinking_budget_b"] == 1280 and meta["scorer_sha256"] == _sha(SCORER_PATH)
    assert not (tmp_path / "out").exists()
    monkeypatch.setenv("H2AB_PREREG_SHA256", "0" * 64)
    assert e.hm.main() == 2 and capsys.readouterr().out.startswith("H2AB_STOP ")
    monkeypatch.setenv("H2AB_PREREG_SHA256", _sha(str(prereg)))
    # the output directory is checked before any wiring: unset, or already there (an earlier run)
    for out_dir in ("", str(tmp_path)):
        monkeypatch.setenv("H2AB_OUT_DIR", out_dir)
        assert e.hm.main() == 2 and "H2AB_OUT_DIR" in capsys.readouterr().out
    monkeypatch.delenv("H2AB_OUT_DIR")
    assert e.hm.main() == 2 and "H2AB_OUT_DIR" in capsys.readouterr().out
    monkeypatch.setenv("H2AB_OUT_DIR", str(tmp_path / "out"))
    checks["s0_deployment_id"] = False
    assert e.hm.main() == 2 and "s0_deployment_id" in capsys.readouterr().out
    assert e.provider.seen == [] and e.harness.CALLS == []


# --------------------------------------------------------------------- #
# what is sent
# --------------------------------------------------------------------- #
def test_wire_requests_differ_only_by_the_thinking_budget(e, monkeypatch):
    """Real google-genai client, real HTTP serialization, no network. Arm B shares
    arm A's client, so the two requests differ in exactly one field."""
    import app.modules.ive_common as ic

    bodies, clients = [], []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        bodies.append({"url": str(request.url), "method": request.method, "body": body,
                       "headers": {k: v for k, v in request.headers.items() if k.lower() != "content-length"}})
        text = json.dumps(payload(0))
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 7,
                              "totalTokenCount": 22}, "responseId": "r"})

    def client(*_a, **_k):
        clients.append(REAL_CLIENT(api_key="offline-test-key", http_options=types.HttpOptions(
            httpx_client=httpx.Client(transport=httpx.MockTransport(handler)))))
        return clients[-1]

    monkeypatch.setattr(genai, "Client", client)
    d, checks, _ = wire(e)
    for index in (0, 1):
        row, turn_exc, live = e.hm.run_pair(d, index, QUESTIONS[index], 1, "primary")
        assert turn_exc is None and row["a_parity"] is True
        assert row["order"] == ("AB" if index == 0 else "BA")
    assert len(bodies) == 4 and len(clients) == 1
    for k in (0, 2):
        first, second = bodies[k], bodies[k + 1]
        a, b = (first, second) if k == 0 else (second, first)      # pair 2 ran B first
        # google-genai 2.28.0 writes the inner field as thinking_budget, exactly as the deployed
        # composer's budget-512 requests (which demonstrably bound thinking in E3) are written
        assert e.scorer.json_diff(a["body"], b["body"]) == [
            ("added", "/generationConfig/thinkingConfig", {"thinking_budget": 1280})]
        assert a["url"] == b["url"] and a["url"].endswith(f"/models/{MODEL}:generateContent")
        assert a["method"] == b["method"] == "POST" and a["headers"] == b["headers"]
        assert "thinkingConfig" not in a["body"]["generationConfig"]
        assert a["body"]["generationConfig"]["responseJsonSchema"] == json.loads(json.dumps(ic.IVE_RESPONSE_SCHEMA))


def test_full_run_81_pairs_two_ive_calls_each_and_no_composer(e, tmp_path):
    import app.modules.ive_common as ic

    script_ok(e)
    e.provider.latency_s["B"] = 21.0
    d, checks, composer = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    assert S["status"] == "COMPLETE" and S["scored_pairs"] == 81 and S["replacements"] == 0
    assert S["provider_calls"] == 162 and S["ive_calls_attempted"] == 162 and S["hard_fail_pairs"] == 0
    assert [t for t, _ in parsed] == ["H2AB_META"] + ["H2AB_ATTEMPT"] * 81 + ["H2AB_SUMMARY"]
    assert parsed[0][1]["composer_detached"] is True and composer.calls == [] and d.core._composer is None
    assert parsed[0][1]["thinking_budget_b"] == 1280 and len(e.clients) == 1      # one shared SDK client
    seen = e.provider.seen
    assert [s["arm"] for s in seen] == expected_arm_sequence(ALL_KEYS)
    orders = [att["order"] for att in attempts(parsed)]
    assert orders[26:29] == ["AB", "BA", "AB"] and orders.count("AB") == 41 and orders.count("BA") == 40
    for k in range(0, 162, 2):
        x, y = seen[k], seen[k + 1]
        assert x["contents"] == y["contents"] and x["model"] == y["model"] == MODEL
        assert x["config"].system_instruction == y["config"].system_instruction == ic.IVE_SYSTEM_PROMPT
        assert x["config"].response_json_schema == y["config"].response_json_schema == ic.IVE_RESPONSE_SCHEMA
        for s in (x, y):
            tc = s["config"].thinking_config
            assert (tc is None) if s["arm"] == "A" else (tc.thinking_budget == 1280 and tc.include_thoughts is None)
    for att in attempts(parsed):
        a, b = att["arms"]["A"], att["arms"]["B"]
        assert att["order"] == att["expected_order"] and att["a_parity"] is True and att["hard_fail_events"] == []
        assert a["status"] == b["status"] == "OK" and att["model_input"]["allowed_ids"] == ["EV-1"]
        assert a["input"]["user"] == b["input"]["user"] and a["input"]["system"] == b["input"]["system"]
        assert a["input"]["schema"]["sha256"] == e.scorer.EXPECTED_SCHEMA_A_SHA256
        assert b["input"]["schema"]["sha256"] == e.scorer.EXPECTED_SCHEMA_B_SHA256
        assert a["tap"][0]["sdk_latency_ms"] == 24000.0 and b["tap"][0]["sdk_latency_ms"] == 21000.0
        assert a["tap"][0]["thinking_config_sent"] is False and a["tap"][0]["thinking_budget_sent"] is None
        assert b["tap"][0]["thinking_config_sent"] is True and b["tap"][0]["thinking_budget_sent"] == 1280
        assert b["tap"][0]["thoughts_tokens"] == 1000 and a["tap"][0]["thoughts_tokens"] == 1700
        assert len(b["report"]["concepts"]) == 5 and len(a["report"]["relations"]) == 6
        assert att["composition_attempted"] is False and att["other_calls"] == []
    assert e.scorer.sha256_text(e.scorer.canonical(ic.IVE_RESPONSE_SCHEMA)) == e.scorer.EXPECTED_SCHEMA_A_SHA256
    with pytest.raises(FileExistsError):
        e.hm.run_programme(d, {}, os.path.dirname(ledger))
    # the offline scorer reads this ledger as written
    r = e.scorer.score(ledger)
    assert r["integrity"]["ok"] and r["run"]["complete"] and r["hard_fail"]["pairs"] == 0
    assert r["latency"]["mean_improvement_ms"] == 3000.0 and r["latency"]["state"] == "MATERIAL"
    assert r["latency"]["median_improvement_ms"] == 3000.0
    assert r["thinking"]["b_over_budget"] == 0 and r["tokens"]["thinking"]["delta_b_minus_a"]["mean"] == -700
    assert r["verdict"] == {"label": "PASS", "step": 7}


def test_the_turn_is_the_unchanged_baseline_turn(e):
    """Arm A's report is what the Core returns; arm B never reaches the Core."""
    script_ok(e, 1)
    d, _, _ = wire(e)
    e.hm.reset_pair(0, "AB")
    e.harness.CURRENT["index"] = 0
    result = d.core.ask(QUESTIONS[0])
    (report,) = result.ive_reports
    assert len(report["concepts"]) == 5 and len(report["relations"]) == 6
    assert json.loads(report["raw_response"]) == payload(0)


# --------------------------------------------------------------------- #
# provider faults: frozen classification and whole-pair replacement
# --------------------------------------------------------------------- #
def test_b_provider_fault_replaces_the_whole_pair_after_30_s(e, tmp_path):
    script_ok(e, 82)
    e.provider.script["B"][0] = api_error(503, "UNAVAILABLE")
    d, checks, _ = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    atts = attempts(parsed)
    assert S["status"] == "COMPLETE" and S["replacements"] == 1 and S["scored_pairs"] == 81
    assert e.sleeps == [30.0] and S["provider_calls"] == 164
    assert atts[0]["invalidated"] is True and atts[1]["kind"] == "replacement" and atts[1]["order"] == "AB"
    assert atts[0]["classification"]["arms"]["B"]["class_key"] == "HTTP|503|UNAVAILABLE"
    assert [f["who"] for f in S["provider_faults"]] == ["B"]
    assert [s["arm"] for s in e.provider.seen][:4] == ["A", "B", "A", "B"]
    r = e.scorer.score(ledger)
    assert r["run"]["replacements"] == 1 and r["run"]["scored_pairs"] == 81 and r["integrity"]["ok"]
    assert r["run"]["provider_fault_calls_by_arm"] == {"A": 0, "B": 1}


def test_a_provider_fault_fails_the_turn_and_replaces_the_pair(e, tmp_path):
    script_ok(e, 82)
    e.provider.script["A"][1] = api_error(429, "RESOURCE_EXHAUSTED")      # index 1 runs B first
    d, checks, _ = wire(e)
    S, parsed, _ = run(e, d, checks, tmp_path)
    atts = attempts(parsed)
    assert S["status"] == "COMPLETE" and S["replacements"] == 1
    bad = atts[1]
    assert bad["order"] == "BA" and bad["invalidated"] and bad["error"] == "ProviderError"
    assert bad["classification"]["turn"]["classification"] == "PROVIDER_FAULT"
    assert bad["classification"]["arms"]["A"]["class_key"] == "HTTP|429|RESOURCE_EXHAUSTED"
    assert bad["a_parity"] is True and bad["arms"]["B"]["status"] == "OK"   # B ran first and is kept


def test_a_second_fault_leaves_the_pair_unresolved(e, tmp_path):
    script_ok(e, 82)
    e.provider.script["B"][0] = httpx.ConnectError("no route")
    e.provider.script["B"][1] = api_error(500, "INTERNAL")
    d, checks, _ = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    assert S["status"] == "COMPLETE" and S["unresolved"] == [{"pass": 1, "index": 0}] and S["scored_pairs"] == 80
    assert [f["class_key"] for f in S["provider_faults"]] == ["TRANSPORT|httpx.ConnectError", "HTTP|500|INTERNAL"]
    r = e.scorer.score(ledger)
    assert r["run"]["unresolved"] == [{"pass": 1, "index": 0}] and r["run"]["complete"]


@pytest.mark.parametrize("faults, calls, unresolved, pending", [
    ({"A": [0, 1], "B": [0]}, 4, [0], []),     # A,B fault, then A faults again: 3 in a row
    ({"B": [0, 2, 4, 6]}, 14, [], [3]),        # 4 faults within 20 calls; slot 3 never got its replacement
])
def test_provider_health_stops_the_run(e, tmp_path, faults, calls, unresolved, pending):
    script_ok(e, 90)
    for arm, positions in faults.items():
        for pos in positions:
            e.provider.script[arm][pos] = api_error(503, "UNAVAILABLE")
    d, checks, _ = wire(e)
    S, _, ledger = run(e, d, checks, tmp_path)
    assert S["status"] == "INCONCLUSIVE_PROVIDER_HEALTH" and S["provider_calls"] == calls
    r = e.scorer.score(ledger)
    assert r["verdict"]["sub_reason"] == "PROVIDER_HEALTH"
    assert r["run"]["unresolved"] == S["unresolved"] == [{"pass": 1, "index": i} for i in unresolved]
    assert r["run"]["pending"] == [{"pass": 1, "index": i} for i in pending]


def test_read_timeout_is_not_a_provider_fault(e, tmp_path):
    script_ok(e)
    e.provider.script["B"][5] = httpx.ReadTimeout("slow")
    d, checks, _ = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    att = attempts(parsed)[5]
    assert S["status"] == "COMPLETE" and S["replacements"] == 0 and att["invalidated"] is False
    assert att["arms"]["B"]["status"] == "CALL_FAILED"
    assert att["classification"]["arms"]["B"]["class_key"] == "PROVIDER_WRAPPED|httpx.ReadTimeout"
    assert att["hard_fail_events"] == [{"code": "G1", "detail": "B CALL_FAILED: PROVIDER_WRAPPED|httpx.ReadTimeout"}]
    r = e.scorer.score(ledger)
    assert r["verdict"] == {"label": "FAIL", "sub_reason": "HARD_GATE", "step": 2, "codes": {"G1": 1}}


# --------------------------------------------------------------------- #
# stop rules and hard-fail events
# --------------------------------------------------------------------- #
def test_a_non_provider_failure_stops_the_run(e, tmp_path):
    script_ok(e, 3)
    e.provider.script["A"][2] = response("this is not json")
    d, checks, _ = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    att = attempts(parsed)[-1]
    assert S["status"] == "INCONCLUSIVE_IVE_OR_TURN_NON_PROVIDER_FAILURE" and len(attempts(parsed)) == 3
    assert att["classification"]["turn"]["class_key"] == "PROVIDER_WRAPPED|app.core.errors.NormalizationError"
    assert att["a_parity"] is True and att["arms"]["A"]["status"] == "INVALID_OUTPUT"
    assert S["provider_calls"] == 6
    assert e.scorer.score(ledger)["verdict"]["sub_reason"] == "IVE_OR_TURN_NON_PROVIDER_FAILURE"


@pytest.mark.parametrize("arm, status", [("A", "INCONCLUSIVE_IVE_OR_TURN_NON_PROVIDER_FAILURE"),
                                         ("B", "STOPPED_HTTP_402")])
def test_http_402_stops_the_run(e, tmp_path, arm, status):
    script_ok(e, 2)
    e.provider.script[arm][1] = api_error(402, "PAYMENT_REQUIRED")
    d, checks, _ = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    assert S["status"] == status and len(attempts(parsed)) == 2 and S["provider_calls"] == 4
    assert attempts(parsed)[-1]["hard_fail_events"] == [] and S["hard_fail_pairs"] == 0
    r = e.scorer.score(ledger)
    # not a fault under the frozen allowlist (no replacement), and an account state, not arm-B behaviour
    assert r["verdict"] == {"label": "INCONCLUSIVE", "sub_reason": "HTTP_402", "step": 1,
                            "hard_fail_pairs_before_stop": 0}


def test_invalid_b_output_is_g1_and_the_run_continues(e, tmp_path):
    script_ok(e)
    e.provider.script["B"][7] = response('{"abstract": "cut off')
    d, checks, _ = wire(e)
    S, parsed, _ = run(e, d, checks, tmp_path)
    att = attempts(parsed)[7]
    assert S["status"] == "COMPLETE" and S["hard_fail_pairs"] == 1
    assert att["arms"]["B"]["status"] == "INVALID_OUTPUT" and att["arms"]["B"]["normalize_error"]
    assert att["hard_fail_events"][0]["code"] == "G1"


def test_schema_invalid_b_output_is_g2_and_three_in_a_row_stop(e, tmp_path):
    script_ok(e, 5)
    e.provider.script["B"][:] = [response({**payload(i), "extra": 1}) for i in range(5)]
    d, checks, _ = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    assert S["status"] == "STOPPED_SYSTEMATIC_B_HARD_FAIL" and S["provider_calls"] == 6
    assert attempts(parsed)[0]["arms"]["B"]["status"] == "OK"        # the app's normalizer accepted it
    assert attempts(parsed)[0]["hard_fail_events"] == [{"code": "G2", "detail": "EXTRA_PROPERTY /extra"}]
    r = e.scorer.score(ledger)
    assert r["verdict"]["label"] == "FAIL" and r["verdict"]["codes"] == {"G2": 3}


def test_b_attribution_defects_are_g3_only_when_a_is_clean(e, tmp_path):
    script_ok(e)
    e.provider.script["B"][3] = response(payload(3, rel_ids=("EV-9",)))
    e.provider.script["A"][4] = response(payload(4, rel_ids=("EV-9",)))
    e.provider.script["B"][4] = response(payload(4, rel_ids=("EV-9",)))
    e.provider.script["B"][6] = response(payload(6, claim_ids=()))
    d, checks, _ = wire(e)
    S, parsed, _ = run(e, d, checks, tmp_path)
    atts = attempts(parsed)
    assert atts[3]["hard_fail_events"] == [{"code": "G3", "detail": "STRAY_RELATION_ID"}]
    assert atts[4]["hard_fail_events"] == []
    assert atts[6]["hard_fail_events"] == [{"code": "G3", "detail": "CLAIM_WITHOUT_EVIDENCE"}]
    assert S["status"] == "COMPLETE" and S["hard_fail_pairs"] == 2


def test_guard_refuses_beyond_the_call_cap(e, tmp_path):
    script_ok(e, 3)
    d, checks, _ = wire(e)
    e.cap.MAX_IVE_CALLS = 3
    S, parsed, _ = run(e, d, checks, tmp_path)
    assert S["status"] == "STOPPED_HARNESS_GUARD" and len(e.provider.seen) == 3
    last = attempts(parsed)[-1]
    assert last["order"] == "BA" and last["arms"]["A"]["status"] == "REFUSED"


def test_a_refused_b_call_is_a_guard_stop_not_a_b_failure(e, tmp_path):
    script_ok(e, 1)
    d, checks, _ = wire(e)
    e.cap.MAX_IVE_CALLS = 1                    # slot 0 runs A first; the guard refuses B
    S, parsed, ledger = run(e, d, checks, tmp_path)
    att = attempts(parsed)[0]
    assert S["status"] == "STOPPED_HARNESS_GUARD" and len(e.provider.seen) == 1
    assert att["arms"]["A"]["status"] == "OK" and att["arms"]["B"]["status"] == "REFUSED"
    assert att["hard_fail_events"] == [] and S["hard_fail_pairs"] == 0
    r = e.scorer.score(ledger)
    assert r["verdict"]["sub_reason"] == "HARNESS_INTEGRITY" and r["excluded"]["b_failed_not_g1"] == [[1, 0]]


def test_a_lone_surrogate_in_model_output_is_recorded_and_scored(e, tmp_path):
    """Valid JSON can carry a lone UTF-16 surrogate escape (an emoji cut in half).
    The ledger is ASCII-escaped, so it can stop neither the run nor the scorer."""
    script_ok(e)
    pl = payload(1)
    pl["abstract"] = "emoji cut \ud83d here"
    text = json.dumps(pl)
    assert "\\ud83d" in text and text.isascii()
    e.provider.script["B"][1] = response(text)
    d, checks, _ = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    assert S["status"] == "COMPLETE" and S["scored_pairs"] == 81 and open(ledger, "rb").read().isascii()
    att = attempts(parsed)[1]
    assert att["arms"]["B"]["status"] == "OK" and att["arms"]["B"]["report"]["abstract"] == "emoji cut \ud83d here"
    assert e.scorer.main(["score", ledger, str(tmp_path / "scored")]) == 0


def test_arm_a_parity_fails_when_the_in_process_path_rejects_a_core_report(e, tmp_path):
    script_ok(e, 1)
    real = e.hm.adapter_equivalent

    def rejecting(outcome, mi, app):
        if outcome is e.hm.AB["outcomes"].get("A"):
            return None, e.hm.wrap_like_core(app.ProviderError, "gemini produced invalid output: x", ValueError("x"))
        return real(outcome, mi, app)

    e.mp.setattr(e.hm, "adapter_equivalent", rejecting)
    d, checks, _ = wire(e)
    S, parsed, ledger = run(e, d, checks, tmp_path)
    att = attempts(parsed)[0]
    assert att["error"] is None and att["a_parity"] is False         # the Core accepted what the copy rejected
    assert S["status"] == "STOPPED_HARNESS_CAPTURE" and len(e.provider.seen) == 2
    assert e.scorer.score(ledger)["verdict"]["sub_reason"] == "HARNESS_INTEGRITY"


class _ExtraCallEngine:
    """Wraps the real adapter and makes one extra backend call first."""

    def __init__(self, inner, extra_backend, schema):
        self._inner, self._extra, self._schema = inner, extra_backend, schema
        self.engine_id, self.provider, self.model = "gemini", "gemini", MODEL

    def run(self, model_input):
        self._extra.generate(system="x", user="y", schema=self._schema)
        return self._inner.run(model_input)


@pytest.mark.parametrize("same_backend", [False, True])
def test_guard_refuses_unauthorised_calls_before_the_provider(e, tmp_path, same_backend):
    import app.modules.ive_common as ic
    from app.modules.gemini_ive.adapter import GeminiIVE

    script_ok(e, 2)
    ive_backend = e.gbm.GeminiBackend(MODEL, telemetry_label="ive")
    if same_backend:   # a second IVE generate() inside one turn
        engine = _ExtraCallEngine(GeminiIVE(ive_backend, model=MODEL), ive_backend, ic.IVE_RESPONSE_SCHEMA)
    else:              # a non-IVE call with its own schema
        rogue = e.gbm.GeminiBackend(MODEL, telemetry_label="composer", thinking_budget=512)
        engine = _ExtraCallEngine(GeminiIVE(ive_backend, model=MODEL), rogue, {"type": "object"})
    d, checks, composer = wire(e, engine=engine)
    S, parsed, _ = run(e, d, checks, tmp_path)
    assert S["status"] == "STOPPED_HARNESS_GUARD" and len(attempts(parsed)) == 1
    assert len(e.provider.seen) == (2 if same_backend else 0) and composer.calls == []
    assert attempts(parsed)[0]["guard_refusals"]


def test_adapter_equivalent_classifies_like_the_core(e):
    """Arm B's in-process wrapping must classify exactly as the Core's own path
    does when the same failure hits arm A."""
    cases = [api_error(503, "UNAVAILABLE"), api_error(400, "INVALID_ARGUMENT"), httpx.ConnectTimeout("t"),
             httpx.ReadTimeout("r"), response("[1, 2]"), response('{"abstract": "a"}'),
             response(json.dumps({**payload(0), "confidence": 2.0}))]
    for case in cases:
        e.provider.script["A"].append(case)
        e.provider.script["B"].append(case)
    d, _, _ = wire(e)
    for k in range(len(cases)):
        row, turn_exc, live = e.hm.run_pair(d, 0, QUESTIONS[0], 1, "primary")
        c = e.hm.classify_ab(d, row, turn_exc, live)
        assert turn_exc is not None and row["a_parity"] is True
        assert c["arms"]["A"]["class_key"] == c["arms"]["B"]["class_key"] == c["turn"]["class_key"], k
