"""H1 live A/B (C3/R4) offline scorer and analyzer (h1_ab_score.py). Stdlib only.

Operator request 2026-10-07 18:31Z ("H1 LIVE A/B - PREPARE ONLY, DO NOT
EXECUTE"). Implements the scoring and the ordered verdict of
H1_AB_C3R4_PREREG.md. It reads files only: it makes no provider call and
imports nothing from the application.

    python h1_ab_score.py score    <h1ab_ledger.jsonl> <out_prefix>
    python h1_ab_score.py baseline <h1cap_ledger.jsonl> <out.json>

`score` reads the A/B ledger written by voe_h1_ab_harness.py and writes
<out_prefix>_summary.json (every number, every endpoint state and the verdict)
and <out_prefix>_pairs.csv (one row per scored pair).

`baseline` reads the H1 Step 0 capture ledger (27 unchanged IVE reports) and
writes the attribution and schema profile of the current IVE. That profile
sets the chance that the paired attribution rule (G3) fires on noise alone.

The harness imports this module (by sha256) for `schema_b_from` and
`pair_hard_fail_events`, so the request schema, the run-time systematic-failure
stop and the offline verdict all come from the same code and the same data.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import random
import re
import sys

SCORER_VERSION = "h1-ab-score-v1"

# The unchanged v0.4 IVE provider schema (app.modules.ive_common.IVE_RESPONSE_SCHEMA,
# repo and e6880e7: ive_common.py sha256 d9af7362...2819), canonical JSON.
SCHEMA_A_CANONICAL = (
    '{"additionalProperties":false,"properties":{"abstract":{"type":"string"},"claims":{"items":'
    '{"additionalProperties":false,"properties":{"claim_id":{"type":"string"},"confidence":{"type":'
    '"number"},"evidence_document_ids":{"items":{"type":"string"},"type":"array"},"statement":{"type"'
    ':"string"}},"required":["claim_id","statement","evidence_document_ids","confidence"],"type":'
    '"object"},"type":"array"},"concepts":{"items":{"additionalProperties":false,"properties":'
    '{"description":{"type":"string"},"name":{"type":"string"}},"required":["name","description"],'
    '"type":"object"},"type":"array"},"confidence":{"type":"number"},"highlights":{"items":{"type":'
    '"string"},"type":"array"},"relations":{"items":{"additionalProperties":false,"properties":'
    '{"evidence_document_ids":{"items":{"type":"string"},"type":"array"},"relation":{"type":"string"},'
    '"source":{"type":"string"},"target":{"type":"string"}},"required":["source","relation","target",'
    '"evidence_document_ids"],"type":"object"},"type":"array"},"uncertainty":{"items":{"type":"string"'
    '},"type":"array"}},"required":["abstract","highlights","claims","concepts","relations",'
    '"uncertainty","confidence"],"type":"object"}'
)
EXPECTED_SCHEMA_A_SHA256 = "e4e577d629a3b7bc1309b22a45f6a698db2b747b403601e7cb1c5b288f39e5d8"
# Arm B: arm A plus exactly these two keywords. Nothing else differs.
CAP = {"concepts": 3, "relations": 4}
EXPECTED_SCHEMA_B_SHA256 = "dbe6bc784763fc9b2a555b991209e4cc66bbbf52879794fae54c5b39a3a0074e"

PASSES = 3
N_QUESTIONS = 27
SCHEDULED_PAIRS = PASSES * N_QUESTIONS

# ---- preregistered analysis constants (H1_AB_C3R4_PREREG.md section 8) ----
SEED = 20261006
RESAMPLES = 10_000
CI_LEVEL = 0.95
# Non-inferiority margins on B - A (PROPOSED in the prereg, frozen with it).
MARGIN_CLAIM_COUNT = 0.5           # claims per report
MARGIN_EVIDENCE_COVERAGE = 0.05    # share of the turn's admitted evidence ids cited by claims
MARGIN_CLAIM_CONTENT = 0.10        # cross-arm minus within-A claim-statement similarity
MARGIN_UNCERTAINTY_COUNT = 0.25    # uncertainty items per report
MARGIN_UNCERTAINTY_CONTENT = 0.10  # cross-arm minus within-A uncertainty similarity
MARGIN_CONFIDENCE = 0.05           # overall report confidence, two-sided equivalence
LATENCY_MATERIAL_MS = 500.0        # operator's materiality threshold for the median gain
WARNING_SIGN_TEST_ALPHA = 0.05
# Run-time stop S4 (PROPOSED): this many consecutive scored pairs with a hard-fail event.
SYSTEMATIC_B_STOP = 3
# gemini-2.5-pro list price (verified 2026-10-06), prompts <= 200k tokens. ESTIMATED cost only.
PRICE_INPUT_PER_M = 1.25
PRICE_OUTPUT_PER_M = 10.0          # visible + thinking

# Harness run statuses (voe_h1_ab_harness.py).
ST_COMPLETE = "COMPLETE"
ST_GUARD = "STOPPED_HARNESS_GUARD"
ST_CAPTURE = "STOPPED_HARNESS_CAPTURE"
ST_TURN = "INCONCLUSIVE_IVE_OR_TURN_NON_PROVIDER_FAILURE"
ST_402 = "STOPPED_HTTP_402"
ST_HEALTH = "INCONCLUSIVE_PROVIDER_HEALTH"
ST_SYSTEMATIC = "STOPPED_SYSTEMATIC_B_HARD_FAIL"

DEFECTS = ("STRAY_CLAIM_ID", "STRAY_RELATION_ID", "CLAIM_WITHOUT_EVIDENCE")


# ------------------------------------------------------------------ #
# schemas
# ------------------------------------------------------------------ #
def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def schema_b_from(schema_a: dict) -> dict:
    """Arm B's request schema: a deep copy of arm A's with only the two caps added.
    The argument is never modified (the copy is made first)."""
    b = copy.deepcopy(schema_a)
    b["properties"]["concepts"]["maxItems"] = CAP["concepts"]
    b["properties"]["relations"]["maxItems"] = CAP["relations"]
    return b


def json_diff(x, y, path: str = "") -> list:
    """Structural differences between two JSON values, as (kind, path, ...) tuples."""
    out = []
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            p = f"{path}/{k}"
            if k not in x:
                out.append(("added", p, y[k]))
            elif k not in y:
                out.append(("removed", p, x[k]))
            else:
                out.extend(json_diff(x[k], y[k], p))
    elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
        for i, (a, b) in enumerate(zip(x, y)):
            out.extend(json_diff(a, b, f"{path}/{i}"))
    elif type(x) is not type(y) or x != y:
        out.append(("changed", path, x, y))
    return out


EXPECTED_B_DIFF = [("added", "/properties/concepts/maxItems", CAP["concepts"]),
                   ("added", "/properties/relations/maxItems", CAP["relations"])]

SCHEMA_A = json.loads(SCHEMA_A_CANONICAL)
SCHEMA_B = schema_b_from(SCHEMA_A)
if sha256_text(canonical(SCHEMA_A)) != EXPECTED_SCHEMA_A_SHA256 \
        or sha256_text(canonical(SCHEMA_B)) != EXPECTED_SCHEMA_B_SHA256 \
        or json_diff(SCHEMA_A, SCHEMA_B) != EXPECTED_B_DIFF:
    raise RuntimeError("embedded IVE schema identity check failed")

_SUPPORTED_KEYWORDS = frozenset({"type", "properties", "required", "additionalProperties",
                                 "items", "maxItems", "minItems"})


def _type_ok(value, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    raise ValueError(f"unsupported type {name!r}")


def schema_violations(instance, schema: dict, path: str = "") -> list:
    """(code, path) for every violation of `schema`. Implements exactly the
    keywords the IVE request schemas use, and refuses any other keyword."""
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        raise ValueError(f"unsupported schema keywords {sorted(unknown)}")
    if "type" in schema and not _type_ok(instance, schema["type"]):
        return [("WRONG_TYPE", path or "/")]
    out = []
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                out.append(("MISSING_REQUIRED", f"{path}/{key}"))
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    out.append(("EXTRA_PROPERTY", f"{path}/{key}"))
        for key, sub in props.items():
            if key in instance:
                out.extend(schema_violations(instance[key], sub, f"{path}/{key}"))
    if isinstance(instance, list):
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            out.append(("MAX_ITEMS", path or "/"))
        if "minItems" in schema and len(instance) < schema["minItems"]:
            out.append(("MIN_ITEMS", path or "/"))
        if "items" in schema:
            for i, item in enumerate(instance):
                out.extend(schema_violations(item, schema["items"], f"{path}/{i}"))
    return out


def parse_like_app(text):
    """The logic of app.modules.ive_common.parse_json (repo and e6880e7), with
    ValueError in place of NormalizationError."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        # drop an optional leading language tag line
        if "\n" in s:
            first, rest = s.split("\n", 1)
            if first.strip().lower() in {"json", ""}:
                s = rest
    data = json.loads(s)
    if not isinstance(data, dict):
        raise ValueError("Provider output must be a JSON object.")
    return data


