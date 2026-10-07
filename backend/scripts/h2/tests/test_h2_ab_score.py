"""Offline tests for h2_ab_score.py (the H2 IVE thinking-budget A/B scorer). ZERO provider calls.

Synthetic ledgers exercise every verdict step of H2_AB_THINKING_PREREG.md; the
schema validator is cross-checked against jsonschema, and the parser against
the app's own parse_json. Run from the repository's backend/ directory:
    python -m pytest -q -p no:cacheprovider scripts/h2/tests/test_h2_ab_score.py
"""

from __future__ import annotations

import copy
import csv
import importlib.util
import json
import os
import random
import sys
import uuid

import jsonschema
import pytest

H2_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORER_PATH = os.path.join(H2_DIR, "h2_ab_score.py")
# Stand-in margins for the synthetic verdict tests only, used while the frozen
# values are unset; test_operator_decision_constants fails until they are set.
STAND_IN_CONTENT_MARGIN = 0.05
MODEL = "gemini-2.5-pro"


@pytest.fixture
def s():
    name = f"h2abs_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(name, SCORER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    for margin in ("MARGIN_ABSTRACT_CONTENT", "MARGIN_HIGHLIGHTS_CONTENT"):
        if getattr(mod, margin) is None:
            setattr(mod, margin, STAND_IN_CONTENT_MARGIN)
    return mod


# --------------------------------------------------------------------- #
# synthetic ledgers
# --------------------------------------------------------------------- #
def payload(i, p, *, claims=6, unc=2, conf=0.75, concepts=5, relations=6, claim_ids=("EV-1", "EV-2"),
            rel_ids=("EV-1",), unc_words="the evidence on origins is thin and debated"):
    words = ["money", "credit", "trust", "ledger", "state", "market", "debt", "value", "exchange"]
    return {
        "abstract": f"Abstract for question {i}: " + " ".join(words[(i + p + k) % 9] for k in range(12)),
        "highlights": [f"highlight {i} {words[(p + k) % 9]}" for k in range(4)],
        "claims": [{"claim_id": f"c{k + 1}",
                    "statement": f"Claim {k} on {words[(i + k) % 9]} and {words[(i + k + p) % 9]} in question {i}",
                    "evidence_document_ids": list(claim_ids), "confidence": 0.8} for k in range(claims)],
        "concepts": [{"name": f"Concept {k}", "description": f"about {words[k % 9]}"} for k in range(concepts)],
        "relations": [{"source": "ION", "relation": f"r{k}", "target": words[k % 9],
                       "evidence_document_ids": list(rel_ids)} for k in range(relations)],
        "uncertainty": [f"Uncertainty {k}: {unc_words} ({words[(i + p + k) % 9]})" for k in range(unc)],
        "confidence": conf,
    }


def contract(pl):
    return {"engine_id": "gemini", "provider": "gemini", "model": MODEL, "question": "q",
            "abstract": pl["abstract"], "highlights": pl["highlights"], "claims": pl["claims"],
            "concepts": pl["concepts"], "relations": pl["relations"],
            "evidence_mapping": {c["claim_id"]: c["evidence_document_ids"] for c in pl["claims"]},
            "uncertainty": pl["uncertainty"], "confidence": pl["confidence"]}


def arm(s, pl, ms, *, schema_sha, user="u", visible=1400, thoughts=1700, status="OK", text=None, cls=None,
        budget=None):
    return {"status": status, "text": json.dumps(pl) if text is None else text,
            "report": contract(pl) if status == "OK" else None,
            "input": {"system": {"sha256": "sys"}, "user": {"sha256": user}, "schema": {"sha256": schema_sha}},
            "tap": [{"outcome": "OK", "sdk_latency_ms": ms, "candidates_tokens": visible, "thoughts_tokens": thoughts,
                     "prompt_tokens": 3000, "cached_tokens": None, "thinking_config_sent": budget is not None,
                     "thinking_budget_sent": budget}],
            "classification": cls or {"classification": "OK" if status == "OK" else "ARM_FAILURE", "class_key": None}}


def attempt(s, p, i, a_pl, b_pl, a_ms, b_ms, *, kind="primary", has_pf=False, b_status="OK", b_text=None,
            b_visible=1300, b_thoughts=1000, user_b=None):
    return {"pass": p, "index": i, "kind": kind, "order": s.expected_order(p, i),
            "expected_order": s.expected_order(p, i), "model_input": {"allowed_ids": ["EV-1", "EV-2", "EV-3"]},
            "arms": {"A": arm(s, a_pl, a_ms, schema_sha=s.EXPECTED_SCHEMA_A_SHA256, user=f"u{p}{i}"),
                     "B": arm(s, b_pl, b_ms, schema_sha=s.EXPECTED_SCHEMA_B_SHA256, user=user_b or f"u{p}{i}",
                              status=b_status, text=b_text, visible=b_visible, thoughts=b_thoughts,
                              budget=s.THINKING_BUDGET_B)},
            "a_parity": True, "classification": {"has_pf": has_pf, "calls": [{"provider_fault": has_pf}]},
            "invalidated": has_pf, "unresolved": False}


