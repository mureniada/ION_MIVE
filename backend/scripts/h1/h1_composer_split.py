"""H1 composer-facing split of captured IVE output (h1_composer_split.py). No provider calls.

Reads the h1cap_ledger.jsonl written by voe_h1_ive_capture.py and splits each
captured IVE output into the part the VOE composer receives and the part it
never sees. Supplements h1_sizing.py; stdlib only.

Composer-facing: the values Core._build_composer_input projects from the
report (orchestrator.py:1185-1198): the abstract, every highlight, each
claim's statement and confidence, every uncertainty item and the report
confidence. Measured as the exact value spans in the captured text (JSON
quotes and escapes included, as emitted).

Non-composer-facing: everything else in the captured text, split into the
concepts member, the relations member, claim ids and evidence ids (the rest
of the claims member) and other JSON structure (keys, brackets, separators,
whitespace, any fence). Composer-facing plus the four parts add up to the
whole text exactly, in chars and in UTF-8 bytes.

Token figures are ESTIMATED by char share of the provider's visible-token
count; no tokenizer is used.

    python h1_composer_split.py LEDGER.jsonl OUT.json
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys

_WS = re.compile(r"[ \t\n\r]*")
_DEC = json.JSONDecoder()
PARTS = ("composer_facing", "concepts", "relations", "claim_ids_and_evidence", "other_structure")


def _ws(text: str, i: int) -> int:
    return _WS.match(text, i).end()


def _nbytes(s: str) -> int:
    return len(s.encode("utf-8"))


def object_spans(text: str, start: int) -> list:
    """Members of the object at text[start] == '{': (key, key_start, value_start, value_end)."""
    members = []
    i = _ws(text, start + 1)
    if text[i] == "}":
        return members
    while True:
        key_start = i
        key, i = _DEC.raw_decode(text, i)
        if not isinstance(key, str):
            raise ValueError("object key is not a string")
        i = _ws(text, i)
        if text[i] != ":":
            raise ValueError("expected ':'")
        value_start = _ws(text, i + 1)
        _value, value_end = _DEC.raw_decode(text, value_start)
        members.append((key, key_start, value_start, value_end))
        i = _ws(text, value_end)
        if text[i] == ",":
            i = _ws(text, i + 1)
            continue
        if text[i] == "}":
            return members
        raise ValueError("expected ',' or '}'")


def array_spans(text: str, start: int) -> list:
    """Items of the array at text[start] == '[': (value_start, value_end)."""
    items = []
    i = _ws(text, start + 1)
    if text[i] == "]":
        return items
    while True:
        value_start = i
        _value, i = _DEC.raw_decode(text, i)
        items.append((value_start, i))
        i = _ws(text, i)
        if text[i] == ",":
            i = _ws(text, i + 1)
            continue
        if text[i] == "]":
            return items
        raise ValueError("expected ',' or ']'")


def split_text(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in the text")
    _DEC.raw_decode(text, start)  # the whole object must parse
    members = object_spans(text, start)
    keys = [m[0] for m in members]
    spans: dict = {p: [] for p in PARTS}
    for k, (key, key_start, v0, v1) in enumerate(members):
        own_end = members[k + 1][1] if k + 1 < len(members) else v1
        if key in ("abstract", "confidence"):
            spans["composer_facing"].append((v0, v1))
        elif key in ("highlights", "uncertainty") and text[v0] == "[":
            spans["composer_facing"].extend(array_spans(text, v0))
        elif key == "concepts":
            spans["concepts"].append((key_start, own_end))
        elif key == "relations":
            spans["relations"].append((key_start, own_end))
        elif key == "claims" and text[v0] == "[":
            claim_cf = []
            for c0, _c1 in array_spans(text, v0):
                if text[c0] != "{":
                    continue
                for ckey, _ck0, cv0, cv1 in object_spans(text, c0):
                    if ckey in ("statement", "confidence"):
                        claim_cf.append((cv0, cv1))
            spans["composer_facing"].extend(claim_cf)
            # everything else in the claims member: ids, evidence ids, keys, brackets
            spans["claim_ids_and_evidence"].append(("minus", (key_start, own_end), claim_cf))
    out = {"total_chars": len(text), "total_bytes": _nbytes(text), "keys": keys,
           "duplicate_keys": len(set(keys)) != len(keys)}
    used_c = used_b = 0
    for part in PARTS[:-1]:
        c = b = 0
        for s in spans[part]:
            if isinstance(s[0], str):  # ("minus", whole, holes)
                (w0, w1), holes = s[1], s[2]
                c += (w1 - w0) - sum(h1 - h0 for h0, h1 in holes)
                b += _nbytes(text[w0:w1]) - sum(_nbytes(text[h0:h1]) for h0, h1 in holes)
            else:
                c += s[1] - s[0]
                b += _nbytes(text[s[0]:s[1]])
        out[f"{part}_chars"], out[f"{part}_bytes"] = c, b
        used_c, used_b = used_c + c, used_b + b
    out["other_structure_chars"] = out["total_chars"] - used_c
    out["other_structure_bytes"] = out["total_bytes"] - used_b
    out["non_composer_facing_chars"] = out["total_chars"] - out["composer_facing_chars"]
    out["non_composer_facing_bytes"] = out["total_bytes"] - out["composer_facing_bytes"]
    return out


def pct(xs, p):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * p / 100.0
    f = math.floor(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def dist(xs) -> dict:
    xs = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "min": min(xs), "p25": pct(xs, 25), "median": pct(xs, 50),
            "p75": pct(xs, 75), "p90": pct(xs, 90), "max": max(xs), "mean": sum(xs) / len(xs)}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    ledger, out_path = argv
    with open(ledger, "rb") as fh:
        ledger_sha = hashlib.sha256(fh.read()).hexdigest()
    rows, failures = [], []
    with open(ledger, encoding="utf-8") as fh:
        for line in fh:
            tag, _, body = line.rstrip("\n").partition(" ")
            if tag != "H1_TURN":
                continue
            turn = json.loads(body)
            caps = [c for c in turn.get("captures") or []
                    if c.get("label") == "ive" and c.get("outcome") == "OK" and isinstance(c.get("text"), str)]
            if not caps:
                continue
            ok_calls = [c for c in turn.get("ive_calls") or [] if c.get("outcome") == "OK"]
            vt = ok_calls[-1].get("candidates_tokens") if ok_calls else None
            try:
                r = split_text(caps[-1]["text"])
            except (ValueError, IndexError) as exc:
                failures.append({"index": turn["index"], "error": str(exc)[:200]})
                continue
            r["index"] = turn["index"]
            r["visible_tokens"] = vt
            for part in PARTS + ("non_composer_facing",):
                share = r[f"{part}_chars"] / r["total_chars"] if r["total_chars"] else None
                r[f"{part}_share_chars"] = share
                r[f"{part}_est_tokens"] = vt * share if isinstance(vt, int) and share is not None else None
            rows.append(r)
    tot = sum(r["total_chars"] for r in rows)
    summary = {
        "ledger_sha256": ledger_sha,
        "turns_split": len(rows),
        "split_failures": failures,
        "label_tokens": "ESTIMATED (char share of provider visible tokens)",
        "per_turn": {f"{part}_{m}": dist([r[f"{part}_{m}"] for r in rows])
                     for part in PARTS + ("non_composer_facing",)
                     for m in ("chars", "bytes", "share_chars", "est_tokens")},
        "pooled_share_chars": {part: (sum(r[f"{part}_chars"] for r in rows) / tot if tot else None)
                               for part in PARTS + ("non_composer_facing",)},
        "rows": [{k: r[k] for k in r if k != "keys"} for r in rows],
    }
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps({"turns_split": len(rows), "failures": len(failures),
                      "composer_facing_share_pooled": summary["pooled_share_chars"]["composer_facing"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