# ------------------------------------------------------------------ #
# report features
# ------------------------------------------------------------------ #
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(text) -> frozenset:
    return frozenset(_WORD.findall(text.casefold())) if isinstance(text, str) else frozenset()


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def smbm(xs, ys) -> float:
    """Symmetric mean best-match token Jaccard between two lists of strings.
    Two empty lists match (1.0); one empty list matches nothing (0.0)."""
    xs, ys = list(xs or []), list(ys or [])
    if not xs and not ys:
        return 1.0
    if not xs or not ys:
        return 0.0
    tx, ty = [tokens(x) for x in xs], [tokens(y) for y in ys]
    fwd = sum(max(jaccard(a, b) for b in ty) for a in tx) / len(tx)
    bwd = sum(max(jaccard(b, a) for a in tx) for b in ty) / len(ty)
    return (fwd + bwd) / 2.0


def _ids(value) -> list:
    return [str(x) for x in (value or []) if isinstance(x, (str, int, float))]


def report_features(report: dict, allowed) -> dict:
    """Per-arm features of a normalized IVE report (the app's contract dict).
    `allowed` is the turn's admitted model-context evidence ids (CG-A1 basis);
    None when unknown, in which case the stray-id checks are not evaluated."""
    claims = [c for c in report.get("claims") or [] if isinstance(c, dict)]
    relations = [r for r in report.get("relations") or [] if isinstance(r, dict)]
    claim_ids, relation_ids, no_evidence = set(), set(), 0
    for c in claims:
        ids = _ids(c.get("evidence_document_ids"))
        no_evidence += int(not ids)
        claim_ids.update(ids)
    for r in relations:
        relation_ids.update(_ids(r.get("evidence_document_ids")))
    uncertainty = [u for u in report.get("uncertainty") or [] if isinstance(u, str)]
    highlights = [h for h in report.get("highlights") or [] if isinstance(h, str)]
    defects = set()
    if no_evidence:
        defects.add("CLAIM_WITHOUT_EVIDENCE")
    f = {
        "claims": len(claims),
        "claim_statements": [str(c.get("statement", "")) for c in claims],
        "claim_confidences": [c.get("confidence") for c in claims],
        "claims_without_evidence": no_evidence,
        "claim_ids": sorted(claim_ids),
        "relation_ids": sorted(relation_ids),
        "relation_only_ids": sorted(relation_ids - claim_ids),
        "guard_ids": sorted(claim_ids | relation_ids),
        "uncertainty": uncertainty,
        "uncertainty_count": len(uncertainty),
        "uncertainty_chars": sum(len(u) for u in uncertainty),
        "confidence": report.get("confidence"),
        "abstract": report.get("abstract") if isinstance(report.get("abstract"), str) else "",
        "highlights": highlights,
        "concepts": len([c for c in report.get("concepts") or [] if isinstance(c, dict)]),
        "relations": len(relations),
        "allowed_known": allowed is not None,
        "coverage": None, "stray_claim_ids": None, "stray_relation_ids": None, "cga1_would_pass": None,
    }
    if allowed is not None:
        allowed_set = {str(a) for a in allowed}
        stray_c, stray_r = sorted(claim_ids - allowed_set), sorted(relation_ids - allowed_set)
        if stray_c:
            defects.add("STRAY_CLAIM_ID")
        if stray_r:
            defects.add("STRAY_RELATION_ID")
        f.update({"coverage": (len(claim_ids & allowed_set) / len(allowed_set)) if allowed_set else None,
                  "stray_claim_ids": stray_c, "stray_relation_ids": stray_r,
                  "cga1_would_pass": not stray_c and not stray_r})
    f["defects"] = sorted(defects)
    return f


