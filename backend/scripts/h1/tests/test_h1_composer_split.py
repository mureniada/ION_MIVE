"""Offline tests for h1_composer_split.py (stdlib only, no provider calls)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid

import pytest

H1_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT_PATH = os.path.join(H1_DIR, "h1_composer_split.py")


@pytest.fixture
def split():
    name = f"h1split_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(name, SPLIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def payload(i=0):
    return {
        "abstract": f"Abstract {i}: “credit” — naïve {{braces}} and \"quotes\" \\ ok.",
        "highlights": [f"H{i}a", "Ünïcödé ✓"],
        "claims": [
            {"claim_id": "c1", "statement": f"Claim {i}: ION’s role [x]", "evidence_document_ids": ["EV-1"],
             "confidence": 0.8},
            {"claim_id": "c2", "statement": "Second 🌍", "evidence_document_ids": ["EV-1", "EV-22"],
             "confidence": 0.65},
        ],
        "concepts": [{"name": "Wavelet", "description": "A “wavelet” of change: {not json}"}],
        "relations": [{"source": "ION", "relation": "finances", "target": "nature",
                       "evidence_document_ids": ["EV-1"]}],
        "uncertainty": ["Origins debated.", "Scope unclear"],
        "confidence": 0.7,
    }


def composer_facing_expected(p, dumps):
    parts = [p["abstract"], p["confidence"], *p["highlights"], *p["uncertainty"]]
    for c in p["claims"]:
        parts += [c["statement"], c["confidence"]]
    return sum(len(dumps(x)) for x in parts)


VARIANTS = [
    lambda p: json.dumps(p, ensure_ascii=False),
    lambda p: json.dumps(p, ensure_ascii=False, indent=2),
    lambda p: json.dumps(p, ensure_ascii=True, separators=(",", ":")),
    lambda p: "```json\n" + json.dumps(p, ensure_ascii=False) + "\n```",
]


@pytest.mark.parametrize("variant", VARIANTS)
def test_parts_partition_the_text_exactly(split, variant):
    text = variant(payload())
    r = split.split_text(text)
    for unit in ("chars", "bytes"):
        total = r[f"total_{unit}"]
        assert sum(r[f"{p}_{unit}"] for p in split.PARTS) == total
        assert r[f"composer_facing_{unit}"] + r[f"non_composer_facing_{unit}"] == total
        assert all(r[f"{p}_{unit}"] >= 0 for p in split.PARTS)


def test_composer_facing_is_exactly_the_projected_values(split):
    p = payload(3)
    for ascii_ in (False, True):
        text = json.dumps(p, ensure_ascii=ascii_)
        r = split.split_text(text)
        assert r["composer_facing_chars"] == composer_facing_expected(
            p, lambda x: json.dumps(x, ensure_ascii=ascii_))


def test_non_composer_parts(split):
    p = payload(4)
    text = json.dumps(p, ensure_ascii=False)
    r = split.split_text(text)
    # default separators: '"key": value, ' for each member but the last
    for key in ("concepts", "relations"):
        assert r[f"{key}_chars"] == len(f'"{key}": ') + len(json.dumps(p[key], ensure_ascii=False)) + 2
    claims_member = len('"claims": ') + len(json.dumps(p["claims"], ensure_ascii=False)) + 2
    claim_cf = sum(len(json.dumps(c["statement"], ensure_ascii=False)) + len(json.dumps(c["confidence"]))
                   for c in p["claims"])
    assert r["claim_ids_and_evidence_chars"] == claims_member - claim_cf


def test_end_to_end_on_a_ledger(split, tmp_path):
    texts = [json.dumps(payload(i), ensure_ascii=False, indent=(2 if i % 2 else None)) for i in range(5)]
    ledger = tmp_path / "h1cap_ledger.jsonl"
    with open(ledger, "w", encoding="utf-8") as fh:
        fh.write("H1_META {}\n")
        for i, t in enumerate(texts):
            turn = {"index": i, "captures": [{"label": "ive", "outcome": "OK", "text": t}],
                    "ive_calls": [{"outcome": "OK", "candidates_tokens": 1000 + i}]}
            fh.write("H1_TURN " + json.dumps(turn, ensure_ascii=False) + "\n")
        # a failed turn and a truncated output are skipped or reported, never fatal
        fh.write("H1_TURN " + json.dumps({"index": 5, "captures": [], "ive_calls": []}) + "\n")
        bad = {"index": 6, "captures": [{"label": "ive", "outcome": "OK", "text": texts[0][:-30]}],
               "ive_calls": [{"outcome": "OK", "candidates_tokens": 9}]}
        fh.write("H1_TURN " + json.dumps(bad, ensure_ascii=False) + "\n")
        fh.write("H1_SUMMARY {}\n")
    out = tmp_path / "split.json"
    assert split.main([str(ledger), str(out)]) == 0
    s = json.load(open(out, encoding="utf-8"))
    assert s["turns_split"] == 5 and [f["index"] for f in s["split_failures"]] == [6]
    tot = sum(len(t) for t in texts)
    cf = sum(split.split_text(t)["composer_facing_chars"] for t in texts)
    assert s["pooled_share_chars"]["composer_facing"] == pytest.approx(cf / tot)
    r0 = s["rows"][0]
    assert r0["composer_facing_est_tokens"] == pytest.approx(1000 * r0["composer_facing_chars"] / len(texts[0]))
