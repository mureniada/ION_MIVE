"""H1 live A/B (C3/R4): offline calibration of the quality margins and the
latency rule against unchanged-vs-unchanged IVE pairs (h1_ab_calibration.py).

Operator request 2026-10-07 20:03Z ("H1 PREREG - OFFLINE RULE CALIBRATION
BEFORE APPROVAL"). Reads stored files only and makes no provider call.

    python h1_ab_calibration.py <e3pa_ive_sizing.csv> <h1_ab_baseline.json> \
        <h1_cap_sensitivity.json> <out.json>

Data: the 81 unchanged v0.4 IVE calls of the provider-aware Phase A run (27
questions x 3 passes, one IVE call per turn, same deployment, prompt and schema
as arm A). Step 0 files supply the admitted-evidence count per question and the
per-question C3/R4 token cut used for the realistic effect profile.

Null model ("distinct-observation pairs", primary): every synthetic pair takes
two DIFFERENT stored observations of the same question as A and B. Given the
stored data the pair differences are independent, symmetric around 0 and have
expected variance 2 s^2 (s = the question's within-question SD), so the noise
level is unbiased, integer counts stay integers and each question keeps its own
spread. Sensitivity model ("pooled residuals"): A and B are the question mean
plus two independent draws from all 81 variance-corrected residuals. Both
assume the two calls of a pair are no more alike than calls minutes apart; any
shared provider load would make real pairs less noisy (INFERRED).

Every interval is the scorer's own: a percentile cluster bootstrap over the 27
questions, linear-interpolation quantiles. Shifting every pair difference by a
constant shifts a mean-based interval by that constant, so for the mean
endpoints every operating characteristic follows from the null distribution of
the interval bounds.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys

import numpy as np

CALIBRATION_VERSION = "h1-ab-calibration-v1"
SEED = 20261007
N_Q = 27
SIZES = {"81 (3 passes)": 3, "135 (5 passes)": 5, "162 (6 passes)": 6}
QUALITY_SIMS, QUALITY_BOOT = 4000, 2000
LATENCY_SIMS, LATENCY_BOOT = 2000, 1000
HL_SIMS, HL_BOOT = 600, 400
GAINS_MS = (0, 250, 500, 800, 1000, 1200)
THRESHOLD_MS = 500.0
MARGINS = {
    "claims": (0.25, 0.35, 0.5, 0.75),
    "uncertainty": (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50),
    "coverage": (0.01, 0.02, 0.03, 0.05),
}
PASS_TARGET = 0.90   # "realistically distinguishable": an unchanged system shows NI at least this often


def sha256_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ------------------------------------------------------------------ #
# data
# ------------------------------------------------------------------ #
FIELDS = {"claims": "n_claims", "uncertainty": "n_uncertainty", "uncertainty_chars": "chars_uncertainty",
          "evidence_rendered": "n_evidence", "latency_ms": "ive_sdk_latency_ms",
          "visible_tokens": "ive_candidates_tokens", "thinking_tokens": "ive_thoughts_tokens",
          "prompt_tokens": "ive_prompt_tokens"}


def load(csv_path: str, baseline_path: str, cap_path: str) -> dict:
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    if len(rows) != 81 or any(r["n_ive_calls"] != "1" for r in rows):
        raise SystemExit("expected 81 Phase A rows with one IVE call each")
    rows.sort(key=lambda r: (int(r["index"]), int(r["pass"])))
    X = {k: np.array([float(r[f]) for r in rows]).reshape(N_Q, 3) for k, f in FIELDS.items()}
    base = {p["index"]: p for p in json.load(open(baseline_path, encoding="utf-8"))["per_turn"]}
    cd = np.array([float(base[i]["context_documents"]) for i in range(N_Q)])
    X["coverage"] = X["evidence_rendered"] / cd[:, None]
    cap = {p["index"]: p for p in json.load(open(cap_path, encoding="utf-8"))["per_turn"]}
    capj = json.load(open(cap_path, encoding="utf-8"))
    slope = capj["latency_fit_ms_per_output_token"]["slope"]
    profile = np.array([cap[i]["C3/R4"][3] * slope for i in range(N_Q)])   # ms removed per IVE call
    checks = {
        "prompt_tokens_identical_across_passes": int(sum(len(set(X["prompt_tokens"][i])) == 1 for i in range(N_Q))),
        "rendered_evidence_never_exceeds_admitted": bool((X["evidence_rendered"] <= cd[:, None]).all()),
        "c3r4_profile_slope_ms_per_token": slope,
    }
    return {"X": X, "context_documents": cd, "profile_ms": profile, "checks": checks}


# ------------------------------------------------------------------ #
# noise
# ------------------------------------------------------------------ #
def noise_table(X: dict) -> dict:
    out = {}
    for k in ("claims", "coverage", "uncertainty", "uncertainty_chars", "latency_ms", "visible_tokens",
              "thinking_tokens"):
        x = X[k]
        var = x.var(axis=1, ddof=1)
        sd = float(math.sqrt(var.mean()))
        resid = (x - x.mean(axis=1, keepdims=True)).ravel() * math.sqrt(1.5)
        kurt = float(((resid - resid.mean()) ** 4).mean() / resid.var() ** 2 - 3.0)
        out[k] = {"mean": float(x.mean()), "within_question_sd": sd,
                  "between_question_sd": float(x.mean(axis=1).std(ddof=1)),
                  "questions_varying": int((var > 0).sum()), "max_question_sd": float(math.sqrt(var.max())),
                  "residual_excess_kurtosis": kurt,
                  "se_mean_b_minus_a": {n: sd * math.sqrt(2.0 / (N_Q * p)) for n, p in SIZES.items()}}
    return out


# ------------------------------------------------------------------ #
# synthetic unchanged-vs-unchanged runs
# ------------------------------------------------------------------ #
def null_pairs(rng, x: np.ndarray, sims: int, per_q: int, model: str):
    """(A, B) arrays of shape (sims, 27, per_q[, m]) for observations x of shape (27, 3[, m])."""
    nq, k = x.shape[0], x.shape[1]
    qi = np.arange(nq)[None, :, None]
    if model == "distinct":
        a = rng.integers(0, k, size=(sims, nq, per_q))
        b = (a + rng.integers(1, k, size=(sims, nq, per_q))) % k
        return x[qi, a], x[qi, b]
    if model == "pooled":
        mu = x.mean(axis=1)
        resid = (x - x.mean(axis=1, keepdims=True)) * math.sqrt(k / (k - 1.0))
        pool = resid.reshape((nq * k,) + x.shape[2:])
        ia = rng.integers(0, len(pool), size=(sims, nq, per_q))
        ib = rng.integers(0, len(pool), size=(sims, nq, per_q))
        base = mu[None, :, None] if x.ndim == 2 else mu[None, :, None, :]
        return base + pool[ia], base + pool[ib]
    raise ValueError(model)


def boot_index(rng, boot: int) -> np.ndarray:
    return rng.integers(0, N_Q, size=(boot, N_Q))


def mean_ci(d: np.ndarray, idx: np.ndarray, lo_q=0.025, hi_q=0.975):
    """Pooled mean and percentile cluster-bootstrap CI per simulated run.
    d: (sims, 27, per_q). Equal cluster sizes, so the pooled mean of a
    resample is the mean of its cluster means."""
    cm = d.mean(axis=2)                      # (sims, 27)
    est = cm.mean(axis=1)
    lo, hi = np.empty(len(cm)), np.empty(len(cm))
    for s0 in range(0, len(cm), 500):
        bm = cm[s0:s0 + 500][:, idx].mean(axis=2)          # (chunk, boot)
        lo[s0:s0 + 500], hi[s0:s0 + 500] = np.quantile(bm, [lo_q, hi_q], axis=1)
    return est, lo, hi


def ni_profile(lo: np.ndarray, hi: np.ndarray, margin: float) -> dict:
    """Operating characteristics of 'NONINFERIOR when the CI lower bound > -margin'
    from the null bounds; a true degradation d moves both bounds down by d."""
    p_pass = float((lo > -margin).mean())
    p_inf = float((hi < -margin).mean())

    def passed_at(q):          # true degradation passed with probability q
        return float(margin + np.quantile(lo, 1.0 - q))

    return {"margin": margin, "p_noninferior_if_unchanged": p_pass, "p_not_shown_if_unchanged": 1 - p_pass - p_inf,
            "p_inferior_if_unchanged": p_inf,
            "true_drop_passed_50pct": passed_at(0.5), "true_drop_passed_20pct": passed_at(0.2),
            "true_drop_passed_5pct": passed_at(0.05),
            "p_pass_if_true_drop_equals_margin": float((lo > 0).mean())}


def quality(rng, X: dict) -> dict:
    out = {}
    keys = ("claims", "coverage", "uncertainty", "uncertainty_chars")
    stack = np.stack([X[k] for k in keys], axis=2)          # (27, 3, 4), joint draws keep within-call correlation
    for model in ("distinct", "pooled"):
        out[model] = {}
        for size, per_q in SIZES.items():
            A, B = null_pairs(rng, stack, QUALITY_SIMS, per_q, model)
            idx = boot_index(rng, QUALITY_BOOT)
            res, bounds = {}, {}
            for j, k in enumerate(keys):
                est, lo, hi = mean_ci(B[..., j] - A[..., j], idx)
                bounds[k] = (lo, hi)
                if k in MARGINS:
                    res[k] = {"ci_half_width_median": float(np.median((hi - lo) / 2)),
                              "margins": [ni_profile(lo, hi, m) for m in MARGINS[k]]}
            # warnings computable here: W1 (count), W2 (characters), W3 (emptied, sign test)
            w1 = bounds["uncertainty"][1] < 0
            w2 = bounds["uncertainty_chars"][1] < 0
            ua, ub = A[..., 2], B[..., 2]
            b_only = ((ub == 0) & (ua > 0)).sum(axis=(1, 2))
            a_only = ((ua == 0) & (ub > 0)).sum(axis=(1, 2))
            w3 = np.array([bo > ao and sign_test(int(bo), int(ao)) < 0.05 for bo, ao in zip(b_only, a_only)])
            res["warnings_if_unchanged"] = {"W1": float(w1.mean()), "W2": float(w2.mean()), "W3": float(w3.mean()),
                                            "any_of_W1_W3": float((w1 | w2 | w3).mean())}
            res["_bounds"] = bounds
            res["_warn"] = w1 | w2 | w3
            out[model][size] = res
    return out


def sign_test(n_plus: int, n_minus: int) -> float:
    n = n_plus + n_minus
    if n == 0:
        return 1.0
    k = min(n_plus, n_minus)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


# ------------------------------------------------------------------ #
# latency rules
# ------------------------------------------------------------------ #
def pooled_stat_ci(d: np.ndarray, idx: np.ndarray, stat, qs):
    """Point estimate on all pairs and percentile cluster-bootstrap quantiles of
    `stat` over the pooled pair values of each resample. d: (sims, 27, per_q)."""
    sims, nq, per_q = d.shape
    est = stat(d.reshape(sims, nq * per_q))
    boots = np.empty((sims, len(idx)))
    for b, row in enumerate(idx):
        boots[:, b] = stat(d[:, row, :].reshape(sims, nq * per_q))
    return est, np.quantile(boots, qs, axis=1)


def med(v):
    return np.median(v, axis=1)


def hodges_lehmann(v):
    n = v.shape[1]
    i, j = np.triu_indices(n)
    return np.median((v[:, i] + v[:, j]) / 2.0, axis=1)


def avg(v):
    return v.mean(axis=1)


RULES = {
    "A_median_ge_0.5": "median(A-B) >= 0.5 s",
    "B_median_ge_0.5_and_ci95_two_sided_gt_0": "median >= 0.5 s and two-sided 95% CI lower bound > 0 (current)",
    "C1_hl_ge_0.5_and_one_sided_95_gt_0": "Hodges-Lehmann >= 0.5 s and one-sided 95% lower bound > 0",
    "C2_mean_ge_0.5_and_one_sided_95_gt_0": "mean >= 0.5 s and one-sided 95% lower bound > 0",
    "C3_median_ge_0.5_and_one_sided_95_gt_0": "median >= 0.5 s and one-sided 95% lower bound > 0",
    "C4_hl_ge_0.5_and_one_sided_90_gt_0": "Hodges-Lehmann >= 0.5 s and one-sided 90% lower bound > 0",
}


def latency(rng, X: dict, profile_ms: np.ndarray) -> dict:
    lat = X["latency_ms"]
    out = {}
    for model in ("distinct", "pooled"):
        out[model] = {}
        for size, per_q in SIZES.items():
            A, B = null_pairs(rng, lat, LATENCY_SIMS, per_q, model)
            noise = A - B                                         # A - B: positive = B faster
            idx = boot_index(rng, LATENCY_BOOT)
            m_est, (m_lo95, m_lo90) = pooled_stat_ci(noise, idx, med, [0.025, 0.05])
            a_est, (a_lo95, a_lo90) = pooled_stat_ci(noise, idx, avg, [0.025, 0.05])
            sub = noise[:HL_SIMS]
            hidx = idx[:HL_BOOT]
            h_est, (h_lo95, h_lo90, h_lo80) = pooled_stat_ci(sub, hidx, hodges_lehmann, [0.025, 0.05, 0.10])
            table = {}
            for profile in (("constant", "c3r4_profile") if model == "distinct" else ("constant",)):
                for g in GAINS_MS:
                    if profile == "constant":
                        shift = np.full(N_Q, float(g))
                    else:
                        if g == 0:
                            continue
                        shift = profile_ms * (g / float(np.median(profile_ms)))   # same shape, median scaled to g
                    # Equivariance: rank and mean statistics of (noise + c) move by c only for a constant c, so a
                    # question-varying shift is added to the pair values and the statistics recomputed.
                    if profile == "constant":
                        r = {
                            "A_median_ge_0.5": (m_est + g >= THRESHOLD_MS),
                            "B_median_ge_0.5_and_ci95_two_sided_gt_0": (m_est + g >= THRESHOLD_MS) & (m_lo95 + g > 0),
                            "C2_mean_ge_0.5_and_one_sided_95_gt_0": (a_est + g >= THRESHOLD_MS) & (a_lo90 + g > 0),
                            "C3_median_ge_0.5_and_one_sided_95_gt_0": (m_est + g >= THRESHOLD_MS) & (m_lo90 + g > 0),
                            "C1_hl_ge_0.5_and_one_sided_95_gt_0": (h_est + g >= THRESHOLD_MS) & (h_lo90 + g > 0),
                            "C4_hl_ge_0.5_and_one_sided_90_gt_0": (h_est + g >= THRESHOLD_MS) & (h_lo80 + g > 0),
                        }
                    else:
                        d = noise + shift[None, :, None]
                        me, (ml95, ml90) = pooled_stat_ci(d, idx, med, [0.025, 0.05])
                        ae, (al95, al90) = pooled_stat_ci(d, idx, avg, [0.025, 0.05])
                        hs = d[:HL_SIMS]
                        he, (hl95, hl90, hl80) = pooled_stat_ci(hs, hidx, hodges_lehmann, [0.025, 0.05, 0.10])
                        r = {
                            "A_median_ge_0.5": me >= THRESHOLD_MS,
                            "B_median_ge_0.5_and_ci95_two_sided_gt_0": (me >= THRESHOLD_MS) & (ml95 > 0),
                            "C2_mean_ge_0.5_and_one_sided_95_gt_0": (ae >= THRESHOLD_MS) & (al90 > 0),
                            "C3_median_ge_0.5_and_one_sided_95_gt_0": (me >= THRESHOLD_MS) & (ml90 > 0),
                            "C1_hl_ge_0.5_and_one_sided_95_gt_0": (he >= THRESHOLD_MS) & (hl90 > 0),
                            "C4_hl_ge_0.5_and_one_sided_90_gt_0": (he >= THRESHOLD_MS) & (hl80 > 0),
                        }
                    table[f"{profile}:{g}"] = {k: float(np.mean(v)) for k, v in r.items()}
            out[model][size] = {"rates": table,
                                "sd_median_ms": float(m_est.std()), "sd_mean_ms": float(a_est.std()),
                                "sd_hl_ms": float(h_est.std())}
    return out


# ------------------------------------------------------------------ #
# entry point
# ------------------------------------------------------------------ #
def strip(obj):
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    csv_path, baseline_path, cap_path, out_path = argv
    data = load(csv_path, baseline_path, cap_path)
    rng = np.random.default_rng(SEED)
    result = {
        "tool": "h1_ab_calibration", "version": CALIBRATION_VERSION, "numpy": np.__version__,
        "seed": SEED, "label": "ESTIMATED (offline simulation from stored unchanged IVE calls)",
        "sources": {p: sha256_file(p) for p in (csv_path, baseline_path, cap_path)},
        "checks": data["checks"],
        "c3r4_profile_ms": {"median": float(np.median(data["profile_ms"])), "mean": float(data["profile_ms"].mean()),
                            "zero_questions": int((data["profile_ms"] == 0).sum())},
        "noise": noise_table(data["X"]),
        "quality": strip(quality(rng, data["X"])),
        "latency": latency(rng, data["X"], data["profile_ms"]),
        "rules": RULES,
    }
    blob = (json.dumps(result, sort_keys=True, ensure_ascii=True, indent=1) + "\n").encode("ascii")
    with open(out_path, "xb") as fh:
        fh.write(blob)
    print(json.dumps({"out_sha256": hashlib.sha256(blob).hexdigest()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