def arm_view(arm, schema: dict, allowed) -> dict:
    """Everything the scorer derives from one recorded arm."""
    arm = arm or {}
    status = arm.get("status")
    text = arm.get("text")
    raw, violations = None, []
    if isinstance(text, str):
        try:
            raw = parse_like_app(text)
        except ValueError:
            violations = [("UNPARSEABLE", "/")]
        else:
            violations = schema_violations(raw, schema)
    report = arm.get("report")
    ok = status == "OK" and isinstance(report, dict)
    taps = arm.get("tap") or []
    tap = taps[-1] if taps else {}
    return {
        "ok": ok,
        "status": status,
        "class_key": (arm.get("classification") or {}).get("class_key"),
        "violations": violations,
        "raw_counts": {k: (len(raw[k]) if isinstance(raw, dict) and isinstance(raw.get(k), list) else None)
                       for k in ("concepts", "relations")},
        "key_order": list(raw) if isinstance(raw, dict) else None,
        "features": report_features(report, allowed) if ok else None,
        "tap": tap,
        "tap_rows": len(taps),
    }


def pair_hard_fail_events(row: dict) -> list:
    """Hard-fail events of one scored pair (prereg section 7, G1-G3). B-only by
    construction: a pair whose arm A did not succeed carries no B event (only-A
    and both-failed pairs are excluded and reported; S1 stops the run)."""
    allowed = (row.get("model_input") or {}).get("allowed_ids")
    arms = row.get("arms") or {}
    a = arm_view(arms.get("A"), SCHEMA_A, allowed)
    b = arm_view(arms.get("B"), SCHEMA_B, allowed)
    if not a["ok"]:
        return []
    if not b["ok"]:
        return [{"code": "G1", "detail": f"B {b['status']}: {b['class_key']}"}]
    events = []
    a_codes = {code for code, _ in a["violations"]}
    for code, path in b["violations"]:
        if code == "MAX_ITEMS" or code not in a_codes:
            events.append({"code": "G2", "detail": f"{code} {path}"})
    for defect in sorted(set(b["features"]["defects"]) - set(a["features"]["defects"])):
        events.append({"code": "G3", "detail": defect})
    return events


# ------------------------------------------------------------------ #
# statistics
# ------------------------------------------------------------------ #
def quantile(sorted_values: list, q: float):
    """Linear interpolation between closest ranks (numpy's default method)."""
    n = len(sorted_values)
    if n == 0:
        return None
    pos = q * (n - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def mean(values: list):
    return sum(values) / len(values) if values else None


def median(values: list):
    return quantile(sorted(values), 0.5)


def dist(values: list) -> dict:
    v = sorted(x for x in values if isinstance(x, (int, float)) and not isinstance(x, bool))
    if not v:
        return {"n": 0}
    return {"n": len(v), "min": v[0], "p10": quantile(v, 0.10), "p25": quantile(v, 0.25),
            "median": quantile(v, 0.5), "p75": quantile(v, 0.75), "p90": quantile(v, 0.90),
            "max": v[-1], "mean": sum(v) / len(v)}


def cluster_bootstrap(clusters: list, stat, *, seed: int = SEED, resamples: int = RESAMPLES):
    """Point estimate on the pooled values and a percentile CI from resampling
    whole clusters (questions) with replacement. Each call seeds its own RNG,
    so an endpoint's interval does not depend on the order endpoints run."""
    clusters = [list(c) for c in clusters if c]
    if not clusters:
        return None, (None, None)
    est = stat([v for c in clusters for v in c])
    rng = random.Random(seed)
    n = len(clusters)
    stats = []
    for _ in range(resamples):
        sample = []
        for _ in range(n):
            sample.extend(clusters[rng.randrange(n)])
        stats.append(stat(sample))
    stats.sort()
    tail = (1.0 - CI_LEVEL) / 2.0
    return est, (quantile(stats, tail), quantile(stats, 1.0 - tail))


def sign_test(n_plus: int, n_minus: int) -> float:
    """Exact two-sided binomial sign test (ties excluded by the caller)."""
    n = n_plus + n_minus
    if n == 0:
        return 1.0
    k = min(n_plus, n_minus)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def ni_state(ci, margin: float) -> str:
    lo, hi = ci
    if lo is None:
        return "NOT_EVALUABLE"
    if lo > -margin:
        return "NONINFERIOR"
    if hi < -margin:
        return "INFERIOR"
    return "NOT_SHOWN"


def equivalence_state(ci, margin: float) -> str:
    lo, hi = ci
    if lo is None:
        return "NOT_EVALUABLE"
    if -margin < lo and hi < margin:
        return "EQUIVALENT"
    if lo > margin or hi < -margin:
        return "DIVERGENT"
    return "NOT_SHOWN"


# ------------------------------------------------------------------ #
# ledger
# ------------------------------------------------------------------ #
def read_ledger(path: str) -> dict:
    """Tagged JSON lines. A trailing partial line (a crash mid-write) is kept
    out and reported, never repaired."""
    out = {"meta": [], "attempts": [], "summary": [], "bad_lines": 0, "other": 0}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            tag, _, payload = line.rstrip("\n").partition(" ")
            try:
                obj = json.loads(payload)
            except ValueError:
                out["bad_lines"] += 1
                continue
            if tag == "H1AB_META":
                out["meta"].append(obj)
            elif tag == "H1AB_ATTEMPT":
                out["attempts"].append(obj)
            elif tag == "H1AB_SUMMARY":
                out["summary"].append(obj)
            else:
                out["other"] += 1
    return out


def expected_order(index: int) -> str:
    return "AB" if index % 2 == 0 else "BA"


def scored_set(attempts: list) -> dict:
    """Prereg section 6: per scheduled (pass, index) the primary if it has no
    PROVIDER_FAULT, else the replacement if it has none, else UNRESOLVED."""
    by_key: dict = {}
    for att in attempts:
        by_key.setdefault((att.get("pass"), att.get("index")), []).append(att)
    scored, unresolved, inconsistent = {}, [], []
    for key, atts in sorted(by_key.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or 0)):
        kinds = [a.get("kind") for a in atts]
        if kinds not in (["primary"], ["primary", "replacement"]):
            inconsistent.append({"pass": key[0], "index": key[1], "kinds": kinds})
        chosen = None
        for a in atts:
            has_pf = bool((a.get("classification") or {}).get("has_pf"))
            calls_pf = any(c.get("provider_fault") for c in (a.get("classification") or {}).get("calls") or [])
            if bool(a.get("invalidated")) != has_pf or (calls_pf and not has_pf):
                inconsistent.append({"pass": key[0], "index": key[1], "kind": a.get("kind"),
                                     "reason": "invalidated flag disagrees with the PF classification"})
            if not has_pf:
                chosen = a
                break
        if chosen is None:
            unresolved.append({"pass": key[0], "index": key[1]})
        else:
            scored[key] = chosen
    return {"scored": scored, "unresolved": unresolved, "inconsistent": inconsistent,
            "attempted_keys": sorted(by_key)}


