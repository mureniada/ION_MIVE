"""H1 observability: capture-only IVE measurement harness (voe_h1_ive_capture.py).

Operator request 2026-10-07 17:00Z ("H1 OBSERVABILITY CLOSURE"): persist the
full IVE report the current, unchanged v0.4 staging baseline already produces,
so the size of `concepts` and `relations` can be measured offline
(h1_sizing.py). This harness OBSERVES ONLY. It changes no IVE prompt, schema,
model, thinking budget, retrieval, Context Pack or deployed configuration.

One baseline pass over the frozen 27-question set: sequential, at most 27 IVE
calls, ZERO composer calls.
  * The Core is built from the deployed settings exactly as the frozen E3
    harness builds it (Settings.load -> build_core), inside the container.
  * Composition is skipped through the Core's own no-composer path: in THIS
    process only, `core._composer = None`, so Core.ask returns its
    deterministic base answer and never reaches compose(). The IVE call runs
    before that block and does not read it. The deployed service and its
    configuration are untouched.
  * A fail-closed guard refuses, before it reaches the provider, any Gemini
    call whose backend label is not "ive", and any IVE call beyond 27.
  * The frozen E3 tap (voe_e3_paired_replay.py, e3-call-ledger-v2) records
    each provider call's usage, latency and sanitized error.
  * A pass-through wrapper on GeminiBackend.generate keeps the exact text the
    IVE adapter parses (GenerationResult.text) verbatim, with its sha256,
    chars and UTF-8 bytes. Request inputs are kept only as sha256 and sizes.
  * AskResult.ive_reports (the normalized report: claims, concepts, relations,
    raw_response ...) is persisted as returned.

Run INSIDE the ION_MIVE staging container, new work dir /tmp/h1cap, detached:

    cd /tmp/h1cap && H1_E3_HARNESS_PATH=/tmp/h1cap/voe_e3_paired_replay.py \
      H1_QUESTIONS_PATH=/tmp/h1cap/e3q.json H1_OUT_DIR=/tmp/h1cap/out \
      python /tmp/h1cap/voe_h1_ive_capture.py > /tmp/h1cap/stdout.log 2> /tmp/h1cap/stderr.log

H1_PREFLIGHT_ONLY=1 runs every start check and exits before any provider call.
Output (H1_OUT_DIR must not exist): h1cap_ledger.jsonl = one H1_META line, one
H1_TURN line per question run, one H1_SUMMARY line. stdout carries one
H1_PROGRESS line per turn and a final H1_DONE / H1_STOP / H1_PREFLIGHT line.
Never prints secrets or the environment; reads RAILWAY_DEPLOYMENT_ID by name only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import inspect
import json
import os
import platform
import sys
import time

CAPTURE_VERSION = "h1-ive-capture-v1"
EXPECTED_HARNESS_SHA256 = "1134c4f646c7c667d5d93c14d14bec07012be94096b7e492d92f25d2486865c7"
EXPECTED_QUESTIONS_SHA256 = "b6a414cd8680c28e468a2fde5482800df8a9edb6d5b2e899119476726514b833"
EXPECTED_N_QUESTIONS = 27
EXPECTED_PROFILE_VERSION = "0.4"
EXPECTED_MODEL = "gemini-2.5-pro"
EXPECTED_DEPLOYMENT_ID = "2c91c45e-997c-4d8f-80e7-83be99e9b0af"
EXPECTED_DEPLOYED_COMPOSER_BUDGET = 512
# google-genai 2.28.0 never retries unless HttpOptions.retry_options is set
# (_api_client.retry_args(None) -> stop_after_attempt(1)); the backend sets none.
EXPECTED_GOOGLE_GENAI_VERSION = "2.28.0"
IVE_LABEL = "ive"
MAX_IVE_CALLS = 27
CONSECUTIVE_MISS_STOP = 3

ST_COMPLETE = "COMPLETE"
ST_402 = "STOPPED_HTTP_402"
ST_MISSES = "STOPPED_CONSECUTIVE_FAILURES"
ST_GUARD = "STOPPED_GUARD"
ST_CAPTURE = "STOPPED_CAPTURE_FAILED"

# Every GeminiBackend.generate() call seen by the wrapper, in order.
CAPTURES: list[dict] = []


class H1Stop(Exception):
    """A start check failed; no provider call has been or will be made."""


class H1GuardRefusal(RuntimeError):
    """A Gemini call this measurement does not authorize, refused before the provider."""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_digest(value) -> dict:
    if not isinstance(value, str):
        return {"sha256": None, "chars": None, "utf8_bytes": None}
    data = value.encode("utf-8")
    return {"sha256": hashlib.sha256(data).hexdigest(), "chars": len(value), "utf8_bytes": len(data)}


def schema_digest(schema) -> dict:
    try:
        canonical = json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return {"sha256": None, "chars": None, "utf8_bytes": None}
    return text_digest(canonical)


def load_by_path(name: str, path: str, expected_sha: str):
    actual = sha256_file(path)
    if actual != expected_sha:
        raise H1Stop(f"{name} sha256 mismatch: {actual}")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _dig(obj, *names):
    """Read-only attribute/key path; None when any step is missing."""
    for name in names:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(name)
            continue
        try:
            obj = getattr(obj, name, None)
        except Exception:
            return None
    return obj


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# ------------------------------------------------------------------ #
# guard + capture on GeminiBackend.generate (observational pass-through)
# ------------------------------------------------------------------ #
def install_capture(backend_module, harness) -> None:
    """Wrap GeminiBackend.generate. The guard runs first and refuses, before the
    provider is reached, a non-IVE call or an IVE call beyond MAX_IVE_CALLS.
    Otherwise the original is called with the identical args/kwargs; its result
    object is returned unchanged and an exception is re-raised as the identical
    object (bare `raise`). Capture code never fails a call: its own errors only
    set `telemetry_error`."""
    original = backend_module.GeminiBackend.generate

    def generate(self, *args, **kwargs):
        label = getattr(self, "_telemetry_label", None)
        rec = {"seq": len(CAPTURES), "label": label,
               "question_index": harness.CURRENT["index"], "utc_start": harness._utc_now()}
        try:
            names = ("system", "user", "schema")
            given = dict(zip(names, args))
            given.update({n: kwargs[n] for n in names if n in kwargs})
            rec["input"] = {"system": text_digest(given.get("system")),
                            "user": text_digest(given.get("user")),
                            "schema": schema_digest(given.get("schema"))}
        except Exception:
            rec["telemetry_error"] = True
        attempted = sum(1 for c in CAPTURES
                        if c.get("label") == IVE_LABEL and c.get("outcome") != "REFUSED")
        refusal = None
        if label != IVE_LABEL:
            refusal = f"non-IVE Gemini call (label={label!r})"
        elif attempted >= MAX_IVE_CALLS:
            refusal = f"IVE call cap {MAX_IVE_CALLS} reached"
        if refusal is not None:
            rec.update({"outcome": "REFUSED", "refusal": refusal,
                        "utc_end": harness._utc_now(), "text": None})
            CAPTURES.append(rec)
            raise H1GuardRefusal(f"refused before the provider: {refusal}")
        started = time.monotonic()
        try:
            result = original(self, *args, **kwargs)
        except Exception as exc:  # never KeyboardInterrupt/SystemExit/GeneratorExit
            try:
                rec.update({"outcome": "FAILED", "text": None, "utc_end": harness._utc_now(),
                            "wrapper_ms": round((time.monotonic() - started) * 1000.0, 1),
                            "error": harness.safe_describe_exception(exc)})
            except Exception:
                rec["telemetry_error"] = True
            CAPTURES.append(rec)
            raise
        try:
            text = getattr(result, "text", None)
            estimated = getattr(result, "usage_is_estimated", None)
            rec.update({
                "outcome": "OK",
                "utc_end": harness._utc_now(),
                "wrapper_ms": round((time.monotonic() - started) * 1000.0, 1),
                "text_type": type(text).__name__,
                "text": text if isinstance(text, str) else None,
                "text_digest": text_digest(text),
                "result_input_tokens": _int(getattr(result, "input_tokens", None)),
                "result_output_tokens": _int(getattr(result, "output_tokens", None)),
                "usage_is_estimated": estimated if isinstance(estimated, bool) else None,
            })
        except Exception:
            rec.setdefault("outcome", "OK")
            rec["telemetry_error"] = True
        CAPTURES.append(rec)
        return result

    generate.h1_capture = True
    backend_module.GeminiBackend.generate = generate


# ------------------------------------------------------------------ #
# world: what the run touches (wired in the container, stand-ins offline)
# ------------------------------------------------------------------ #
@dataclasses.dataclass
class World:
    harness: object            # frozen E3 harness module: tap, CALLS, CURRENT, helpers, constants
    gbm: object                # app.modules.gemini_ive.backend
    settings: object
    profile: object
    core: object
    runtime_profile: object    # VOE runtime profile, identity check only
    system_sha: str | None     # composer system instruction sha256, identity check only
    questions: list
    questions_sha256: str
    deployment_id: str | None
    sources: dict              # source text read by the start checks
    info: dict                 # versions and file hashes (identity evidence)


def build_world(env) -> World:
    """Container wiring, mirroring the frozen E3 harness main(). No provider call:
    every SDK client is created lazily at its first generate()."""
    harness = load_by_path("e3_harness", env["H1_E3_HARNESS_PATH"], EXPECTED_HARNESS_SHA256)
    qpath = env["H1_QUESTIONS_PATH"]
    questions_sha = sha256_file(qpath)
    with open(qpath, encoding="utf-8") as fh:
        questions = json.load(fh)

    import google.genai
    import app.core.orchestrator as orch
    import app.modules.gemini_ive.adapter as gadapter
    import app.modules.gemini_ive.backend as gbm
    import app.modules.ive_common as ic
    from app.container import build_core, build_voe_composer, resolve_active_execution_profile
    from app.core.config import Settings
    from app.modules.response_composer import build_composer_system_instruction

    harness.install_tap(gbm)
    install_capture(gbm, harness)
    settings = Settings.load()
    profile = resolve_active_execution_profile(settings)
    core = build_core(settings)
    # Deployed settings unchanged; the composer built here is only an identity
    # witness (profile version, fingerprint, system instruction) and is dropped.
    _identity_composer, runtime_profile = build_voe_composer(profile, settings)
    system_sha = (hashlib.sha256(build_composer_system_instruction(runtime_profile).encode("utf-8")).hexdigest()
                  if runtime_profile is not None else None)
    sources = {"core_ask": inspect.getsource(type(core).ask),
               "core_class": inspect.getsource(type(core)),
               "gemini_backend_module": inspect.getsource(gbm)}
    ive_backend = _dig(core, "_model_gateway", "_engines", "gemini", "_backend")
    info = {
        "google_genai_version": getattr(google.genai, "__version__", None),
        "python_version": platform.python_version(),
        "file_sha256": {name: sha256_file(mod.__file__) for name, mod in (
            ("orchestrator", orch), ("gemini_backend", gbm), ("gemini_adapter", gadapter),
            ("ive_common", ic))},
        "ive_system_prompt": text_digest(getattr(ic, "IVE_SYSTEM_PROMPT", None)),
        "ive_response_schema": schema_digest(getattr(ic, "IVE_RESPONSE_SCHEMA", None)),
        "ive_backend_label": _dig(ive_backend, "_telemetry_label"),
        "ive_backend_thinking_budget": _dig(ive_backend, "_thinking_budget"),
        "core_class_composer_mentions": sources["core_class"].count("self._composer"),
    }
    return World(harness=harness, gbm=gbm, settings=settings, profile=profile, core=core,
                 runtime_profile=runtime_profile, system_sha=system_sha, questions=questions,
                 questions_sha256=questions_sha, deployment_id=env.get("RAILWAY_DEPLOYMENT_ID"),
                 sources=sources, info=info)


def start_checks(world: World) -> dict:
    """Every check runs before any provider call; all must be True to run."""
    h, core, rp = world.harness, world.core, world.runtime_profile
    ask_src = world.sources.get("core_ask") or ""
    backend_src = world.sources.get("gemini_backend_module") or ""
    engine_ids = [str(e) for e in (getattr(world.profile, "engine_ids", ()) or ())]
    deployed_composer = getattr(core, "_composer", None)
    first_engine = ask_src.find("_run_engine(")
    first_composer = ask_src.find("self._composer")
    return {
        "questions_sha256": world.questions_sha256 == EXPECTED_QUESTIONS_SHA256,
        "questions_count": len(world.questions) == EXPECTED_N_QUESTIONS,
        "deployment_id": world.deployment_id == EXPECTED_DEPLOYMENT_ID,
        "model": getattr(world.settings, "gemini_model", None) == EXPECTED_MODEL,
        "single_gemini_engine": engine_ids == ["gemini"],
        "mode_single": "SINGLE" in str(getattr(world.profile, "mode", "")),
        "profile_version": _dig(rp, "binding", "profile_version") == EXPECTED_PROFILE_VERSION,
        "fingerprint_ok": _dig(rp, "binding", "runtime_behavioral_fingerprint_sha256") == h.EXPECTED_FINGERPRINT,
        "system_instruction_ok": world.system_sha == h.EXPECTED_SYSTEM_SHA256,
        "deployed_composer_budget_512":
            getattr(world.settings, "voe_composer_thinking_budget", None) == EXPECTED_DEPLOYED_COMPOSER_BUDGET,
        "core_composer_present": deployed_composer is not None,
        "core_composer_budget_512":
            _dig(deployed_composer, "_backend", "_thinking_budget") == EXPECTED_DEPLOYED_COMPOSER_BUDGET,
        # Core.ask has the no-composer path, and reads the composer only after the IVE call.
        "core_ask_no_composer_path": "if self._composer is not None" in ask_src,
        "composer_read_after_ive": 0 <= first_engine < first_composer,
        "backend_sets_no_retry": bool(backend_src) and not any(
            t in backend_src for t in ("retry_options", "http_options", "HttpRetryOptions")),
        "google_genai_version": world.info.get("google_genai_version") == EXPECTED_GOOGLE_GENAI_VERSION,
        "tap_installed": getattr(world.gbm.GeminiBackend._ensure, "__qualname__", "").startswith("install_tap."),
        "capture_installed": getattr(world.gbm.GeminiBackend.generate, "h1_capture", False) is True,
        "zero_provider_calls": len(h.CALLS) == 0 and len(CAPTURES) == 0,
    }


def build_meta(world: World, checks: dict) -> dict:
    h, rp = world.harness, world.runtime_profile
    try:
        own_sha = sha256_file(os.path.abspath(__file__))
    except Exception:
        own_sha = None
    return {
        "capture_version": CAPTURE_VERSION,
        "harness_telemetry_version": h.HARNESS_TELEMETRY_VERSION,
        "capture_sha256": own_sha,
        "harness_sha256": EXPECTED_HARNESS_SHA256,
        "questions_sha256": world.questions_sha256,
        "questions": len(world.questions),
        "model": getattr(world.settings, "gemini_model", None),
        "deployed_composer_thinking_budget": getattr(world.settings, "voe_composer_thinking_budget", None),
        "profile_version": _dig(rp, "binding", "profile_version"),
        "fingerprint": _dig(rp, "binding", "runtime_behavioral_fingerprint_sha256"),
        "system_instruction_sha256": world.system_sha,
        "execution_profile": {"id": getattr(world.profile, "profile_id", None),
                              "mode": str(getattr(world.profile, "mode", None)),
                              "engine_ids": [str(e) for e in (getattr(world.profile, "engine_ids", ()) or ())]},
        "railway_deployment_id": world.deployment_id,
        "planned": {"passes": 1, "max_ive_calls": MAX_IVE_CALLS, "composer_calls": 0,
                    "sequential": True, "retries": 0, "replacements": 0},
        "start_checks": checks,
        "info": world.info,
    }


# ------------------------------------------------------------------ #
# the measurement pass
# ------------------------------------------------------------------ #
def _http_402(*details) -> bool:
    return any((d or {}).get("http_status") == 402 for d in details)


def check_turn(row: dict, calls: list, caps: list, misses: int):
    """Stop rules, in order. Returns (status, reason) or None."""
    if _http_402(row.get("error_detail"), *[c.get("error") for c in calls],
                 *[c.get("error") for c in caps]):
        return ST_402, f"HTTP 402 at index {row['index']}"
    refused = [c for c in caps if c.get("outcome") == "REFUSED"]
    if refused or row["other_calls"] or row.get("composition_attempted") \
            or len(row["ive_calls"]) > 1 \
            or any(c.get("thinking_config_sent") for c in row["ive_calls"]):
        return ST_GUARD, f"guard condition at index {row['index']}"
    # A generate() that failed before reaching the SDK has a capture but no tap row.
    ive_caps = [c for c in caps if c.get("label") == IVE_LABEL and c.get("outcome") != "REFUSED"]
    ok_calls = [c for c in row["ive_calls"] if c.get("outcome") == "OK"]
    ok_caps = [c for c in ive_caps if c.get("outcome") == "OK" and isinstance(c.get("text"), str)]
    if len(ive_caps) < len(row["ive_calls"]) or len(ok_caps) != len(ok_calls):
        return ST_CAPTURE, f"capture does not match the provider calls at index {row['index']}"
    if misses >= CONSECUTIVE_MISS_STOP:
        return ST_MISSES, f"{CONSECUTIVE_MISS_STOP} consecutive turns without a captured IVE output"
    return None


def run_capture(world: World, meta: dict, out_dir: str) -> dict:
    h, core = world.harness, world.core
    CALLS, CURRENT = h.CALLS, h.CURRENT
    os.makedirs(out_dir, exist_ok=False)
    ledger = open(os.path.join(out_dir, "h1cap_ledger.jsonl"), "x", encoding="utf-8")

    def emit(tag, obj):
        ledger.write(f"{tag} {json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)}\n")
        ledger.flush()
        os.fsync(ledger.fileno())

    # Composition is skipped through the Core's own no-composer path, in this process only.
    core._composer = None
    emit("H1_META", {**meta, "composer_detached": core._composer is None,
                     "utc_run_start": h._utc_now()})
    S = {"turns_run": 0, "turns_failed": 0, "ive_calls": 0, "ive_calls_ok": 0,
         "ive_calls_failed": 0, "captures_ok": 0, "reports_returned": 0,
         "report_raw_matches_capture": 0, "non_ive_calls": 0, "guard_refusals": 0,
         "composition_attempted_turns": 0, "status": None, "stop_reason": None}
    misses = 0
    stop = None
    for index, question in enumerate(world.questions):
        if sum(1 for c in CALLS if c.get("label") == IVE_LABEL) >= MAX_IVE_CALLS:
            stop = (ST_GUARD, f"IVE call cap {MAX_IVE_CALLS} reached before index {index}")
            break
        CURRENT["index"] = index
        first_call, first_cap = len(CALLS), len(CAPTURES)
        utc_start = h._utc_now()
        started = time.monotonic()
        error, error_detail = None, None
        try:
            result = core.ask(question)
        except Exception as exc:  # recorded, never hidden
            result, error = None, type(exc).__name__
            error_detail = h.safe_describe_exception(exc)
        row = {"index": index, "question": question,
               "turn_ms": round((time.monotonic() - started) * 1000.0, 1), "error": error,
               "error_detail": error_detail, "utc_start": utc_start, "utc_end": h._utc_now()}
        reports = []
        if result is not None:
            rendered = result.rendered or {}
            metrics = result.metrics or {}
            reports = list(getattr(result, "ive_reports", None) or [])
            row.update({
                "status": result.status,
                "error_stage": result.error_stage,
                "retrieval_ms": metrics.get("retrieval_latency_ms"),
                "context_characters": metrics.get("context_characters"),
                "context_documents": metrics.get("context_documents"),
                "evidence_ids": [f"{e.get('document_id')}::{e.get('chunk_id')}"
                                 for e in rendered.get("evidence") or []],
                "uncertainty_count": len((rendered.get("uncertainty") or {}).get("reported") or []),
                "composition_attempted": (metrics.get("composition") is not None
                                          or rendered.get("presentation") is not None),
            })
        calls, caps = CALLS[first_call:], CAPTURES[first_cap:]
        row["ive_calls"] = [c for c in calls if c.get("label") == IVE_LABEL]
        row["other_calls"] = [c for c in calls if c.get("label") != IVE_LABEL]
        row["captures"] = caps
        row["ive_reports"] = reports
        ok_caps = [c for c in caps if c.get("outcome") == "OK" and isinstance(c.get("text"), str)]
        raw = reports[0].get("raw_response") if reports and isinstance(reports[0], dict) else None
        row["capture_matches_report_raw"] = (ok_caps[-1]["text"] == raw
                                             if ok_caps and isinstance(raw, str) else None)
        misses = 0 if ok_caps else misses + 1
        stop = check_turn(row, calls, caps, misses)
        emit("H1_TURN", row)
        S["turns_run"] += 1
        S["turns_failed"] += int(result is None)
        S["ive_calls"] += len(row["ive_calls"])
        S["ive_calls_ok"] += sum(1 for c in row["ive_calls"] if c.get("outcome") == "OK")
        S["ive_calls_failed"] += sum(1 for c in row["ive_calls"] if c.get("outcome") != "OK")
        S["captures_ok"] += len(ok_caps)
        S["reports_returned"] += len(reports)
        S["report_raw_matches_capture"] += int(row["capture_matches_report_raw"] is True)
        S["non_ive_calls"] += len(row["other_calls"])
        S["guard_refusals"] += sum(1 for c in caps if c.get("outcome") == "REFUSED")
        S["composition_attempted_turns"] += int(bool(row.get("composition_attempted")))
        print(f"H1_PROGRESS {json.dumps({'index': index, 'captured': bool(ok_caps), 'utc': row['utc_end']})}",
              flush=True)
        if stop:
            break
    S["provider_calls_total"] = len(CALLS)
    S["status"], S["stop_reason"] = stop if stop else (ST_COMPLETE, None)
    S["utc_run_end"] = h._utc_now()
    emit("H1_SUMMARY", S)
    ledger.close()
    return S


def main() -> int:
    sys.path.insert(0, "/app")
    env = os.environ
    try:
        world = build_world(env)
        checks = start_checks(world)
        meta = build_meta(world, checks)
        if not all(checks.values()):
            raise H1Stop(f"start checks failed: {[k for k, v in checks.items() if not v]}")
    except H1Stop as stop:
        print(f"H1_STOP {json.dumps({'reason': str(stop), 'provider_calls': 0})}", flush=True)
        return 2
    except Exception as exc:  # wiring failed before any provider call
        print(f"H1_STOP {json.dumps({'reason': 'wiring error', 'exc_type': type(exc).__name__, 'provider_calls': 0})}",
              flush=True)
        return 2

    if env.get("H1_PREFLIGHT_ONLY") == "1":
        # every start check above passed; exit before the first provider call
        print(f"H1_PREFLIGHT {json.dumps({'ok': True, 'meta': meta, 'provider_calls': len(world.harness.CALLS)}, default=str)}",
              flush=True)
        return 0

    S = run_capture(world, meta, env["H1_OUT_DIR"])
    print(f"H1_DONE {json.dumps({'status': S['status'], 'ive_calls': S['ive_calls'], 'non_ive_calls': S['non_ive_calls'], 'captures_ok': S['captures_ok']})}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
