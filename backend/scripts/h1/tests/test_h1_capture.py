"""Offline tests for voe_h1_ive_capture.py and h1_sizing.py. ZERO provider calls.

Every test runs with sockets blocked. The google-genai Client is a fake; the
SDK's real `types` (2.28.0) build the request config and the response objects,
so `response.text` follows the real SDK rule (thought parts excluded).

The turn path is the REAL repository code: Core.ask (driven with the repo's own
stand-ins from tests/test_core_voe_composition_v0_1.py for retrieval and
governance), the real ModelGateway, GeminiIVE adapter, GeminiBackend and
ive_common normalization, plus the frozen E3 harness tap loaded by sha256.

Run from the repository's backend/ directory, with H1_TEST_E3_HARNESS set to
the frozen voe_e3_paired_replay.py (sha256 1134c4f6...65c7):
    python -m pytest -q -p no:cacheprovider <this file>
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import inspect
import json
import os
import socket
import sys
import uuid
from types import SimpleNamespace

import pytest
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

if "H1_TEST_E3_HARNESS" not in os.environ:
    pytest.skip("H1_TEST_E3_HARNESS (path to the frozen E3 harness) is not set", allow_module_level=True)

H1_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE_PATH = os.path.join(H1_DIR, "voe_h1_ive_capture.py")
SIZING_PATH = os.path.join(H1_DIR, "h1_sizing.py")
E3_HARNESS_PATH = os.environ["H1_TEST_E3_HARNESS"]
MODEL = "gemini-2.5-pro"


# --------------------------------------------------------------------- #
# isolation
# --------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*_a, **_k):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeModels:
    """Scripted provider: each item is a response object or an exception."""

    def __init__(self, script, seen):
        self._script = script
        self.seen = seen

    def generate_content(self, *, model, contents, config):
        self.seen.append({"model": model, "contents": contents, "config": config})
        if not self._script:
            raise AssertionError("unexpected extra provider call")
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def env(monkeypatch):
    """Fresh capture + frozen harness modules, the real backend module, a fake
    client. Class attributes the run patches are restored after each test."""
    import app.modules.gemini_ive.backend as gbm

    monkeypatch.setattr(gbm.GeminiBackend, "_ensure", gbm.GeminiBackend._ensure)
    monkeypatch.setattr(gbm.GeminiBackend, "generate", gbm.GeminiBackend.generate)
    tag = uuid.uuid4().hex[:8]
    cap = _load(f"h1cap_{tag}", CAPTURE_PATH)
    harness = cap.load_by_path(f"e3h_{tag}", E3_HARNESS_PATH, cap.EXPECTED_HARNESS_SHA256)
    script, seen = [], []
    monkeypatch.setattr(genai, "Client", lambda *a, **k: SimpleNamespace(models=FakeModels(script, seen)))
    return SimpleNamespace(cap=cap, harness=harness, gbm=gbm, script=script, seen=seen, mp=monkeypatch)


def response(text, *, prompt=1100, visible=1400, thoughts=1700, rid="resp"):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[
            types.Part(text="private reasoning summary", thought=True),
            types.Part(text=text)]))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt, candidates_token_count=visible,
            thoughts_token_count=thoughts, total_token_count=prompt + visible + thoughts),
        response_id=rid)


def api_error(code, status):
    return genai_errors.APIError(code, {"error": {"code": code, "message": "scripted", "status": status}})


def ive_payload(i):
    return {
        "abstract": f"Abstract {i}: money as “credit” — naïve {{braces}} and \"quotes\" \\ ok.",
        "highlights": [f"H{i}a", "Ünïcödé highlight ✓"],
        "claims": [{"claim_id": "c1", "statement": f"Claim {i}: ION’s role [x] {{y}}",
                    "evidence_document_ids": ["EV-1"], "confidence": 0.8}],
        "concepts": [{"name": f"Concept {i}", "description": "A “wavelet” of change: {not json}"},
                     {"name": "Second", "description": "émoji 🌍 and \"q\""}],
        "relations": [{"source": "ION", "relation": "finances", "target": "nature",
                       "evidence_document_ids": ["EV-1", "EV-2"]}],
        "uncertainty": ["Origins debated."],
        "confidence": 0.7,
    }


def ive_text(i):
    p = ive_payload(i)
    if i % 3 == 0:
        return json.dumps(p, ensure_ascii=False)                       # compact-ish default separators
    if i % 3 == 1:
        return json.dumps(p, ensure_ascii=False, indent=2)             # pretty-printed
    return "```json\n" + json.dumps(p, ensure_ascii=False) + "\n```"   # fenced


def make_core(e, *, engine=None, composer=None):
    from tests.test_core_voe_composition_v0_1 import _core, _patch_gate, _voe_profile, _RecordingComposer
    from app.modules.gemini_ive.adapter import GeminiIVE
    from app.modules.model_gateway import ModelGateway

    if composer is None:
        composer = _RecordingComposer()
        composer._backend = e.gbm.GeminiBackend(MODEL, telemetry_label="composer", thinking_budget=512)
    core = _core(composer=composer, voe_runtime_profile=_voe_profile())
    _patch_gate(e.mp)
    engine = engine or GeminiIVE(e.gbm.GeminiBackend(MODEL, telemetry_label="ive"), model=MODEL)
    core._model_gateway = ModelGateway({"gemini": engine})
    return core, composer


def make_world(e, core, questions, **over):
    from app.modules.execution_profile import STANDARD_GEMINI

    e.harness.install_tap(e.gbm)
    e.cap.install_capture(e.gbm, e.harness)
    h = e.harness
    kw = dict(
        harness=h, gbm=e.gbm,
        settings=SimpleNamespace(gemini_model=MODEL, voe_composer_thinking_budget=512),
        profile=STANDARD_GEMINI, core=core,
        runtime_profile=SimpleNamespace(binding=SimpleNamespace(
            profile_version="0.4", runtime_behavioral_fingerprint_sha256=h.EXPECTED_FINGERPRINT)),
        system_sha=h.EXPECTED_SYSTEM_SHA256,
        questions=questions, questions_sha256=e.cap.EXPECTED_QUESTIONS_SHA256,
        deployment_id=e.cap.EXPECTED_DEPLOYMENT_ID,
        sources={"core_ask": inspect.getsource(type(core).ask),
                 "core_class": inspect.getsource(type(core)),
                 "gemini_backend_module": inspect.getsource(e.gbm)},
        info={"google_genai_version": genai.__version__},
    )
    kw.update(over)
    return e.cap.World(**kw)


QUESTIONS = [f"Question {i}: what does The Works say about ION?" for i in range(27)]


def run(e, tmp_path, world, name="out"):
    checks = e.cap.start_checks(world)
    meta = e.cap.build_meta(world, checks)
    out = str(tmp_path / name)
    S = e.cap.run_capture(world, meta, out)
    lines = open(os.path.join(out, "h1cap_ledger.jsonl"), encoding="utf-8").read().splitlines()
    parsed = [(ln.split(" ", 1)[0], json.loads(ln.split(" ", 1)[1])) for ln in lines]
    return S, parsed, out


# --------------------------------------------------------------------- #
# start checks
# --------------------------------------------------------------------- #
def test_frozen_harness_is_loaded_only_by_its_sha(env, tmp_path):
    bad = tmp_path / "h.py"
    bad.write_bytes(open(E3_HARNESS_PATH, "rb").read() + b"\n")
    with pytest.raises(env.cap.H1Stop):
        env.cap.load_by_path("e3h_bad", str(bad), env.cap.EXPECTED_HARNESS_SHA256)


def test_start_checks_pass_and_make_zero_provider_calls(env):
    core, composer = make_core(env)
    world = make_world(env, core, QUESTIONS)
    checks = env.cap.start_checks(world)
    assert all(checks.values()), [k for k, v in checks.items() if not v]
    assert env.seen == [] and env.harness.CALLS == [] and env.cap.CAPTURES == []
    assert composer.calls == []


@pytest.mark.parametrize("override, failing", [
    ({"deployment_id": "other"}, "deployment_id"),
    ({"settings": SimpleNamespace(gemini_model="gemini-2.5-flash", voe_composer_thinking_budget=512)}, "model"),
    ({"settings": SimpleNamespace(gemini_model=MODEL, voe_composer_thinking_budget=None)},
     "deployed_composer_budget_512"),
    ({"system_sha": "0" * 64}, "system_instruction_ok"),
    ({"questions_sha256": "0" * 64}, "questions_sha256"),
    ({"questions": QUESTIONS[:26]}, "questions_count"),
    ({"info": {"google_genai_version": "2.27.0"}}, "google_genai_version"),
])
def test_start_checks_fail_closed(env, override, failing):
    core, _ = make_core(env)
    over = dict(override)
    checks = env.cap.start_checks(make_world(env, core, over.pop("questions", QUESTIONS), **over))
    assert checks[failing] is False
    assert [k for k, v in checks.items() if not v] == [failing]
    assert env.seen == []


def test_start_checks_read_the_source(env):
    core, _ = make_core(env)
    world = make_world(env, core, QUESTIONS)
    ask = world.sources["core_ask"]
    backend = world.sources["gemini_backend_module"]
    variants = {
        "core_ask_no_composer_path": dict(world.sources, core_ask=ask.replace(
            "if self._composer is not None", "if True")),
        "composer_read_after_ive": dict(world.sources, core_ask="self._composer\n" + ask),
        "backend_sets_no_retry": dict(world.sources, gemini_backend_module=backend + "\nretry_options=1\n"),
    }
    for key, sources in variants.items():
        world.sources = sources
        assert env.cap.start_checks(world)[key] is False, key
    core._composer = None
    world.sources = {"core_ask": ask, "core_class": "", "gemini_backend_module": backend}
    assert env.cap.start_checks(world)["core_composer_present"] is False


def test_build_world_wiring_on_repo_code(env, monkeypatch, tmp_path):
    """The real container wiring path, with only build_core swapped for the
    stand-in Core (no Qdrant, no embedder). This checkout carries an older VOE
    bundle than the deployed v0.4, and the questions here are synthetic, so
    exactly those identity checks must fail; everything else must pass."""
    import app.container as container
    from tests.voe_pack import COMMITTED_VOE_PACK_DIR

    core, _ = make_core(env)
    monkeypatch.setattr(container, "build_core", lambda settings: core)
    for k, v in {"GEMINI_MODEL": MODEL, "EXECUTION_PROFILE": "STANDARD_GEMINI",
                 "VOE_PROFILE_ENABLED": "true", "VOE_PROFILE_BUNDLE_DIR": str(COMMITTED_VOE_PACK_DIR),
                 "VOE_COMPOSER_THINKING_BUDGET": "512"}.items():
        monkeypatch.setenv(k, v)
    qfile = tmp_path / "q.json"
    qfile.write_text(json.dumps(QUESTIONS), encoding="utf-8")
    world = env.cap.build_world({"H1_E3_HARNESS_PATH": E3_HARNESS_PATH, "H1_QUESTIONS_PATH": str(qfile),
                                 "RAILWAY_DEPLOYMENT_ID": env.cap.EXPECTED_DEPLOYMENT_ID})
    checks = env.cap.start_checks(world)
    assert sorted(k for k, v in checks.items() if not v) == [
        "fingerprint_ok", "profile_version", "questions_sha256", "system_instruction_ok"]
    assert world.info["ive_backend_label"] == "ive" and world.info["ive_backend_thinking_budget"] is None
    assert world.info["ive_system_prompt"]["sha256"] and world.info["ive_response_schema"]["sha256"]
    assert world.harness.CALLS == [] and env.seen == []


def test_main_preflight_only_and_stop(env, monkeypatch, capsys):
    core, _ = make_core(env)
    world = make_world(env, core, QUESTIONS)
    monkeypatch.setattr(env.cap, "build_world", lambda _env: world)
    monkeypatch.setenv("H1_PREFLIGHT_ONLY", "1")
    assert env.cap.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("H1_PREFLIGHT ") and '"provider_calls": 0' in out
    world.deployment_id = "other"
    assert env.cap.main() == 2
    assert capsys.readouterr().out.startswith("H1_STOP ")
    assert env.seen == []


# --------------------------------------------------------------------- #
# the measurement pass
# --------------------------------------------------------------------- #
def test_full_pass_captures_every_ive_output_and_never_composes(env, tmp_path):
    import app.modules.ive_common as ic

    texts = [ive_text(i) for i in range(27)]
    env.script.extend(response(t, rid=f"r{i}") for i, t in enumerate(texts))
    core, composer = make_core(env)
    world = make_world(env, core, QUESTIONS)
    S, parsed, out = run(env, tmp_path, world)

    assert S["status"] == "COMPLETE" and S["turns_run"] == 27
    assert S["ive_calls"] == 27 and S["ive_calls_ok"] == 27 and S["provider_calls_total"] == 27
    assert S["non_ive_calls"] == 0 and S["guard_refusals"] == 0 and S["composition_attempted_turns"] == 0
    assert S["captures_ok"] == 27 and S["report_raw_matches_capture"] == 27
    assert composer.calls == [] and core._composer is None
    assert [t for t, _ in parsed] == ["H1_META"] + ["H1_TURN"] * 27 + ["H1_SUMMARY"]
    assert parsed[0][1]["composer_detached"] is True
    assert len(env.seen) == 27
    schema = json.loads(json.dumps(ic.IVE_RESPONSE_SCHEMA))
    for i, (seen, (_, row)) in enumerate(zip(env.seen, parsed[1:28])):
        # the request is the unchanged IVE request
        assert seen["model"] == MODEL
        assert seen["config"].thinking_config is None
        assert seen["config"].system_instruction == ic.IVE_SYSTEM_PROMPT
        assert seen["config"].response_json_schema == schema
        # the capture is the exact visible text, byte for byte
        (capture,) = row["captures"]
        assert capture["outcome"] == "OK" and capture["label"] == "ive"
        assert capture["text"] == texts[i]
        assert capture["text_digest"]["sha256"] == hashlib.sha256(texts[i].encode("utf-8")).hexdigest()
        assert capture["text_digest"]["utf8_bytes"] == len(texts[i].encode("utf-8"))
        assert capture["input"]["user"]["sha256"] == hashlib.sha256(seen["contents"].encode("utf-8")).hexdigest()
        assert capture["input"]["system"]["sha256"] == hashlib.sha256(ic.IVE_SYSTEM_PROMPT.encode()).hexdigest()
        # the full normalized report is persisted as returned
        (report,) = row["ive_reports"]
        assert report["raw_response"] == texts[i]
        assert report["concepts"] == ive_payload(i)["concepts"]
        assert report["relations"] == ive_payload(i)["relations"]
        assert row["capture_matches_report_raw"] is True
        assert row["composition_attempted"] is False
        (call,) = row["ive_calls"]
        assert call["thinking_config_sent"] is False and call["candidates_tokens"] == 1400
        assert call["question_index"] == i == row["index"]
    with pytest.raises(FileExistsError):       # never overwrites an earlier run
        env.cap.run_capture(world, {}, out)
    assert len(env.seen) == 27


def test_http_402_stops_the_run(env, tmp_path):
    env.script.extend([response(ive_text(0)), response(ive_text(1)), api_error(402, "PAYMENT_REQUIRED")]
                      + [response(ive_text(i)) for i in range(24)])
    core, _ = make_core(env)
    S, parsed, _ = run(env, tmp_path, make_world(env, core, QUESTIONS))
    assert S["status"] == "STOPPED_HTTP_402" and S["turns_run"] == 3 and len(env.seen) == 3
    assert parsed[3][1]["ive_calls"][0]["error"]["http_status"] == 402


def test_three_consecutive_failures_stop_but_a_success_resets(env, tmp_path):
    env.script.extend([api_error(503, "UNAVAILABLE"), response(ive_text(1)), api_error(503, "UNAVAILABLE"),
                       api_error(500, "INTERNAL"), api_error(503, "UNAVAILABLE")]
                      + [response(ive_text(i)) for i in range(22)])
    core, _ = make_core(env)
    S, _, _ = run(env, tmp_path, make_world(env, core, QUESTIONS))
    assert S["status"] == "STOPPED_CONSECUTIVE_FAILURES" and S["turns_run"] == 5 and len(env.seen) == 5
    assert S["ive_calls_failed"] == 4 and S["captures_ok"] == 1


class _ExtraCallEngine:
    """Wraps the real adapter and makes one extra backend call first."""

    def __init__(self, inner, extra_backend):
        self._inner, self._extra = inner, extra_backend
        self.engine_id, self.provider, self.model = "gemini", "gemini", MODEL

    def run(self, model_input):
        self._extra.generate(system="x", user="y", schema={"type": "object"})
        return self._inner.run(model_input)


def test_guard_refuses_a_non_ive_call_before_the_provider(env, tmp_path):
    from app.modules.gemini_ive.adapter import GeminiIVE

    env.script.extend(response(ive_text(i)) for i in range(27))
    rogue = env.gbm.GeminiBackend(MODEL, telemetry_label="composer", thinking_budget=512)
    engine = _ExtraCallEngine(GeminiIVE(env.gbm.GeminiBackend(MODEL, telemetry_label="ive"), model=MODEL), rogue)
    core, composer = make_core(env, engine=engine)
    S, parsed, _ = run(env, tmp_path, make_world(env, core, QUESTIONS))
    assert S["status"] == "STOPPED_GUARD" and S["turns_run"] == 1
    assert env.seen == []                       # nothing reached the provider
    assert S["guard_refusals"] == 1 and S["non_ive_calls"] == 0 and composer.calls == []
    assert parsed[1][1]["captures"][0]["outcome"] == "REFUSED"


def test_a_second_ive_call_in_one_turn_stops_the_run(env, tmp_path):
    from app.modules.gemini_ive.adapter import GeminiIVE

    env.script.extend(response(ive_text(i)) for i in range(27))
    ive_backend = env.gbm.GeminiBackend(MODEL, telemetry_label="ive")
    engine = _ExtraCallEngine(GeminiIVE(ive_backend, model=MODEL), ive_backend)
    core, _ = make_core(env, engine=engine)
    S, _, _ = run(env, tmp_path, make_world(env, core, QUESTIONS))
    assert S["status"] == "STOPPED_GUARD" and S["turns_run"] == 1 and len(env.seen) == 2


def test_call_cap_holds_at_27(env, tmp_path):
    env.script.extend(response(ive_text(i)) for i in range(28))
    core, _ = make_core(env)
    S, _, _ = run(env, tmp_path, make_world(env, core, QUESTIONS + ["Question 27?"]))
    assert S["status"] == "STOPPED_GUARD" and S["turns_run"] == 27 and len(env.seen) == 27
    # and the guard itself refuses a 28th IVE call at the backend boundary
    backend = env.gbm.GeminiBackend(MODEL, telemetry_label="ive")
    with pytest.raises(env.cap.H1GuardRefusal):
        backend.generate(system="s", user="u", schema={})
    assert len(env.seen) == 27


def test_missing_capture_text_stops_the_run(env, tmp_path):
    real = env.gbm.GeminiBackend.generate

    def textless(self, **kw):
        result = real(self, **kw)
        return SimpleNamespace(text=None, input_tokens=result.input_tokens,
                               output_tokens=result.output_tokens, usage_is_estimated=False)

    env.mp.setattr(env.gbm.GeminiBackend, "generate", textless)
    env.script.extend(response(ive_text(i)) for i in range(27))
    core, _ = make_core(env)
    S, _, _ = run(env, tmp_path, make_world(env, core, QUESTIONS))
    assert S["status"] == "STOPPED_CAPTURE_FAILED" and S["turns_run"] == 1 and len(env.seen) == 1


# --------------------------------------------------------------------- #
# sizing analyzer
# --------------------------------------------------------------------- #
@pytest.fixture
def sizing():
    return _load(f"h1sizing_{uuid.uuid4().hex[:8]}", SIZING_PATH)


TRICKY = [
    json.dumps(ive_payload(0), ensure_ascii=False),
    json.dumps(ive_payload(1), ensure_ascii=False, indent=2),
    json.dumps(ive_payload(2), ensure_ascii=True, separators=(",", ":")),
    "```json\n" + json.dumps(ive_payload(3), ensure_ascii=False) + "\n```",
    "  \n" + json.dumps({**ive_payload(4), "concepts": [], "relations": []}, indent=4) + "\n  ",
    '{"a":{"b":[1,{"c":"}]{"}]},"concepts":[],"z":"\\"\\u00e9\\""}',
    "{}",
]


@pytest.mark.parametrize("text", TRICKY)
def test_member_spans_partition_the_text_exactly(sizing, text):
    obj, members = sizing.object_members(text)
    assert [m["key"] for m in members] == list(obj)
    for m in members:
        assert json.loads(text[m["value_start"]:m["value_end"]]) == obj[m["key"]]
        assert json.loads(text[m["key_start"]:text.index(":", m["key_start"])].strip()) == m["key"]
    a = sizing.analyze_text(text)
    owned_c = sum(f["chars"] for f in a["fields"].values())
    owned_b = sum(f["bytes"] for f in a["fields"].values())
    assert owned_c + a["envelope_chars"] == len(text)
    assert owned_b + a["envelope_bytes"] == len(text.encode("utf-8"))
    assert a["canon_total_chars"] == len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def test_analyze_text_counts_and_member_sizes(sizing):
    p = ive_payload(5)
    text = json.dumps(p, ensure_ascii=False)
    a = sizing.analyze_text(text)
    # default separators: '"key": value, ' for every member but the last
    for key in ("concepts", "relations"):
        expect = len(f'"{key}": ') + len(json.dumps(p[key], ensure_ascii=False)) + len(", ")
        assert a["fields"][key]["chars"] == expect
        assert a["fields"][key]["value_chars"] == len(json.dumps(p[key], ensure_ascii=False))
        assert a["fields"][key]["items"] == len(p[key])
    assert a["fields"]["confidence"]["chars"] == len('"confidence": 0.7')
    assert a["envelope_chars"] == 2
    assert a["concepts_name_chars"] == sum(len(c["name"]) for c in p["concepts"])
    assert a["concepts_description_chars"] == sum(len(c["description"]) for c in p["concepts"])
    assert a["relations_evidence_ids"] == 2 and a["claims_evidence_ids"] == 1


def test_truncated_output_is_reported_not_fatal(sizing):
    text = json.dumps(ive_payload(6))[:-40]
    turn = {"index": 0, "captures": [{"label": "ive", "outcome": "OK", "text": text}],
            "ive_calls": [{"outcome": "OK", "candidates_tokens": 100}]}
    row = sizing.turn_row(turn)
    assert row["captured"] is True and row["parse_ok"] is False and row["total_chars"] == len(text)


def test_sizing_end_to_end_on_a_captured_pass(env, sizing, tmp_path):
    texts = [ive_text(i) for i in range(27)]
    env.script.extend(response(t, visible=1000 + i * 10, thoughts=1500 + i * 7) for i, t in enumerate(texts))
    core, _ = make_core(env)
    S, _, out = run(env, tmp_path, make_world(env, core, QUESTIONS))
    assert S["status"] == "COMPLETE"
    prefix = str(tmp_path / "h1s")
    assert sizing.main([os.path.join(out, "h1cap_ledger.jsonl"), prefix]) == 0
    rows = list(csv.DictReader(open(prefix + "_turns.csv", encoding="utf-8")))
    summary = json.load(open(prefix + "_summary.json", encoding="utf-8"))
    assert len(rows) == 27 and all(r["parse_ok"] == "True" for r in rows)
    assert summary["source"]["parsed"] == 27 and summary["source"]["ledger_status"] == "COMPLETE"
    assert summary["cross_checks"]["capture_matches_report_raw"]["True"] == 27
    assert summary["cross_checks"]["report_counts_match_raw"] == 27
    cr = tot = 0
    for i, (t, r) in enumerate(zip(texts, rows)):
        a = sizing.analyze_text(t)
        c = a["fields"]["concepts"]["chars"] + a["fields"]["relations"]["chars"]
        assert int(r["cr_chars"]) == c and int(r["total_chars"]) == len(t)
        assert int(r["visible_tokens"]) == 1000 + i * 10
        assert float(r["cr_est_visible_tokens"]) == pytest.approx((1000 + i * 10) * c / len(t))
        cr, tot = cr + c, tot + len(t)
    assert summary["pooled"]["concepts_relations"]["share_chars"] == pytest.approx(cr / tot)
    assert summary["estimated"]["label"] == "ESTIMATED"