# ------------------------------------------------------------------ #
# scoring
# ------------------------------------------------------------------ #
def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def integrity(meta: dict, attempts: list, views: dict) -> dict:
    """Checks that can only fail on a harness defect. Any failure makes the
    result INCONCLUSIVE (HARNESS_INTEGRITY)."""
    problems = []
    if sha256_text(canonical(meta.get("schema_a") or {})) != EXPECTED_SCHEMA_A_SHA256:
        problems.append("META schema_a differs from the preregistered arm-A schema")
    if sha256_text(canonical(meta.get("schema_b") or {})) != EXPECTED_SCHEMA_B_SHA256:
        problems.append("META schema_b differs from the preregistered arm-B schema")
    for att in attempts:
        where = f"pass {att.get('pass')} index {att.get('index')} {att.get('kind')}"
        arms = att.get("arms") or {}
        if att.get("order") is not None and att.get("order") != expected_order(att.get("index", 0)):
            problems.append(f"{where}: order {att.get('order')} != {expected_order(att.get('index', 0))}")
        digests = {arm: (rec or {}).get("input") or {} for arm, rec in arms.items()}
        if {"A", "B"} <= set(digests) and all(digests[x] for x in ("A", "B")):
            for part in ("system", "user"):
                if digests["A"].get(part) != digests["B"].get(part):
                    problems.append(f"{where}: {part} prompt differs between arms")
            if (digests["A"].get("schema") or {}).get("sha256") != EXPECTED_SCHEMA_A_SHA256:
                problems.append(f"{where}: arm A request schema is not the preregistered schema")
            if (digests["B"].get("schema") or {}).get("sha256") != EXPECTED_SCHEMA_B_SHA256:
                problems.append(f"{where}: arm B request schema is not the preregistered schema")
        for arm, rec in arms.items():
            for tap in (rec or {}).get("tap") or []:
                if tap.get("thinking_config_sent"):
                    problems.append(f"{where}: arm {arm} sent a thinking config")
        if att.get("a_parity") is False:
            problems.append(f"{where}: in-process normalization of arm A differs from the Core's")
    for key, (a, b) in views.items():
        for arm, v in (("A", a), ("B", b)):
            if v["status"] in ("OK", "INVALID_OUTPUT") and v["tap_rows"] != 1:
                problems.append(f"pass {key[0]} index {key[1]}: arm {arm} has {v['tap_rows']} provider-call rows")
    return {"ok": not problems, "problems": problems[:50], "problem_count": len(problems)}


