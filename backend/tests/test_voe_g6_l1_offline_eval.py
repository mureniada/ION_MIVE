"""VOE G6 L1 offline evaluator: fixtures, isolation, hashing, detectors,
verdict law and evidence record.

Every test that composes runs under `netguard`'s `guarded` decorator: cloud
SDK imports and outbound sockets are denied for its whole duration. No test
reads a real credential; the secret-isolation test plants a dummy sentinel.
"""

from __future__ import annotations

import ast
import copy
import functools
import json
from pathlib import Path

import pytest

from app.modules.response_composer import VOEResponseComposer
from scripts import voe_g6_l1_offline_eval as ev
from tests.netguard import guarded

EVALUATOR_SOURCE = Path(ev.__file__).read_text(encoding="utf-8")

# Pins the approved canonical fixture set: any change to fixture wording,
# numbers or review metadata changes this value and must stop for approval.
APPROVED_FIXTURE_SET_SHA256 = "16faa8e94d8e9b5498c2d85cb23fbf77fdd051f0493ed921313aadeedb80e9f0"

SECRET_SENTINEL_NAME = "G6_TEST_SECRET_SENTINEL"
SECRET_SENTINEL_VALUE = "g6-dummy-sentinel-NOT-A-CREDENTIAL-7Q2X"


@functools.lru_cache(maxsize=1)
def _profile():
    return ev.committed_voe_profile()


def _fixture_doc():
    return ev.load_fixture_set()


def _cases():
    return {c["case_id"]: c for c in _fixture_doc()["cases"]}


def _seeds():
    return ev.load_seed_set()["seeds"]


_KNOWN_GOOD = [s for s in _seeds() if s["kind"] == "known_good"]
_KNOWN_BAD = [s for s in _seeds() if s["kind"] == "known_bad"]


def _evaluate(seed):
    return ev.evaluate_case(_cases()[seed["case_id"]], seed["composed_text"], _profile(),
                            seed_id=seed["seed_id"], seed_kind=seed["kind"])


def _compose_capturing(case, text="A composed answer."):
    backend = ev.ScriptedComposerBackend(text)
    composer = VOEResponseComposer(backend, provider=ev.SCRIPTED_PROVIDER, requested_model=ev.SCRIPTED_MODEL)
    composer.compose(ev.build_composer_input(case, _profile()))
    return backend


# --------------------------------------------------------------------- #
# fixture validity
# --------------------------------------------------------------------- #
def test_fixture_set_is_the_approved_twelve_cases():
    doc = _fixture_doc()
    assert doc["fixture_schema_id"] == "ION_VOE_G6_FIXTURE_V0_1"
    assert [c["case_id"] for c in doc["cases"]] == [f"G6-{i:02d}" for i in range(1, 13)]


def test_fixture_set_hash_is_pinned_to_the_approved_wording():
    assert ev.sha256_obj(_fixture_doc()) == APPROVED_FIXTURE_SET_SHA256


def test_rule_catalogue_is_the_approved_eighteen_rules():
    assert list(ev.RULES) == [f"A{i}" for i in range(1, 7)] + [f"B{i}" for i in range(1, 9)] + [f"C{i}" for i in range(1, 5)]
    tiers = [spec["tier"] for spec in ev.RULES.values()]
    assert (tiers.count("A"), tiers.count("B"), tiers.count("C")) == (6, 8, 4)
    assert [r for r in ev.RULES if ev.is_blocking(r)] == [r for r in ev.RULES if r[0] in "AB"]


def test_every_detector_maps_only_to_catalogued_rules():
    for rules in ev.DETECTOR_RULES.values():
        assert set(rules) <= set(ev.RULES)


