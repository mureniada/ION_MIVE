"""H1 live A/B (C3/R4): sizing of the preregistered margins and latency rule (h1_ab_sizing.py). Stdlib only.

Reproduces every ESTIMATED noise and operating-characteristic figure in
H1_AB_C3R4_PREREG.md sections 8, 10 and 14 from the 81 unchanged v0.4 IVE calls
of the provider-aware Phase A run (e3pa_ive_sizing.csv: 3 passes x 27
questions, one IVE call each). Reads one file, makes no provider call.

    python h1_ab_sizing.py <e3pa_ive_sizing.csv> <out.json>

Model for the operating characteristics: A = question mean + residual,
B = question mean + residual - true gain, residuals drawn independently from the
pooled within-question residuals (variance-corrected). Independent arms ignore
any shared provider load between the two calls of a pair, so the latency
figures are, if anything, pessimistic (INFERRED).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import statistics
import sys

SIZING_VERSION = "h1-ab-sizing-v1"
PAIRS = 81
Z95 = 1.959963984540054
SIM_SEED = 20261007
SIM_RUNS = 400
SIM_RESAMPLES = 500
GAINS_MS = (0, 500, 800, 1200, 1600, 2000)
THRESHOLD_MS = 500.0
COUNT_FIELDS = ("n_claims", "n_uncertainty", "chars_uncertainty", "n_highlights",
                "ive_sdk_latency_ms", "ive_thoughts_tokens", "ive_candidates_tokens")
NI_MARGINS = {"n_claims": (0.35, 0.5), "n_uncertainty": (0.25, 0.30, 0.35)}


def phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def quantile(s: list, q: float) -> float:
    pos = q * (len(s) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def median(v: list) -> float:
    return quantile(sorted(v), 0.5)


def load(path: str) -> dict:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    by_q: dict = {}
    for r in rows:
        by_q.setdefault(int(r["index"]), []).append(r)
    if len(rows) != PAIRS or len(by_q) != 27 or {len(v) for v in by_q.values()} != {3}:
        raise SystemExit("expected 81 rows: 27 questions x 3 passes")
    return by_q


def within_sd(by_q: dict, field: str) -> float:
    return math.sqrt(sum(statistics.variance([float(r[field]) for r in v]) for v in by_q.values()) / len(by_q))


def noise(by_q: dict) -> dict:
    out = {}
    for f in COUNT_FIELDS:
        sd = within_sd(by_q, f)
        se = math.sqrt(2.0) * sd / math.sqrt(PAIRS)          # SE of a mean B - A over 81 pairs, no true effect
        entry = {"within_question_sd": sd, "se_mean_b_minus_a": se, "ci95_half_width": Z95 * se,
                 "questions_differing_across_passes": sum(1 for v in by_q.values() if len({r[f] for r in v}) > 1)}
        if f in NI_MARGINS:
            # noninferiority shown when mean - half_width > -margin
            entry["chance_ni_shown_if_no_effect"] = {str(m): phi((m - Z95 * se) / se) for m in NI_MARGINS[f]}
            entry["chance_ni_shown_if_true_drop_0.25"] = {str(m): phi((m - 0.25 - Z95 * se) / se)
                                                        for m in NI_MARGINS[f]}
        out[f] = entry
    return out


def ols_latency_on_tokens(by_q: dict) -> dict:
    rows = [r for v in by_q.values() for r in v]
    x = [float(r["ive_candidates_tokens"]) + float(r["ive_thoughts_tokens"]) for r in rows]
    y = [float(r["ive_sdk_latency_ms"]) for r in rows]
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    icpt = my - slope * mx
    ssr = sum((b - icpt - slope * a) ** 2 for a, b in zip(x, y))
    sst = sum((b - my) ** 2 for b in y)
    return {"intercept_ms": icpt, "ms_per_output_token": slope, "r2": 1.0 - ssr / sst,
            "residual_sd_ms": math.sqrt(ssr / (n - 2))}


def latency_rule(by_q: dict) -> dict:
    """Chance that the preregistered latency rule fires, by true median gain."""
    lat = {i: [float(r["ive_sdk_latency_ms"]) for r in v] for i, v in by_q.items()}
    mu = {i: sum(v) / len(v) for i, v in lat.items()}
    res = [(x - mu[i]) * math.sqrt(3.0 / 2.0) for i, v in lat.items() for x in v]
    qs = sorted(lat)
    rng = random.Random(SIM_SEED)
    out = []
    for gain in GAINS_MS:
        alone = with_ci = 0
        for _ in range(SIM_RUNS):
            clusters = [[(mu[i] + rng.choice(res)) - (mu[i] + rng.choice(res) - gain) for _ in range(3)] for i in qs]
            est = median([d for c in clusters for d in c])
            stats = []
            for _ in range(SIM_RESAMPLES):
                sample = []
                for _ in range(len(clusters)):
                    sample.extend(clusters[rng.randrange(len(clusters))])
                stats.append(median(sample))
            stats.sort()
            lo = quantile(stats, 0.025)
            alone += est >= THRESHOLD_MS
            with_ci += est >= THRESHOLD_MS and lo > 0
        out.append({"true_gain_ms": gain, "p_median_ge_threshold": alone / SIM_RUNS,
                    "p_median_ge_threshold_and_ci_above_0": with_ci / SIM_RUNS})
    return {"runs_per_gain": SIM_RUNS, "bootstrap_resamples": SIM_RESAMPLES, "seed": SIM_SEED,
            "threshold_ms": THRESHOLD_MS, "rows": out}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    by_q = load(argv[0])
    result = {"tool": "h1_ab_sizing", "version": SIZING_VERSION, "label": "ESTIMATED",
              "source_sha256": hashlib.sha256(open(argv[0], "rb").read()).hexdigest(),
              "noise": noise(by_q), "latency_vs_output_tokens": ols_latency_on_tokens(by_q),
              "latency_rule": latency_rule(by_q)}
    data = (json.dumps(result, sort_keys=True, indent=1) + "\n").encode("utf-8")
    with open(argv[1], "xb") as fh:
        fh.write(data)
    print(json.dumps({"out_sha256": hashlib.sha256(data).hexdigest(),
                      "latency_rule": [(r["true_gain_ms"], r["p_median_ge_threshold"],
                                        r["p_median_ge_threshold_and_ci_above_0"])
                                       for r in result["latency_rule"]["rows"]]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