def write_ledger(path, s, attempts, *, status="COMPLETE", summary=True, meta_budget=1280):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("H2AB_META " + json.dumps({"schema_a": s.SCHEMA_A, "schema_b": s.SCHEMA_B,
                                            "thinking_budget_b": meta_budget, "prereg_sha256": "prereg"}) + "\n")
        for a in attempts:
            fh.write("H2AB_ATTEMPT " + json.dumps(a) + "\n")
        if summary:
            fh.write("H2AB_SUMMARY " + json.dumps({"status": status, "stop_reason": None, "provider_calls": 162,
                                                   "provider_faults": []}) + "\n")
    return str(path)


def full(s, *, b_payload=None, lat=None, b_text=None, b_status=None, seed=7):
    """81 scored pairs (3 passes). Defaults: B = A's content, B 3 s faster and thinking 1000 tokens."""
    rng = random.Random(seed)
    out = []
    for p in range(1, s.PASSES + 1):
        for i in range(27):
            a_pl = payload(i, p)
            b_pl = b_payload(i, p) if b_payload else payload(i, p)
            a_ms = 24000 + rng.gauss(0, 2500)
            b_ms = lat(i, p, a_ms, rng) if lat else a_ms - 3000 + rng.gauss(0, 300)
            out.append(attempt(s, p, i, a_pl, b_pl, a_ms, b_ms,
                               b_text=b_text(i, p) if b_text else None,
                               b_status=b_status(i, p) if b_status else "OK"))
    return out


def scored(s, tmp_path, attempts, **kw):
    return s.score(write_ledger(tmp_path / f"l{uuid.uuid4().hex[:6]}.jsonl", s, attempts, **kw))


# --------------------------------------------------------------------- #
# building blocks
# --------------------------------------------------------------------- #
def test_embedded_schemas_are_the_preregistered_ones(s):
    """H2 leaves the schema unchanged: both arms use the module's own schema (no H1 caps)."""
    import app.modules.ive_common as ic

    assert s.sha256_text(s.canonical(ic.IVE_RESPONSE_SCHEMA)) == s.EXPECTED_SCHEMA_A_SHA256
    assert s.SCHEMA_A == json.loads(json.dumps(ic.IVE_RESPONSE_SCHEMA))
    assert s.SCHEMA_B is s.SCHEMA_A and s.EXPECTED_SCHEMA_B_SHA256 == s.EXPECTED_SCHEMA_A_SHA256
    assert s.json_diff(ic.IVE_RESPONSE_SCHEMA, s.SCHEMA_B) == []
    assert all("maxItems" not in ic.IVE_RESPONSE_SCHEMA["properties"][k] for k in ("concepts", "relations"))


def _mutations(base):
    yield base
    for key in list(base):
        m = copy.deepcopy(base)
        del m[key]
        yield m
    yield {**base, "extra": 1}
    yield {**base, "confidence": "high"}
    yield {**base, "confidence": True}
    yield {**base, "concepts": [{"name": "x"}]}
    yield {**base, "concepts": [{"name": "x", "description": "d", "z": 1}]}
    yield {**base, "concepts": [{"name": "x", "description": "d"}] * 4}
    yield {**base, "relations": [{"source": "a", "relation": "b", "target": "c", "evidence_document_ids": ["E"]}] * 5}
    yield {**base, "relations": [{"source": "a", "relation": "b", "target": "c", "evidence_document_ids": [1]}]}
    yield {**base, "claims": [{"claim_id": "c", "statement": "s", "evidence_document_ids": ["E"], "confidence": 1}]}
    yield {**base, "highlights": "not a list"}
    yield {**base, "uncertainty": [None]}
    yield [base]


def test_schema_validator_agrees_with_jsonschema(s):
    base = payload(0, 1, concepts=3, relations=4)
    n = 0
    for inst in _mutations(base):
        try:
            jsonschema.validate(inst, s.SCHEMA_A)
            expected = True
        except jsonschema.ValidationError:
            expected = False
        assert (s.schema_violations(inst, s.SCHEMA_A) == []) is expected, inst
        n += 1
    assert n == 20
    assert s.schema_violations({**base, "concepts": base["concepts"] * 9}, s.SCHEMA_A) == []   # no cap in H2
    with pytest.raises(ValueError):
        s.schema_violations({}, {"type": "object", "pattern": "x"})


@pytest.mark.parametrize("text", [
    '{"a": 1}', '  {"a": 1}\n', '```json\n{"a": 1}\n```', '```\n{"a": 1}\n```', '```JSON\n{"a": 1}```',
    '[1, 2]', 'not json', '', '```json\n[1]\n```', '{"a": "```"}',
])
def test_parse_like_app_matches_the_app(s, text):
    import app.modules.ive_common as ic
    from app.core.errors import NormalizationError

    try:
        expected = ic.parse_json(text)
    except NormalizationError:
        expected = "ERR"
    try:
        got = s.parse_like_app(text)
    except ValueError:
        got = "ERR"
    assert got == expected


def test_similarity_measures(s):
    assert s.jaccard(s.tokens("Money, money!"), s.tokens("money")) == 1.0
    assert s.tokens("Ünïcödé_x 42") == frozenset({"ünïcödé", "x", "42"})
    assert s.smbm([], []) == 1.0 and s.smbm(["a"], []) == 0.0
    assert s.smbm(["a b", "c d"], ["a b"]) == pytest.approx((0.5 + 1.0) / 2)


