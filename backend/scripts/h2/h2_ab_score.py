"""H2 live A/B (IVE thinking budget 1280) offline scorer and analyzer (h2_ab_score.py). Stdlib only.

Operator decision 2026-10-07 21:25Z ("H2 1280, FINAL PREPARATION ONLY").
Implements the scoring and the ordered verdict of H2_AB_THINKING_PREREG.md.
It reads files only: it makes no provider call and imports nothing from the
application. Derived from the H1 scorer (h1_ab_score.py); the one change under
test is the IVE thinking budget, so both arms use the unchanged IVE schema.

    python h2_ab_score.py score <h2ab_ledger.jsonl> <out_prefix>

`score` reads the A/B ledger written by voe_h2_ab_harness.py and writes
<out_prefix>_summary.json (every number, every endpoint state and the verdict)
and <out_prefix>_pairs.csv (one row per scored pair).

The harness imports this module (by sha256) for THINKING_BUDGET_B and
`pair_hard_fail_events`, so the arm-B request, the run-time systematic-failure
stop and the offline verdict all come from the same code and the same data.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import sys

SCORER_VERSION = "h2-ab-score-v1"

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
# H2 does not touch the schema: arm B sends the identical module schema object.
EXPECTED_SCHEMA_B_SHA256 = EXPECTED_SCHEMA_A_SHA256
# The one change: arm B's IVE call carries ThinkingConfig(thinking_budget=1280);
# arm A sends no thinking config (the deployed provider default).
THINKING_BUDGET_B = 1280

PASSES = 3
N_QUESTIONS = 27
SCHEDULED_PAIRS = PASSES * N_QUESTIONS

# ---- preregistered analysis constants (H2_AB_THINKING_PREREG.md section 8) ----
SEED = 20261006
RESAMPLES = 10_000
CI_LEVEL = 0.95
# Non-inferiority margins on B - A for 81 pairs, calibrated against unchanged-vs-unchanged
# noise of the 215 stored unchanged v0.4 IVE reports (VOE_LATENCY_H1_RULE_CALIBRATION.md;
# abstract and highlights: VOE_LATENCY_H2_ABSTRACT_HIGHLIGHTS_CALIBRATION.md).
MARGIN_CLAIM_COUNT = 0.45          # claims per report
MARGIN_EVIDENCE_COVERAGE = 0.05    # share of the turn's admitted evidence ids cited by claims
MARGIN_CLAIM_CONTENT = 0.04        # cross-arm minus within-A claim-statement similarity
MARGIN_UNCERTAINTY_COUNT = 0.45    # uncertainty items per report
MARGIN_UNCERTAINTY_CONTENT = 0.125  # cross-arm minus within-A uncertainty similarity
MARGIN_CONFIDENCE = 0.02           # overall report confidence, two-sided equivalence
MARGIN_ABSTRACT_CONTENT = None     # cross-arm minus within-A abstract token Jaccard (set by the calibration)
MARGIN_HIGHLIGHTS_CONTENT = None   # cross-arm minus within-A highlights similarity (set by the calibration)
# Latency rule: MATERIAL when mean(A - B) >= the threshold AND the one-sided 95%
# cluster-bootstrap lower bound of that mean is above 0.
LATENCY_MATERIAL_MS = 2000.0       # operator's materiality threshold for H2 (several seconds)
LATENCY_LOWER_BOUND_LEVEL = 0.95   # one-sided: the 5th percentile of the bootstrap means
WARNING_SIGN_TEST_ALPHA = 0.05
# Run-time stop S4: this many consecutive scored pairs with a hard-fail event.
SYSTEMATIC_B_STOP = 3
# gemini-2.5-pro list price (verified 2026-10-06), prompts <= 200k tokens. ESTIMATED cost only.
PRICE_INPUT_PER_M = 1.25
PRICE_OUTPUT_PER_M = 10.0          # visible + thinking

# Harness run statuses (voe_h2_ab_harness.py).
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


SCHEMA_A = json.loads(SCHEMA_A_CANONICAL)
SCHEMA_B = SCHEMA_A
if sha256_text(canonical(SCHEMA_A)) != EXPECTED_SCHEMA_A_SHA256:
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
        except Exception:  # ValueError, or RecursionError on pathologically nested JSON
            violations = [("UNPARSEABLE", "/")]
        else:
            violations = schema_violations(raw, schema)
    report = arm.get("report")
    ok = status == "OK" and isinstance(report, dict)
    taps = arm.get("tap") or []
    tap = taps[-1] if taps else {}
    http = (arm.get("error") or {}).get("http_status")
    return {
        "ok": ok,
        "status": status,
        "class_key": (arm.get("classification") or {}).get("class_key"),
        "http_status": http if http is not None else (tap.get("error") or {}).get("http_status"),
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
    and both-failed pairs are excluded and reported; S1 stops the run). An HTTP
    402 on arm B is an account state, not arm-B behaviour: S2 stops the run
    there and the verdict is INCONCLUSIVE (HTTP_402), never a G1 event."""
    allowed = (row.get("model_input") or {}).get("allowed_ids")
    arms = row.get("arms") or {}
    a = arm_view(arms.get("A"), SCHEMA_A, allowed)
    b = arm_view(arms.get("B"), SCHEMA_B, allowed)
    if not a["ok"]:
        return []
    if not b["ok"]:
        # REFUSED / NOT_RUN / UNSCORED are harness states: the guard or capture stop decides those
        if b["status"] not in ("CALL_FAILED", "INVALID_OUTPUT") or b["http_status"] == 402:
            return []
        return [{"code": "G1", "detail": f"B {b['status']}: {b['class_key']}"}]
    events = []
    a_codes = {code for code, _ in a["violations"]}
    for code, path in b["violations"]:
        if code not in a_codes:
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