def _mutations():
    def extra_input_key(c): c["composer_input"]["claim_ids"] = ["C1"]
    def extra_claim_key(c): c["composer_input"]["report_claims"][0]["claim_id"] = "C1"
    def uncertainty_not_string(c): c["composer_input"]["report_uncertainty"].append({"text": "x"})
    def confidence_out_of_range(c): c["composer_input"]["report_claims"][0]["confidence"] = 1.5
    def confidence_is_bool(c): c["composer_input"]["report_confidence"] = True
    def response_depth_set(c): c["composer_input"]["response_depth"] = "DEEP"
    def claim_ids_length_mismatch(c): c["review_meta"]["claim_ids"].append("C9")
    def uncertainty_links_mismatch(c): c["review_meta"]["uncertainty_links"].pop()
    def unknown_qualifies_id(c): c["review_meta"]["uncertainty_links"][0]["qualifies_claim_ids"] = ["C9"]
    def unknown_rule_id(c): c["review_meta"]["rules_under_test"]["primary"].append("D1")
    def missing_review_meta_key(c): del c["review_meta"]["expected_invariants"]
    def extra_case_key(c): c["notes"] = "x"
    return [extra_input_key, extra_claim_key, uncertainty_not_string, confidence_out_of_range,
            confidence_is_bool, response_depth_set, claim_ids_length_mismatch,
            uncertainty_links_mismatch, unknown_qualifies_id, unknown_rule_id,
            missing_review_meta_key, extra_case_key]


@pytest.mark.parametrize("mutate", _mutations(), ids=lambda f: f.__name__)
def test_invalid_fixture_is_rejected(mutate):
    case = copy.deepcopy(_cases()["G6-02"])
    mutate(case)
    with pytest.raises(ev.FixtureError):
        ev.validate_fixture(case)


def test_duplicate_case_id_is_rejected():
    doc = copy.deepcopy(_fixture_doc())
    doc["cases"][1]["case_id"] = "G6-01"
    with pytest.raises(ev.FixtureError):
        ev.validate_fixture_set(doc)


# --------------------------------------------------------------------- #
# review_meta isolation
# --------------------------------------------------------------------- #
@guarded
def test_composer_input_is_built_from_composer_input_only():
    for case in _cases().values():
        altered = copy.deepcopy(case)
        altered["review_meta"] = {"anything": "else entirely"}
        assert ev.build_composer_input(altered, _profile()) == ev.build_composer_input(case, _profile())


@guarded
def test_sent_payload_is_exactly_the_composer_input_projection_for_every_fixture():
    for case in _cases().values():
        backend = _compose_capturing(case)
        checks = ev.review_meta_isolation_checks(case, backend.received_user)
        assert all(checks.values()), (case["case_id"], checks)
        assert json.loads(backend.received_user) == ev.expected_payload_projection(case["composer_input"])


@guarded
def test_planted_review_meta_marker_never_reaches_the_payload():
    marker = "G6-REVIEW-META-ONLY-MARKER-5d1c"
    for case in _cases().values():
        planted = copy.deepcopy(case)
        planted["review_meta"]["category"] = marker
        planted["review_meta"]["expected_invariants"].append(marker)
        planted["review_meta"]["claim_ids"][0] = marker
        backend = _compose_capturing(planted)
        assert marker not in backend.received_user
        assert marker not in backend.received_system
        assert all(ev.review_meta_isolation_checks(planted, backend.received_user).values())


def test_isolation_check_detects_a_leak():
    case = _cases()["G6-10"]
    payload = json.loads(ev.build_composer_user_payload(ev.build_composer_input(case, _profile())))
    payload["claims"][0]["claim_id"] = "C1"
    payload["uncertainty"].append(case["review_meta"]["expected_invariants"][0])
    checks = ev.review_meta_isolation_checks(case, json.dumps(payload, ensure_ascii=False))
    assert not checks["payload_equals_composer_input_projection"]
    assert not checks["payload_claim_keys_exact"]
    assert not checks["no_review_meta_string_in_payload"]