def test_order_alternates_in_run_order_and_every_question_meets_both(s):
    passes = range(1, s.PASSES + 1)
    slots = [s.expected_order(p, i) for p in passes for i in range(27)]
    assert slots[:3] == ["AB", "BA", "AB"] and all(x != y for x, y in zip(slots, slots[1:]))
    assert len(slots) == 81 and slots.count("AB") == 41 and slots.count("BA") == 40
    assert s.expected_order(2, 0) == "BA" and s.expected_order(3, 0) == "AB"
    # three passes: every question meets both orders
    assert all({s.expected_order(p, i) for p in passes} == {"AB", "BA"} for i in range(27))


def test_operator_decision_constants():
    """Operator decision 2026-10-07 21:25Z: budget 1280, 81 pairs / 3 passes, 81-pair margins,
    mean latency rule at 2.0 s. Reads the module file as written (no stand-in margins), so
    it fails until the calibrated abstract and highlights margins are set."""
    spec = importlib.util.spec_from_file_location(f"h2abs_raw_{uuid.uuid4().hex[:8]}", SCORER_PATH)
    raw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(raw)
    assert raw.THINKING_BUDGET_B == 1280
    assert (raw.PASSES, raw.N_QUESTIONS, raw.SCHEDULED_PAIRS) == (3, 27, 81)
    assert (raw.MARGIN_CLAIM_COUNT, raw.MARGIN_EVIDENCE_COVERAGE, raw.MARGIN_CLAIM_CONTENT,
            raw.MARGIN_UNCERTAINTY_COUNT, raw.MARGIN_UNCERTAINTY_CONTENT, raw.MARGIN_CONFIDENCE) == (
        0.45, 0.05, 0.04, 0.45, 0.125, 0.02)
    for m in (raw.MARGIN_ABSTRACT_CONTENT, raw.MARGIN_HIGHLIGHTS_CONTENT):
        assert isinstance(m, float) and 0 < m < 1, "abstract/highlights margins not calibrated"
    assert (raw.LATENCY_MATERIAL_MS, raw.LATENCY_LOWER_BOUND_LEVEL, raw.CI_LEVEL) == (2000.0, 0.95, 0.95)
    assert (raw.SEED, raw.RESAMPLES) == (20261006, 10_000)


def test_hodges_lehmann(s):
    assert s.hodges_lehmann([]) is None and s.hodges_lehmann([5.0]) == 5.0
    assert s.hodges_lehmann([1.0, 2.0, 9.0]) == 3.5          # Walsh averages 1, 1.5, 2, 5, 5.5, 9
    assert s.hodges_lehmann([0.0, 10.0, 10.0, 10.0, 1000.0]) == 10.0


def test_gain_at_equal_thinking(s):
    pts = [(dt, 1000.0 + 7.5 * dt) for dt in (-300, -100, 0, 50, 200)]
    assert s.gain_at_equal_thinking(pts) == pytest.approx(1000.0)
    assert s.gain_at_equal_thinking([(0, 900.0), (0, 1100.0)]) == pytest.approx(1000.0)   # slope unidentified


def test_quantile_and_bootstrap_are_deterministic(s):
    assert s.quantile([1, 2, 3, 4], 0.5) == 2.5 and s.quantile([5], 0.9) == 5
    clusters = [[1.0, 2.0], [3.0], [10.0, -1.0, 4.0]]
    one = s.cluster_bootstrap(clusters, s.mean, resamples=500)
    two = s.cluster_bootstrap(clusters, s.mean, resamples=500)
    assert one == two and one[0] == pytest.approx(19.0 / 6)
    assert one[1][0] < one[0] < one[1][1]
    assert s.cluster_bootstrap([], s.mean) == (None, (None, None))
    assert s.sign_test(0, 6) == pytest.approx(2 / 64) and s.sign_test(3, 3) == 1.0


def test_report_features_and_defects(s):
    pl = payload(1, 1, claim_ids=("EV-1", "EV-9"), rel_ids=("EV-1", "EV-8"))
    pl["claims"].append({"claim_id": "cx", "statement": "bare", "evidence_document_ids": [], "confidence": 0.5})
    f = s.report_features(contract(pl), ["EV-1", "EV-2"])
    assert f["defects"] == ["CLAIM_WITHOUT_EVIDENCE", "STRAY_CLAIM_ID", "STRAY_RELATION_ID"]
    assert f["stray_claim_ids"] == ["EV-9"] and f["stray_relation_ids"] == ["EV-8"]
    assert f["coverage"] == 0.5 and f["cga1_would_pass"] is False and f["relation_only_ids"] == ["EV-8"]
    unknown = s.report_features(contract(pl), None)
    assert unknown["defects"] == ["CLAIM_WITHOUT_EVIDENCE"] and unknown["cga1_would_pass"] is None


