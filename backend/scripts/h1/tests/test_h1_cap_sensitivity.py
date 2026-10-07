"""Offline tests for h1_cap_sensitivity.py (stdlib only, no provider calls)."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
import uuid

import pytest

H1_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAP_PATH = os.path.join(H1_DIR, "h1_cap_sensitivity.py")


@pytest.fixture
def cap():
    name = f"h1cap_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(name, CAP_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def payload(nc=5, nr=6):
    return {
        "abstract": "ION finances “nature” via the Wavelet model — naïve {braces} and \"quotes\".",
        "highlights": ["Pyramid of value ✓", "Credit 🌍"],
        "claims": [
            {"claim_id": "c1", "statement": "ION’s role [x] in credit", "evidence_document_ids": ["EV-1"],
             "confidence": 0.8},
            {"claim_id": "c2", "statement": "Second", "evidence_document_ids": ["EV-1", "EV-2"],
             "confidence": 0.65},
        ],
        "concepts": [{"name": f"Concept {i} “q”", "description": f"Desc {i}: {{not json}} é"}
                     for i in range(nc)],
        "relations": [{"source": f"Concept {i % nc} “q”" if nc else "x", "relation": f"rel-{i}",
                       "target": "nature", "evidence_document_ids": [f"EV-{1 + i % 4}"]}
                      for i in range(nr)],
        "uncertainty": ["Origins debated."],
        "confidence": 0.7,
    }


FORMATS = [
    lambda p: json.dumps(p, ensure_ascii=False),
    lambda p: json.dumps(p, ensure_ascii=False, indent=2),
    lambda p: json.dumps(p, ensure_ascii=True, separators=(",", ":")),
    lambda p: "```json\n" + json.dumps(p, ensure_ascii=False, indent=4) + "\n```",
]


def truncated(p, c, r):
    q = copy.deepcopy(p)
    q["concepts"], q["relations"] = q["concepts"][:c], q["relations"][:r]
    return q


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("keep", [0, 1, 3, 4, 5, 6, 9])
def test_removed_span_equals_the_serialized_difference(cap, fmt, keep):
    p = payload(5, 6)
    full = fmt(p)
    parsed = cap.Parsed(full)
    for key, other in (("concepts", "relations"), ("relations", "concepts")):
        cut = parsed.cut(key, keep)
        q = truncated(p, keep if key == "concepts" else 99, keep if key == "relations" else 99)
        short = fmt(q)
        assert cut["chars"] == len(full) - len(short)
        assert cut["bytes"] == len(full.encode("utf-8")) - len(short.encode("utf-8"))
        assert cut["items_removed"] == max(0, len(p[key]) - keep)
        assert cut["removed"] == p[key][keep:]


def test_simulate_estimates_and_combined_cut(cap):
    p = payload(5, 6)
    text = json.dumps(p, ensure_ascii=False, indent=2)
    parsed = cap.Parsed(text)
    s = cap.simulate(parsed, {"name": "C3/R4", "max_concepts": 3, "max_relations": 4}, 1500, 7.5)
    short = json.dumps(truncated(p, 3, 4), ensure_ascii=False, indent=2)
    assert s["chars"] == len(text) - len(short)
    assert s["concepts_removed"] == 2 and s["relations_removed"] == 2 and s["affected"]
    assert s["est_tokens"] == pytest.approx(1500 * s["chars"] / len(text))
    assert s["est_ms"] == pytest.approx(s["est_tokens"] * 7.5)
    none = cap.simulate(parsed, {"name": "C9/R9", "max_concepts": 9, "max_relations": 9}, 1500, 7.5)
    assert none["chars"] == 0 and not none["affected"] and none["est_ms"] == 0


def test_guard_ids_leaving_the_cited_set(cap):
    p = payload(2, 0)
    p["relations"] = [
        {"source": "a", "relation": "r", "target": "b", "evidence_document_ids": ["EV-1"]},
        {"source": "c", "relation": "r", "target": "d", "evidence_document_ids": ["EV-9"]},
        {"source": "e", "relation": "r", "target": "f", "evidence_document_ids": ["EV-1", "EV-7"]},
        {"source": "g", "relation": "r", "target": "h", "evidence_document_ids": []},
    ]
    parsed = cap.Parsed(json.dumps(p))
    s = cap.simulate(parsed, {"name": "C9/R1", "max_concepts": 9, "max_relations": 1}, 100, 1.0)
    # EV-1 is still cited by the claims and the kept relation; EV-9 and EV-7 only by dropped relations
    assert s["guard_ids_leaving"] == ["EV-7", "EV-9"]
    assert s["removed_relations_without_evidence"] == 1
    s2 = cap.simulate(parsed, {"name": "C9/R3", "max_concepts": 9, "max_relations": 3}, 100, 1.0)
    assert s2["guard_ids_leaving"] == []


def test_dangling_relations_and_mentions(cap):
    p = payload(0, 0)
    p["abstract"] = "The WAVELET model and the bank."
    p["concepts"] = [{"name": "Bank", "description": "d"}, {"name": "Wavelet", "description": "d"},
                     {"name": "Ledger", "description": "d"}]
    p["relations"] = [
        {"source": " wavelet ", "relation": "shapes", "target": "Bank", "evidence_document_ids": []},
        {"source": "Ledger", "relation": "records", "target": "credit", "evidence_document_ids": []},
        {"source": "Bank", "relation": "lends", "target": "ION’s role", "evidence_document_ids": []},
    ]
    parsed = cap.Parsed(json.dumps(p, ensure_ascii=False))
    s = cap.simulate(parsed, {"name": "C1/R2", "max_concepts": 1, "max_relations": 2}, 100, 1.0)
    assert s["concepts_removed"] == 2 and s["relations_removed"] == 1
    assert s["dangling_kept_relations"] == 2           # " wavelet " and "Ledger" name dropped concepts
    assert s["removed_concepts_named_elsewhere"] == 1  # Wavelet is in the abstract, Ledger is not
    assert s["removed_relations_endpoints_named_elsewhere"] == 1  # "Bank" and "ION’s role" both appear


def test_key_order_and_candidates(cap):
    with pytest.raises(ValueError):
        cap.parse_candidates("C4-R5")
    assert cap.parse_candidates(cap.DEFAULT_CANDIDATES) == [
        {"name": "C4/R5", "max_concepts": 4, "max_relations": 5},
        {"name": "C3/R4", "max_concepts": 3, "max_relations": 4},
        {"name": "C3/R3", "max_concepts": 3, "max_relations": 3}]
    p = payload()
    rows = [{"parsed": cap.Parsed(json.dumps(p))}]
    q = {k: p[k] for k in ("abstract", "uncertainty", "confidence", "highlights", "claims",
                            "concepts", "relations")}
    rows.append({"parsed": cap.Parsed(json.dumps(q))})
    k = cap.key_order_check(rows)
    assert k["turns_concepts_relations_before_uncertainty_and_confidence"] == 1
    assert sum(k["orders"].values()) == 2


def test_end_to_end_on_a_ledger(cap, tmp_path, capsys):
    shapes = [(2, 1), (4, 5), (5, 6), (6, 7), (3, 3)]
    texts, rows = [], []
    for i, (nc, nr) in enumerate(shapes):
        texts.append(json.dumps(payload(nc, nr), ensure_ascii=False, indent=(2 if i % 2 else None)))
    ledger = tmp_path / "h1cap_ledger.jsonl"
    with open(ledger, "w", encoding="utf-8") as fh:
        fh.write("H1_META {}\n")
        for i, t in enumerate(texts):
            vis, th = 1000 + 100 * i, 1500 + 10 * i
            turn = {"index": i, "captures": [{"label": "ive", "outcome": "OK", "text": t}],
                    "ive_calls": [{"outcome": "OK", "candidates_tokens": vis, "thoughts_tokens": th,
                                   "sdk_latency_ms": 900.0 + 7.5 * (vis + th)}],
                    "ive_reports": [{**json.loads(t), "raw_response": t}]}
            fh.write("H1_TURN " + json.dumps(turn, ensure_ascii=False) + "\n")
        fh.write("H1_TURN " + json.dumps({"index": 5, "captures": [], "ive_calls": []}) + "\n")
        bad = {"index": 6, "captures": [{"label": "ive", "outcome": "OK", "text": texts[1][:-40]}],
               "ive_calls": [{"outcome": "OK", "candidates_tokens": 9}]}
        fh.write("H1_TURN " + json.dumps(bad, ensure_ascii=False) + "\n")
        fh.write("H1_SUMMARY {}\n")
    out = tmp_path / "cap.json"
    assert cap.main([str(ledger), str(out)]) == 0
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    raw = out.read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    assert printed["out_sha256"] == hashlib.sha256(raw).hexdigest()
    s = json.loads(raw)
    assert s["turns_parsed"] == 5 and [f["index"] for f in s["parse_failures"]] == [6]
    assert s["report_counts_match"] == 5
    assert s["latency_fit_ms_per_output_token"]["slope"] == pytest.approx(7.5)
    assert s["slope_matches_step0"] is False  # synthetic slope differs from Step 0
    c45, c34, c33 = s["candidates"]
    assert [c["candidate"] for c in s["candidates"]] == ["C4/R5", "C3/R4", "C3/R3"]
    # C4/R5 cuts (5,6) and (6,7); C3/R3 cuts every shape except (2,1) and (3,3)
    assert c45["turns_affected"] == 2 and c45["concepts_items_removed_total"] == 1 + 2
    assert c45["relations_items_removed_total"] == 1 + 2
    assert c33["turns_affected"] == 3 and c33["concepts_items_removed_total"] == 1 + 2 + 3
    assert c33["relations_items_removed_total"] == 2 + 3 + 4
    assert c34["turns_concepts_cut"] == 3 and c34["turns_relations_cut"] == 3
    for c in s["candidates"]:
        assert c["concepts_items_total"] == sum(x for x, _ in shapes)
        per_turn_chars = [t[c["candidate"]][2] for t in s["per_turn"]]
        assert c["chars_removed_all_turns"]["mean"] == pytest.approx(sum(per_turn_chars) / 5)
        assert c["pooled_share_removed"] == pytest.approx(sum(per_turn_chars) / sum(len(t) for t in texts))
        assert len(c["examples"]["concepts"]) <= 5 and len(c["examples"]["relations"]) <= 5
    t2 = s["per_turn"][2]
    full = texts[2]
    short = json.dumps(truncated(payload(5, 6), 3, 3), ensure_ascii=False, indent=None)
    assert t2["C3/R3"][2] == len(full) - len(short)
    est = (1000 + 100 * 2) * t2["C3/R3"][2] / len(full)
    assert t2["C3/R3"][3] == round(est, 1)
    assert s["key_order"]["turns_concepts_relations_before_uncertainty_and_confidence"] == 5