# --------------------------------------------------------------------- #
# deterministic hashing
# --------------------------------------------------------------------- #
def test_hashing_is_independent_of_key_order_and_line_endings():
    case = _cases()["G6-04"]
    reordered = json.loads(json.dumps(case, sort_keys=False))
    reordered = {k: reordered[k] for k in reversed(list(reordered))}
    assert ev.sha256_obj(reordered) == ev.sha256_obj(case)
    crlf_text = ev.FIXTURES_PATH.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
    assert ev.sha256_obj(json.loads(crlf_text)) == APPROVED_FIXTURE_SET_SHA256


@guarded
def test_system_instruction_hash_is_the_known_production_value():
    backend = _compose_capturing(_cases()["G6-01"])
    assert ev.sha256_text(backend.received_system) == ev.EXPECTED_SYSTEM_INSTRUCTION_SHA256


@guarded
def test_calibration_record_is_byte_identical_across_runs():
    first = ev.canonical_json(ev.calibrate(_fixture_doc(), ev.load_seed_set(), _profile()))
    second = ev.canonical_json(ev.calibrate(_fixture_doc(), ev.load_seed_set(), _profile()))
    assert first == second


# --------------------------------------------------------------------- #
# detectors: true positives on known-bad, false positives on known-good
# --------------------------------------------------------------------- #
@guarded
@pytest.mark.parametrize("seed", _KNOWN_BAD, ids=lambda s: s["seed_id"])
def test_known_bad_seed_triggers_its_target_detector(seed):
    record = _evaluate(seed)
    assert any(
        f["detector"] == seed["target_detector"]
        and seed["target_rule"] in f["rules"]
        and (seed["target_detail"] is None or f["detail"] == seed["target_detail"])
        for f in record["flags"]
    ), record["flags"]


@guarded
@pytest.mark.parametrize("seed", _KNOWN_GOOD, ids=lambda s: s["seed_id"])
def test_known_good_seed_raises_no_blocking_flag(seed):
    record = _evaluate(seed)
    blocking = [f for f in record["flags"] if any(ev.is_blocking(r) for r in f["rules"])]
    assert blocking == []
    assert record["tier_c_advisory"] == sorted(seed["expected_tier_c_detectors"])
    assert record["outcome"] == ev.OUTCOME_PENDING
    assert all(record["structural_checks"].values())


def test_every_detector_has_a_known_bad_seed():
    assert {s["target_detector"] for s in _KNOWN_BAD} == set(ev.DETECTOR_RULES)


@guarded
def test_calibration_summary_is_clean():
    cal = ev.calibrate(_fixture_doc(), ev.load_seed_set(), _profile())["calibration"]
    assert cal["known_bad_false_negatives"] == []
    assert cal["known_good_false_positives"] == []
    assert cal["known_good_tier_c_mismatches"] == []
    assert cal["authoritative_outcome_mismatches"] == []
    assert cal["all_structural_checks_passed"] is True
    assert len(cal["known_bad_true_positives"]) == len(_KNOWN_BAD)


# --------------------------------------------------------------------- #
# verdict law
# --------------------------------------------------------------------- #
@guarded
@pytest.mark.parametrize("seed_id", ["BAD-CITE-URL", "BAD-CITE-DOI", "BAD-CITE-BRACKET-WITH-REFERENCE"])
def test_new_url_doi_or_referenced_bracket_is_an_authoritative_a5_fail(seed_id):
    record = _evaluate(next(s for s in _KNOWN_BAD if s["seed_id"] == seed_id))
    assert record["rule_verdicts"]["A5"]["verdict"] == ev.VERDICT_FAIL
    assert record["rule_verdicts"]["A5"]["decided_by"] == "AUTOMATION"
    assert record["outcome"] == ev.OUTCOME_AUTOMATED_FAIL


@guarded
@pytest.mark.parametrize("seed_id", ["BAD-CITE-BRACKET-BARE", "BAD-CITE-AUTHOR-YEAR", "BAD-CITE-PHRASE"])
def test_other_citation_forms_are_flags_not_verdicts(seed_id):
    record = _evaluate(next(s for s in _KNOWN_BAD if s["seed_id"] == seed_id))
    assert record["rule_verdicts"]["A5"]["verdict"] == ev.VERDICT_UNKNOWN
    assert record["outcome"] == ev.OUTCOME_PENDING


