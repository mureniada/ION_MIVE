"""VOE-LATENCY E3 follow-up: pooled claim-coverage decision (runs locally, stdlib only).

    python voe_e3_pooled.py OUT_DIR replay1.jsonl [replay2.jsonl ...]

Reads the `E3_PAIR` lines `voe_e3_paired_replay.py` printed (arm A = provider
default, arm B = the budget under test) from every file, pools them, and
applies the decision rule pre-registered in
voe-latency/e3/E3_FOLLOWUP_PREREGISTRATION.md:

    FAIL     a pair where only arm B failed to compose (hard gate), or the
             exact two-sided sign test on claim-loss discordance gives
             p < 0.05 with arm B losing more claims.
    PASS     not FAIL, and the lower bound of the 95% pair-level cluster
             bootstrap CI of the pooled claim-coverage difference (B - A)
             is above -5 percentage points, and no new-claim / authority
             flag (G6 rules A1, A5, A6) occurs only in arm B. If such flags
             exist the verdict is PASS_PENDING_FLAG_REVIEW: each listed
             sentence is reviewed against the composer input.
    NOT_ADOPTED  otherwise.

Writes OUT_DIR/pooled.json and OUT_DIR/pairs.csv and prints pooled.json.
The only content printed is the sentences around new-claim / authority
flags; nothing else from the answers, and never secrets or the environment.
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from math import comb, sqrt
from pathlib import Path

MARGIN = -0.05
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261006
AUTHORITY_RULES = {"A1", "A5", "A6"}
BLOCKING_TIERS = ("A", "B")


def load(paths: list[Path]) -> list[dict]:
    pairs = []
    for run, path in enumerate(paths, start=1):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("E3_PAIR "):
                row = json.loads(line[len("E3_PAIR "):])
                row["run"] = run
                pairs.append(row)
    return pairs


def _detected(ledger: list[dict], key: str) -> set[str]:
    return {item[key] for item in ledger if item["auto_status"] == "DETECTED"}


def _sentence(text: str, match: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if match and match in sentence:
            return sentence.strip()
    return ""


def _authority(arm: dict) -> dict[tuple[str, str], str]:
    return {
        (f["detector"], f["match"]): _sentence(arm["composed_text"], f["match"])
        for f in arm["g6_flags"]
        if AUTHORITY_RULES & set(f["rules"])
    }


def _blocking(arm: dict) -> int:
    return sum(1 for f in arm["g6_flags"] if any(r[0] in BLOCKING_TIERS for r in f["rules"]))


def _metaphor(arm: dict) -> int:
    return sum(1 for f in arm["g6_flags"] if f["detector"] == "D-METAPHOR")


def sign_test(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def pair_row(p: dict) -> dict:
    a, b = p["arms"]["A"], p["arms"]["B"]
    det_a = _detected(a["g6_claim_ledger"], "claim_id")
    det_b = _detected(b["g6_claim_ledger"], "claim_id")
    unc_a = _detected(a["g6_uncertainty_ledger"], "uncertainty_id")
    unc_b = _detected(b["g6_uncertainty_ledger"], "uncertainty_id")
    auth_a, auth_b = _authority(a), _authority(b)
    return {
        "run": p["run"],
        "index": p["index"],
        "order": p.get("order"),
        "n_claims": len(p["composer_input"]["report_claims"]),
        "claims_det_A": len(det_a),
        "claims_det_B": len(det_b),
        "claims_lost_only_B": len(det_a - det_b),
        "claims_lost_only_A": len(det_b - det_a),
        "n_uncertainty": len(p["composer_input"]["report_uncertainty"]),
        "unc_lost_only_B": len(unc_a - unc_b),
        "unc_lost_only_A": len(unc_b - unc_a),
        "blocking_A": _blocking(a),
        "blocking_B": _blocking(b),
        "metaphor_A": _metaphor(a),
        "metaphor_B": _metaphor(b),
        "lat_A": a["composer_latency_ms"],
        "lat_B": b["composer_latency_ms"],
        "think_A": (a["calls"][-1] if a["calls"] else {}).get("thoughts_tokens"),
        "think_B": (b["calls"][-1] if b["calls"] else {}).get("thoughts_tokens"),
        "_authority_only_B": [
            {"detector": d, "match": m, "sentence": s}
            for (d, m), s in sorted(auth_b.items()) if (d, m) not in auth_a
        ],
        "_authority_only_A": [
            {"detector": d, "match": m, "sentence": s}
            for (d, m), s in sorted(auth_a.items()) if (d, m) not in auth_b
        ],
    }


def bootstrap_ci(rows: list[dict]) -> tuple[float, float]:
    rng = random.Random(BOOTSTRAP_SEED)
    stats = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [rng.choice(rows) for _ in rows]
        total = sum(r["n_claims"] for r in sample)
        diff = sum(r["claims_det_B"] - r["claims_det_A"] for r in sample)
        stats.append(diff / total if total else 0.0)
    stats.sort()
    return stats[int(0.025 * len(stats))], stats[int(0.975 * len(stats)) - 1]


def decide(pairs: list[dict]) -> dict:
    composed = [p for p in pairs if "arms" in p
                and p["arms"]["A"]["status"] == "COMPOSED" and p["arms"]["B"]["status"] == "COMPOSED"]
    not_composed = [
        {"run": p["run"], "index": p["index"],
         "A": p.get("arms", {}).get("A", {}).get("status"), "B": p.get("arms", {}).get("B", {}).get("status")}
        for p in pairs if p not in composed
    ]
    b_only_failures = [f for f in not_composed if f["A"] == "COMPOSED" and f["B"] != "COMPOSED"]
    rows = [pair_row(p) for p in composed]
    n = sum(r["n_claims"] for r in rows)
    lost_b = sum(r["claims_lost_only_B"] for r in rows)
    lost_a = sum(r["claims_lost_only_A"] for r in rows)
    diff = (lost_a - lost_b) / n if n else 0.0
    wald_se = sqrt(max(lost_a + lost_b - (lost_a - lost_b) ** 2 / n, 0.0)) / n if n else 0.0
    ci_low, ci_high = bootstrap_ci(rows) if rows else (0.0, 0.0)
    p_sign = sign_test(lost_b, lost_a)
    authority_b = [dict(f, run=r["run"], index=r["index"]) for r in rows for f in r["_authority_only_B"]]
    authority_a = [dict(f, run=r["run"], index=r["index"]) for r in rows for f in r["_authority_only_A"]]

    if b_only_failures:
        verdict = "FAIL"
        reason = "a pair failed to compose only in arm B (hard gate)"
    elif p_sign < 0.05 and lost_b > lost_a:
        verdict = "FAIL"
        reason = "sign test on claim-loss discordance favours arm A at p < 0.05"
    elif ci_low > MARGIN and not authority_b:
        verdict = "PASS"
        reason = "bootstrap CI lower bound above the -5 pp margin; no B-only authority flags"
    elif ci_low > MARGIN:
        verdict = "PASS_PENDING_FLAG_REVIEW"
        reason = "bootstrap CI lower bound above the -5 pp margin; B-only authority flags need review"
    else:
        verdict = "NOT_ADOPTED"
        reason = "non-inferiority within -5 pp not shown"

    return {
        "verdict": verdict,
        "reason": reason,
        "pairs_total": len(pairs),
        "pairs_both_composed": len(rows),
        "pairs_by_run": {str(run): sum(1 for r in rows if r["run"] == run)
                         for run in sorted({r["run"] for r in rows})},
        "not_composed": not_composed,
        "claims_total": n,
        "claims_detected_A": sum(r["claims_det_A"] for r in rows),
        "claims_detected_B": sum(r["claims_det_B"] for r in rows),
        "claims_lost_only_B": lost_b,
        "claims_lost_only_A": lost_a,
        "sign_test_p": round(p_sign, 4),
        "coverage_diff_B_minus_A_pp": round(100 * diff, 2),
        "bootstrap_ci95_pp": [round(100 * ci_low, 2), round(100 * ci_high, 2)],
        "wald_ci95_pp": [round(100 * (diff - 1.96 * wald_se), 2), round(100 * (diff + 1.96 * wald_se), 2)],
        "secondary": {
            "uncertainty_lost_only_B": sum(r["unc_lost_only_B"] for r in rows),
            "uncertainty_lost_only_A": sum(r["unc_lost_only_A"] for r in rows),
            "uncertainty_sign_test_p": round(sign_test(sum(r["unc_lost_only_B"] for r in rows),
                                                       sum(r["unc_lost_only_A"] for r in rows)), 4),
            "blocking_flags_A": sum(r["blocking_A"] for r in rows),
            "blocking_flags_B": sum(r["blocking_B"] for r in rows),
            "metaphor_flags_A": sum(r["metaphor_A"] for r in rows),
            "metaphor_flags_B": sum(r["metaphor_B"] for r in rows),
            "composer_latency_ms_p50_A": _median([r["lat_A"] for r in rows]),
            "composer_latency_ms_p50_B": _median([r["lat_B"] for r in rows]),
            "thoughts_p50_A": _median([r["think_A"] for r in rows if r["think_A"] is not None]),
            "thoughts_p50_B": _median([r["think_B"] for r in rows if r["think_B"] is not None]),
        },
        "authority_flags_only_B": authority_b,
        "authority_flags_only_A": authority_a,
        "_rows": rows,
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def main() -> None:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    result = decide(load([Path(p) for p in sys.argv[2:]]))
    rows = result.pop("_rows")
    columns = [k for k in rows[0] if not k.startswith("_")] if rows else []
    with (out_dir / "pairs.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "pooled.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