def hodges_lehmann(values: list):
    """One-sample Hodges-Lehmann estimate: the median of the Walsh averages
    (x_i + x_j) / 2 over i <= j."""
    v = list(values)
    if not v:
        return None
    return median([(v[i] + v[j]) / 2.0 for i in range(len(v)) for j in range(i, len(v))])


def dist(values: list) -> dict:
    v = sorted(x for x in values if isinstance(x, (int, float)) and not isinstance(x, bool))
    if not v:
        return {"n": 0}
    return {"n": len(v), "min": v[0], "p10": quantile(v, 0.10), "p25": quantile(v, 0.25),
            "median": quantile(v, 0.5), "p75": quantile(v, 0.75), "p90": quantile(v, 0.90),
            "max": v[-1], "mean": sum(v) / len(v)}


def cluster_bootstrap(clusters: list, stat, *, seed: int = SEED, resamples: int = RESAMPLES,
                      level: float = CI_LEVEL):
    """Point estimate on the pooled values and a two-sided percentile interval
    at `level` from resampling whole clusters (questions) with replacement.
    The lower end of the level-0.90 interval is the one-sided 95% lower bound.
    Each call seeds its own RNG, so an endpoint's interval does not depend on
    the order endpoints run."""
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
    tail = (1.0 - level) / 2.0
    return est, (quantile(stats, tail), quantile(stats, 1.0 - tail))


def sign_test(n_plus: int, n_minus: int) -> float:
    """Exact two-sided binomial sign test (ties excluded by the caller)."""
    n = n_plus + n_minus
    if n == 0:
        return 1.0
    k = min(n_plus, n_minus)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def gain_at_equal_thinking(points: list) -> float:
    """Intercept of the least-squares line of the A-B latency difference on the
    A-B thinking-token difference, over (thinking_diff, latency_diff) points:
    the latency gain at equal thinking. With no spread in the thinking
    difference the slope is unidentified and taken as 0 (the mean difference)."""
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    slope = sum((p[0] - mx) * (p[1] - my) for p in points) / sxx if sxx > 0 else 0.0
    return my - slope * mx