def score(ledger_path: str) -> dict:
    led = read_ledger(ledger_path)
    meta = led["meta"][0] if led["meta"] else {}
    summary = led["summary"][-1] if led["summary"] else {}
    attempts = led["attempts"]
    ss = scored_set(attempts)
    status = summary.get("status")

    views, events = {}, {}
    for key, row in ss["scored"].items():
        allowed = (row.get("model_input") or {}).get("allowed_ids")
        arms = row.get("arms") or {}
        views[key] = (arm_view(arms.get("A"), SCHEMA_A, allowed), arm_view(arms.get("B"), SCHEMA_B, allowed))
        events[key] = pair_hard_fail_events(row)
    integ = integrity(meta, attempts, views)
    if ss["inconsistent"]:
        integ["ok"] = False
        integ["problems"].extend(f"scored-set inconsistency: {x}" for x in ss["inconsistent"][:10])
        integ["problem_count"] += len(ss["inconsistent"])

    final_keys = set(ss["scored"]) | {(u["pass"], u["index"]) for u in ss["unresolved"]}
    expected_keys = {(p, i) for p in range(1, PASSES + 1) for i in range(N_QUESTIONS)}
    complete = status == ST_COMPLETE and final_keys == expected_keys and led["bad_lines"] == 0

    # ---------------- hard gate (G1-G3) ----------------
    hard_pairs = {k: e for k, e in events.items() if e}
    by_code: dict = {}
    for evs in hard_pairs.values():
        for e in evs:
            by_code[e["code"]] = by_code.get(e["code"], 0) + 1
    excluded = {"only_a_failed": [], "both_failed": [], "b_failed_g1": []}
    for key, (a, b) in views.items():
        if not a["ok"]:
            excluded["both_failed" if not b["ok"] else "only_a_failed"].append(list(key))
        elif not b["ok"]:
            excluded["b_failed_g1"].append(list(key))

    # ---------------- quality endpoints ----------------
    both = {k: v for k, v in views.items() if v[0]["ok"] and v[1]["ok"]}

    def clusters_of(fn):
        per_q: dict = {}
        for (p, i), (a, b) in sorted(both.items()):
            val = fn(a["features"], b["features"])
            if val is not None:
                per_q.setdefault(i, []).append(val)
        return [per_q[i] for i in sorted(per_q)]

    def delta(field):
        def fn(fa, fb):
            xa, xb = _num(fa.get(field)), _num(fb.get(field))
            return None if xa is None or xb is None else xb - xa
        return fn

    def cross_minus_within(sim):
        """Per question: mean cross-pass A-vs-B similarity minus mean A-vs-A similarity."""
        per_q: dict = {}
        for (p, i), (a, b) in both.items():
            per_q.setdefault(i, {})[p] = (a["features"], b["features"])
        vals = []
        for i in sorted(per_q):
            passes = sorted(per_q[i])
            within = [sim(per_q[i][p][0], per_q[i][q][0]) for x, p in enumerate(passes) for q in passes[x + 1:]]
            cross = [sim(per_q[i][p][0], per_q[i][q][1]) for p in passes for q in passes if p != q]
            if within and cross:
                vals.append([mean(cross) - mean(within)])
        return vals

    endpoints = {}

    def ni(name, clusters, margin, kind="ni"):
        est, ci = cluster_bootstrap(clusters, mean)
        state = ni_state(ci, margin) if kind == "ni" else equivalence_state(ci, margin)
        endpoints[name] = {"estimate": est, "ci95": list(ci), "margin": margin, "test": kind,
                           "units": len(clusters), "n": sum(len(c) for c in clusters), "state": state}

    ni("claim_count", clusters_of(delta("claims")), MARGIN_CLAIM_COUNT)
    ni("evidence_coverage", clusters_of(delta("coverage")), MARGIN_EVIDENCE_COVERAGE)
    ni("claim_content", cross_minus_within(lambda x, y: smbm(x["claim_statements"], y["claim_statements"])),
       MARGIN_CLAIM_CONTENT)
    ni("uncertainty_count", clusters_of(delta("uncertainty_count")), MARGIN_UNCERTAINTY_COUNT)
    ni("uncertainty_content", cross_minus_within(lambda x, y: smbm(x["uncertainty"], y["uncertainty"])),
       MARGIN_UNCERTAINTY_CONTENT)
    ni("confidence", clusters_of(delta("confidence")), MARGIN_CONFIDENCE, kind="equivalence")

    # ---------------- uncertainty warnings ----------------
    unc_chars = cluster_bootstrap(clusters_of(delta("uncertainty_chars")), mean)
    b_only_empty = sum(1 for a, b in both.values()
                       if b["features"]["uncertainty_count"] == 0 < a["features"]["uncertainty_count"])
    a_only_empty = sum(1 for a, b in both.values()
                       if a["features"]["uncertainty_count"] == 0 < b["features"]["uncertainty_count"])
    p_empty = sign_test(b_only_empty, a_only_empty)
    warnings = {
        "W1_count_reduced": {"triggered": endpoints["uncertainty_count"]["ci95"][1] is not None
                             and endpoints["uncertainty_count"]["ci95"][1] < 0,
                             "ci95": endpoints["uncertainty_count"]["ci95"]},
        "W2_chars_reduced": {"triggered": unc_chars[1][1] is not None and unc_chars[1][1] < 0,
                             "estimate": unc_chars[0], "ci95": list(unc_chars[1])},
        "W3_b_only_empty": {"triggered": b_only_empty > a_only_empty and p_empty < WARNING_SIGN_TEST_ALPHA,
                            "b_only_empty": b_only_empty, "a_only_empty": a_only_empty, "p": p_empty},
        "W4_content_drift": {"triggered": endpoints["uncertainty_content"]["ci95"][1] is not None
                             and endpoints["uncertainty_content"]["ci95"][1] < 0,
                             "ci95": endpoints["uncertainty_content"]["ci95"]},
    }

    # ---------------- latency and tokens ----------------
    def tap_ok(v):
        return v["tap"].get("outcome") == "OK" and _num(v["tap"].get("sdk_latency_ms")) is not None

    lat = {k: v for k, v in views.items() if tap_ok(v[0]) and tap_ok(v[1])}
    lat_clusters: dict = {}
    by_order: dict = {"AB": [], "BA": []}
    for (p, i), (a, b) in sorted(lat.items()):
        d = a["tap"]["sdk_latency_ms"] - b["tap"]["sdk_latency_ms"]
        lat_clusters.setdefault(i, []).append(d)
        by_order[expected_order(i)].append(d)
    med, med_ci = cluster_bootstrap([lat_clusters[i] for i in sorted(lat_clusters)], median)
    if med is None:
        lat_state = "NOT_EVALUABLE"
    elif med >= LATENCY_MATERIAL_MS and med_ci[0] > 0:
        lat_state = "MATERIAL"
    elif med >= LATENCY_MATERIAL_MS:
        lat_state = "NOT_SHOWN"
    else:
        lat_state = "NOT_MATERIAL"

    def per_arm(field, arm):
        return [_num(v[arm]["tap"].get(field)) for v in lat.values()]

    def tok_delta(field):
        cl: dict = {}
        for (p, i), (a, b) in sorted(lat.items()):
            xa, xb = _num(a["tap"].get(field)), _num(b["tap"].get(field))
            if xa is not None and xb is not None:
                cl.setdefault(i, []).append(xb - xa)
        est, ci = cluster_bootstrap([cl[i] for i in sorted(cl)], mean)
        pooled = [x for i in sorted(cl) for x in cl[i]]
        return {"mean": est, "ci95": list(ci), "dist": dist(pooled),
                "changed": ci[0] is not None and (ci[0] > 0 or ci[1] < 0)}

    latency = {
        "pairs": len(lat),
        "a_ms": dist(per_arm("sdk_latency_ms", 0)), "b_ms": dist(per_arm("sdk_latency_ms", 1)),
        "delta_a_minus_b_ms": dist([x for c in lat_clusters.values() for x in c]),
        "median_improvement_ms": med, "median_improvement_ci95": list(med_ci),
        "threshold_ms": LATENCY_MATERIAL_MS, "state": lat_state,
        "by_order_median_ms": {o: median(v) for o, v in by_order.items()},
    }
    tokens_rep = {
        "visible": {"a": dist(per_arm("candidates_tokens", 0)), "b": dist(per_arm("candidates_tokens", 1)),
                    "delta_b_minus_a": tok_delta("candidates_tokens")},
        "thinking": {"a": dist(per_arm("thoughts_tokens", 0)), "b": dist(per_arm("thoughts_tokens", 1)),
                     "delta_b_minus_a": tok_delta("thoughts_tokens")},
        "cached": {"a": dist(per_arm("cached_tokens", 0)), "b": dist(per_arm("cached_tokens", 1))},
        "prompt": {"a": dist(per_arm("prompt_tokens", 0)), "b": dist(per_arm("prompt_tokens", 1))},
    }

    # ---------------- report-only ----------------
    def same_pass(sim):
        return dist([sim(a["features"], b["features"]) for a, b in both.values()])

    report_only = {
        "claims": {"a": dist([a["features"]["claims"] for a, _ in both.values()]),
                   "b": dist([b["features"]["claims"] for _, b in both.values()]),
                   "exact_statement_sets_equal": sum(
                       1 for a, b in both.values()
                       if sorted(" ".join(s.split()).casefold() for s in a["features"]["claim_statements"])
                       == sorted(" ".join(s.split()).casefold() for s in b["features"]["claim_statements"])),
                   "same_pass_smbm": same_pass(lambda x, y: smbm(x["claim_statements"], y["claim_statements"]))},
        "evidence": {"coverage_a": dist([a["features"]["coverage"] for a, _ in both.values()]),
                     "coverage_b": dist([b["features"]["coverage"] for _, b in both.values()]),
                     "claim_id_set_jaccard_same_pass": same_pass(
                         lambda x, y: jaccard(frozenset(x["claim_ids"]), frozenset(y["claim_ids"])))},
        "uncertainty": {"count_a": dist([a["features"]["uncertainty_count"] for a, _ in both.values()]),
                        "count_b": dist([b["features"]["uncertainty_count"] for _, b in both.values()]),
                        "chars_a": dist([a["features"]["uncertainty_chars"] for a, _ in both.values()]),
                        "chars_b": dist([b["features"]["uncertainty_chars"] for _, b in both.values()])},
        "confidence": {"a": dist([a["features"]["confidence"] for a, _ in both.values()]),
                       "b": dist([b["features"]["confidence"] for _, b in both.values()])},
        "abstract": {"chars_a": dist([len(a["features"]["abstract"]) for a, _ in both.values()]),
                     "chars_b": dist([len(b["features"]["abstract"]) for _, b in both.values()]),
                     "cross_minus_within_jaccard": dict(zip(("estimate", "ci95"), cluster_bootstrap(
                         cross_minus_within(lambda x, y: jaccard(tokens(x["abstract"]), tokens(y["abstract"]))),
                         mean)))},
        "highlights": {"count_a": dist([len(a["features"]["highlights"]) for a, _ in both.values()]),
                       "count_b": dist([len(b["features"]["highlights"]) for _, b in both.values()]),
                       "cross_minus_within_smbm": dict(zip(("estimate", "ci95"), cluster_bootstrap(
                           cross_minus_within(lambda x, y: smbm(x["highlights"], y["highlights"])), mean)))},
    }
    cap_rep = {
        "a_raw_concepts": dist([v[0]["raw_counts"]["concepts"] for v in views.values()]),
        "a_raw_relations": dist([v[0]["raw_counts"]["relations"] for v in views.values()]),
        "b_raw_concepts": dist([v[1]["raw_counts"]["concepts"] for v in views.values()]),
        "b_raw_relations": dist([v[1]["raw_counts"]["relations"] for v in views.values()]),
        "a_over_cap_concepts": sum(1 for v in views.values() if (v[0]["raw_counts"]["concepts"] or 0) > CAP["concepts"]),
        "a_over_cap_relations": sum(1 for v in views.values() if (v[0]["raw_counts"]["relations"] or 0) > CAP["relations"]),
        "b_max_items_violations": sum(1 for v in views.values() for c, _ in v[1]["violations"] if c == "MAX_ITEMS"),
        "a_schema_violation_pairs": sum(1 for v in views.values() if v[0]["violations"]),
        "b_schema_violation_pairs": sum(1 for v in views.values() if v[1]["violations"]),
        "key_order_a": sorted({"|".join(v[0]["key_order"]) for v in views.values() if v[0]["key_order"]}),
        "key_order_b": sorted({"|".join(v[1]["key_order"]) for v in views.values() if v[1]["key_order"]}),
    }
    cga1 = {
        "pairs": len(both),
        "a_would_fail": sum(1 for a, _ in both.values() if a["features"]["cga1_would_pass"] is False),
        "b_would_fail": sum(1 for _, b in both.values() if b["features"]["cga1_would_pass"] is False),
        "b_only_would_fail": sum(1 for a, b in both.values()
                                 if b["features"]["cga1_would_pass"] is False and a["features"]["cga1_would_pass"]),
        "relation_only_ids_a": dist([len(a["features"]["relation_only_ids"]) for a, _ in both.values()]),
        "relation_only_ids_b": dist([len(b["features"]["relation_only_ids"]) for _, b in both.values()]),
        "guard_ids_a": dist([len(a["features"]["guard_ids"]) for a, _ in both.values()]),
        "guard_ids_b": dist([len(b["features"]["guard_ids"]) for _, b in both.values()]),
        "defects_a": {d: sum(1 for a, _ in both.values() if d in a["features"]["defects"]) for d in DEFECTS},
        "defects_b": {d: sum(1 for _, b in both.values() if d in b["features"]["defects"]) for d in DEFECTS},
    }

    def arm_cost(arm):
        total = 0.0
        for att in attempts:
            for tap in ((att.get("arms") or {}).get(arm) or {}).get("tap") or []:
                pin = _num(tap.get("prompt_tokens")) or 0
                out = (_num(tap.get("candidates_tokens")) or 0) + (_num(tap.get("thoughts_tokens")) or 0)
                total += pin * PRICE_INPUT_PER_M / 1e6 + out * PRICE_OUTPUT_PER_M / 1e6
        return round(total, 4)

    cost = {"label": "ESTIMATED", "a_usd": arm_cost("A"), "b_usd": arm_cost("B")}

    result = {
        "tool": "h1_ab_score", "scorer_version": SCORER_VERSION, "ledger_sha256": sha256_file(ledger_path),
        "prereg_sha256": meta.get("prereg_sha256"),
        "run": {"status": status, "stop_reason": summary.get("stop_reason"), "complete": complete,
                "scheduled_pairs": SCHEDULED_PAIRS, "attempts": len(attempts),
                "replacements": sum(1 for a in attempts if a.get("kind") == "replacement"),
                "scored_pairs": len(ss["scored"]), "unresolved": ss["unresolved"],
                "provider_calls": summary.get("provider_calls"),
                "provider_faults": summary.get("provider_faults"),
                "bad_lines": led["bad_lines"]},
        "integrity": integ,
        "hard_fail": {"pairs": len(hard_pairs), "by_code": by_code,
                      "events": [{"pass": k[0], "index": k[1], "events": e} for k, e in sorted(hard_pairs.items())]},
        "excluded": excluded,
        "quality_pairs": len(both),
        "endpoints": endpoints,
        "uncertainty_warnings": warnings,
        "latency": latency, "tokens": tokens_rep,
        "cap": cap_rep, "cga1": cga1, "report_only": report_only, "cost": cost,
    }
    result["verdict"] = decide(result)
    result["_pair_rows"] = pair_rows(views, events, ss["scored"])
    return result