def test_url_already_in_the_input_is_not_flagged():
    case = copy.deepcopy(_cases()["G6-12"])
    case["composer_input"]["report_abstract"] += " See https://example.org/admitted."
    flags = ev.detect_citations("Details: https://example.org/admitted.", case["composer_input"])
    assert flags == []


@guarded
def test_tier_c_violations_stay_advisory():
    for seed in (s for s in _KNOWN_BAD if s["target_rule"].startswith("C")):
        record = _evaluate(seed)
        verdict = record["rule_verdicts"][seed["target_rule"]]
        assert verdict["blocking"] is False
        assert verdict["verdict"] == ev.VERDICT_UNKNOWN
        assert record["outcome"] == ev.OUTCOME_PENDING
    forced = ev.rule_verdicts([ev._flag("D-METAPHOR", ["C3"], "like a", authoritative=True)])
    assert forced["C3"]["verdict"] == ev.VERDICT_UNKNOWN
    assert ev.case_outcome({"ok": True}, forced) == ev.OUTCOME_PENDING


@guarded
def test_automation_never_grants_pass_and_l1_never_grants_g6():
    record = ev.calibrate(_fixture_doc(), ev.load_seed_set(), _profile())
    assert record["g6_overall"] == "NOT_GRANTED_L1_ONLY"
    for result in record["results"]:
        assert all(v["verdict"] != ev.VERDICT_PASS for v in result["rule_verdicts"].values())
        assert result["outcome"] in {ev.OUTCOME_PENDING, ev.OUTCOME_AUTOMATED_FAIL}
        assert result["human_review"]["status"] == "PENDING"


def test_structural_failure_is_an_automated_fail():
    verdicts = ev.rule_verdicts([])
    assert ev.case_outcome({"payload_equals_composer_input_projection": False}, verdicts) == ev.OUTCOME_AUTOMATED_FAIL


# --------------------------------------------------------------------- #
# B1: FAIL versus FLAG
# --------------------------------------------------------------------- #
def test_b1_disposition_follows_the_approved_semantics():
    d = ev.b1_disposition
    assert d(carried=True, qualifies_claim_ids=["C1"], asserted_claim_ids={"C1"}) == ev.VERDICT_PASS
    assert d(carried=False, qualifies_claim_ids=["C1"], asserted_claim_ids={"C1"}) == ev.VERDICT_FAIL
    assert d(carried=True, weakened=True, qualifies_claim_ids=["C1"], asserted_claim_ids={"C1"}) == ev.VERDICT_FAIL
    assert d(carried=False, qualifies_claim_ids=["C1"], asserted_claim_ids={"C2"}) == ev.VERDICT_FLAG
    assert d(carried=False, qualifies_claim_ids=[], asserted_claim_ids={"C1", "C2"}) == ev.VERDICT_FLAG


@guarded
def test_b1_branch_is_fail_for_qualifying_and_flag_for_non_qualifying_items():
    fail_record = _evaluate(next(s for s in _KNOWN_BAD if s["seed_id"] == "BAD-UNC-FAIL-BRANCH"))
    flag_record = _evaluate(next(s for s in _KNOWN_BAD if s["seed_id"] == "BAD-UNC-FLAG-BRANCH"))
    assert {u["b1_branch_if_omitted"] for u in fail_record["uncertainty_ledger"] if u["auto_status"] == "NOT_DETECTED"} == {"FAIL_BRANCH"}
    assert [u["b1_branch_if_omitted"] for u in flag_record["uncertainty_ledger"]] == ["FLAG_BRANCH"]
    assert flag_record["uncertainty_ledger"][0]["auto_status"] == "NOT_DETECTED"
    # Human review decides B1: automation leaves it UNKNOWN on both branches.
    assert fail_record["rule_verdicts"]["B1"]["verdict"] == ev.VERDICT_UNKNOWN
    assert flag_record["rule_verdicts"]["B1"]["verdict"] == ev.VERDICT_UNKNOWN


