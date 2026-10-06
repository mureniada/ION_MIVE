"""VOE-LATENCY E3 analysis of the paired replay (runs locally, stdlib only).

    python voe_e3_analyze.py replay.jsonl OUT_DIR

Reads the `E3_PAIR` / `E3_META` lines `voe_e3_paired_replay.py` printed and
writes to OUT_DIR:
    summary.json          per-arm and paired statistics (compact)
    blind_pack.md         blinded side-by-side: per pair the IVE claims and
                          uncertainty the composer restyled, then Answer X and
                          Answer Y. Arm identity is NOT in this file
    blind_key.json        X/Y -> arm mapping (keep sealed until judgment)
and prints summary.json plus the SHA-256 of blind_key.json.
"""

from __future__ import annotations

import hashlib
import json
import random
import secrets
import statistics
import sys
from pathlib import Path

BLOCKING_TIERS = ("A", "B")
HELD_PHRASES = ("nature banking", "rather than life serving money")
BLIND_SUBSET = 8  # canonical question plus 7 others


def load(path: Path) -> tuple[dict, list[dict]]:
    meta, pairs = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("E3_META "):
            meta = json.loads(line[len("E3_META "):])
        elif line.startswith("E3_PAIR "):
            pairs.append(json.loads(line[len("E3_PAIR "):]))
    return meta, pairs


def _q(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p50": round(statistics.median(ordered), 1),
        "mean": round(statistics.fmean(ordered), 1),
        "min": round(ordered[0], 1),
        "max": round(ordered[-1], 1),
    }


def _composer_call(arm: dict) -> dict:
    calls = arm.get("calls") or []
    return calls[-1] if calls else {}


def _blocking(flags: list[dict]) -> list[dict]:
    return [f for f in flags if any(r[0] in BLOCKING_TIERS for r in f["rules"])]


def arm_stats(pairs: list[dict], arm: str) -> dict:
    rows = [p["arms"][arm] for p in pairs if "arms" in p]
    composed = [r for r in rows if r["status"] == "COMPOSED"]
    calls = [_composer_call(r) for r in rows]
    detectors: dict[str, int] = {}
    for r in composed:
        for f in r["g6_flags"]:
            detectors[f["detector"]] = detectors.get(f["detector"], 0) + 1
    claims = [c for r in composed for c in r["g6_claim_ledger"]]
    uncs = [u for r in composed for u in r["g6_uncertainty_ledger"]]
    return {
        "turns": len(rows),
        "composed": len(composed),
        "non_composed_statuses": sorted({r["status"] for r in rows} - {"COMPOSED"}),
        "thinking_config_sent": sorted({str(c.get("thinking_budget_sent")) for c in calls}),
        "composer_latency_ms": _q([r["composer_latency_ms"] for r in composed]),
        "thoughts_tokens": _q([c["thoughts_tokens"] for c in calls if c.get("thoughts_tokens") is not None]),
        "visible_tokens": _q([c["candidates_tokens"] for c in calls if c.get("candidates_tokens") is not None]),
        "prompt_tokens": _q([c["prompt_tokens"] for c in calls if c.get("prompt_tokens") is not None]),
        "cache_hits": sum(1 for c in calls if (c.get("cached_tokens") or 0) > 0),
        "words": _q([r["words"] for r in composed]),
        "suggested_questions_count": _q([len(r["suggested_questions"]) for r in composed]),
        "turns_without_suggestions": sum(1 for r in composed if not r["suggested_questions"]),
        "g6_flags_by_detector": dict(sorted(detectors.items())),
        "g6_blocking_flags_total": sum(len(_blocking(r["g6_flags"])) for r in composed),
        "g6_authoritative_fails": sum(1 for r in composed for f in r["g6_flags"] if f["authoritative"]),
        "claims_detected": f"{sum(c['auto_status'] == 'DETECTED' for c in claims)}/{len(claims)}",
        "uncertainty_detected": f"{sum(u['auto_status'] == 'DETECTED' for u in uncs)}/{len(uncs)}",
        "held_phrase_hits": sum(
            1 for r in composed for h in HELD_PHRASES
            if h in (r["composed_text"] + " " + " ".join(r["suggested_questions"])).lower()
        ),
    }