def test_hard_fail_events_are_b_only(s):
    a_pl, b_pl = payload(0, 1), payload(0, 1, concepts=3, relations=4)
    row = attempt(s, 1, 0, a_pl, b_pl, 1, 1)
    assert s.pair_hard_fail_events(row) == []           # fewer concepts/relations is no event in H2
    # G2: B output misses a required field (the parsed text is checked, not the normalized report)
    row = attempt(s, 1, 0, a_pl, b_pl, 1, 1, b_text=json.dumps({k: v for k, v in b_pl.items() if k != "highlights"}))
    assert s.pair_hard_fail_events(row) == [{"code": "G2", "detail": "MISSING_REQUIRED /highlights"}]
    row = attempt(s, 1, 0, a_pl, b_pl, 1, 1, b_text=json.dumps({**b_pl, "confidence": "high"}))
    assert s.pair_hard_fail_events(row) == [{"code": "G2", "detail": "WRONG_TYPE /confidence"}]
    # G3: B-only stray relation id; not an event when A has the same defect
    row = attempt(s, 1, 0, a_pl, payload(0, 1, rel_ids=("EV-7",)), 1, 1)
    assert s.pair_hard_fail_events(row) == [{"code": "G3", "detail": "STRAY_RELATION_ID"}]
    row = attempt(s, 1, 0, payload(0, 1, rel_ids=("EV-7",)), payload(0, 1, rel_ids=("EV-7",)), 1, 1)
    assert s.pair_hard_fail_events(row) == []
    # G3: B-only stray claim id and B-only claim without evidence
    row = attempt(s, 1, 0, a_pl, payload(0, 1, claim_ids=("EV-1", "EV-99")), 1, 1)
    assert s.pair_hard_fail_events(row) == [{"code": "G3", "detail": "STRAY_CLAIM_ID"}]
    row = attempt(s, 1, 0, a_pl, payload(0, 1, claim_ids=()), 1, 1)
    assert s.pair_hard_fail_events(row) == [{"code": "G3", "detail": "CLAIM_WITHOUT_EVIDENCE"}]
    # G1: B failed where A succeeded; nothing when A failed too
    row = attempt(s, 1, 0, a_pl, b_pl, 1, 1, b_status="INVALID_OUTPUT", b_text="{trunc")
    row["arms"]["B"]["classification"] = {"classification": "ARM_FAILURE", "class_key": "PROVIDER_WRAPPED|x"}
    assert s.pair_hard_fail_events(row) == [{"code": "G1", "detail": "B INVALID_OUTPUT: PROVIDER_WRAPPED|x"}]
    row["arms"]["A"]["status"] = "CALL_FAILED"
    assert s.pair_hard_fail_events(row) == []
    # G2 by kind: a violation A shares is not B-only
    bad = dict(b_pl, extra=1)
    row = attempt(s, 1, 0, dict(a_pl, extra=1), bad, 1, 1)
    assert s.pair_hard_fail_events(row) == []
    row = attempt(s, 1, 0, a_pl, bad, 1, 1)
    assert s.pair_hard_fail_events(row) == [{"code": "G2", "detail": "EXTRA_PROPERTY /extra"}]
    # harness states are not arm-B behaviour: the guard or capture stop decides those
    for status in ("REFUSED", "NOT_RUN", "UNSCORED"):
        row = attempt(s, 1, 0, a_pl, b_pl, 1, 1, b_status=status)
        assert s.pair_hard_fail_events(row) == [], status


def test_unparseable_output_never_raises(s):
    nested = "[" * 200_000 + "]" * 200_000          # valid JSON nesting that exhausts the parser's recursion
    view = s.arm_view({"status": "INVALID_OUTPUT", "text": nested}, s.SCHEMA_B, None)
    assert view["violations"] == [("UNPARSEABLE", "/")] and view["ok"] is False
    a_pl = payload(0, 1)
    row = attempt(s, 1, 0, a_pl, a_pl, 1, 1, b_status="INVALID_OUTPUT", b_text=nested)
    assert [e["code"] for e in s.pair_hard_fail_events(row)] == ["G1"]


def test_thinking_config_must_be_the_preregistered_one(s):
    ok_a = {"thinking_config_sent": False, "thinking_budget_sent": None}
    ok_b = {"thinking_config_sent": True, "thinking_budget_sent": 1280}
    assert s.thinking_as_preregistered("A", ok_a) and s.thinking_as_preregistered("B", ok_b)
    assert not s.thinking_as_preregistered("A", ok_b)                      # any config on A
    assert not s.thinking_as_preregistered("B", ok_a)                      # none on B
    for bad in (1024, 1536, -1, "1280", 1280.5, None):
        assert not s.thinking_as_preregistered("B", {"thinking_config_sent": True, "thinking_budget_sent": bad})
    assert not s.thinking_as_preregistered("A", {})                        # unrecorded is not "none sent"


def test_scored_set_rules(s):
    a_pl, b_pl = payload(0, 1), payload(0, 1, concepts=3, relations=4)
    atts = [attempt(s, 1, 0, a_pl, b_pl, 1, 1, has_pf=True),
            attempt(s, 1, 0, a_pl, b_pl, 1, 1, kind="replacement"),
            attempt(s, 1, 1, a_pl, b_pl, 1, 1, has_pf=True),
            attempt(s, 1, 1, a_pl, b_pl, 1, 1, kind="replacement", has_pf=True),
            attempt(s, 1, 2, a_pl, b_pl, 1, 1)]
    ss = s.scored_set(atts)
    assert sorted(ss["scored"]) == [(1, 0), (1, 2)] and ss["scored"][(1, 0)]["kind"] == "replacement"
    assert ss["unresolved"] == [{"pass": 1, "index": 1}] and ss["pending"] == [] and ss["inconsistent"] == []
    # a faulted primary whose replacement never ran (the run stopped first) is pending, not unresolved
    ss = s.scored_set(atts + [attempt(s, 1, 3, a_pl, b_pl, 1, 1, has_pf=True)])
    assert ss["pending"] == [{"pass": 1, "index": 3}] and ss["unresolved"] == [{"pass": 1, "index": 1}]
    atts[4]["invalidated"] = True              # flag disagrees with the classification
    assert s.scored_set(atts)["inconsistent"]