# --------------------------------------------------------------------- #
# evidence record serialization
# --------------------------------------------------------------------- #
@guarded
def test_evidence_record_round_trips_and_carries_the_required_fields(tmp_path, capsys):
    out = tmp_path / "g6_l1_record.json"
    assert ev.main(["--out", str(out)]) == 0
    written = out.read_text(encoding="utf-8")
    record = json.loads(written)
    assert written == ev.canonical_json(record) + "\n"
    assert record["record_schema_id"] == "ION_VOE_G6_L1_RECORD_V0_1"
    assert record["layer"] == "L1"
    assert record["fixture_set_sha256"] == APPROVED_FIXTURE_SET_SHA256
    assert len(record["results"]) == len(_seeds())
    required = {"case_id", "seed_id", "seed_kind", "hashes", "base", "review_meta", "composed_text",
                "structural_checks", "flags", "claim_ledger", "uncertainty_ledger", "rule_verdicts",
                "tier_c_advisory", "outcome", "human_review"}
    for result in record["results"]:
        assert set(result) == required
        assert set(result["hashes"]) == {"fixture_sha256", "composer_input_sha256", "user_payload_sha256",
                                         "system_instruction_sha256", "composed_text_sha256"}
        assert set(result["rule_verdicts"]) == set(ev.RULES)
    assert json.loads(capsys.readouterr().out)["g6_overall"] == "NOT_GRANTED_L1_ONLY"


# --------------------------------------------------------------------- #
# secret isolation (planted dummy sentinel only)
# --------------------------------------------------------------------- #
@guarded
def test_planted_secret_sentinel_never_enters_payload_or_record(monkeypatch, tmp_path):
    monkeypatch.setenv(SECRET_SENTINEL_NAME, SECRET_SENTINEL_VALUE)
    for case in _cases().values():
        backend = _compose_capturing(case)
        assert SECRET_SENTINEL_VALUE not in backend.received_user
        assert SECRET_SENTINEL_VALUE not in backend.received_system
    out = tmp_path / "record.json"
    assert ev.main(["--out", str(out)]) == 0
    serialized = out.read_text(encoding="utf-8")
    assert SECRET_SENTINEL_VALUE not in serialized
    assert SECRET_SENTINEL_NAME not in serialized


def test_evaluator_never_reads_the_process_environment():
    imported = _imported_module_names(EVALUATOR_SOURCE)
    assert "os" not in imported
    attributes = {n.attr for n in ast.walk(ast.parse(EVALUATOR_SOURCE)) if isinstance(n, ast.Attribute)}
    assert not attributes & {"environ", "getenv", "putenv"}


# --------------------------------------------------------------------- #
# static isolation: no network or provider module
# --------------------------------------------------------------------- #
_FORBIDDEN_IMPORT_PREFIXES = (
    "app.container", "app.modules.gemini_ive", "app.modules.openai_ive", "app.modules.model_gateway",
    "qdrant_client", "openai", "google", "anthropic", "socket", "http", "urllib", "requests", "httpx",
    "subprocess",
)


def _imported_module_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_evaluator_imports_no_network_or_provider_module():
    for name in _imported_module_names(EVALUATOR_SOURCE):
        assert not any(name == p or name.startswith(p + ".") for p in _FORBIDDEN_IMPORT_PREFIXES), name


def test_seed_file_is_marked_as_calibration_material_not_fixtures():
    doc = ev.load_seed_set()
    assert "NOT canonical G6 fixtures" in doc["note"]
    assert {s["case_id"] for s in doc["seeds"]} <= set(_cases())
    assert {s["case_id"] for s in _KNOWN_GOOD} == set(_cases())
