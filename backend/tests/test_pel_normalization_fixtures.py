"""ION PEL Phase-2B.1R3 final clarified historical fixture conformance
tests.

Runs the frozen, final-clarified `ION_PEL_SINGLE_TARGET_DEFECT_ADMISSION_V0_2_2`
parser against the twelve preserved Runs 14-16 raw checker outputs
(`ION_PEL_PHASE2B0F_FROZEN_SOURCE_FIXTURE_PACK_v0.1`, MANIFEST.json SHA-256
d44468bf8172e2dba403868d686e6e2775fd8c6598be6d10c7a1b2afdc4c2750) and checks
them against the mandate's minimum expected matrix. This is parser
conformance testing against a frozen grammar, not semantic-correctness
testing: the fixture pack deliberately contains no gold normalized-output
file, and none is read here.

Per mandate section 6 (the historical fixture pack, raw bytes, MANIFEST.json,
FIXTURE_BINDINGS.json, is NOT rewritten for v0.2.2 -- it remains labeled
`ION_PEL_SINGLE_TARGET_DEFECT_ADMISSION_V0_1` and is left byte-identical).
These tests reuse only the raw fixture bytes and the historical `focus_key`
from the expectation matrix below, and invoke the parser explicitly with the
current (v0.2.2) `OUTPUT_CONTRACT_ID` constant -- the fixture pack's own
v0.1-labeled `output_contract_id` field is never read here.

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
Fixture file I/O belongs only in tests -- the production parser reads
nothing from disk itself.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pel.normalization import normalize_single_target_checker_output
from pel.normalization_contract import OUTPUT_CONTRACT_ID
from pel.normalization_models import NormalizedJudgmentV0_2_2
from pel.validation import validate_normalized_judgment_v0_2_2

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "pel_phase2b0f"
RAW_DIR = FIXTURE_ROOT / "raw"

MANIFEST_SHA256 = "d44468bf8172e2dba403868d686e6e2775fd8c6598be6d10c7a1b2afdc4c2750"

EXPECTED = {
    "ION_PEL_RUN14_CLAUDE_R1_RAW_v0.1.txt": dict(
        focus_key="X26_READ", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="NONE", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN14_CLAUDE_R2_RAW_v0.1.txt": dict(
        focus_key="X26_READ", primary_verdict="NO", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="PRESENT", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN14_CLAUDE_R3_RAW_v0.1.txt": dict(
        focus_key="X26_READ", primary_verdict="NO", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="PRESENT", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN15_GEMINI_G1_RAW_v0.1.txt": dict(
        focus_key="X26_READ", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="NONE", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN15_GEMINI_G2_RAW_v0.1.txt": dict(
        focus_key="X26_READ", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="NONE", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN15_GEMINI_G3_RAW_v0.1.txt": dict(
        focus_key="X26_READ", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="NONE", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN16_CLAUDE_C1_RAW_v0.1.txt": dict(
        focus_key="A107_DIRECTION", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="PRESENT", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN16_CLAUDE_C2_RAW_v0.1.txt": dict(
        focus_key="A107_DIRECTION", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="PRESENT", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN16_CLAUDE_C3_RAW_v0.1.txt": dict(
        focus_key="A107_DIRECTION", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="PRESENT", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN16_GEMINI_G1_RAW_v0.1.txt": dict(
        focus_key="A107_DIRECTION", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="NONE", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN16_GEMINI_G2_RAW_v0.1.txt": dict(
        focus_key="A107_DIRECTION", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="PRESENT", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
    "ION_PEL_RUN16_GEMINI_G3_RAW_v0.1.txt": dict(
        focus_key="A107_DIRECTION", primary_verdict="YES", noticed=True,
        declined_as_borderline=False, confidence="HIGH",
        other_findings_state="NONE", final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
    ),
}


def _manifest() -> dict:
    return json.loads((FIXTURE_ROOT / "MANIFEST.json").read_text(encoding="utf-8"))


def _manifest_entry(filename: str) -> dict:
    for entry in _manifest()["files"]:
        if entry["filename"] == filename:
            return entry
    raise AssertionError(f"{filename} not present in MANIFEST.json")


def _normalize(filename: str) -> tuple[NormalizedJudgmentV0_2_2, dict]:
    raw_bytes = (RAW_DIR / filename).read_bytes()
    entry = _manifest_entry(filename)
    expected = EXPECTED[filename]
    result = normalize_single_target_checker_output(
        raw_bytes=raw_bytes,
        run_id=f"fixture-{filename}",
        evidence_id=f"fixture-evidence-{filename}",
        source_raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        output_contract_id=OUTPUT_CONTRACT_ID,
        focus_key=expected["focus_key"],
        normalized_at="2026-08-15T00:00:00+00:00",
    )
    return result, entry


def _assert_matches_manifest(filename: str) -> None:
    raw_bytes = (RAW_DIR / filename).read_bytes()
    entry = _manifest_entry(filename)
    assert len(raw_bytes) == entry["bytes"], (
        f"{filename}: byte count {len(raw_bytes)} != manifest {entry['bytes']}"
    )
    assert hashlib.sha256(raw_bytes).hexdigest() == entry["sha256"], (
        f"{filename}: SHA-256 does not match MANIFEST.json"
    )


def _assert_matches_expected(filename: str) -> None:
    result, _entry = _normalize(filename)
    expected = EXPECTED[filename]
    assert result.parse_status == expected["parse_status"], (
        f"{filename}: parse_status={result.parse_status!r}, "
        f"diagnostics={[d.to_dict() for d in result.diagnostics]}"
    )
    assert result.primary_verdict == expected["primary_verdict"], filename
    assert result.noticed == expected["noticed"], filename
    assert result.declined_as_borderline == expected["declined_as_borderline"], filename
    assert result.confidence == expected["confidence"], filename
    assert result.other_findings_state == expected["other_findings_state"], filename
    assert result.final_result == expected["final_result"], filename
    validate_normalized_judgment_v0_2_2(result.to_dict())


# --------------------------------------------------------------------------- #
# fixture-pack identity
# --------------------------------------------------------------------------- #

def test_manifest_sha256_matches_frozen_value():
    manifest_bytes = (FIXTURE_ROOT / "MANIFEST.json").read_bytes()
    assert hashlib.sha256(manifest_bytes).hexdigest() == MANIFEST_SHA256


def test_all_twelve_fixtures_present_in_manifest():
    assert len(_manifest()["files"]) == 12
    assert set(EXPECTED) == {e["filename"] for e in _manifest()["files"]}


def test_twelve_of_twelve_fixture_source_sha256_match_manifest():
    for filename in EXPECTED:
        _assert_matches_manifest(filename)


# --------------------------------------------------------------------------- #
# per-fixture conformance (mandate section 31 minimum expected matrix)
# --------------------------------------------------------------------------- #

def test_run14_claude_r1():
    _assert_matches_expected("ION_PEL_RUN14_CLAUDE_R1_RAW_v0.1.txt")


def test_run14_claude_r2():
    _assert_matches_expected("ION_PEL_RUN14_CLAUDE_R2_RAW_v0.1.txt")


def test_run14_claude_r3_markdown_table_form():
    _assert_matches_expected("ION_PEL_RUN14_CLAUDE_R3_RAW_v0.1.txt")


def test_run15_gemini_g1_compact_inline_form():
    _assert_matches_expected("ION_PEL_RUN15_GEMINI_G1_RAW_v0.1.txt")


def test_run15_gemini_g2_compact_inline_form():
    _assert_matches_expected("ION_PEL_RUN15_GEMINI_G2_RAW_v0.1.txt")


def test_run15_gemini_g3_compact_inline_form():
    _assert_matches_expected("ION_PEL_RUN15_GEMINI_G3_RAW_v0.1.txt")


def test_run16_claude_c1():
    _assert_matches_expected("ION_PEL_RUN16_CLAUDE_C1_RAW_v0.1.txt")


def test_run16_claude_c2():
    _assert_matches_expected("ION_PEL_RUN16_CLAUDE_C2_RAW_v0.1.txt")


def test_run16_claude_c3():
    _assert_matches_expected("ION_PEL_RUN16_CLAUDE_C3_RAW_v0.1.txt")


def test_run16_gemini_g1():
    _assert_matches_expected("ION_PEL_RUN16_GEMINI_G1_RAW_v0.1.txt")


def test_run16_gemini_g2():
    _assert_matches_expected("ION_PEL_RUN16_GEMINI_G2_RAW_v0.1.txt")


def test_run16_gemini_g3():
    _assert_matches_expected("ION_PEL_RUN16_GEMINI_G3_RAW_v0.1.txt")


# --------------------------------------------------------------------------- #
# aggregate: twelve of twelve parse_status = PARSED
# --------------------------------------------------------------------------- #

def test_twelve_of_twelve_parse_status_parsed():
    statuses = {}
    for filename in EXPECTED:
        result, _entry = _normalize(filename)
        statuses[filename] = result.parse_status
    failures = {f: s for f, s in statuses.items() if s != "PARSED"}
    assert not failures, f"non-PARSED fixtures: {failures}"


def test_byte_trace_verification_across_all_fixtures():
    """Every non-null field-trace span's source_excerpt_sha256 must equal
    SHA-256 of that exact raw byte slice, for every one of the 12 fixtures."""
    for filename in EXPECTED:
        raw_bytes = (RAW_DIR / filename).read_bytes()
        result, _entry = _normalize(filename)
        for trace in result.field_traces:
            if trace.start_byte is None:
                continue
            excerpt = raw_bytes[trace.start_byte:trace.end_byte]
            assert hashlib.sha256(excerpt).hexdigest() == trace.source_excerpt_sha256, (
                f"{filename}: {trace.field_name} excerpt hash mismatch"
            )


def test_determinism_across_all_fixtures():
    for filename in EXPECTED:
        first, _entry = _normalize(filename)
        second, _entry2 = _normalize(filename)
        assert first == second, filename
