"""H1 Step 0.5 offline cap sensitivity (h1_cap_sensitivity.py). No provider calls.

Reads the h1cap_ledger.jsonl written by voe_h1_ive_capture.py and simulates
candidate caps on the IVE `concepts` and `relations` arrays by TRUNCATION:
the first C concepts and the first R relations are kept, exactly as emitted.

This is sizing and inspection only. It is NOT the provider's behaviour under a
schema cap (maxItems): a model asked for at most C items may pick different
items, word them differently, think differently, and change the fields it
writes after them.

Removed size is an exact span of the captured text. Dropping items k+1..n of an
array removes the text from the end of item k to the end of item n: the
separators, the whitespace and the dropped items, as emitted. Dropping all items
removes everything between the brackets. Either way the span equals the length
difference between the full and the truncated JSON for json.dumps-style output.

Token and latency figures are ESTIMATED: tokens by char share of the provider's
visible-token count, latency by the Step 0 method (OLS of IVE call latency on
visible + thinking tokens), recomputed from the same ledger.

Downstream checks per candidate, against the consumers found in the v0.4 source:
- the CG-A1 citation guard (orchestrator._enforce_citation_subset) checks claim
  and relation evidence ids on context turns: the ids that would leave its
  cited set are those cited only by dropped relations;
- kept relations whose source or target names a dropped concept;
- whether dropped concept names and relation endpoints appear in the abstract,
  highlights or claim statements.

    python h1_cap_sensitivity.py LEDGER.jsonl OUT.json [C4/R5,C3/R4,C3/R3]

OUT.json is one line of canonical JSON (sorted keys, compact) plus a newline,
written as bytes, so its sha256 does not depend on the platform.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys

DEFAULT_CANDIDATES = "C4/R5,C3/R4,C3/R3"
STEP0_SLOPE_MS_PER_TOKEN = 7.487351073597748  # h1s_summary.json (Step 0), for cross-check only
EXAMPLES_PER_KIND = 5
EXAMPLE_CHARS = 160
_WS = re.compile(r"[ \t\n\r]*")
_DEC = json.JSONDecoder()
_CAND = re.compile(r"^C(\d+)/R(\d+)$")


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


def parse_candidates(spec: str) -> list:
    out = []
    for part in spec.split(","):
        m = _CAND.match(part.strip())
        if not m:
            raise ValueError(f"bad candidate {part!r}; expected like C4/R5")
        out.append({"name": part.strip(), "max_concepts": int(m.group(1)),
                    "max_relations": int(m.group(2))})
    return out


def removed_span(items: list, array_start: int, array_end: int, keep: int):
    """(start, end) of the text removed by keeping the first `keep` items, or None."""
    n = len(items)
    if n <= keep:
        return None
    if keep == 0:
        return (array_start + 1, array_end - 1)  # everything between the brackets
    return (items[keep - 1][1], items[n - 1][1])


def _norm(s) -> str:
    return " ".join(str(s).split()).casefold()


def _short(s: str) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= EXAMPLE_CHARS else s[: EXAMPLE_CHARS - 1] + "…"


class Parsed:
    """The captured IVE text with exact spans of its concepts and relations items."""

    def __init__(self, text: str):
        start = text.find("{")
        if start < 0:
            raise ValueError("no JSON object in the text")
        self.obj, _end = _DEC.raw_decode(text, start)
        if not isinstance(self.obj, dict):
            raise ValueError("top-level JSON is not an object")
        self.text = text
        self.members = object_spans(text, start)
        self.keys = [m[0] for m in self.members]
        self.arrays = {}
        for key, _k0, v0, v1 in self.members:
            if key in ("concepts", "relations") and text[v0] == "[":
                spans = array_spans(text, v0)
                self.arrays[key] = {"start": v0, "end": v1, "items": spans,
                                    "values": [json.loads(text[a:b]) for a, b in spans]}
        for key in ("concepts", "relations"):
            self.arrays.setdefault(key, {"start": None, "end": None, "items": [], "values": []})

    def cut(self, key: str, keep: int) -> dict:
        arr = self.arrays[key]
        span = (removed_span(arr["items"], arr["start"], arr["end"], keep)
                if arr["start"] is not None else None)
        removed = arr["values"][keep:] if len(arr["values"]) > keep else []
        if span is None:
            return {"items_removed": 0, "chars": 0, "bytes": 0, "removed": [], "kept": arr["values"]}
        return {"items_removed": len(removed), "chars": span[1] - span[0],
                "bytes": _nbytes(self.text[span[0]:span[1]]), "removed": removed,
                "kept": arr["values"][:keep]}


def _ev_ids(item) -> list:
    ids = item.get("evidence_document_ids") if isinstance(item, dict) else None
    return [str(x) for x in ids] if isinstance(ids, list) else []


def simulate(p: Parsed, cand: dict, visible_tokens, slope) -> dict:
    total_chars = len(p.text)
    c = p.cut("concepts", cand["max_concepts"])
    r = p.cut("relations", cand["max_relations"])
    chars = c["chars"] + r["chars"]
    share = chars / total_chars if total_chars else None
    tokens = (visible_tokens * share
              if isinstance(visible_tokens, int) and share is not None else None)
    ms = tokens * slope if tokens is not None and slope is not None else None

    claims = p.obj.get("claims") if isinstance(p.obj.get("claims"), list) else []
    claim_ids = {i for cl in claims for i in _ev_ids(cl)}
    all_rel = p.arrays["relations"]["values"]
    cited_all = claim_ids | {i for rel in all_rel for i in _ev_ids(rel)}
    cited_kept = claim_ids | {i for rel in r["kept"] for i in _ev_ids(rel)}
    leaving = sorted(cited_all - cited_kept)

    removed_names = {_norm(x.get("name")) for x in c["removed"] if isinstance(x, dict) and x.get("name")}
    dangling = [rel for rel in r["kept"] if isinstance(rel, dict)
                and (_norm(rel.get("source", "")) in removed_names
                     or _norm(rel.get("target", "")) in removed_names)]

    pool_parts = [p.obj.get("abstract") or ""]
    pool_parts += [h for h in (p.obj.get("highlights") or []) if isinstance(h, str)]
    pool_parts += [cl.get("statement") or "" for cl in claims if isinstance(cl, dict)]
    pool = _norm(" \n ".join(str(x) for x in pool_parts))
    concepts_named = sum(1 for x in c["removed"] if isinstance(x, dict) and x.get("name")
                         and _norm(x["name"]) in pool)
    relations_named = sum(1 for x in r["removed"] if isinstance(x, dict)
                          and _norm(x.get("source", "")) in pool and _norm(x.get("target", "")) in pool)
    return {
        "concepts_removed": c["items_removed"], "relations_removed": r["items_removed"],
        "concepts_chars": c["chars"], "relations_chars": r["chars"],
        "chars": chars, "bytes": c["bytes"] + r["bytes"], "share_chars": share,
        "est_tokens": tokens, "est_ms": ms,
        "affected": bool(c["items_removed"] or r["items_removed"]),
        "guard_ids_leaving": leaving,
        "removed_relations_without_evidence": sum(1 for x in r["removed"] if not _ev_ids(x)),
        "dangling_kept_relations": len(dangling),
        "removed_concepts_named_elsewhere": concepts_named,
        "removed_relations_endpoints_named_elsewhere": relations_named,
        "removed_concepts": c["removed"], "removed_relations": r["removed"],
    }


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
    """Same fit as h1_sizing.py."""
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


def read_turns(path: str) -> list:
    turns = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            tag, _, body = line.rstrip("\n").partition(" ")
            if tag == "H1_TURN":
                turns.append(json.loads(body))
    return turns


def load_rows(turns: list) -> tuple:
    rows, failures = [], []
    for turn in turns:
        caps = [c for c in turn.get("captures") or []
                if c.get("label") == "ive" and c.get("outcome") == "OK" and isinstance(c.get("text"), str)]
        if not caps:
            continue
        ok_calls = [c for c in turn.get("ive_calls") or [] if c.get("outcome") == "OK"]
        call = ok_calls[-1] if ok_calls else {}
        try:
            parsed = Parsed(caps[-1]["text"])
        except (ValueError, IndexError) as exc:
            failures.append({"index": turn.get("index"), "error": str(exc)[:200]})
            continue
        reports = turn.get("ive_reports") or []
        rep = reports[0] if reports and isinstance(reports[0], dict) else {}
        counts_match = (isinstance(rep.get("concepts"), list) and isinstance(rep.get("relations"), list)
                        and len(rep["concepts"]) == len(parsed.arrays["concepts"]["values"])
                        and len(rep["relations"]) == len(parsed.arrays["relations"]["values"]))
        rows.append({"index": turn.get("index"), "parsed": parsed,
                     "visible_tokens": call.get("candidates_tokens"),
                     "thoughts_tokens": call.get("thoughts_tokens"),
                     "sdk_latency_ms": call.get("sdk_latency_ms"),
                     "report_counts_match": counts_match})
    return rows, failures


def key_order_check(rows: list) -> dict:
    orders = {}
    before = 0
    for r in rows:
        keys = r["parsed"].keys
        orders["|".join(keys)] = orders.get("|".join(keys), 0) + 1
        pos = {k: i for i, k in enumerate(keys)}
        if all(k in pos for k in ("concepts", "relations", "uncertainty", "confidence")) and \
                max(pos["concepts"], pos["relations"]) < min(pos["uncertainty"], pos["confidence"]):
            before += 1
    return {"orders": orders, "turns_concepts_relations_before_uncertainty_and_confidence": before}


def summarize_candidate(cand: dict, rows: list, sims: list) -> dict:
    n = len(rows)
    affected = [s for s in sims if s["affected"]]
    total_chars = sum(len(r["parsed"].text) for r in rows)
    examples_c, examples_r = [], []
    for r, s in zip(rows, sims):
        if s["removed_concepts"] and len(examples_c) < EXAMPLES_PER_KIND:
            x = s["removed_concepts"][0]
            x = x if isinstance(x, dict) else {"name": str(x)}
            examples_c.append({"index": r["index"], "name": _short(x.get("name", "")),
                               "description": _short(x.get("description", ""))})
        if s["removed_relations"] and len(examples_r) < EXAMPLES_PER_KIND:
            x = s["removed_relations"][0]
            x = x if isinstance(x, dict) else {"source": str(x)}
            examples_r.append({"index": r["index"],
                               "relation": _short(f"{x.get('source', '')} | {x.get('relation', '')} | "
                                                  f"{x.get('target', '')}"),
                               "evidence_document_ids": _ev_ids(x)})
    leaving = [len(s["guard_ids_leaving"]) for s in sims]
    return {
        "candidate": cand["name"], "max_concepts": cand["max_concepts"],
        "max_relations": cand["max_relations"],
        "turns": n, "turns_affected": len(affected),
        "turns_affected_share": len(affected) / n if n else None,
        "turns_concepts_cut": sum(1 for s in sims if s["concepts_removed"]),
        "turns_relations_cut": sum(1 for s in sims if s["relations_removed"]),
        "concepts_items_total": sum(len(r["parsed"].arrays["concepts"]["values"]) for r in rows),
        "relations_items_total": sum(len(r["parsed"].arrays["relations"]["values"]) for r in rows),
        "concepts_items_removed_total": sum(s["concepts_removed"] for s in sims),
        "relations_items_removed_total": sum(s["relations_removed"] for s in sims),
        "concepts_removed_per_turn": dist([s["concepts_removed"] for s in sims]),
        "relations_removed_per_turn": dist([s["relations_removed"] for s in sims]),
        "chars_removed_all_turns": dist([s["chars"] for s in sims]),
        "chars_removed_affected_turns": dist([s["chars"] for s in affected]),
        "share_removed_all_turns": dist([s["share_chars"] for s in sims]),
        "pooled_share_removed": (sum(s["chars"] for s in sims) / total_chars) if total_chars else None,
        "est_tokens_removed_all_turns": dist([s["est_tokens"] for s in sims]),
        "est_tokens_removed_total": sum(s["est_tokens"] or 0 for s in sims),
        "est_saving_ms_all_turns": dist([s["est_ms"] for s in sims]),
        "est_saving_ms_affected_turns": dist([s["est_ms"] for s in affected]),
        "guard_turns_with_cited_set_change": sum(1 for x in leaving if x),
        "guard_ids_leaving_total": sum(leaving),
        "removed_relations_without_evidence": sum(s["removed_relations_without_evidence"] for s in sims),
        "dangling_kept_relations_total": sum(s["dangling_kept_relations"] for s in sims),
        "dangling_turns": sum(1 for s in sims if s["dangling_kept_relations"]),
        "removed_concepts_named_elsewhere": sum(s["removed_concepts_named_elsewhere"] for s in sims),
        "removed_relations_endpoints_named_elsewhere": sum(
            s["removed_relations_endpoints_named_elsewhere"] for s in sims),
        "examples": {"concepts": examples_c, "relations": examples_r},
    }


def run(ledger: str, out_path: str, spec: str = DEFAULT_CANDIDATES) -> dict:
    with open(ledger, "rb") as fh:
        ledger_sha = hashlib.sha256(fh.read()).hexdigest()
    candidates = parse_candidates(spec)
    rows, failures = load_rows(read_turns(ledger))
    fit = ols([(r["visible_tokens"] or 0) + (r["thoughts_tokens"] or 0)
               if isinstance(r["visible_tokens"], int) else None for r in rows],
              [r["sdk_latency_ms"] for r in rows])
    slope = fit.get("slope")
    per_turn = [{"index": r["index"], "total_chars": len(r["parsed"].text),
                 "visible_tokens": r["visible_tokens"],
                 "concepts": len(r["parsed"].arrays["concepts"]["values"]),
                 "relations": len(r["parsed"].arrays["relations"]["values"])} for r in rows]
    out_c = []
    for cand in candidates:
        sims = [simulate(r["parsed"], cand, r["visible_tokens"], slope) for r in rows]
        out_c.append(summarize_candidate(cand, rows, sims))
        for t, s in zip(per_turn, sims):
            t[cand["name"]] = [s["concepts_removed"], s["relations_removed"], s["chars"],
                               None if s["est_tokens"] is None else round(s["est_tokens"], 1)]
    summary = {
        "tool": "h1_cap_sensitivity", "label": "ESTIMATED tokens and latency; truncation is NOT "
                                               "provider behaviour under a schema cap",
        "ledger_sha256": ledger_sha, "turns_parsed": len(rows), "parse_failures": failures,
        "report_counts_match": sum(1 for r in rows if r["report_counts_match"]),
        "latency_fit_ms_per_output_token": fit,
        "step0_slope_ms_per_token": STEP0_SLOPE_MS_PER_TOKEN,
        "slope_matches_step0": (slope is not None and abs(slope - STEP0_SLOPE_MS_PER_TOKEN) < 1e-9),
        "key_order": key_order_check(rows),
        "candidates": out_c,
        "per_turn_columns": "per candidate: [concepts removed, relations removed, chars removed, est tokens]",
        "per_turn": per_turn,
    }
    data = json.dumps(summary, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(out_path, "wb") as fh:
        fh.write(data.encode("utf-8"))
    summary["_out_sha256"] = hashlib.sha256(data.encode("utf-8")).hexdigest()
    return summary


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    s = run(*argv)
    print(json.dumps({"turns_parsed": s["turns_parsed"], "failures": len(s["parse_failures"]),
                      "slope_matches_step0": s["slope_matches_step0"],
                      "out_sha256": s["_out_sha256"],
                      "affected_share": {c["candidate"]: c["turns_affected_share"] for c in s["candidates"]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
