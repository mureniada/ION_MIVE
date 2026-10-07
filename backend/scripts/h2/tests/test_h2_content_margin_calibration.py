"""Offline tests for h2_content_margin_calibration.py. ZERO provider calls.

    python -m pytest -q -p no:cacheprovider scripts/h2/tests/test_h2_content_margin_calibration.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import sys
import uuid

import pytest

H2_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIB_PATH = os.path.join(H2_DIR, "h2_content_margin_calibration.py")
SCORER_PATH = os.path.join(H2_DIR, "h2_ab_score.py")
WORDS = ("money credit trust ledger state market debt value exchange bank tax coin gold labour "
         "price wage rent bond loan risk").split()


@pytest.fixture
def c():
    name = f"h2cal_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(name, CALIB_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def report(rng, i, noise):
    def text(n, salt):
        base = [WORDS[(i * 7 + salt + k) % len(WORDS)] for k in range(n)]
        return " ".join(w if rng.random() >= noise else rng.choice(WORDS) + str(rng.randrange(50)) for w in base)

    return {"abstract": text(30, 0), "highlights": [text(8, 10 + h) for h in range(4)],
            "claims": [{"claim_id": f"c{k}", "statement": text(12, 20 + k), "evidence_document_ids": ["E1"],
                        "confidence": 0.8} for k in range(5)],
            "uncertainty": [text(10, 40 + u) for u in range(2)], "relations": [], "concepts": [], "confidence": 0.9}


def write_reports(path, noise, per_q=8, seed=3, questions=27):
    rng = random.Random(seed)
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(questions):
            for _ in range(per_q if i else per_q - 1):          # one question has 7, as in the stored set
                fh.write(json.dumps({"index": i, "report": report(rng, i, noise)}) + "\n")
    return str(path)


def run(c, tmp_path, noise, sims=60, boot=300, **kw):
    reports = write_reports(tmp_path / f"r{uuid.uuid4().hex[:6]}.jsonl", noise, **kw)
    out = tmp_path / f"o{uuid.uuid4().hex[:6]}.json"
    rc = c.main([SCORER_PATH, reports, str(out), str(sims), str(boot)])
    return rc, (json.load(open(out, encoding="utf-8")) if rc == 0 else None), out


def test_identical_reports_need_the_smallest_margin(c, tmp_path):
    rc, r, _ = run(c, tmp_path, noise=0.0)
    assert rc == 0
    for name in c.ENDPOINTS:
        ep = r["endpoints"][name]
        assert ep["null_estimate"]["mean"] == 0.0 and ep["null_lower_bound"]["0.05"] == 0.0
        assert ep["recommended_margin"] == 0.005 and ep["same_question_similarity_mean"] == 1.0


def test_noisy_reports_give_a_positive_calibrated_margin(c, tmp_path):
    rc, r, out = run(c, tmp_path, noise=0.35)
    assert rc == 0 and r["design"]["pairs"] == 81 and r["inputs"]["reports"] == 215
    for name in c.ENDPOINTS:
        ep = r["endpoints"][name]
        m = ep["recommended_margin"]
        assert m is not None and 0.005 < m < 0.3, name
        assert ep["unchanged_pass_rate_at_recommended"] >= 0.95
        assert ep["unchanged_pass_rate"][f"{m - 0.005:.3f}"] < 0.95       # the smallest such margin
        assert abs(ep["null_estimate"]["mean"]) < 0.02                     # unbiased under the null
        assert ep["degradation_detected_50"] < ep["degradation_detected_90"]
    with pytest.raises(FileExistsError):                                    # never overwrites
        c.main([SCORER_PATH, write_reports(tmp_path / "x.jsonl", 0.35), str(out), "5", "50"])


def test_draws_use_six_distinct_reports_and_the_scorer_function(c, tmp_path, monkeypatch):
    scorer = c.load_scorer(SCORER_PATH)
    by_q = c.load_reports(scorer, write_reports(tmp_path / "r.jsonl", 0.2))
    tables = c.similarity_tables(scorer, by_q)
    seen = []
    real = scorer.content_clusters

    def spy(pairs, sim):
        for i in {k[1] for k in pairs}:
            ids = [pairs[(p, i)][arm][1] for arm in (0, 1) for p in (1, 2, 3)]
            seen.append(len(set(ids)) == 6)
        return real(pairs, sim)

    monkeypatch.setattr(scorer, "content_clusters", spy)
    c.simulate(scorer, tables, by_q, 3, 50)
    assert seen and all(seen)


def test_too_few_reports_is_refused(c, tmp_path, capsys):
    rc, r, _ = run(c, tmp_path, noise=0.2, per_q=5)
    assert rc == 2 and r is None and "need 27 questions" in capsys.readouterr().out