def content_clusters(features: dict, sim) -> list:
    """Content endpoints: per question, the mean cross-pass A-vs-B similarity minus
    the mean A-vs-A similarity, one value per question (a cluster of one).
    `features` maps (pass, index) to (A features, B features) of pairs where both
    arms succeeded. The calibration script calls this same function."""
    per_q: dict = {}
    for (p, i), (fa, fb) in features.items():
        per_q.setdefault(i, {})[p] = (fa, fb)
    vals = []
    for i in sorted(per_q):
        passes = sorted(per_q[i])
        within = [sim(per_q[i][p][0], per_q[i][q][0]) for x, p in enumerate(passes) for q in passes[x + 1:]]
        cross = [sim(per_q[i][p][0], per_q[i][q][1]) for p in passes for q in passes if p != q]
        if within and cross:
            vals.append([mean(cross) - mean(within)])
    return vals


CONTENT_SIMILARITY = {
    "claim_content": lambda x, y: smbm(x["claim_statements"], y["claim_statements"]),
    "uncertainty_content": lambda x, y: smbm(x["uncertainty"], y["uncertainty"]),
    "abstract_content": lambda x, y: jaccard(tokens(x["abstract"]), tokens(y["abstract"])),
    "highlights_content": lambda x, y: smbm(x["highlights"], y["highlights"]),
}


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
            if tag == "H2AB_META":
                out["meta"].append(obj)
            elif tag == "H2AB_ATTEMPT":
                out["attempts"].append(obj)
            elif tag == "H2AB_SUMMARY":
                out["summary"].append(obj)
            else:
                out["other"] += 1
    return out


def expected_order(pass_no: int, index: int) -> str:
    """Prereg section 4: the 81 scheduled pairs alternate AB, BA, AB, ... in run
    order (slot = (pass - 1) * 27 + index), so with 27 questions every question
    meets both orders across the three passes (41 AB, 40 BA). A replacement
    keeps its slot's order. The harness takes the order from here."""
    return "AB" if ((pass_no - 1) * N_QUESTIONS + index) % 2 == 0 else "BA"


def _attempt_has_402(att: dict) -> bool:
    if (att.get("error_detail") or {}).get("http_status") == 402:
        return True
    for rec in (att.get("arms") or {}).values():
        rec = rec or {}
        if (rec.get("error") or {}).get("http_status") == 402:
            return True
        if any((t.get("error") or {}).get("http_status") == 402 for t in rec.get("tap") or []):
            return True
    return False


def scored_set(attempts: list) -> dict:
    """Prereg section 5: per scheduled (pass, index) the primary if it has no
    PROVIDER_FAULT, else the replacement if it has none, else UNRESOLVED. A
    faulted primary whose replacement never ran (the run stopped first) is
    PENDING: neither scored nor unresolved, and the run is not complete."""
    by_key: dict = {}
    for att in attempts:
        by_key.setdefault((att.get("pass"), att.get("index")), []).append(att)
    scored, unresolved, pending, inconsistent = {}, [], [], []
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
        if chosen is not None:
            scored[key] = chosen
        elif kinds == ["primary"]:
            pending.append({"pass": key[0], "index": key[1]})
        else:
            unresolved.append({"pass": key[0], "index": key[1]})
    return {"scored": scored, "unresolved": unresolved, "pending": pending, "inconsistent": inconsistent,
            "attempted_keys": sorted(by_key)}


# ------------------------------------------------------------------ #
# scoring
# ------------------------------------------------------------------ #
def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def thinking_as_preregistered(arm: str, tap: dict) -> bool:
    """Arm A sends no thinking config; arm B sends exactly thinking_budget = THINKING_BUDGET_B."""
    if arm == "A":
        return tap.get("thinking_config_sent") is False and tap.get("thinking_budget_sent") is None
    return tap.get("thinking_config_sent") is True and tap.get("thinking_budget_sent") == THINKING_BUDGET_B