# --------------------------------------------------------------------- #
# verdict steps
# --------------------------------------------------------------------- #
def test_pass_when_quality_holds_and_the_gain_is_material(s, tmp_path):
    r = scored(s, tmp_path, full(s))
    assert r["integrity"]["ok"] and r["run"]["complete"] and r["run"]["scored_pairs"] == 81
    assert {k: v["state"] for k, v in r["endpoints"].items()} == {
        "claim_count": "NONINFERIOR", "evidence_coverage": "NONINFERIOR", "claim_content": "NONINFERIOR",
        "uncertainty_count": "NONINFERIOR", "uncertainty_content": "NONINFERIOR", "confidence": "EQUIVALENT",
        "abstract_content": "NONINFERIOR", "highlights_content": "NONINFERIOR"}
    assert r["endpoints"]["abstract_content"]["margin"] == s.MARGIN_ABSTRACT_CONTENT
    assert r["endpoints"]["highlights_content"]["margin"] == s.MARGIN_HIGHLIGHTS_CONTENT
    assert not any(w["triggered"] for w in r["uncertainty_warnings"].values())
    assert r["latency"]["state"] == "MATERIAL" and 2800 < r["latency"]["mean_improvement_ms"] < 3200
    assert r["latency"]["threshold_ms"] == 2000.0
    assert r["latency"]["mean_improvement_lower_bound_one_sided_95"] > 0
    assert 2800 < r["latency"]["median_improvement_ms"] < 3200 and r["latency"]["median_improvement_ci95"][0] > 0
    assert 2800 < r["latency"]["hodges_lehmann_improvement_ms"] < 3200
    assert r["verdict"] == {"label": "PASS", "step": 7}
    assert r["thinking"]["budget_b"] == 1280 and r["thinking"]["b_over_budget"] == 0
    assert r["thinking"]["b_over_budget_share"] == 0.0 and r["thinking"]["b_thoughts"]["median"] == 1000
    assert r["schema"]["b_schema_violation_pairs"] == 0 and r["schema"]["a_schema_violation_pairs"] == 0
    assert r["tokens"]["visible"]["delta_b_minus_a"]["mean"] == -100
    assert r["tokens"]["thinking"]["delta_b_minus_a"]["mean"] == -700
    assert r["tokens"]["thinking"]["delta_b_minus_a"]["changed"] is True
    lat = r["latency"]
    assert lat["delta_b_minus_a_ms"]["median"] == pytest.approx(-lat["median_improvement_ms"])
    assert lat["gain_at_equal_thinking_ms"]["label"] == "REPORT_ONLY" and lat["gain_at_equal_thinking_ms"]["pairs"] == 81
    assert set(lat["by_order_median_ms"]) == set(lat["by_order_mean_ms"]) == {"AB", "BA"}


def test_gain_at_equal_thinking_removes_a_thinking_shift(s, tmp_path):
    atts = full(s)
    for k, att in enumerate(atts):
        extra = (k % 7 - 3) * 100                       # B thinks 300 fewer .. 300 more tokens
        a_ms = att["arms"]["A"]["tap"][0]["sdk_latency_ms"]
        att["arms"]["B"]["tap"][0]["thoughts_tokens"] = 1700 + extra
        att["arms"]["B"]["tap"][0]["sdk_latency_ms"] = a_ms - 800 + 7.5 * extra
    r = scored(s, tmp_path, atts)
    g = r["latency"]["gain_at_equal_thinking_ms"]
    assert g["estimate"] == pytest.approx(800) and g["ci95"] == [pytest.approx(800), pytest.approx(800)]
    assert r["tokens"]["thinking"]["delta_b_minus_a"]["mean"] == pytest.approx(
        sum((k % 7 - 3) * 100 for k in range(81)) / 81)
    assert r["verdict"]["step"] == 7          # report-only: the verdict still comes from the raw latency rule


def test_not_material_below_two_seconds(s, tmp_path):
    # a clearly real 1.5 s gain is still below the operator's 2.0 s bar
    r = scored(s, tmp_path, full(s, lat=lambda i, p, a, rng: a - 1500 + rng.gauss(0, 50)))
    assert r["latency"]["mean_improvement_lower_bound_one_sided_95"] > 0
    assert r["latency"]["state"] == "NOT_MATERIAL" and r["verdict"]["label"] == "NOT_MATERIAL"


def test_latency_not_shown_when_questions_disagree(s, tmp_path):
    # 14 questions 9 s faster in B, 13 questions 5.5 s slower: mean 2.02 s, one-sided bound below 0
    r = scored(s, tmp_path, full(s, lat=lambda i, p, a, rng: a - (9000 if i < 14 else -5500)))
    assert r["latency"]["mean_improvement_ms"] == pytest.approx((14 * 9000 - 13 * 5500) / 27)
    assert r["latency"]["mean_improvement_ms"] >= 2000
    assert r["latency"]["mean_improvement_lower_bound_one_sided_95"] <= 0 and r["latency"]["state"] == "NOT_SHOWN"
    assert r["verdict"] == {"label": "INCONCLUSIVE", "sub_reason": "LATENCY_NOT_SHOWN", "step": 7}


