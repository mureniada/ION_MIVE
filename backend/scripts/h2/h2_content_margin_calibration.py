"""H2 live A/B (IVE thinking budget 1280): offline null calibration of the content
non-inferiority margins (h2_content_margin_calibration.py). Stdlib only. ZERO provider calls.

Operator decision 2026-10-07 21:25Z ("H2 1280, FINAL PREPARATION ONLY"), item 1:
calibrate the abstract and highlights margins on stored unchanged reports. The
claim-content and uncertainty-content endpoints are recomputed alongside as a
cross-check against the margins already calibrated for 81 pairs (0.04 / 0.125).

    python h2_content_margin_calibration.py <h2_ab_score.py> <reports.jsonl> <out.json> [sims] [boot]

reports.jsonl: one stored, unchanged v0.4 IVE report per line,
    {"index": <question index 0-26>, "report": <normalized IVE report dict>}
(the app's contract dict: abstract, highlights, claims, uncertainty, ...). Every
question needs at least 6 reports.

Null model (exact scorer emulation): each simulated run draws, per question, 6
DIFFERENT stored reports of that question; the first 3 are arm A of passes 1-3,
the last 3 arm B of passes 1-3. Both arms are therefore the unchanged system.
Each endpoint is computed by the scorer's own content_clusters and
CONTENT_SIMILARITY, and its interval by the scorer's own cluster_bootstrap
(seed and level as frozen; resamples = boot). An unchanged system passes an
endpoint when the lower 95% bound is above -margin.

Recommended margin: the smallest multiple of 0.005 at which at least 95% of
unchanged runs pass (the target in H2_THINKING_PREREG_DESIGN.md). Because the
endpoint shifts exactly by d when every cross-arm similarity drops by d, the
detection rates for a true degradation d follow from the same null
distribution: P(FAIL or NOT_SHOWN) = P(lower bound <= d - margin).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import random
import sys

CALIBRATION_VERSION = "h2-content-margin-calibration-v1"
SEED = 20261007
PASSES = 3
PASS_TARGET = 0.95
STEP = 0.005
ENDPOINTS = ("abstract_content", "highlights_content", "claim_content", "uncertainty_content")
GRID = tuple(round(STEP * k, 3) for k in range(1, 61))     # 0.005 .. 0.300


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_scorer(path: str):
    spec = importlib.util.spec_from_file_location("h2_ab_score_calib", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_reports(scorer, path: str) -> dict:
    """{question index: [features, ...]} with the scorer's own report_features."""
    by_q: dict = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            by_q.setdefault(int(row["index"]), []).append(scorer.report_features(row["report"], None))
    return by_q


def similarity_tables(scorer, by_q: dict) -> dict:
    """Every pairwise similarity, once: {endpoint: {question: n x n matrix}}."""
    out = {}
    for name in ENDPOINTS:
        sim = scorer.CONTENT_SIMILARITY[name]
        out[name] = {i: [[sim(x, y) for y in obs] for x in obs] for i, obs in by_q.items()}
    return out