def integrity(meta: dict, attempts: list, views: dict) -> dict:
    """Checks that can only fail on a harness defect. Any failure makes the
    result INCONCLUSIVE (HARNESS_INTEGRITY)."""
    problems = []
    if sha256_text(canonical(meta.get("schema_a") or {})) != EXPECTED_SCHEMA_A_SHA256:
        problems.append("META schema_a differs from the preregistered arm-A schema")
    if sha256_text(canonical(meta.get("schema_b") or {})) != EXPECTED_SCHEMA_B_SHA256:
        problems.append("META schema_b differs from the preregistered arm-B schema")
    if meta.get("thinking_budget_b") != THINKING_BUDGET_B:
        problems.append("META thinking_budget_b differs from the preregistered budget")
    for att in attempts:
        where = f"pass {att.get('pass')} index {att.get('index')} {att.get('kind')}"
        arms = att.get("arms") or {}
        exp = expected_order(att.get("pass") or 1, att.get("index") or 0)
        if att.get("order") is not None and att.get("order") != exp:
            problems.append(f"{where}: order {att.get('order')} != {exp}")
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
                if not thinking_as_preregistered(arm, tap):
                    problems.append(f"{where}: arm {arm} thinking config is not the preregistered one")
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
    excluded = {"only_a_failed": [], "both_failed": [], "b_failed_g1": [], "b_failed_not_g1": []}
    for key, (a, b) in views.items():
        if not a["ok"]:
            excluded["both_failed" if not b["ok"] else "only_a_failed"].append(list(key))
        elif not b["ok"]:
            g1 = any(e["code"] == "G1" for e in events[key])
            excluded["b_failed_g1" if g1 else "b_failed_not_g1"].append(list(key))

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
        return content_clusters({k: (a["features"], b["features"]) for k, (a, b) in both.items()}, sim)

    endpoints = {}

    def ni(name, clusters, margin, kind="ni"):
        est, ci = cluster_bootstrap(clusters, mean)
        state = ni_state(ci, margin) if kind == "ni" else equivalence_state(ci, margin)
        endpoints[name] = {"estimate": est, "ci95": list(ci), "margin": margin, "test": kind,
                           "units": len(clusters), "n": sum(len(c) for c in clusters), "state": state}

    ni("claim_count", clusters_of(delta("claims")), MARGIN_CLAIM_COUNT)
    ni("evidence_coverage", clusters_of(delta("coverage")), MARGIN_EVIDENCE_COVERAGE)
    ni("claim_content", cross_minus_within(CONTENT_SIMILARITY["claim_content"]), MARGIN_CLAIM_CONTENT)
    ni("uncertainty_count", clusters_of(delta("uncertainty_count")), MARGIN_UNCERTAINTY_COUNT)
    ni("uncertainty_content", cross_minus_within(CONTENT_SIMILARITY["uncertainty_content"]),
       MARGIN_UNCERTAINTY_CONTENT)
    ni("confidence", clusters_of(delta("confidence")), MARGIN_CONFIDENCE, kind="equivalence")
    ni("abstract_content", cross_minus_within(CONTENT_SIMILARITY["abstract_content"]), MARGIN_ABSTRACT_CONTENT)
    ni("highlights_content", cross_minus_within(CONTENT_SIMILARITY["highlights_content"]),
       MARGIN_HIGHLIGHTS_CONTENT)

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
    adj_clusters: dict = {}
    by_order: dict = {"AB": [], "BA": []}
    for (p, i), (a, b) in sorted(lat.items()):
        d = a["tap"]["sdk_latency_ms"] - b["tap"]["sdk_latency_ms"]
        lat_clusters.setdefault(i, []).append(d)
        by_order[expected_order(p, i)].append(d)
        ta, tb = _num(a["tap"].get("thoughts_tokens")), _num(b["tap"].get("thoughts_tokens"))
        if ta is not None and tb is not None:
            adj_clusters.setdefault(i, []).append((ta - tb, d))
    lat_cl = [lat_clusters[i] for i in sorted(lat_clusters)]
    mean_gain, (mean_lb, mean_ub) = cluster_bootstrap(lat_cl, mean, level=1.0 - 2.0 * (1.0 - LATENCY_LOWER_BOUND_LEVEL))
    if mean_gain is None:
        lat_state = "NOT_EVALUABLE"
    elif mean_gain >= LATENCY_MATERIAL_MS and mean_lb > 0:
        lat_state = "MATERIAL"
    elif mean_gain >= LATENCY_MATERIAL_MS:
        lat_state = "NOT_SHOWN"
    else:
        lat_state = "NOT_MATERIAL"
    # secondary, report-only (prereg 10): the median gain with its two-sided 95% CI and the HL estimate
    med, med_ci = cluster_bootstrap(lat_cl, median)

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

    adj = [adj_clusters[i] for i in sorted(adj_clusters)]
    adj_est, adj_ci = cluster_bootstrap(adj, gain_at_equal_thinking)
    pooled_ab = [x for c in lat_clusters.values() for x in c]
    latency = {
        "pairs": len(lat),
        "a_ms": dist(per_arm("sdk_latency_ms", 0)), "b_ms": dist(per_arm("sdk_latency_ms", 1)),
        "delta_b_minus_a_ms": dist([-x for x in pooled_ab]),
        "delta_a_minus_b_ms": dist(pooled_ab),
        "mean_improvement_ms": mean_gain, "mean_improvement_lower_bound_one_sided_95": mean_lb,
        "mean_improvement_ci90": [mean_lb, mean_ub],
        "threshold_ms": LATENCY_MATERIAL_MS, "rule": "mean(A-B) >= threshold AND one-sided 95% lower bound > 0",
        "state": lat_state,
        "median_improvement_ms": med, "median_improvement_ci95": list(med_ci),
        "hodges_lehmann_improvement_ms": hodges_lehmann(pooled_ab),
        "secondary_label": "REPORT_ONLY (median, its CI and the HL estimate have no verdict effect)",
        "by_order_mean_ms": {o: mean(v) for o, v in by_order.items()},
        "by_order_median_ms": {o: median(v) for o, v in by_order.items()},
        # report-only (prereg 10): the gain left once the B-A thinking-token difference is regressed out
        "gain_at_equal_thinking_ms": {"label": "REPORT_ONLY", "estimate": adj_est, "ci95": list(adj_ci),
                                      "pairs": sum(len(c) for c in adj)},
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
                     "chars_b": dist([len(b["features"]["abstract"]) for _, b in both.values()])},
        "highlights": {"count_a": dist([len(a["features"]["highlights"]) for a, _ in both.values()]),
                       "count_b": dist([len(b["features"]["highlights"]) for _, b in both.values()])},
    }
    b_thoughts = [_num(v[1]["tap"].get("thoughts_tokens")) for v in lat.values()]
    b_thoughts = [x for x in b_thoughts if x is not None]
    thinking_rep = {
        "label": "REPORT_ONLY (budget adherence; no verdict effect)",
        "budget_b": THINKING_BUDGET_B,
        "a_thoughts": dist([_num(v[0]["tap"].get("thoughts_tokens")) for v in lat.values()]),
        "b_thoughts": dist(b_thoughts),
        "b_over_budget": sum(1 for x in b_thoughts if x > THINKING_BUDGET_B),
        "b_over_budget_share": (sum(1 for x in b_thoughts if x > THINKING_BUDGET_B) / len(b_thoughts))
        if b_thoughts else None,
    }
    schema_rep = {
        "a_raw_concepts": dist([v[0]["raw_counts"]["concepts"] for v in views.values()]),
        "a_raw_relations": dist([v[0]["raw_counts"]["relations"] for v in views.values()]),
        "b_raw_concepts": dist([v[1]["raw_counts"]["concepts"] for v in views.values()]),
        "b_raw_relations": dist([v[1]["raw_counts"]["relations"] for v in views.values()]),
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
    # A B-only pattern here can mean schema-induced server errors that the frozen allowlist counts as faults.
    pf_by_arm = {"A": 0, "B": 0}
    for att in attempts:
        for c in (att.get("classification") or {}).get("calls") or []:
            if c.get("provider_fault") and c.get("who") in pf_by_arm:
                pf_by_arm[c["who"]] += 1

    result = {
        "tool": "h2_ab_score", "scorer_version": SCORER_VERSION, "ledger_sha256": sha256_file(ledger_path),
        "prereg_sha256": meta.get("prereg_sha256"),
        "run": {"status": status, "stop_reason": summary.get("stop_reason"), "complete": complete,
                "scheduled_pairs": SCHEDULED_PAIRS, "attempts": len(attempts),
                "replacements": sum(1 for a in attempts if a.get("kind") == "replacement"),
                "scored_pairs": len(ss["scored"]), "unresolved": ss["unresolved"], "pending": ss["pending"],
                "provider_calls": summary.get("provider_calls"),
                "provider_faults": summary.get("provider_faults"),
                "provider_fault_calls_by_arm": pf_by_arm,
                "http_402_attempts": sum(1 for a in attempts if _attempt_has_402(a)),
                "bad_lines": led["bad_lines"]},
        "integrity": integ,
        "hard_fail": {"pairs": len(hard_pairs), "by_code": by_code,
                      "events": [{"pass": k[0], "index": k[1], "events": e} for k, e in sorted(hard_pairs.items())]},
        "excluded": excluded,
        "quality_pairs": len(both),
        "endpoints": endpoints,
        "uncertainty_warnings": warnings,
        "latency": latency, "tokens": tokens_rep,
        "thinking": thinking_rep, "schema": schema_rep, "cga1": cga1, "report_only": report_only, "cost": cost,
    }
    result["verdict"] = decide(result)
    result["_pair_rows"] = pair_rows(views, events, ss["scored"])
    return result


def decide(r: dict) -> dict:
    """Prereg section 12: ordered; the first matching step decides."""
    status = r["run"]["status"]
    if not r["integrity"]["ok"] or status in (ST_GUARD, ST_CAPTURE):
        return {"label": "INCONCLUSIVE", "sub_reason": "HARNESS_INTEGRITY", "step": 1,
                "hard_fail_pairs_before_stop": r["hard_fail"]["pairs"]}
    # A 402 on arm A fails the turn, so the frozen F1-before-F2 order reports it under S1.
    if status == ST_402 or (status == ST_TURN and r["run"]["http_402_attempts"]):
        return {"label": "INCONCLUSIVE", "sub_reason": "HTTP_402", "step": 1,
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
                "a_defects", "b_defects", "claim_smbm", "unc_smbm", "abstract_jaccard", "highlights_smbm"]


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
            "abstract_jaccard": jaccard(tokens(fa["abstract"]), tokens(fb["abstract"])) if both else None,
            "highlights_smbm": smbm(fa["highlights"], fb["highlights"]) if both else None,
        })
    return rows


# ------------------------------------------------------------------ #
# entry point
# ------------------------------------------------------------------ #
def _write_json(path: str, obj) -> str:
    # ASCII-escaped: model-chosen keys can reach the summary, and a lone surrogate must not stop the write
    data = (json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str) + "\n").encode("ascii")
    with open(path, "xb") as fh:
        fh.write(data)
    return hashlib.sha256(data).hexdigest()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 3 and argv[0] == "score":
        result = score(argv[1])
        rows = result.pop("_pair_rows")
        summary_sha = _write_json(argv[2] + "_summary.json", result)
        with open(argv[2] + "_pairs.csv", "x", encoding="utf-8", errors="backslashreplace", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=PAIR_COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(json.dumps({"verdict": result["verdict"], "summary_sha256": summary_sha,
                          "scored_pairs": result["run"]["scored_pairs"]}))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