def decide(r: dict) -> dict:
    """Prereg section 9: ordered; the first matching step decides."""
    status = r["run"]["status"]
    if not r["integrity"]["ok"] or status in (ST_GUARD, ST_CAPTURE):
        return {"label": "INCONCLUSIVE", "sub_reason": "HARNESS_INTEGRITY", "step": 1,
                "hard_fail_pairs_before_stop": r["hard_fail"]["pairs"]}
    if status == ST_HEALTH:
        return {"label": "INCONCLUSIVE", "sub_reason": "PROVIDER_HEALTH", "step": 1,
                "hard_fail_pairs_before_stop": r["hard_fail"]["pairs"]}
    if status == ST_TURN:
        return {"label": "INCONCLUSIVE", "sub_reason": "IVE_OR_TURN_NON_PROVIDER_FAILURE", "step": 1,
                "hard_fail_pairs_before_stop": r["hard_fail"]["pairs"]}
    if r["hard_fail"]["pairs"]:
        return {"label": "FAIL", "sub_reason": "HARD_GATE", "step": 2, "codes": r["hard_fail"]["by_code"]}
    if not r["run"]["complete"]:
        return {"label": "INCONCLUSIVE", "sub_reason": "INCOMPLETE", "step": 3, "status": status}
    states = {k: v["state"] for k, v in r["endpoints"].items()}
    bad = sorted(k for k, s in states.items() if s in ("INFERIOR", "DIVERGENT"))
    if bad:
        return {"label": "FAIL", "sub_reason": "QUALITY", "step": 4, "endpoints": bad}
    unshown = sorted(k for k, s in states.items() if s in ("NOT_SHOWN", "NOT_EVALUABLE"))
    if unshown:
        return {"label": "INCONCLUSIVE", "sub_reason": "NI_NOT_SHOWN", "step": 5, "endpoints": unshown}
    warned = sorted(k for k, w in r["uncertainty_warnings"].items() if w["triggered"])
    if warned:
        return {"label": "WARNING", "sub_reason": "UNCERTAINTY", "step": 6, "warnings": warned}
    lat = r["latency"]["state"]
    if lat == "MATERIAL":
        return {"label": "PASS", "step": 7}
    if lat == "NOT_MATERIAL":
        return {"label": "NOT_MATERIAL", "step": 7}
    return {"label": "INCONCLUSIVE", "sub_reason": "LATENCY_NOT_SHOWN", "step": 7}


