"""H2 (IVE thinking budget) offline calibration (h2_thinking_calibration.py). ZERO provider calls.

Operator request 2026-10-07 21:13Z ("CLOSE H1, MOVE TO H2 DESIGN/CALIBRATION").
Uses stored unchanged data only:
  * e3pa_ive_sizing.csv: 81 unchanged IVE calls (27 questions x 3 passes) with
    visible tokens, thinking tokens and SDK latency;
  * the three E3 composer pair files (e3pa_pairs.csv, e3v04_pairs.csv,
    part8_pairs.csv): gemini-2.5-pro composer calls without a budget (A) and with
    thinking budget 512 (B). They show how this model actually uses a budget.

Two adherence models bound the projection:
  M1 ceiling:     thinking under budget b = min(T, b)        (the budget only truncates)
  M2 compression: thinking under budget b = min(T, r * b)    (r from the composer: the
                  model settles well under its budget once the budget binds)
Projected saving per call = (thinking slope, ms per token) x removed thinking tokens.
Visible output is assumed unchanged (UNKNOWN; a live run must measure it).

    python h2_thinking_calibration.py <e3pa_ive_sizing.csv> <pairs1.csv> [<pairs2.csv> ...] <out.json>
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys

import numpy as np

SEED = 20261007
BUDGETS = (1536, 1280, 1024, 768)
SIZES = {27: 1, 54: 2, 81: 3}           # pairs: passes
GAINS_MS = (0, 1000, 2000, 3000, 4000)
SIMS, BOOT = 4000, 2000
THRESHOLD_MS = 2000.0


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def load_ive(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    q = sorted({int(r["index"]) for r in rows})
    by = {i: sorted((r for r in rows if int(r["index"]) == i), key=lambda r: int(r["pass"])) for i in q}
    f = lambda k: np.array([[float(r[k]) for r in by[i]] for i in q])
    return {"T": f("ive_thoughts_tokens"), "V": f("ive_candidates_tokens"), "L": f("ive_sdk_latency_ms")}


def load_composer(paths):
    tA, tB, lA, lB = [], [], [], []
    for p in paths:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            try:
                vals = [float(r[k]) for k in ("think_A", "think_B", "lat_A", "lat_B")]
            except (KeyError, ValueError):
                continue
            for lst, v in zip((tA, tB, lA, lB), vals):
                lst.append(v)
    return tuple(np.array(x) for x in (tA, tB, lA, lB))


def ols(y, cols):
    X = np.column_stack([np.ones(len(y))] + cols)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    s2 = resid @ resid / (len(y) - X.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    return beta, se, float(r2), float(np.sqrt(s2))


def q(v, p):
    return float(np.quantile(v, p))


def summary(v):
    return {"median": q(v, 0.5), "mean": float(v.mean()), "p10": q(v, 0.1), "p90": q(v, 0.9)}


def projection(T, budget, r, slope):
    """Per-call removed thinking tokens and saving (ms) under budget `budget`."""
    ceiling = budget * r
    removed = np.clip(T - ceiling, 0, None)
    save = slope * removed
    return {"cap_binding_rate": float((T > ceiling).mean()), "removed_tokens": summary(removed),
            "saving_ms": summary(save), "share_saving_below_500ms": float((save < 500).mean()),
            "share_saving_ge_2000ms": float((save >= 2000).mean())}


def null_pairs(rng, L, sims, per_q):
    """A and B are two different stored observations of the same question."""
    nq, k = L.shape
    i = rng.integers(0, k, size=(sims, nq, per_q))
    j = (i + 1 + rng.integers(0, k - 1, size=(sims, nq, per_q))) % k
    qi = np.arange(nq)[None, :, None]
    return i, j, qi


def boot_mean_lb(rng, D, boot, level=0.95):
    """One-sided cluster-bootstrap lower bound of the pooled mean; D: sims x clusters x per_q."""
    sims, nq, per_q = D.shape
    cm = D.mean(axis=2)                                   # equal cluster sizes: pooled mean = mean of cluster means
    idx = rng.integers(0, nq, size=(boot, nq))
    bm = cm[:, idx].mean(axis=2)                          # sims x boot
    return np.quantile(bm, 1 - level, axis=1)


def power(rng, data, slope, r, budgets):
    L, T = data["L"], data["T"]
    out = {}
    for n, per_q in SIZES.items():
        i, j, qi = null_pairs(rng, L, SIMS, per_q)
        base = L[qi, i] - L[qi, j]                       # A - B under no effect
        rows = {}
        gains = {f"constant_{g}": np.full_like(base, g) for g in GAINS_MS}
        for b in budgets:                                # B's own baseline thinking decides its saving
            gains[f"budget_{b}_r{r}"] = slope * np.clip(T[qi, j] - b * r, 0, None)
        lb0 = boot_mean_lb(rng, base, BOOT)
        m0 = base.mean(axis=(1, 2))
        for name, g in gains.items():
            gm = g.mean(axis=(1, 2))
            # shift-equivariance holds for constant gains; heterogeneous gains are bootstrapped directly
            if name.startswith("constant_"):
                m, lb = m0 + gm, lb0 + gm
            else:
                d = base + g
                m, lb = d.mean(axis=(1, 2)), boot_mean_lb(rng, d, BOOT)
            rows[name] = {
                "true_mean_gain_ms": float(gm.mean()),
                "R1_mean_ge_2s_and_lb95_gt_0": float(((m >= THRESHOLD_MS) & (lb > 0)).mean()),
                "R2_mean_ge_2s_and_lb95_gt_1s": float(((m >= THRESHOLD_MS) & (lb > 1000)).mean()),
                "R3_lb95_gt_1s": float((lb > 1000).mean()),
            }
        out[f"{n} pairs ({per_q} pass{'es' if per_q > 1 else ''})"] = {
            "sd_mean_ms": float(m0.std()), "rates": rows}
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    ive_path, pair_paths, out_path = argv[0], argv[1:-1], argv[-1]
    rng = np.random.default_rng(SEED)
    data = load_ive(ive_path)
    T, V, L = (data[k].ravel() for k in ("T", "V", "L"))

    beta, se, r2, rsd = ols(L, [V, T])
    beta1, se1, r21, _ = ols(L, [V + T])
    tA, tB, lA, lB = load_composer(pair_paths)
    cb, cse, cr2, _ = ols(lA - lB, [tA - tB])
    ratio = tB / 512.0
    r_mid, r_lo, r_hi = q(ratio, 0.5), q(ratio, 0.1), q(ratio, 0.9)
    within_sd = float(np.sqrt(data["T"].var(axis=1, ddof=1).mean()))

    slopes = {"ive_thinking_ms_per_token": float(beta[2]), "ive_thinking_se": float(se[2]),
              "ive_visible_ms_per_token": float(beta[1]), "ive_visible_se": float(se[1]),
              "ive_intercept_ms": float(beta[0]), "ive_r2": r2, "ive_resid_sd_ms": rsd,
              "ive_pooled_output_ms_per_token": float(beta1[1]), "ive_pooled_r2": r21,
              "composer_ms_per_removed_thinking_token": float(cb[1]), "composer_se": float(cse[1]),
              "composer_r2": cr2}
    slope_mid = float(beta1[1])                       # pooled per-output-token slope (most precise)
    slope_band = (float(beta[2] - 1.96 * se[2]), float(beta[2] + 1.96 * se[2]))

    proj = {}
    for b in BUDGETS:
        proj[str(b)] = {
            "M1_ceiling": projection(T, b, 1.0, slope_mid),
            "M2_compression_mid": projection(T, b, r_mid, slope_mid),
            "sensitivity": {
                "M2_r_low": projection(T, b, r_lo, slope_mid)["saving_ms"],
                "M2_r_high": projection(T, b, r_hi, slope_mid)["saving_ms"],
                "M2_slope_low": projection(T, b, r_mid, slope_band[0])["saving_ms"],
                "M2_slope_high": projection(T, b, r_mid, slope_band[1])["saving_ms"],
                "M1_slope_low": projection(T, b, 1.0, slope_band[0])["saving_ms"],
                "M1_slope_high": projection(T, b, 1.0, slope_band[1])["saving_ms"],
            },
            # thinking variance: the question-mean baseline instead of single calls
            "M2_question_means": projection(data["T"].mean(axis=1), b, r_mid, slope_mid)["saving_ms"],
        }

    pw = power(rng, data, slope_mid, round(r_mid, 3), BUDGETS)
    out = {
        "tool": "h2_thinking_calibration", "seed": SEED, "numpy": np.__version__, "provider_calls": 0,
        "sources": {p: sha256_file(p) for p in [ive_path, *pair_paths]},
        "ive_baseline": {"calls": int(T.size), "thinking": summary(T), "visible": summary(V), "latency_ms": summary(L),
                         "thinking_within_question_sd": within_sd},
        "composer_budget_512_evidence": {"pairs": int(tA.size), "thinking_A": summary(tA), "thinking_B": summary(tB),
                                         "b_over_512": int((tB > 512).sum()), "ratio_used_over_budget": summary(ratio),
                                         "latency_A_ms": summary(lA), "latency_B_ms": summary(lB)},
        "slopes": slopes, "adherence_r": {"mid": r_mid, "p10": r_lo, "p90": r_hi},
        "projection": proj, "live_design_power": pw,
        "rules": {"R1": "mean(A-B) >= 2.0 s AND one-sided 95% cluster-bootstrap lower bound > 0",
                  "R2": "mean(A-B) >= 2.0 s AND one-sided 95% lower bound > 1.0 s",
                  "R3": "one-sided 95% lower bound > 1.0 s"},
    }
    data_bytes = (json.dumps(out, indent=1, sort_keys=True) + "\n").encode("ascii")
    with open(out_path, "xb") as fh:
        fh.write(data_bytes)
    print(json.dumps({"out_sha256": hashlib.sha256(data_bytes).hexdigest()}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
