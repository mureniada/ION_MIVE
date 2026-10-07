"""H1 offline sizing of captured IVE output (h1_sizing.py). No provider calls.

Reads the h1cap_ledger.jsonl written by voe_h1_ive_capture.py and measures,
for every turn with a captured IVE output, how much of that output the
`concepts` and `relations` fields take, next to claims, highlights,
uncertainty and abstract.

Basis: the exact text the IVE adapter parsed (the capture), as the provider
emitted it. Each top-level member of the JSON object owns the span from its key
to the next key (key, colon, value, separator, whitespace); the braces, outer
whitespace and any code fence form the envelope. Member spans plus envelope add
up to the whole text exactly, in chars and in UTF-8 bytes. `*_value_*` columns
measure the value alone as emitted; `*_canon_chars` re-serializes the value
compactly (formatting excluded).

Visible tokens are the provider's own count (usage candidates_token_count).
Per-field token and latency figures are ESTIMATED: tokens by char share,
latency by an OLS slope of IVE call latency on output tokens (visible +
thinking). No tokenizer is used.

    python h1_sizing.py LEDGER.jsonl OUT_PREFIX

writes OUT_PREFIX_turns.csv and OUT_PREFIX_summary.json.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys

FIELDS = ("abstract", "highlights", "claims", "concepts", "relations", "uncertainty", "confidence")
_WS = re.compile(r"[ \t\n\r]*")
_DEC = json.JSONDecoder()


def _ws(text: str, i: int) -> int:
    return _WS.match(text, i).end()


def _nbytes(s: str) -> int:
    return len(s.encode("utf-8"))


def _canon(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# ------------------------------------------------------------------ #
# span-aware walk of the top-level JSON object
# ------------------------------------------------------------------ #
def object_members(text: str):
    """Return (obj, members). Each member: key, key_start, value_start,
    value_end, own_end (start of the next key, or the value end for the last
    member) and the decoded value. The adapter's parse_json() strips outer
    whitespace and an optional ``` fence; the object starts at the first '{'
    either way."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in the text")
    obj, _end = _DEC.raw_decode(text, start)
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON value is not an object")
    members = []
    i = _ws(text, start + 1)
    if text[i] != "}":
        while True:
            key_start = i
            key, i = _DEC.raw_decode(text, i)
            if not isinstance(key, str):
                raise ValueError("object key is not a string")
            i = _ws(text, i)
            if text[i] != ":":
                raise ValueError("expected ':'")
            value_start = _ws(text, i + 1)
            value, value_end = _DEC.raw_decode(text, value_start)
            members.append({"key": key, "key_start": key_start, "value_start": value_start,
                            "value_end": value_end, "value": value})
            i = _ws(text, value_end)
            if text[i] == ",":
                i = _ws(text, i + 1)
                continue
            if text[i] == "}":
                break
            raise ValueError("expected ',' or '}'")
    for k, m in enumerate(members):
        m["own_end"] = members[k + 1]["key_start"] if k + 1 < len(members) else m["value_end"]
    return obj, members


def _str_chars(items, key) -> int:
    return sum(len(x[key]) for x in items if isinstance(x, dict) and isinstance(x.get(key), str))


def _id_count(items) -> int:
    return sum(len(x["evidence_document_ids"]) for x in items
               if isinstance(x, dict) and isinstance(x.get("evidence_document_ids"), list))


def analyze_text(text: str) -> dict:
    out = {"total_chars": len(text), "total_bytes": _nbytes(text)}
    obj, members = object_members(text)
    keys = [m["key"] for m in members]
    fields: dict = {}
    owned_chars = owned_bytes = 0
    for m in members:
        own = text[m["key_start"]:m["own_end"]]
        val = text[m["value_start"]:m["value_end"]]
        fields[m["key"]] = {
            "chars": len(own), "bytes": _nbytes(own),
            "value_chars": len(val), "value_bytes": _nbytes(val),
            "canon_chars": len(_canon(m["value"])),
            "items": len(m["value"]) if isinstance(m["value"], list) else None,
        }
        owned_chars += len(own)
        owned_bytes += _nbytes(own)
    concepts = obj.get("concepts") if isinstance(obj.get("concepts"), list) else []
    relations = obj.get("relations") if isinstance(obj.get("relations"), list) else []
    claims = obj.get("claims") if isinstance(obj.get("claims"), list) else []
    out.update({
        "keys": keys,
        "duplicate_keys": len(set(keys)) != len(keys),
        "other_keys": [k for k in keys if k not in FIELDS],
        "fields": fields,
        "envelope_chars": out["total_chars"] - owned_chars,
        "envelope_bytes": out["total_bytes"] - owned_bytes,
        "canon_total_chars": len(_canon(obj)),
        "concepts_name_chars": _str_chars(concepts, "name"),
        "concepts_description_chars": _str_chars(concepts, "description"),
        "relations_source_chars": _str_chars(relations, "source"),
        "relations_relation_chars": _str_chars(relations, "relation"),
        "relations_target_chars": _str_chars(relations, "target"),
        "relations_evidence_ids": _id_count(relations),
        "claims_statement_chars": _str_chars(claims, "statement"),
        "claims_evidence_ids": _id_count(claims),
    })
    return out


# ------------------------------------------------------------------ #
# ledger -> per-turn rows
# ------------------------------------------------------------------ #
def read_ledger(path: str):
    meta, turns, summary = None, [], None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            tag, _, body = line.partition(" ")
            obj = json.loads(body)
            if tag == "H1_META":
                meta = obj
            elif tag == "H1_TURN":
                turns.append(obj)
            elif tag == "H1_SUMMARY":
                summary = obj
    return meta, turns, summary


def turn_row(turn: dict) -> dict:
    caps = [c for c in turn.get("captures") or []
            if c.get("label") == "ive" and c.get("outcome") == "OK" and isinstance(c.get("text"), str)]
    ok_calls = [c for c in turn.get("ive_calls") or [] if c.get("outcome") == "OK"]
    row = {"index": turn["index"], "captured": bool(caps)}
    if not caps:
        return row
    text = caps[-1]["text"]
    call = ok_calls[-1] if ok_calls else {}
    row.update({
        "visible_tokens": call.get("candidates_tokens"),
        "thoughts_tokens": call.get("thoughts_tokens"),
        "prompt_tokens": call.get("prompt_tokens"),
        "sdk_latency_ms": call.get("sdk_latency_ms"),
        "capture_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "capture_matches_report_raw": turn.get("capture_matches_report_raw"),
    })
    try:
        a = analyze_text(text)
    except (ValueError, IndexError) as exc:
        row.update({"parse_ok": False, "parse_error": str(exc)[:200],
                    "total_chars": len(text), "total_bytes": _nbytes(text)})
        return row
    row.update({"parse_ok": True, "total_chars": a["total_chars"], "total_bytes": a["total_bytes"],
                "envelope_chars": a["envelope_chars"], "envelope_bytes": a["envelope_bytes"],
                "canon_total_chars": a["canon_total_chars"],
                "formatting_chars": a["total_chars"] - a["canon_total_chars"],
                "duplicate_keys": a["duplicate_keys"], "other_keys": "|".join(a["other_keys"])})
    for f in FIELDS:
        rec = a["fields"].get(f)
        for k in ("items", "chars", "bytes", "value_chars", "value_bytes", "canon_chars"):
            row[f"{f}_{k}"] = None if rec is None else rec[k]
    for k in ("concepts_name_chars", "concepts_description_chars", "relations_source_chars",
              "relations_relation_chars", "relations_target_chars", "relations_evidence_ids",
              "claims_statement_chars", "claims_evidence_ids"):
        row[k] = a[k]
    cr_chars = (row["concepts_chars"] or 0) + (row["relations_chars"] or 0)
    cr_bytes = (row["concepts_bytes"] or 0) + (row["relations_bytes"] or 0)
    row.update({
        "cr_chars": cr_chars, "cr_bytes": cr_bytes,
        "cr_share_chars": cr_chars / a["total_chars"] if a["total_chars"] else None,
        "cr_share_bytes": cr_bytes / a["total_bytes"] if a["total_bytes"] else None,
    })
    vt = row["visible_tokens"]
    row["cr_est_visible_tokens"] = (vt * row["cr_share_chars"]
                                    if isinstance(vt, int) and row["cr_share_chars"] is not None else None)
    reports = turn.get("ive_reports") or []
    rep = reports[0] if reports and isinstance(reports[0], dict) else {}
    row["report_concepts_items"] = len(rep["concepts"]) if isinstance(rep.get("concepts"), list) else None
    row["report_relations_items"] = len(rep["relations"]) if isinstance(rep.get("relations"), list) else None
    row["report_counts_match_raw"] = (row["report_concepts_items"] == row["concepts_items"]
                                      and row["report_relations_items"] == row["relations_items"])
    return row


# ------------------------------------------------------------------ #
# summary
# ------------------------------------------------------------------ #
def pct(xs, p):
    """Linear interpolation between closest ranks (numpy's default)."""
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


def ols(xs, ys) -> dict:
    pts = [(x, y) for x, y in zip(xs, ys) if isinstance(x, (int, float)) and isinstance(y, (int, float))]
    n = len(pts)
    if n < 3:
        return {"n": n}
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if sxx == 0:
        return {"n": n}
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((y - intercept - slope * x) ** 2 for x, y in pts)
    ss_tot = sum((y - my) ** 2 for _, y in pts)
    return {"n": n, "slope": slope, "intercept": intercept,
            "r2": 1 - ss_res / ss_tot if ss_tot else None}


DIST_KEYS = (
    "total_chars", "total_bytes", "visible_tokens", "thoughts_tokens", "sdk_latency_ms",
    "concepts_items", "concepts_chars", "concepts_bytes", "concepts_value_chars", "concepts_canon_chars",
    "relations_items", "relations_chars", "relations_bytes", "relations_value_chars", "relations_canon_chars",
    "cr_chars", "cr_bytes", "cr_share_chars", "cr_share_bytes", "cr_est_visible_tokens",
    "claims_items", "claims_chars", "claims_bytes", "highlights_items", "highlights_chars",
    "highlights_bytes", "uncertainty_items", "uncertainty_chars", "uncertainty_bytes",
    "abstract_chars", "abstract_bytes", "envelope_chars", "formatting_chars",
)


def summarize(rows: list, meta, ledger_summary, ledger_sha: str) -> dict:
    ok = [r for r in rows if r.get("parse_ok")]
    tot_c = sum(r["total_chars"] for r in ok)
    tot_b = sum(r["total_bytes"] for r in ok)
    fit = ols([(r.get("visible_tokens") or 0) + (r.get("thoughts_tokens") or 0)
               if isinstance(r.get("visible_tokens"), int) else None for r in ok],
              [r.get("sdk_latency_ms") for r in ok])
    est_ms = ([r["cr_est_visible_tokens"] * fit["slope"] for r in ok
               if r.get("cr_est_visible_tokens") is not None] if "slope" in fit else [])
    pooled = {"total_chars": tot_c, "total_bytes": tot_b}
    for f in FIELDS:
        c = sum(r.get(f"{f}_chars") or 0 for r in ok)
        b = sum(r.get(f"{f}_bytes") or 0 for r in ok)
        pooled[f] = {"chars": c, "bytes": b, "share_chars": c / tot_c if tot_c else None,
                     "share_bytes": b / tot_b if tot_b else None}
    cr_c = pooled["concepts"]["chars"] + pooled["relations"]["chars"]
    cr_b = pooled["concepts"]["bytes"] + pooled["relations"]["bytes"]
    pooled["concepts_relations"] = {"chars": cr_c, "bytes": cr_b,
                                    "share_chars": cr_c / tot_c if tot_c else None,
                                    "share_bytes": cr_b / tot_b if tot_b else None}
    return {
        "source": {"ledger_sha256": ledger_sha,
                   "capture_version": (meta or {}).get("capture_version"),
                   "ledger_status": (ledger_summary or {}).get("status"),
                   "turns": len(rows), "captured": sum(1 for r in rows if r.get("captured")),
                   "parsed": len(ok), "parse_failures": sum(1 for r in rows if r.get("parse_ok") is False)},
        "cross_checks": {
            "capture_matches_report_raw": {str(v): sum(1 for r in ok if r.get("capture_matches_report_raw") is v)
                                           for v in (True, False, None)},
            "report_counts_match_raw": sum(1 for r in ok if r.get("report_counts_match_raw")),
            "duplicate_key_turns": sum(1 for r in ok if r.get("duplicate_keys")),
            "turns_with_other_keys": sum(1 for r in ok if r.get("other_keys")),
        },
        "measured": {k: dist([r.get(k) for r in ok]) for k in DIST_KEYS},
        "pooled": pooled,
        "estimated": {
            "label": "ESTIMATED",
            "cr_visible_tokens_method": "visible_tokens x concepts+relations char share, per turn",
            "cr_visible_tokens_total": sum(r["cr_est_visible_tokens"] for r in ok
                                           if r.get("cr_est_visible_tokens") is not None),
            "latency_fit_ms_per_output_token": fit,
            "cr_latency_ms": dist(est_ms),
            "caveat": "visible-token generation only; any effect on thinking tokens is UNKNOWN",
        },
    }


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    ledger, prefix = argv
    with open(ledger, "rb") as fh:
        ledger_sha = hashlib.sha256(fh.read()).hexdigest()
    meta, turns, ledger_summary = read_ledger(ledger)
    rows = [turn_row(t) for t in turns]
    columns = []
    for r in rows:
        for k in r:
            if k not in columns:
                columns.append(k)
    with open(f"{prefix}_turns.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    summary = summarize(rows, meta, ledger_summary, ledger_sha)
    with open(f"{prefix}_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps({"turns": len(rows), "parsed": summary["source"]["parsed"],
                      "cr_share_chars_pooled": summary["pooled"]["concepts_relations"]["share_chars"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