PAIR_COLUMNS = ["pass", "index", "order", "kind", "a_status", "b_status", "events",
                "a_claims", "b_claims", "a_coverage", "b_coverage", "a_unc", "b_unc",
                "a_unc_chars", "b_unc_chars", "a_conf", "b_conf",
                "a_concepts_raw", "b_concepts_raw", "a_relations_raw", "b_relations_raw",
                "a_ms", "b_ms", "a_visible", "b_visible", "a_thinking", "b_thinking",
                "a_defects", "b_defects", "claim_smbm", "unc_smbm"]


def pair_rows(views: dict, events: dict, scored: dict) -> list:
    rows = []
    for key in sorted(views):
        a, b = views[key]
        fa, fb = a["features"] or {}, b["features"] or {}
        both = a["ok"] and b["ok"]
        rows.append({
            "pass": key[0], "index": key[1], "order": scored[key].get("order"), "kind": scored[key].get("kind"),
            "a_status": a["status"], "b_status": b["status"],
            "events": ";".join(f"{e['code']}:{e['detail']}" for e in events[key]),
            "a_claims": fa.get("claims"), "b_claims": fb.get("claims"),
            "a_coverage": fa.get("coverage"), "b_coverage": fb.get("coverage"),
            "a_unc": fa.get("uncertainty_count"), "b_unc": fb.get("uncertainty_count"),
            "a_unc_chars": fa.get("uncertainty_chars"), "b_unc_chars": fb.get("uncertainty_chars"),
            "a_conf": fa.get("confidence"), "b_conf": fb.get("confidence"),
            "a_concepts_raw": a["raw_counts"]["concepts"], "b_concepts_raw": b["raw_counts"]["concepts"],
            "a_relations_raw": a["raw_counts"]["relations"], "b_relations_raw": b["raw_counts"]["relations"],
            "a_ms": a["tap"].get("sdk_latency_ms"), "b_ms": b["tap"].get("sdk_latency_ms"),
            "a_visible": a["tap"].get("candidates_tokens"), "b_visible": b["tap"].get("candidates_tokens"),
            "a_thinking": a["tap"].get("thoughts_tokens"), "b_thinking": b["tap"].get("thoughts_tokens"),
            "a_defects": "|".join(fa.get("defects") or []), "b_defects": "|".join(fb.get("defects") or []),
            "claim_smbm": smbm(fa["claim_statements"], fb["claim_statements"]) if both else None,
            "unc_smbm": smbm(fa["uncertainty"], fb["uncertainty"]) if both else None,
        })
    return rows


