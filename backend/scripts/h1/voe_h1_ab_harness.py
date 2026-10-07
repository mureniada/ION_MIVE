"""H1 live A/B (C3/R4): paired IVE-only harness (voe_h1_ab_harness.py). PREPARED, NOT RUN.

Operator request 2026-10-07 18:31Z ("H1 LIVE A/B - PREPARE ONLY, DO NOT
EXECUTE"). Implements H1_AB_C3R4_PREREG.md: does capping the IVE's `concepts`
(maxItems 3) and `relations` (maxItems 4) through the structured-output schema
alone reduce IVE latency without degrading the report?

One Core.ask per pair, so retrieval and the Context Pack are shared by
construction:
  * The Core is built from the deployed settings exactly as in H1 Step 0
    (voe_h1_ive_capture.build_world, imported by sha256) inside the staging
    container. Composition is skipped in THIS process only (core._composer = None).
  * At the IVE call, a wrapper on GeminiBackend.generate makes TWO provider
    calls with the identical system and user prompt objects, in the
    predetermined order (h1_ab_score.expected_order: the 81 scheduled pairs
    alternate AB, BA, AB, ... in run order; a replacement keeps its slot's order):
        arm A: the unchanged module-level IVE_RESPONSE_SCHEMA object;
        arm B: a deep copy of it with only concepts.maxItems = 3 and
               relations.maxItems = 4 added (h1_ab_score.schema_b_from).
    Same backend object, model, system instruction and user prompt; no
    thinking config in either call; no new prompt instruction anywhere.
  * Arm A's result goes back to the Core, so the turn is the unchanged
    baseline turn. Arm B's text is normalized in-process with the app's own
    parse_json / normalize and the arguments the adapter uses; a B failure is
    wrapped exactly as the adapter and Core would wrap it, so both arms are
    classified by the same frozen rule. Arm A is normalized the same way and
    must equal the Core's own report (parity check).
  * Below the wrapper: the H1 Step 0 guard + capture (verbatim text, input
    digests; IVE call cap raised to the structural maximum) and the frozen E3
    tap (usage, SDK latency, sanitized errors).
  * A pass-through recorder on GeminiIVE.run keeps the admitted evidence ids
    (model_input.evidence[*].candidate_id, the CG-A1 basis) and the question.

Provider faults: the frozen classify_failure (voe_e3_index17_probe.py,
2b63a7e3...) and the frozen Health rule and constants of the v0.4/512
provider-aware reconfirmation orchestrator (voe_e3_pa_reconfirm.py,
7f242c00...), both imported unchanged by sha256. A PROVIDER_FAULT on either
arm invalidates the whole pair: wait 30 s, rerun the whole pair once in the
same order; a second fault makes it UNRESOLVED.

Run INSIDE the ION_MIVE staging container, new work dir /tmp/h1ab, detached:

    cd /tmp/h1ab && H1_E3_HARNESS_PATH=/tmp/h1ab/voe_e3_paired_replay.py \
      H1_QUESTIONS_PATH=/tmp/h1ab/e3q.json \
      H1AB_CAPTURE_PATH=/tmp/h1ab/voe_h1_ive_capture.py \
      H1AB_CLASSIFIER_PATH=/tmp/h1ab/voe_e3_index17_probe.py \
      H1AB_PA_PATH=/tmp/h1ab/voe_e3_pa_reconfirm.py \
      H1AB_SCORER_PATH=/tmp/h1ab/h1_ab_score.py \
      H1AB_PREREG_PATH=/tmp/h1ab/H1_AB_C3R4_PREREG.md H1AB_PREREG_SHA256=<frozen sha> \
      H1AB_OUT_DIR=/tmp/h1ab/out \
      python /tmp/h1ab/voe_h1_ab_harness.py > /tmp/h1ab/stdout.log 2> /tmp/h1ab/stderr.log

H1AB_PREFLIGHT_ONLY=1 runs every start check and exits before any provider call.
Output (H1AB_OUT_DIR must not exist): h1ab_ledger.jsonl = one H1AB_META line,
one H1AB_ATTEMPT line per pair attempt, one H1AB_SUMMARY line. stdout carries
one H1AB_PROGRESS line per attempt and a final H1AB_DONE / H1AB_STOP /
H1AB_PREFLIGHT line. Never prints secrets or the environment; reads
RAILWAY_DEPLOYMENT_ID by name only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import inspect
import json
import os
import sys
import time
from types import SimpleNamespace

AB_VERSION = "h1-ab-c3r4-v1"
EXPECTED_CAPTURE_SHA256 = "4284a5ce8176a5ebf6b712bc2a6896325a5c0aa597cc64b71c039f14b69dbfb7"
EXPECTED_CLASSIFIER_SHA256 = "2b63a7e32d5d8dfe888d1eaf49103b566743dd1165319c76103e61ce524eecb6"
EXPECTED_PA_SHA256 = "7f242c00e8014078bcc16f5abaf640dc0274e2214ac60bbb89043f2ea5b2207c"
EXPECTED_SCORER_SHA256 = "3e4866ec7ebf81bfc9c1283f3267d417a91bb7019d1f3cc9d5b18cf45a40a4e3"
EXPECTED_IVE_SYSTEM_SHA256 = "6b7f7a6b6e66f88c69880ca0a780d367ca6375055050d4e0f3cf9e6ddcc883f6"
# Deployed e6880e7 == repo (H1 Step 0.5, 12-file comparison).
EXPECTED_SOURCE_SHA256 = {
    "orchestrator": "73f8c89a83d9f102a34600318baae1a2e930d9f47442f8f67140d1d2e458fe4f",
    "gemini_backend": "af468211d38a87874323c5efff324a4f0457b264911f81b3fc0f2a1f365b1e43",
    "gemini_adapter": "89155a7bac3ba6741ab32caed4af0d00258e159c39fe2667beef3ab3d2bc7c4f",
    "ive_common": "d9af7362dea0c56b0d74b3c83e63bddf2c31084118ea0559b2e67d0151a12819",
}
ADAPTER_CALL = "system=ic.IVE_SYSTEM_PROMPT, user=prompt, schema=ic.IVE_RESPONSE_SCHEMA"
# 81 pairs x (primary + one replacement) x 2 arms: the most the frozen logic can ever make.
MAX_IVE_CALLS = 324

ST_COMPLETE = "COMPLETE"
ST_GUARD = "STOPPED_HARNESS_GUARD"
ST_CAPTURE = "STOPPED_HARNESS_CAPTURE"
ST_TURN = "INCONCLUSIVE_IVE_OR_TURN_NON_PROVIDER_FAILURE"
ST_402 = "STOPPED_HTTP_402"
ST_HEALTH = "INCONCLUSIVE_PROVIDER_HEALTH"
ST_SYSTEMATIC = "STOPPED_SYSTEMATIC_B_HARD_FAIL"

# The pair in progress: set by run_pair, read by the two wrappers.
AB: dict = {}


class H1ABStop(Exception):
    """A start check failed; no provider call has been or will be made."""


class H1ABGuardRefusal(RuntimeError):
    """An IVE call this experiment does not authorize, refused before the provider."""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_by_path(name: str, path: str, expected_sha: str):
    actual = sha256_file(path)
    if actual != expected_sha:
        raise H1ABStop(f"{name} sha256 mismatch: {actual}")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def reset_pair(index: int, order: str) -> None:
    AB.clear()
    AB.update({"index": index, "order": tuple(order), "adapter_calls": 0,
               "outcomes": {}, "model_input": None, "refused": None})


# ------------------------------------------------------------------ #
# wiring: the A/B wrapper above the Step 0 guard + capture
# ------------------------------------------------------------------ #
def install_ab(gbm, adapter_mod, ic, harness, cap, scorer) -> SimpleNamespace:
    """Install the dual-call wrapper on GeminiBackend.generate (above the Step 0
    capture, which sits above the E3 tap) and the model-input recorder on
    GeminiIVE.run. Neither changes what the Core sends or receives for arm A."""
    inner = gbm.GeminiBackend.generate
    if getattr(inner, "h1_capture", False) is not True:
        raise H1ABStop("the Step 0 capture must be installed below the A/B wrapper")
    schema_a = ic.IVE_RESPONSE_SCHEMA
    schema_b = scorer.schema_b_from(schema_a)

    def generate(self, *args, **kwargs):
        refusal = None
        if args or set(kwargs) != {"system", "user", "schema"}:
            refusal = "unexpected generate() call shape"
        elif not AB.get("order"):
            refusal = "no pair in progress"
        elif AB["adapter_calls"] >= 1:
            refusal = "a second IVE generate() in one pair"
        elif kwargs["schema"] is not schema_a:
            refusal = "the schema is not the module-level IVE schema object"
        if refusal is not None:
            AB["refused"] = refusal
            raise H1ABGuardRefusal(f"refused before the provider: {refusal}")
        AB["adapter_calls"] += 1
        system, user = kwargs["system"], kwargs["user"]
        for position, arm in enumerate(AB["order"]):
            first_call, first_cap = len(harness.CALLS), len(cap.CAPTURES)
            rec = {"position": position, "utc_start": harness._utc_now(), "refused": False}
            started = time.monotonic()
            try:
                result, exc = inner(self, system=system, user=user,
                                    schema=schema_a if arm == "A" else schema_b), None
            except cap.H1GuardRefusal as refused:
                AB["refused"] = str(refused)
                rec.update({"refused": True, "result": None, "exc": refused})
                result, exc = None, refused
            except Exception as error:  # never KeyboardInterrupt/SystemExit/GeneratorExit
                result, exc = None, error
            rec.update({"result": result, "exc": exc, "utc_end": harness._utc_now(),
                        "wrapper_ms": round((time.monotonic() - started) * 1000.0, 1),
                        "tap": list(harness.CALLS[first_call:]), "captures": list(cap.CAPTURES[first_cap:])})
            AB["outcomes"][arm] = rec
            if rec["refused"]:
                raise exc  # stop at once: no further provider call in this pair
        a = AB["outcomes"]["A"]
        if a["exc"] is not None:
            raise a["exc"]  # the identical object the adapter would have seen
        return a["result"]

    generate.h1ab = True
    generate.h1ab_inner = inner
    gbm.GeminiBackend.generate = generate

    original_run = adapter_mod.GeminiIVE.run

    def run(self, model_input):
        try:
            AB["model_input"] = {
                "question": model_input.question,
                "allowed_ids": [str(item.candidate_id) for item in model_input.evidence],
                "conversation_memory": getattr(model_input, "conversation_memory", None) is not None,
                "engine_id": self.engine_id, "provider": self.provider, "model": self.model,
            }
        except Exception:  # recording must never fail the call
            AB["model_input"] = {"telemetry_error": True}
        return original_run(self, model_input)

    run.h1ab = True
    adapter_mod.GeminiIVE.run = run
    return SimpleNamespace(schema_a=schema_a, schema_b=schema_b, inner=inner, generate=generate,
                           original_run=original_run, run=run)


# ------------------------------------------------------------------ #
# the adapter's handling, for an arm whose result the Core never saw
# ------------------------------------------------------------------ #
def wrap_like_core(error_cls, message: str, cause):
    try:
        raise error_cls(message, stage="gemini") from cause
    except error_cls as wrapped:
        return wrapped


def adapter_equivalent(outcome: dict, mi: dict, app):
    """GeminiIVE.run (adapter.py lines 52-76) and Core._run_engine's fallback
    (orchestrator.py lines 1142-1144), for one arm. Returns (report, None) or
    (None, the exception the Core would have raised)."""
    exc = outcome.get("exc")
    if exc is not None:
        return None, wrap_like_core(app.ProviderError, f"gemini call failed: {exc}", exc)
    result = outcome.get("result")
    try:
        usage = app.Usage(input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                          latency_ms=outcome.get("wrapper_ms"), usage_is_estimated=result.usage_is_estimated)
        raw = app.ic.parse_json(result.text)
        report = app.ic.normalize(raw, engine_id=mi["engine_id"], provider=mi["provider"], model=mi["model"],
                                  question=mi["question"], raw_text=result.text, usage=usage)
    except app.NormalizationError as invalid:
        return None, wrap_like_core(app.ProviderError, f"gemini produced invalid output: {invalid}", invalid)
    except Exception as other:  # escapes the adapter; Core._run_engine wraps it
        return None, wrap_like_core(app.ProviderError, f"gemini provider failed: {other}", other)
    return report, None


def _classify(d, exc) -> dict:
    cls, key, insufficient = d.runner.classify_failure(
        exc, provider_error_type=d.app.ProviderError, output_error_type=d.pa._NeverMatches,
        api_error_type=d.app.APIError)
    return {"classification": cls, "class_key": key, "telemetry_insufficient": insufficient,
            "exc_class": type(exc).__name__,
            "cause_class": type(exc.__cause__).__name__ if exc.__cause__ is not None else None}


# ------------------------------------------------------------------ #
# one pair attempt
# ------------------------------------------------------------------ #
def run_pair(d, index: int, question: str, pass_no: int, kind: str):
    h, cap = d.harness, d.cap
    order = d.scorer.expected_order(pass_no, index)
    reset_pair(index, order)
    h.CURRENT["index"] = index
    first_call, first_cap = len(h.CALLS), len(cap.CAPTURES)
    utc_start = h._utc_now()
    started = time.monotonic()
    result, turn_exc = None, None
    try:
        result = d.core.ask(question)
    except Exception as exc:  # recorded, never hidden
        turn_exc = exc
    row = {"pass": pass_no, "index": index, "question": question, "kind": kind,
           "expected_order": order, "order": "".join(AB["outcomes"]) or None,
           "turn_ms": round((time.monotonic() - started) * 1000.0, 1),
           "utc_start": utc_start, "utc_end": h._utc_now(),
           "error": type(turn_exc).__name__ if turn_exc is not None else None,
           "error_detail": h.safe_describe_exception(turn_exc) if turn_exc is not None else None}
    core_reports = []
    if result is not None:
        rendered = result.rendered or {}
        metrics = result.metrics or {}
        core_reports = list(getattr(result, "ive_reports", None) or [])
        row.update({
            "status": result.status, "error_stage": result.error_stage,
            "retrieval_ms": metrics.get("retrieval_latency_ms"),
            "context_characters": metrics.get("context_characters"),
            "context_documents": metrics.get("context_documents"),
            "evidence_ids": [f"{e.get('document_id')}::{e.get('chunk_id')}" for e in rendered.get("evidence") or []],
            "uncertainty_count": len((rendered.get("uncertainty") or {}).get("reported") or []),
            "composition_attempted": metrics.get("composition") is not None or rendered.get("presentation") is not None,
        })
    calls, caps = h.CALLS[first_call:], cap.CAPTURES[first_cap:]
    row["provider_calls"] = len(calls)
    row["other_calls"] = [c for c in calls if c.get("label") != cap.IVE_LABEL]
    row["guard_refusals"] = [c.get("refusal") for c in caps if c.get("outcome") == "REFUSED"] + (
        [AB["refused"]] if AB["refused"] else [])
    row["adapter_calls"] = AB["adapter_calls"]
    mi = AB.get("model_input")
    row["model_input"] = mi
    mi_ok = isinstance(mi, dict) and all(k in mi for k in ("question", "allowed_ids", "engine_id", "provider", "model"))

    arms, live, problems = {}, {}, []
    in_process = {}
    for arm in ("A", "B"):
        o = AB["outcomes"].get(arm)
        if o is None:
            arms[arm] = {"status": "NOT_RUN"}
            continue
        capt = (o.get("captures") or [{}])[-1]
        rec = {"position": o["position"], "utc_start": o["utc_start"], "utc_end": o["utc_end"],
               "wrapper_ms": o["wrapper_ms"], "input": capt.get("input"), "tap": o["tap"],
               "capture_outcome": capt.get("outcome"), "text": capt.get("text"),
               "text_digest": capt.get("text_digest"),
               "error": h.safe_describe_exception(o["exc"]) if o.get("exc") is not None else None}
        if o.get("refused"):
            rec["status"] = "REFUSED"
        elif not mi_ok:
            rec["status"] = "UNSCORED"
            problems.append("model input not recorded")
        else:
            report, exc = adapter_equivalent(o, mi, d.app)
            live[arm] = exc
            if exc is None:
                in_process[arm] = report.to_contract_dict()
                rec["status"] = "OK"
                rec["report"] = {k: v for k, v in in_process[arm].items() if k != "raw_response"}
                if report.raw_response != capt.get("text"):
                    problems.append(f"arm {arm} capture text differs from the provider text")
            else:
                rec["status"] = "CALL_FAILED" if o.get("exc") is not None else "INVALID_OUTPUT"
                rec["normalize_error"] = None if o.get("exc") is not None else h._sanitize(exc.__cause__)
            if o.get("exc") is None:
                ok_taps = [t for t in o["tap"] if t.get("outcome") == "OK"]
                if len(o["tap"]) != 1 or len(ok_taps) != 1 or capt.get("outcome") != "OK" \
                        or capt.get("text") != getattr(o.get("result"), "text", None):
                    problems.append(f"arm {arm} provider call not captured exactly once")
            elif len(o["tap"]) > 1:
                problems.append(f"arm {arm} has more than one provider-call row")
        arms[arm] = rec
    row["arms"] = arms
    # Parity: arm A handled here must match what the Core itself produced or raised.
    if "A" in in_process:
        # None when the turn failed after a valid IVE report (stop rule S1 decides that case)
        row["a_parity"] = (core_reports[0] == in_process["A"]) if core_reports else (
            None if turn_exc is not None else False)
    elif live.get("A") is not None and turn_exc is not None:
        row["a_parity"] = _classify(d, turn_exc)["class_key"] == _classify(d, live["A"])["class_key"]
    else:
        row["a_parity"] = None
    row["capture_problems"] = problems
    return row, turn_exc, live


def classify_ab(d, row: dict, turn_exc, live: dict) -> dict:
    """Per-call classification over the ordered call sequence of one attempt
    (the structure of the frozen Phase A classify_attempt, for two IVE arms)."""
    PF = d.pa.PF
    turn = _classify(d, turn_exc) if turn_exc is not None else None
    arms = {}
    for arm in ("A", "B"):
        status = row["arms"][arm]["status"]
        if status == "OK":
            arms[arm] = {"classification": "OK", "class_key": None, "telemetry_insufficient": False}
        elif live.get(arm) is not None:
            arms[arm] = _classify(d, live[arm])
        else:
            arms[arm] = {"classification": status, "class_key": None, "telemetry_insufficient": False}
    seq = []
    for arm in row.get("order") or "":
        a = arms[arm]
        for tap in row["arms"][arm].get("tap") or []:
            err = tap.get("error") or {}
            fault = a["classification"] == PF and tap.get("outcome") == "FAILED"
            seq.append({"who": arm, "provider_fault": fault, "class_key": a["class_key"] if fault else None,
                        "http_status": err.get("http_status"), "provider_status": err.get("provider_status"),
                        "exc_type": err.get("exc_type"), "outcome": tap.get("outcome"),
                        "utc_start": tap.get("utc_start"), "utc_end": tap.get("utc_end")})
    pf_classified = sum(1 for a in arms.values() if a["classification"] == PF)
    pf_calls = sum(1 for s in seq if s["provider_fault"])
    turn_pf = bool(turn and turn["classification"] == PF)
    return {"turn": turn, "arms": arms, "calls": seq,
            "pf_call_mismatch": pf_classified != pf_calls or (turn_pf and arms["A"]["classification"] != PF),
            "has_pf": pf_calls > 0 or pf_classified > 0 or turn_pf}


def stop_check(d, row: dict, c: dict, health):
    """Stop rules after each attempt, in order: harness guard, harness capture,
    then the frozen Phase A F1 (S1), F2 (S2), F3 (S3). Returns (status, reason) or None."""
    where = f"pass {row['pass']} index {row['index']} ({row['kind']})"
    PF = d.pa.PF
    taps = [t for arm in row["arms"].values() for t in arm.get("tap") or []]
    digests = {arm: rec.get("input") or {} for arm, rec in row["arms"].items() if rec.get("input")}
    guard = []
    if row["guard_refusals"]:
        guard.append("refusal")
    if row["other_calls"] or row.get("composition_attempted"):
        guard.append("non-IVE call or composition")
    if any(t.get("thinking_config_sent") for t in taps):
        guard.append("thinking config sent")
    if row["order"] is not None and len(row["order"]) == 2 and row["order"] != row["expected_order"]:
        guard.append("order")
    if len(digests) == 2:
        if any(digests["A"].get(p) != digests["B"].get(p) for p in ("system", "user")):
            guard.append("prompt differs between arms")
        if (digests["A"].get("schema") or {}).get("sha256") != d.scorer.EXPECTED_SCHEMA_A_SHA256 \
                or (digests["B"].get("schema") or {}).get("sha256") != d.scorer.EXPECTED_SCHEMA_B_SHA256:
            guard.append("request schema identity")
    if d.cap.schema_digest(d.app.ic.IVE_RESPONSE_SCHEMA)["sha256"] != d.scorer.EXPECTED_SCHEMA_A_SHA256:
        guard.append("module IVE schema changed")
    if guard:
        return ST_GUARD, f"guard ({', '.join(guard)}) at {where}"
    if row["capture_problems"] or row.get("a_parity") is False:
        return ST_CAPTURE, f"capture ({'; '.join(row['capture_problems']) or 'arm A parity'}) at {where}"
    # F1 (S1): an IVE or turn-level non-provider failure, or a turn without IVE arms
    if (c["turn"] is not None and c["turn"]["classification"] != PF) or \
            (c["turn"] is None and row["arms"]["A"]["status"] == "NOT_RUN"):
        return ST_TURN, f"non-provider turn failure at {where}"
    # F2 (S2): HTTP 402 on any call
    if any((t.get("error") or {}).get("http_status") == 402 for t in taps) or \
            (row.get("error_detail") or {}).get("http_status") == 402 or \
            any((rec.get("error") or {}).get("http_status") == 402 for rec in row["arms"].values()):
        return ST_402, f"HTTP 402 at {where}"
    # F3 (S3): the frozen provider-health rule over the ordered call sequence
    health.extend([s["provider_fault"] for s in c["calls"]])
    triggered = health.triggered()
    if triggered:
        return ST_HEALTH, triggered
    return None


# ------------------------------------------------------------------ #
# the programme: 3 passes x 27 questions, frozen whole-pair replacement
# ------------------------------------------------------------------ #
@dataclasses.dataclass
class Deps:
    harness: object     # frozen E3 tap module (CALLS, CURRENT, helpers)
    cap: object         # H1 Step 0 capture module (World, guard, CAPTURES)
    runner: object      # frozen classifier module
    pa: object          # frozen Phase A orchestrator module (Health, constants)
    scorer: object      # h1_ab_score module
    app: object         # SimpleNamespace(ic, ProviderError, NormalizationError, Usage, APIError)
    world: object
    wiring: object
    core: object
    questions: list
    sleep: object = time.sleep


def run_programme(d: Deps, meta: dict, out_dir: str) -> dict:
    h = d.harness
    os.makedirs(out_dir, exist_ok=False)
    ledger = open(os.path.join(out_dir, "h1ab_ledger.jsonl"), "x", encoding="utf-8")

    def emit(tag, obj):
        ledger.write(f"{tag} {json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)}\n")
        ledger.flush()
        os.fsync(ledger.fileno())

    # Composition is skipped through the Core's own no-composer path, in this process only.
    d.core._composer = None
    emit("H1AB_META", {**meta, "composer_detached": d.core._composer is None, "utc_run_start": h._utc_now()})
    health = d.pa.Health()
    S = {"scheduled": d.scorer.PASSES * len(d.questions), "primary_attempts": 0, "replacements": 0,
         "unresolved": [], "provider_faults": [], "non_provider_failures": [], "scored_pairs": 0,
         "hard_fail_pairs": 0, "status": None, "stop_reason": None}
    stop, streak = None, 0
    for pass_no in range(1, d.scorer.PASSES + 1):
        for index, question in enumerate(d.questions):
            for kind in ("primary", "replacement"):
                if kind == "primary":
                    S["primary_attempts"] += 1
                else:
                    S["replacements"] += 1
                    d.sleep(d.pa.REPLACEMENT_WAIT_S)
                row, turn_exc, live = run_pair(d, index, question, pass_no, kind)
                c = classify_ab(d, row, turn_exc, live)
                for arm in ("A", "B"):
                    row["arms"][arm]["classification"] = c["arms"][arm]
                stop = stop_check(d, row, c, health)
                invalidated = c["has_pf"]
                unresolved = invalidated and kind == "replacement"
                events = []
                if not invalidated:
                    events = d.scorer.pair_hard_fail_events(row)
                    streak = streak + 1 if events else 0
                    if stop is None and streak >= d.scorer.SYSTEMATIC_B_STOP:
                        stop = (ST_SYSTEMATIC, f"{streak} consecutive scored pairs with a hard-fail event "
                                               f"(last: pass {pass_no} index {index})")
                row.update({"classification": c, "invalidated": invalidated, "unresolved": unresolved,
                            "hard_fail_events": events, "stop": list(stop) if stop else None})
                emit("H1AB_ATTEMPT", row)
                for s in c["calls"]:
                    if s["provider_fault"]:
                        S["provider_faults"].append({"pass": pass_no, "index": index, "kind": kind, "who": s["who"],
                                                     "http": s["http_status"], "status": s["provider_status"],
                                                     "class_key": s["class_key"], "utc": s["utc_start"]})
                for who, a in [("turn", c["turn"])] + list(c["arms"].items()):
                    if a is not None and a["classification"] not in ("OK", d.pa.PF, "NOT_RUN"):
                        S["non_provider_failures"].append({"pass": pass_no, "index": index, "kind": kind,
                                                           "who": who, **a})
                if not invalidated:
                    S["scored_pairs"] += 1
                    S["hard_fail_pairs"] += int(bool(events))
                elif unresolved:
                    S["unresolved"].append({"pass": pass_no, "index": index})
                print(f"H1AB_PROGRESS {json.dumps({'pass': pass_no, 'index': index, 'kind': kind, 'invalidated': invalidated, 'events': len(events), 'utc': row['utc_end']})}",
                      flush=True)
                if stop or not invalidated:
                    break
            if stop:
                break
        if stop:
            break
    S["provider_calls"] = len(h.CALLS)
    S["ive_calls_attempted"] = sum(1 for c in d.cap.CAPTURES if c.get("outcome") != "REFUSED")
    S["status"], S["stop_reason"] = stop if stop else (ST_COMPLETE, None)
    S["utc_run_end"] = h._utc_now()
    emit("H1AB_SUMMARY", S)
    ledger.close()
    return S


# ------------------------------------------------------------------ #
# start checks, meta, entry point
# ------------------------------------------------------------------ #
def ab_start_checks(d: Deps) -> dict:
    """A/B-specific checks, after the 19 Step 0 checks; all run before any provider call."""
    ic, info, w = d.app.ic, d.world.info, d.wiring
    canonical, scorer = d.scorer.canonical, d.scorer
    adapter_src = inspect.getsource(w.original_run)
    concepts_a = ic.IVE_RESPONSE_SCHEMA["properties"]["concepts"]
    relations_a = ic.IVE_RESPONSE_SCHEMA["properties"]["relations"]
    passes, n_q = range(1, d.scorer.PASSES + 1), range(len(d.questions))
    slots = [d.scorer.expected_order(p, i) for p in passes for i in n_q]
    return {
        "schema_a_sha": scorer.sha256_text(canonical(ic.IVE_RESPONSE_SCHEMA)) == scorer.EXPECTED_SCHEMA_A_SHA256
        == (info.get("ive_response_schema") or {}).get("sha256"),
        "schema_b_sha": scorer.sha256_text(canonical(w.schema_b)) == scorer.EXPECTED_SCHEMA_B_SHA256,
        "schema_b_diff_exactly_two_caps": scorer.json_diff(ic.IVE_RESPONSE_SCHEMA, w.schema_b) == scorer.EXPECTED_B_DIFF,
        "schema_b_is_a_deep_copy": w.schema_b is not ic.IVE_RESPONSE_SCHEMA
        and w.schema_b["properties"] is not ic.IVE_RESPONSE_SCHEMA["properties"]
        and w.schema_b["properties"]["concepts"] is not concepts_a
        and w.schema_b["properties"]["relations"] is not relations_a,
        "schema_a_has_no_caps": "maxItems" not in concepts_a and "maxItems" not in relations_a,
        "wrapper_sends_module_schema_for_a": w.schema_a is ic.IVE_RESPONSE_SCHEMA,
        "ive_system_prompt": (info.get("ive_system_prompt") or {}).get("sha256") == EXPECTED_IVE_SYSTEM_SHA256,
        "source_files": info.get("file_sha256") == EXPECTED_SOURCE_SHA256,
        "ive_backend_label": info.get("ive_backend_label") == d.cap.IVE_LABEL,
        "ive_backend_no_thinking_budget": info.get("ive_backend_thinking_budget") is None
        and _ive_backend(d) is not None,
        "adapter_call_shape": ADAPTER_CALL in adapter_src,
        "ab_wrapper_installed": d.world.gbm.GeminiBackend.generate is w.generate
        and getattr(w.inner, "h1_capture", False) is True,
        "model_input_recorder_installed": getattr(_adapter_class(d), "run", None) is w.run,
        "ive_call_cap": d.cap.MAX_IVE_CALLS == MAX_IVE_CALLS,
        "frozen_replacement_rule": d.pa.REPLACEMENT_WAIT_S == 30.0 and d.pa.HEALTH_CONSECUTIVE == 3
        and d.pa.HEALTH_WINDOW == 20 and d.pa.HEALTH_WINDOW_MAX == 4
        and d.pa.PF == d.runner.PROVIDER_FAULT,
        "plan_81_pairs": d.scorer.PASSES * len(d.questions) == d.scorer.SCHEDULED_PAIRS == 81,
        "order_alternates_and_balances": slots[:1] == ["AB"] and all(x != y for x, y in zip(slots, slots[1:]))
        and all({d.scorer.expected_order(p, i) for p in passes} == {"AB", "BA"} for i in n_q),
        "zero_provider_calls": len(d.harness.CALLS) == 0 and len(d.cap.CAPTURES) == 0,
    }


def _ive_backend(d):
    return d.cap._dig(d.core, "_model_gateway", "_engines", "gemini", "_backend")


def _adapter_class(d):
    engine = d.cap._dig(d.core, "_model_gateway", "_engines", "gemini")
    return type(engine) if engine is not None else None


def build_meta(d: Deps, checks: dict, prereg_sha: str | None) -> dict:
    base = d.cap.build_meta(d.world, checks)
    try:
        own_sha = sha256_file(os.path.abspath(__file__))
    except Exception:
        own_sha = None
    base.update({
        "ab_version": AB_VERSION, "ab_harness_sha256": own_sha, "prereg_sha256": prereg_sha,
        "capture_module_sha256": EXPECTED_CAPTURE_SHA256, "e3_tap_sha256": d.cap.EXPECTED_HARNESS_SHA256,
        "classifier_sha256": EXPECTED_CLASSIFIER_SHA256, "phase_a_orchestrator_sha256": EXPECTED_PA_SHA256,
        "scorer_sha256": EXPECTED_SCORER_SHA256,
        "schema_a": d.wiring.schema_a, "schema_b": d.wiring.schema_b,
        "schema_a_sha256": d.scorer.EXPECTED_SCHEMA_A_SHA256, "schema_b_sha256": d.scorer.EXPECTED_SCHEMA_B_SHA256,
        "planned": {"passes": d.scorer.PASSES, "questions": len(d.questions), "pairs": d.scorer.SCHEDULED_PAIRS,
                    "order": "AB when (pass - 1) * 27 + index is even, else BA; a replacement keeps its slot's order",
                    "ive_calls_per_pair": 2, "max_ive_calls": MAX_IVE_CALLS, "composer_calls": 0,
                    "sequential": True, "replacement_wait_s": d.pa.REPLACEMENT_WAIT_S,
                    "health": [d.pa.HEALTH_CONSECUTIVE, d.pa.HEALTH_WINDOW, d.pa.HEALTH_WINDOW_MAX],
                    "systematic_b_stop": d.scorer.SYSTEMATIC_B_STOP},
    })
    base.pop("capture_version", None)
    base["capture_module_version"] = d.cap.CAPTURE_VERSION
    return base


def build_deps(env) -> tuple:
    """Container wiring. No provider call: every SDK client is created lazily."""
    cap = load_by_path("h1_capture", env["H1AB_CAPTURE_PATH"], EXPECTED_CAPTURE_SHA256)
    runner = load_by_path("e3_classifier", env["H1AB_CLASSIFIER_PATH"], EXPECTED_CLASSIFIER_SHA256)
    pa = load_by_path("e3pa_orchestrator", env["H1AB_PA_PATH"], EXPECTED_PA_SHA256)
    scorer = load_by_path("h1_ab_score", env["H1AB_SCORER_PATH"], EXPECTED_SCORER_SHA256)
    cap.MAX_IVE_CALLS = MAX_IVE_CALLS
    world = cap.build_world(env)
    step0 = cap.start_checks(world)
    import app.modules.gemini_ive.adapter as gadapter
    import app.modules.ive_common as ic
    from app.core.errors import NormalizationError, ProviderError
    from app.core.models import Usage
    from google.genai.errors import APIError

    return assemble(world, cap, runner, pa, scorer, gadapter, step0,
                    SimpleNamespace(ic=ic, ProviderError=ProviderError, NormalizationError=NormalizationError,
                                    Usage=Usage, APIError=APIError))


def assemble(world, cap, runner, pa, scorer, gadapter, step0: dict, app) -> tuple:
    wiring = install_ab(world.gbm, gadapter, app.ic, world.harness, cap, scorer)
    d = Deps(harness=world.harness, cap=cap, runner=runner, pa=pa, scorer=scorer, app=app,
             world=world, wiring=wiring, core=world.core, questions=world.questions)
    checks = {**{f"s0_{k}": v for k, v in step0.items()}, **ab_start_checks(d)}
    return d, checks


def main() -> int:
    sys.path.insert(0, "/app")
    env = os.environ
    try:
        prereg_sha = sha256_file(env["H1AB_PREREG_PATH"])
        if prereg_sha != env["H1AB_PREREG_SHA256"]:
            raise H1ABStop(f"prereg sha256 mismatch: {prereg_sha}")
        d, checks = build_deps(env)
        meta = build_meta(d, checks, prereg_sha)
        if not all(checks.values()):
            raise H1ABStop(f"start checks failed: {[k for k, v in checks.items() if not v]}")
    except Exception as exc:  # nothing has reached the provider
        reason = str(exc) if type(exc).__name__ in ("H1ABStop", "H1Stop") else "wiring error"
        print(f"H1AB_STOP {json.dumps({'reason': reason, 'exc_type': type(exc).__name__, 'provider_calls': 0})}",
              flush=True)
        return 2

    if env.get("H1AB_PREFLIGHT_ONLY") == "1":
        # every start check above passed; exit before the first provider call
        print(f"H1AB_PREFLIGHT {json.dumps({'ok': True, 'meta': meta, 'provider_calls': len(d.harness.CALLS)}, default=str)}",
              flush=True)
        return 0

    S = run_programme(d, meta, env["H1AB_OUT_DIR"])
    print(f"H1AB_DONE {json.dumps({'status': S['status'], 'scored_pairs': S['scored_pairs'], 'provider_calls': S['provider_calls'], 'hard_fail_pairs': S['hard_fail_pairs']})}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