def quantile(sorted_values: list, q: float):
    n = len(sorted_values)
    pos = q * (n - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def simulate(scorer, tables: dict, by_q: dict, sims: int, boot: int) -> dict:
    rng = random.Random(SEED)
    questions = sorted(by_q)
    out = {name: {"estimate": [], "lower": []} for name in ENDPOINTS}
    for _ in range(sims):
        draw = {i: rng.sample(range(len(by_q[i])), 2 * PASSES) for i in questions}
        # (pass, index) -> (A, B) as (question, stored-report position); the similarity reads the tables
        pairs = {(p, i): ((i, draw[i][p - 1]), (i, draw[i][PASSES + p - 1]))
                 for i in questions for p in range(1, PASSES + 1)}
        for name in ENDPOINTS:
            table = tables[name]
            clusters = scorer.content_clusters(pairs, lambda x, y, t=table: t[x[0]][x[1]][y[1]])
            est, (lo, _) = scorer.cluster_bootstrap(clusters, scorer.mean, resamples=boot)
            out[name]["estimate"].append(est)
            out[name]["lower"].append(lo)
    return out


def summarize(name: str, est: list, lower: list, tables: dict) -> dict:
    lower_sorted, est_sorted = sorted(lower), sorted(est)
    n = len(lower)

    def pass_rate(m):
        return sum(1 for x in lower if x > -m) / n

    rates = {f"{m:.3f}": pass_rate(m) for m in GRID}
    recommended = next((m for m in GRID if pass_rate(m) >= PASS_TARGET), None)
    same_q = [v for mat in tables[name].values() for a, row in enumerate(mat) for b, v in enumerate(row) if a < b]
    res = {
        "null_estimate": {"mean": sum(est) / n, "sd": math.sqrt(sum((x - sum(est) / n) ** 2 for x in est) / (n - 1)),
                          "p05": quantile(est_sorted, 0.05), "p95": quantile(est_sorted, 0.95)},
        "null_lower_bound": {q: quantile(lower_sorted, float(q)) for q in ("0.01", "0.05", "0.10", "0.50", "0.90")},
        "same_question_similarity_mean": sum(same_q) / len(same_q) if same_q else None,
        "unchanged_pass_rate": rates,
        "recommended_margin": recommended,
    }
    if recommended is not None:
        res["unchanged_pass_rate_at_recommended"] = pass_rate(recommended)
        # true degradation d at which the endpoint fails to show NI with probability 50% / 90%
        res["degradation_detected_50"] = recommended + quantile(lower_sorted, 0.50)
        res["degradation_detected_90"] = recommended + quantile(lower_sorted, 0.90)
    return res


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in (3, 4, 5):
        print(__doc__)
        return 2
    scorer_path, reports_path, out_path = argv[:3]
    sims = int(argv[3]) if len(argv) > 3 else 2000
    boot = int(argv[4]) if len(argv) > 4 else 2000
    scorer = load_scorer(scorer_path)
    by_q = load_reports(scorer, reports_path)
    short = {i: len(v) for i, v in by_q.items() if len(v) < 2 * PASSES}
    if short or len(by_q) != scorer.N_QUESTIONS:
        print(json.dumps({"error": "need 27 questions with >= 6 reports each", "questions": len(by_q),
                          "short": short}))
        return 2
    tables = similarity_tables(scorer, by_q)
    raw = simulate(scorer, tables, by_q, sims, boot)
    result = {
        "tool": "h2_content_margin_calibration", "version": CALIBRATION_VERSION,
        "label": "ESTIMATED (offline null simulation from stored unchanged IVE reports; 0 provider calls)",
        "inputs": {"scorer_sha256": sha256_file(scorer_path), "scorer_version": scorer.SCORER_VERSION,
                   "reports_sha256": sha256_file(reports_path), "reports": sum(len(v) for v in by_q.values()),
                   "per_question": {str(i): len(by_q[i]) for i in sorted(by_q)}},
        "design": {"passes": PASSES, "pairs": PASSES * len(by_q), "sims": sims, "boot": boot, "seed": SEED,
                   "scorer_bootstrap_seed": scorer.SEED, "ci_level": scorer.CI_LEVEL, "pass_target": PASS_TARGET,
                   "step": STEP},
        "endpoints": {name: summarize(name, raw[name]["estimate"], raw[name]["lower"], tables)
                      for name in ENDPOINTS},
        "frozen_margins_for_cross_check": {"claim_content": scorer.MARGIN_CLAIM_CONTENT,
                                           "uncertainty_content": scorer.MARGIN_UNCERTAINTY_CONTENT},
    }
    data = (json.dumps(result, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")
    with open(out_path, "xb") as fh:
        fh.write(data)
    print(json.dumps({"out_sha256": hashlib.sha256(data).hexdigest(),
                      "recommended": {k: v["recommended_margin"] for k, v in result["endpoints"].items()}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