def test_latency_rule_uses_the_mean_not_the_median(s, tmp_path):
    # 15 questions 3 s faster, 12 questions 1 s slower: median 3 s but mean 1.22 s
    r = scored(s, tmp_path, full(s, lat=lambda i, p, a, rng: a - (3000 if i < 15 else -1000)))
    assert r["latency"]["median_improvement_ms"] == pytest.approx(3000)
    assert r["latency"]["mean_improvement_ms"] == pytest.approx((15 * 3000 - 12 * 1000) / 27)
    assert r["latency"]["state"] == "NOT_MATERIAL" and r["verdict"]["label"] == "NOT_MATERIAL"


def test_latency_lower_bound_is_one_sided_95(s, tmp_path):
    """The rule's bound is the 5th percentile of the bootstrap means (one-sided 95%),
    not the 2.5th. Shift-equivariance places a constant offset so that the
    one-sided bound is above 0 while the two-sided 95% lower limit is not."""
    base = [9000.0 if i < 14 else -5500.0 for i in range(27)]
    clusters = [[g] * s.PASSES for g in base]
    _, (q05, _) = s.cluster_bootstrap(clusters, s.mean, level=0.90)
    _, (q025, _) = s.cluster_bootstrap(clusters, s.mean)
    assert q025 < q05
    shift = -(q025 + q05) / 2.0
    r = scored(s, tmp_path, full(s, lat=lambda i, p, a, rng: a - (base[i] + shift)))
    lat = r["latency"]
    assert lat["mean_improvement_lower_bound_one_sided_95"] == pytest.approx(q05 + shift)
    assert lat["mean_improvement_lower_bound_one_sided_95"] > 0 > q025 + shift
    assert lat["mean_improvement_ms"] >= 2000 and lat["state"] == "MATERIAL" and r["verdict"]["label"] == "PASS"


def test_uncertainty_reduction_is_a_warning_not_a_success(s, tmp_path):
    def b_payload(i, p):
        drop = (i + p) % 9 == 0          # 9 of 81 pairs lose one uncertainty item
        return payload(i, p, unc=1 if drop else 2)

    r = scored(s, tmp_path, full(s, b_payload=b_payload))
    assert r["endpoints"]["uncertainty_count"]["state"] == "NONINFERIOR"
    assert r["uncertainty_warnings"]["W1_count_reduced"]["triggered"] is True
    assert r["uncertainty_warnings"]["W2_chars_reduced"]["triggered"] is True
    assert r["verdict"]["label"] == "WARNING" and r["verdict"]["step"] == 6


def test_emptied_uncertainty_triggers_the_sign_test(s, tmp_path):
    def b_payload(i, p):
        return payload(i, p, unc=0 if (i + p) % 3 == 0 else 2)

    r = scored(s, tmp_path, full(s, b_payload=b_payload))
    w3 = r["uncertainty_warnings"]["W3_b_only_empty"]
    assert w3["b_only_empty"] == 27 and w3["a_only_empty"] == 0 and w3["triggered"]
    assert r["verdict"]["label"] in ("FAIL", "INCONCLUSIVE", "WARNING")


def test_fewer_claims_fail_quality(s, tmp_path):
    r = scored(s, tmp_path, full(s, b_payload=lambda i, p: payload(i, p, claims=4)))
    assert r["endpoints"]["claim_count"]["state"] == "INFERIOR"
    assert r["verdict"] == {"label": "FAIL", "sub_reason": "QUALITY", "step": 4, "endpoints": ["claim_count"]}


def test_changed_claim_content_fails_quality(s, tmp_path):
    def b_payload(i, p):
        pl = payload(i, p)
        for c in pl["claims"]:
            c["statement"] = f"entirely different wording {c['claim_id']} zebra quartz"
        return pl

    r = scored(s, tmp_path, full(s, b_payload=b_payload))
    assert r["endpoints"]["claim_content"]["state"] == "INFERIOR" and r["verdict"]["label"] == "FAIL"


def test_confidence_shift_is_divergent(s, tmp_path):
    r = scored(s, tmp_path, full(s, b_payload=lambda i, p: payload(i, p, conf=0.9)))
    assert r["endpoints"]["confidence"]["state"] == "DIVERGENT"
    assert r["verdict"]["sub_reason"] == "QUALITY" and r["verdict"]["endpoints"] == ["confidence"]


def test_hard_gate_beats_quality_and_latency(s, tmp_path):
    atts = full(s)
    atts[40]["arms"]["B"]["report"]["relations"][0]["evidence_document_ids"] = ["EV-404"]
    r = scored(s, tmp_path, atts)
    assert r["hard_fail"]["pairs"] == 1 and r["hard_fail"]["by_code"] == {"G3": 1}
    assert r["verdict"] == {"label": "FAIL", "sub_reason": "HARD_GATE", "step": 2, "codes": {"G3": 1}}