# ------------------------------------------------------------------ #
# baseline: the Step 0 capture ledger (unchanged IVE, 27 reports)
# ------------------------------------------------------------------ #
def baseline(ledger_path: str) -> dict:
    """Attribution and schema profile of the current IVE from the H1 Step 0
    ledger. Step 0 did not record the admitted evidence set, so a claim id is
    checked against the turn's rendered evidence (the renderer lists every
    claim-cited id that is admitted, and only those); relation-only ids
    cannot be checked and are counted as UNVERIFIABLE."""
    turns = []
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            tag, _, payload = line.rstrip("\n").partition(" ")
            if tag == "H1_TURN":
                turns.append(json.loads(payload))
    per_turn = []
    for t in turns:
        reports = t.get("ive_reports") or []
        caps = [c for c in t.get("captures") or [] if c.get("outcome") == "OK" and isinstance(c.get("text"), str)]
        if not reports or not isinstance(reports[0], dict):
            per_turn.append({"index": t.get("index"), "report": False})
            continue
        f = report_features(reports[0], None)
        rendered = [str(e) for e in t.get("evidence_ids") or []]
        stray = [cid for cid in f["claim_ids"] if not any(e.startswith(cid + "::") for e in rendered)]
        violations = []
        raw_counts = {"concepts": None, "relations": None}
        if caps:
            try:
                raw = parse_like_app(caps[-1]["text"])
            except ValueError:
                violations = [("UNPARSEABLE", "/")]
            else:
                violations = schema_violations(raw, SCHEMA_A)
                raw_counts = {k: len(raw[k]) if isinstance(raw.get(k), list) else None
                              for k in ("concepts", "relations")}
        per_turn.append({
            "index": t.get("index"), "report": True,
            "claims": f["claims"], "claims_without_evidence": f["claims_without_evidence"],
            "claim_ids": len(f["claim_ids"]), "claim_ids_not_rendered": len(stray),
            "relation_ids": len(f["relation_ids"]), "relation_only_ids_unverifiable": len(f["relation_only_ids"]),
            "context_documents": t.get("context_documents"),
            "schema_violations": sorted({c for c, _ in violations}),
            "raw_concepts": raw_counts["concepts"], "raw_relations": raw_counts["relations"],
        })
    have = [p for p in per_turn if p["report"]]
    n = len(have)

    def rate(pred):
        k = sum(1 for p in have if pred(p))
        return {"reports": k, "of": n, "rate": (k / n) if n else None}

    rates = {
        "STRAY_CLAIM_ID": rate(lambda p: p["claim_ids_not_rendered"] > 0),
        "CLAIM_WITHOUT_EVIDENCE": rate(lambda p: p["claims_without_evidence"] > 0),
        "SCHEMA_VIOLATION": rate(lambda p: bool(p["schema_violations"])),
        "RELATION_ONLY_IDS_PRESENT": rate(lambda p: p["relation_only_ids_unverifiable"] > 0),
    }
    noise = {}
    for name in ("STRAY_CLAIM_ID", "CLAIM_WITHOUT_EVIDENCE"):
        p = rates[name]["rate"]
        noise[name] = None if p is None else 1.0 - (1.0 - p * (1.0 - p)) ** SCHEDULED_PAIRS
    return {
        "tool": "h1_ab_score baseline", "scorer_version": SCORER_VERSION,
        "ledger_sha256": sha256_file(ledger_path), "turns": len(turns), "reports": n,
        "rates": rates,
        "chance_of_one_or_more_b_only_pairs_in_81_if_unchanged": {
            "label": "ESTIMATED (independent arms at the Step 0 per-report rate)", **noise},
        "a_over_cap": {"concepts_gt3": sum(1 for p in have if (p["raw_concepts"] or 0) > CAP["concepts"]),
                       "relations_gt4": sum(1 for p in have if (p["raw_relations"] or 0) > CAP["relations"])},
        "caveat": "Step 0 did not record the admitted evidence set: STRAY_RELATION_ID cannot be measured here.",
        "per_turn": per_turn,
    }


# ------------------------------------------------------------------ #
# entry point
# ------------------------------------------------------------------ #
def _write_json(path: str, obj) -> str:
    data = (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str) + "\n").encode("utf-8")
    with open(path, "xb") as fh:
        fh.write(data)
    return hashlib.sha256(data).hexdigest()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 3 and argv[0] == "score":
        result = score(argv[1])
        rows = result.pop("_pair_rows")
        summary_sha = _write_json(argv[2] + "_summary.json", result)
        with open(argv[2] + "_pairs.csv", "x", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=PAIR_COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(json.dumps({"verdict": result["verdict"], "summary_sha256": summary_sha,
                          "scored_pairs": result["run"]["scored_pairs"]}))
        return 0
    if len(argv) == 3 and argv[0] == "baseline":
        result = baseline(argv[1])
        out_sha = _write_json(argv[2], result)
        print(json.dumps({"reports": result["reports"], "rates": result["rates"], "out_sha256": out_sha}))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