def paired_stats(pairs: list[dict]) -> dict:
    both = [p for p in pairs if "arms" in p
            and p["arms"]["A"]["status"] == "COMPOSED" and p["arms"]["B"]["status"] == "COMPOSED"]
    d_lat = [p["arms"]["B"]["composer_latency_ms"] - p["arms"]["A"]["composer_latency_ms"] for p in both]
    d_think = [
        _composer_call(p["arms"]["B"]).get("thoughts_tokens", 0) - _composer_call(p["arms"]["A"]).get("thoughts_tokens", 0)
        for p in both
    ]
    per_pair = []
    worse = better = 0
    for p in both:
        a, b = p["arms"]["A"], p["arms"]["B"]
        ka = {(f["detector"], f["match"]) for f in _blocking(a["g6_flags"])}
        kb = {(f["detector"], f["match"]) for f in _blocking(b["g6_flags"])}
        only_b, only_a = sorted(kb - ka), sorted(ka - kb)
        worse += bool(only_b)
        better += bool(only_a)
        ua = {u["uncertainty_id"] for u in a["g6_uncertainty_ledger"] if u["auto_status"] == "DETECTED"}
        ub = {u["uncertainty_id"] for u in b["g6_uncertainty_ledger"] if u["auto_status"] == "DETECTED"}
        ca = {c["claim_id"] for c in a["g6_claim_ledger"] if c["auto_status"] == "DETECTED"}
        cb = {c["claim_id"] for c in b["g6_claim_ledger"] if c["auto_status"] == "DETECTED"}
        per_pair.append({
            "index": p["index"],
            "order": p.get("order"),
            "lat_A": a["composer_latency_ms"], "lat_B": b["composer_latency_ms"],
            "think_A": _composer_call(a).get("thoughts_tokens"), "think_B": _composer_call(b).get("thoughts_tokens"),
            "words_A": a["words"], "words_B": b["words"],
            "blocking_only_in_B": [f"{d}:{m}" for d, m in only_b],
            "blocking_only_in_A": [f"{d}:{m}" for d, m in only_a],
            "uncertainty_lost_in_B": sorted(ua - ub), "uncertainty_lost_in_A": sorted(ub - ua),
            "claims_lost_in_B": sorted(ca - cb), "claims_lost_in_A": sorted(cb - ca),
        })
    by_position = {
        arm: {pos: _q([p["arms"][arm]["composer_latency_ms"] for p in both if p["arms"][arm]["position"] == pos])
              for pos in (0, 1)}
        for arm in ("A", "B")
    }
    return {
        "pairs_both_composed": len(both),
        "delta_latency_ms_B_minus_A": _q(d_lat),
        "delta_thoughts_B_minus_A": _q(d_think),
        "pairs_with_blocking_flags_only_in_B": worse,
        "pairs_with_blocking_flags_only_in_A": better,
        "latency_by_call_position": by_position,
        "per_pair": per_pair,
    }


def turn_stats(pairs: list[dict]) -> dict:
    return {
        "turn_errors": [p["index"] for p in pairs if p.get("error") or p.get("error_stage")],
        "retrieval_ms": _q([p["retrieval_ms"] for p in pairs if p.get("retrieval_ms") is not None]),
        "uncertainty_count_distribution": {
            str(k): v for k, v in sorted(
                {c: sum(1 for p in pairs if p.get("uncertainty_count") == c)
                 for c in {p.get("uncertainty_count") for p in pairs}}.items(),
                key=lambda kv: str(kv[0]))
        },
        "ive_thoughts_tokens": _q([c["thoughts_tokens"] for p in pairs for c in p.get("ive_calls", [])
                                   if c.get("thoughts_tokens") is not None]),
        "ive_thinking_config_sent": sorted({str(c.get("thinking_config_sent")) for p in pairs
                                            for c in p.get("ive_calls", [])}),
    }


def blind_pack(pairs: list[dict], out_dir: Path) -> str:
    eligible = [p for p in pairs if "arms" in p
                and p["arms"]["A"]["status"] == "COMPOSED" and p["arms"]["B"]["status"] == "COMPOSED"]
    canonical = [p for p in eligible if p["index"] == 0]
    others = [p for p in eligible if p["index"] != 0]
    rng = random.SystemRandom()
    chosen = canonical + rng.sample(others, min(BLIND_SUBSET - len(canonical), len(others)))
    key, lines = {}, ["# E3 blinded side-by-side", "",
                      "For each pair: which answer is better, or are they equivalent? "
                      "Note any lost caveat, new claim, factual drift, voice, ethics, metaphor or "
                      "suggested-question problem.", ""]
    for n, p in enumerate(chosen, start=1):
        x_arm = secrets.choice(("A", "B"))
        y_arm = "B" if x_arm == "A" else "A"
        key[str(n)] = {"index": p["index"], "X": x_arm, "Y": y_arm}
        ci = p["composer_input"]
        lines += [f"## Pair {n}", "", f"**Question:** {p['question']}", "",
                  "**What the composer was given (IVE claims and uncertainty):**", ""]
        lines += [f"- ({c['confidence']}) {c['statement']}" for c in ci["report_claims"]]
        lines += [f"- Uncertainty: {u}" for u in ci["report_uncertainty"]] + [""]
        for label, arm in (("X", x_arm), ("Y", y_arm)):
            a = p["arms"][arm]
            lines += [f"### Answer {label}", "", a["composed_text"], ""]
            if a["suggested_questions"]:
                lines += ["Suggested next questions:"] + [f"- {s}" for s in a["suggested_questions"]] + [""]
    (out_dir / "blind_pack.md").write_text("\n".join(lines), encoding="utf-8")
    key_bytes = json.dumps(key, sort_keys=True, indent=1).encode("utf-8")
    (out_dir / "blind_key.json").write_bytes(key_bytes)
    return hashlib.sha256(key_bytes).hexdigest()


def main() -> None:
    src, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    meta, pairs = load(src)
    summary = {
        "meta": meta,
        "turns": turn_stats(pairs),
        "arm_A": arm_stats(pairs, "A"),
        "arm_B": arm_stats(pairs, "B"),
        "paired": paired_stats(pairs),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    key_sha = blind_pack(pairs, out_dir)
    print(json.dumps(summary, ensure_ascii=False))
    print(f"BLIND_KEY_SHA256 {key_sha}")


if __name__ == "__main__":
    main()