def test_b_failure_is_hard_gate_and_excluded_from_quality(s, tmp_path):
    r = scored(s, tmp_path, full(s, b_status=lambda i, p: "CALL_FAILED" if (i, p) == (5, 2) else "OK"))
    assert r["excluded"]["b_failed_g1"] == [[2, 5]] and r["quality_pairs"] == 80
    assert r["verdict"]["label"] == "FAIL" and r["verdict"]["codes"] == {"G1": 1}


@pytest.mark.parametrize("status, label, sub", [
    ("INCONCLUSIVE_PROVIDER_HEALTH", "INCONCLUSIVE", "PROVIDER_HEALTH"),
    ("INCONCLUSIVE_IVE_OR_TURN_NON_PROVIDER_FAILURE", "INCONCLUSIVE", "IVE_OR_TURN_NON_PROVIDER_FAILURE"),
    ("STOPPED_HARNESS_GUARD", "INCONCLUSIVE", "HARNESS_INTEGRITY"),
    ("STOPPED_HTTP_402", "INCONCLUSIVE", "HTTP_402"),
])
def test_stops_decide_first(s, tmp_path, status, label, sub):
    r = scored(s, tmp_path, full(s)[:30], status=status)
    assert r["verdict"]["label"] == label and r["verdict"]["sub_reason"] == sub


@pytest.mark.parametrize("arm, status", [("B", "STOPPED_HTTP_402"),
                                         ("A", "INCONCLUSIVE_IVE_OR_TURN_NON_PROVIDER_FAILURE")])
def test_http_402_is_inconclusive_never_a_b_failure(s, tmp_path, arm, status):
    atts = full(s)[:12]
    rec = atts[-1]["arms"][arm]
    rec.update({"status": "CALL_FAILED", "report": None, "text": None,
                "error": {"exc_type": "google.genai.errors.ClientError", "http_status": 402}})
    rec["tap"][0].update({"outcome": "FAILED", "error": {"http_status": 402, "provider_status": "PAYMENT_REQUIRED"}})
    if arm == "A":
        atts[-1]["error_detail"] = {"http_status": 402}
    assert s.pair_hard_fail_events(atts[-1]) == []
    r = scored(s, tmp_path, atts, status=status)
    assert r["run"]["http_402_attempts"] == 1 and r["hard_fail"]["pairs"] == 0
    assert r["excluded"]["b_failed_not_g1" if arm == "B" else "only_a_failed"] == [[1, 11]]
    assert r["excluded"]["b_failed_g1"] == []
    assert r["verdict"] == {"label": "INCONCLUSIVE", "sub_reason": "HTTP_402", "step": 1,
                            "hard_fail_pairs_before_stop": 0}


def test_a_stop_reports_hard_fail_seen_before_it(s, tmp_path):
    atts = full(s)[:10]
    atts[3]["arms"]["B"]["report"]["claims"][0]["evidence_document_ids"] = []
    r = scored(s, tmp_path, atts, status="INCONCLUSIVE_PROVIDER_HEALTH")
    assert r["verdict"]["label"] == "INCONCLUSIVE" and r["verdict"]["hard_fail_pairs_before_stop"] == 1


def test_missing_summary_or_pairs_is_incomplete(s, tmp_path):
    r = scored(s, tmp_path, full(s), summary=False)
    assert r["verdict"]["sub_reason"] == "INCOMPLETE"
    r = scored(s, tmp_path, full(s)[:-1])
    assert r["verdict"]["sub_reason"] == "INCOMPLETE"


def test_unresolved_pairs_do_not_make_the_run_incomplete(s, tmp_path):
    atts = full(s)
    pf = copy.deepcopy(atts[10])
    pf.update({"invalidated": True, "classification": {"has_pf": True, "calls": [{"provider_fault": True}]}})
    rep = copy.deepcopy(pf)
    rep["kind"] = "replacement"
    atts[10:11] = [pf, rep]
    r = scored(s, tmp_path, atts)
    assert r["run"]["unresolved"] == [{"pass": 1, "index": 10}] and r["run"]["complete"]
    assert r["run"]["scored_pairs"] == 80 and r["verdict"]["label"] == "PASS"
    # without its replacement the slot is pending and the run is not complete
    r = scored(s, tmp_path, atts[:11] + atts[12:])
    assert r["run"]["pending"] == [{"pass": 1, "index": 10}] and r["run"]["unresolved"] == []
    assert not r["run"]["complete"] and r["verdict"]["sub_reason"] == "INCOMPLETE"


@pytest.mark.parametrize("breakage", ["user", "order", "schema", "thinking", "thinking_b_budget",
                                      "thinking_b_missing", "meta_budget", "parity", "taps"])
def test_integrity_failures_make_it_inconclusive(s, tmp_path, breakage):
    atts = full(s)
    att = atts[12]
    if breakage == "user":
        att["arms"]["B"]["input"]["user"] = {"sha256": "different"}
    elif breakage == "order":
        att["order"] = "BA" if att["order"] == "AB" else "AB"
    elif breakage == "schema":
        att["arms"]["B"]["input"]["schema"] = {"sha256": "a capped schema"}
    elif breakage == "thinking":
        att["arms"]["A"]["tap"][0]["thinking_config_sent"] = True
    elif breakage == "thinking_b_budget":
        att["arms"]["B"]["tap"][0]["thinking_budget_sent"] = 1024
    elif breakage == "thinking_b_missing":
        att["arms"]["B"]["tap"][0].update({"thinking_config_sent": False, "thinking_budget_sent": None})
    elif breakage == "parity":
        att["a_parity"] = False
    elif breakage == "taps":
        att["arms"]["A"]["tap"].append(dict(att["arms"]["A"]["tap"][0]))
    r = scored(s, tmp_path, atts, meta_budget=1024 if breakage == "meta_budget" else 1280)
    assert r["integrity"]["ok"] is False
    assert r["verdict"]["label"] == "INCONCLUSIVE" and r["verdict"]["sub_reason"] == "HARNESS_INTEGRITY"


def test_main_writes_new_files_only(s, tmp_path):
    ledger = write_ledger(tmp_path / "l.jsonl", s, full(s))
    prefix = str(tmp_path / "out")
    assert s.main(["score", ledger, prefix]) == 0
    summary = json.load(open(prefix + "_summary.json", encoding="utf-8"))
    rows = list(csv.DictReader(open(prefix + "_pairs.csv", encoding="utf-8")))
    assert summary["verdict"]["label"] == "PASS" and len(rows) == 81 and rows[0]["order"] == "AB"
    assert float(rows[0]["abstract_jaccard"]) == 1.0 and float(rows[0]["highlights_smbm"]) == 1.0
    with pytest.raises(FileExistsError):
        s.main(["score", ledger, prefix])
    assert s.main(["nonsense"]) == 2


def test_model_chosen_text_cannot_stop_the_outputs(s, tmp_path):
    """A lone UTF-16 surrogate is a valid JSON escape (an emoji cut in half). In a
    model-chosen key it reaches the G2 detail, the CSV and the summary; every
    write must still succeed."""
    atts = full(s)
    bad = payload(4, 1)
    bad["k\udc00"] = 1
    atts[4]["arms"]["B"]["text"] = json.dumps(bad)
    ledger = write_ledger(tmp_path / "l.jsonl", s, atts)
    prefix = str(tmp_path / "out")
    assert s.main(["score", ledger, prefix]) == 0
    raw = open(prefix + "_summary.json", "rb").read()
    summary = json.loads(raw)
    assert raw.isascii() and summary["verdict"]["codes"] == {"G2": 1}
    assert summary["hard_fail"]["events"][0]["events"] == [{"code": "G2", "detail": "EXTRA_PROPERTY /k\udc00"}]
    rows = list(csv.DictReader(open(prefix + "_pairs.csv", encoding="utf-8")))
    assert rows[4]["events"] == "G2:EXTRA_PROPERTY /k\\udc00"


# --------------------------------------------------------------------- #
# H2-specific endpoints and reports
# --------------------------------------------------------------------- #
def test_changed_abstract_fails_quality(s, tmp_path):
    def b_payload(i, p):
        pl = payload(i, p)
        pl["abstract"] = f"An unrelated summary {i} about zebra quartz harbour lantern"
        return pl

    r = scored(s, tmp_path, full(s, b_payload=b_payload))
    assert r["endpoints"]["abstract_content"]["state"] == "INFERIOR"
    assert r["endpoints"]["highlights_content"]["state"] == "NONINFERIOR"
    assert r["verdict"] == {"label": "FAIL", "sub_reason": "QUALITY", "step": 4, "endpoints": ["abstract_content"]}


def test_dropped_highlights_fail_quality(s, tmp_path):
    def b_payload(i, p):
        pl = payload(i, p)
        pl["highlights"] = pl["highlights"][:1]
        return pl

    r = scored(s, tmp_path, full(s, b_payload=b_payload))
    assert r["endpoints"]["highlights_content"]["state"] == "INFERIOR"
    assert r["report_only"]["highlights"]["count_b"]["median"] == 1
    assert r["verdict"]["sub_reason"] == "QUALITY" and r["verdict"]["endpoints"] == ["highlights_content"]


def test_content_endpoint_compares_cross_arm_with_within_a(s, tmp_path):
    """Identical arms give exactly 0 for every content endpoint: cross-pass A-vs-B equals A-vs-A."""
    r = scored(s, tmp_path, full(s))
    for name in ("claim_content", "uncertainty_content", "abstract_content", "highlights_content"):
        ep = r["endpoints"][name]
        assert ep["estimate"] == pytest.approx(0.0) and ep["units"] == 27 and ep["n"] == 27, name


def test_thinking_adherence_is_reported_not_judged(s, tmp_path):
    atts = full(s)
    for k, att in enumerate(atts):
        att["arms"]["B"]["tap"][0]["thoughts_tokens"] = 1400 if k % 4 == 0 else 900   # 21 of 81 over 1280
    r = scored(s, tmp_path, atts)
    assert r["thinking"]["b_over_budget"] == 21 and r["thinking"]["b_over_budget_share"] == pytest.approx(21 / 81)
    assert r["thinking"]["label"].startswith("REPORT_ONLY") and r["verdict"]["label"] == "PASS"


def test_slower_b_is_not_material(s, tmp_path):
    r = scored(s, tmp_path, full(s, lat=lambda i, p, a, rng: a + 1500 + rng.gauss(0, 300)))
    assert r["latency"]["mean_improvement_ms"] < 0 and r["verdict"]["label"] == "NOT_MATERIAL"
