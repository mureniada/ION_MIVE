"""ION PEL Phase-2B.1R3 final clarified synthetic/countercase parser tests,
plus the Phase-2B.1 source/capability boundary check.

Covers the frozen `ION_PEL_SINGLE_TARGET_DEFECT_ADMISSION_V0_2_2` contract
(`ION_PEL_PHASE2B0_2_HARDENED_OUTPUT_CONTRACT_FREEZE_v0.2.md`, the
clarification successor
`ION_PEL_PHASE2B0_3_CONTRACT_CLARIFICATION_FREEZE_v0.2.1.md`, and the final
positional clarification
`ION_PEL_PHASE2B0_4_UNKNOWN_ASSIGNMENT_POSITION_CLARIFICATION_FREEZE_v0.2.2.md`),
its retained H1-H12 and C21-01..C21-10 countercase matrices, and its new
C22-01..C22-10 unknown-assignment-position countercase matrix: every
countercase must never reach `parse_status=PARSED` on a structurally
non-unique document, an inexact closed-enum token, a mid-sentence/quoted
unknown-assignment silently promoted to a structural boundary, or a
dash-only free-text value ("no FALSE PARSED").

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
All raw inputs here are synthetic, hand-authored text -- not fixture files
and not expected-output data derived from the fixture pack.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from pel.normalization import (
    _b_role_candidates,
    _classify_b_sequences,
    _enumerate_b_sequences,
    _find_field_candidates,
    _uap1_standalone_positions,
    _uap2_table_row_positions,
    normalize_single_target_checker_output,
)
from pel.normalization_contract import OUTPUT_CONTRACT_ID

PEL_DIR = Path(__file__).resolve().parents[1] / "pel"
NORMALIZATION_FILES = ("normalization.py", "normalization_contract.py", "normalization_models.py")

FORBIDDEN_IMPORT_ROOTS = {
    "app", "t4", "requests", "httpx", "socket", "openai", "anthropic", "google",
}
FORBIDDEN_SYMBOL_NAMES = {
    "NormalizedJudgment", "StabilitySummary", "CrossModelComparison", "GoldEvaluator",
}
FORBIDDEN_FIELD_OR_ATTR_NAMES = {
    "gold_evaluator", "stability_analyzer", "cross_model_comparator",
    "majority_vote", "semantic_admission", "action_right", "winner_model",
}


def _doc(
    *,
    focus_key="X26_READ",
    primary="YES",
    noticed="YES",
    declined="NO",
    defect="NONE",
    defect_label="DEFECT_DESCRIPTION_OR_NONE",
    rule_basis="R1",
    confidence="HIGH",
    other="NONE",
    final="MATERIAL_DEFECT_FOUND",
    preamble="",
    extra_b_field="",
) -> bytes:
    return (
        f"{preamble}"
        f"A. PRIMARY CLASSIFICATION\n\n"
        f"{focus_key}_DEFECT_ADMITTED = {primary}\n\n"
        f"B. PRIMARY ANALYSIS\n\n"
        f"{focus_key}_NOTICED = {noticed}\n"
        f"DECLINED_AS_BORDERLINE = {declined}\n"
        f"{defect_label} = {defect}\n"
        f"RULE_BASIS = {rule_basis}\n"
        f"CONFIDENCE = {confidence}\n"
        f"{extra_b_field}"
        f"\nC. OTHER MATERIAL FINDINGS\n\n"
        f"{other}\n\n"
        f"D. FINAL RESULT\n\n"
        f"{final}\n"
    ).encode("utf-8")


def _parse(raw_bytes: bytes, *, focus_key="X26_READ", output_contract_id=None,
           source_raw_sha256=None, run_id="run-1", evidence_id="ev-1"):
    return normalize_single_target_checker_output(
        raw_bytes=raw_bytes,
        run_id=run_id,
        evidence_id=evidence_id,
        source_raw_sha256=source_raw_sha256 or hashlib.sha256(raw_bytes).hexdigest(),
        output_contract_id=output_contract_id or OUTPUT_CONTRACT_ID,
        focus_key=focus_key,
        normalized_at="2026-08-15T00:00:00+00:00",
    )


# --------------------------------------------------------------------------- #
# UTF-8 boundary
# --------------------------------------------------------------------------- #

def test_strict_utf8_valid_parse():
    result = _parse(_doc())
    assert result.parse_status == "PARSED"


def test_invalid_utf8_is_unparseable():
    raw = b"A. PRIMARY CLASSIFICATION\n\xff\xfe not valid utf-8"
    result = _parse(raw, source_raw_sha256=hashlib.sha256(raw).hexdigest())
    assert result.parse_status == "UNPARSEABLE"
    assert [d.code for d in result.diagnostics] == ["INVALID_UTF8"]


# --------------------------------------------------------------------------- #
# trusted source identity
# --------------------------------------------------------------------------- #

def test_source_sha_match_parses():
    raw = _doc()
    result = _parse(raw, source_raw_sha256=hashlib.sha256(raw).hexdigest())
    assert result.parse_status == "PARSED"


def test_source_sha_mismatch_is_unparseable():
    raw = _doc()
    result = _parse(raw, source_raw_sha256="a" * 64)
    assert result.parse_status == "UNPARSEABLE"
    assert [d.code for d in result.diagnostics] == ["SOURCE_EVIDENCE_MISMATCH"]
    assert result.primary_verdict is None


# --------------------------------------------------------------------------- #
# output contract selection
# --------------------------------------------------------------------------- #

def test_supported_contract_parses():
    result = _parse(_doc(), output_contract_id=OUTPUT_CONTRACT_ID)
    assert result.parse_status == "PARSED"


def test_unsupported_contract_is_unparseable():
    raw = _doc()
    result = _parse(raw, output_contract_id="SOME_OTHER_CONTRACT_V1")
    assert result.parse_status == "UNPARSEABLE"
    assert [d.code for d in result.diagnostics] == ["UNSUPPORTED_OUTPUT_CONTRACT"]
    assert result.output_contract_id == "SOME_OTHER_CONTRACT_V1"


# --------------------------------------------------------------------------- #
# focus_key / provenance
# --------------------------------------------------------------------------- #

def test_focus_key_externally_controls_expected_task_field():
    raw = _doc(focus_key="FOO_BAR", primary="YES", noticed="YES")
    result = _parse(raw, focus_key="FOO_BAR")
    assert result.primary_verdict == "YES"
    assert result.focus_key == "FOO_BAR"


def test_raw_decorative_title_never_overrides_run_id():
    raw = _doc(preamble="ION PEL RUN 12 -- STALE DECORATIVE TITLE\n\n")
    result = _parse(raw, run_id="run-14-true-identity")
    assert result.run_id == "run-14-true-identity"
    assert result.parse_status == "PARSED"


# --------------------------------------------------------------------------- #
# presentation forms
# --------------------------------------------------------------------------- #

def test_line_oriented_form():
    result = _parse(_doc())
    assert result.parse_status == "PARSED"


def test_compact_inline_form():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n"
        b"X26_READ_DEFECT_ADMITTED = YES\n"
        b"B. PRIMARY ANALYSIS X26_READ_NOTICED = YES DECLINED_AS_BORDERLINE = NO "
        b"DEFECT_DESCRIPTION_OR_NONE = inline text value RULE_BASIS = R1, R2 "
        b"CONFIDENCE = HIGH\n"
        b"C. OTHER MATERIAL FINDINGS\n"
        b"NONE\n"
        b"D. FINAL RESULT\n"
        b"MATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.noticed is True
    assert result.declined_as_borderline is False
    assert result.defect_description_text == "inline text value"
    assert result.rule_basis_text == "R1, R2"
    assert result.confidence == "HIGH"


def test_markdown_wrapped_form():
    raw = (
        b"**A. PRIMARY CLASSIFICATION**\n\n"
        b"X26_READ_DEFECT_ADMITTED = **YES**\n\n"
        b"---\n\n"
        b"**B. PRIMARY ANALYSIS**\n\n"
        b"- X26_READ_NOTICED = **YES**\n"
        b"- DECLINED_AS_BORDERLINE = **NO**\n"
        b"- DEFECT_DESCRIPTION_OR_NONE = **NONE**\n"
        b"- RULE_BASIS: R1\n"
        b"- CONFIDENCE = **HIGH**\n\n"
        b"---\n\n"
        b"**C. OTHER MATERIAL FINDINGS**\n\n"
        b"NONE\n\n"
        b"---\n\n"
        b"**D. FINAL RESULT**\n\n"
        b"**MATERIAL_DEFECT_FOUND**\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.primary_verdict == "YES"
    assert result.confidence == "HIGH"
    assert result.defect_description_text is None


def test_markdown_table_b_section():
    raw = (
        b"## A. PRIMARY CLASSIFICATION\n\n"
        b"X26_READ_DEFECT_ADMITTED = **NO**\n\n"
        b"---\n\n"
        b"## B. PRIMARY ANALYSIS\n\n"
        b"| Field Value | |\n"
        b"| --- | --- |\n"
        b"| **X26_READ_NOTICED** | YES |\n"
        b"| **DECLINED_AS_BORDERLINE** | NO |\n"
        b"| **DEFECT_DESCRIPTION_OR_NONE** | NONE -- trailing note not equal to NONE |\n"
        b"| **RULE_BASIS** | R3; R1 |\n"
        b"| **CONFIDENCE** | HIGH |\n\n"
        b"---\n\n"
        b"## C. OTHER MATERIAL FINDINGS\n\n"
        b"NONE\n\n"
        b"---\n\n"
        b"## D. FINAL RESULT\n\n"
        b"**MATERIAL_DEFECT_FOUND**\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.primary_verdict == "NO"
    assert result.noticed is True
    assert result.declined_as_borderline is False
    # exact "NONE" is required; trailing text disqualifies the NONE state.
    assert result.defect_description_text == "NONE -- trailing note not equal to NONE"
    assert result.rule_basis_text == "R3; R1"
    assert result.confidence == "HIGH"


# --------------------------------------------------------------------------- #
# defect-description label / alias
# --------------------------------------------------------------------------- #

def test_defect_description_or_none_direct_label():
    result = _parse(_doc(defect_label="DEFECT_DESCRIPTION_OR_NONE", defect="some text"))
    assert result.defect_description_text == "some text"
    for trace in result.field_traces:
        if trace.field_name == "defect_description_text":
            assert trace.trace_kind == "EXACT_EXTRACT"


def test_historical_defect_description_exact_alias():
    result = _parse(_doc(defect_label="DEFECT_DESCRIPTION", defect="some text"))
    assert result.defect_description_text == "some text"
    for trace in result.field_traces:
        if trace.field_name == "defect_description_text":
            assert trace.trace_kind == "CONTRACT_MAP"
            assert trace.rule_id == "PEL-NORM2-R011"


def test_unrecognized_similar_label_is_not_accepted():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\n"
        b"X26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\n"
        b"DECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_NOTES = this is not the recognized field\n"
        b"RULE_BASIS = R1\n"
        b"CONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\n"
        b"NONE\n\n"
        b"D. FINAL RESULT\n\n"
        b"MATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    # the near-alias must not be accepted as defect_description; the real
    # required field is therefore MISSING, which downgrades to PARTIAL.
    assert result.defect_description_text is None
    assert result.parse_status == "PARTIAL"
    assert "MISSING_REQUIRED_FIELD" in [d.code for d in result.diagnostics]


# --------------------------------------------------------------------------- #
# primary_verdict / noticed / declined / confidence enums
# --------------------------------------------------------------------------- #

def test_primary_verdict_yes():
    assert _parse(_doc(primary="YES")).primary_verdict == "YES"


def test_primary_verdict_no():
    assert _parse(_doc(primary="NO")).primary_verdict == "NO"


def test_primary_verdict_unresolved_preserved_distinctly():
    result = _parse(_doc(primary="UNRESOLVED"))
    assert result.primary_verdict == "UNRESOLVED"
    for trace in result.field_traces:
        if trace.field_name == "primary_verdict":
            assert trace.state == "EXPLICIT_UNKNOWN"


def test_noticed_yes():
    assert _parse(_doc(noticed="YES")).noticed is True


def test_noticed_no():
    assert _parse(_doc(noticed="NO")).noticed is False


def test_declined_yes():
    assert _parse(_doc(declined="YES")).declined_as_borderline is True


def test_declined_no():
    assert _parse(_doc(declined="NO")).declined_as_borderline is False


def test_confidence_high_medium_low():
    for level in ("HIGH", "MEDIUM", "LOW"):
        assert _parse(_doc(confidence=level)).confidence == level


def test_confidence_unknown_is_invalid_value_and_partial():
    result = _parse(_doc(confidence="UNKNOWN"))
    assert result.confidence is None
    assert result.parse_status == "PARTIAL"
    assert "INVALID_ENUM_VALUE" in [d.code for d in result.diagnostics]


# --------------------------------------------------------------------------- #
# missing required field / section
# --------------------------------------------------------------------------- #

def test_missing_required_field_is_partial():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\n"
        b"X26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\n"
        b"DECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"RULE_BASIS = R1\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\n"
        b"NONE\n\n"
        b"D. FINAL RESULT\n\n"
        b"MATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.confidence is None
    assert result.parse_status == "PARTIAL"
    assert "MISSING_REQUIRED_FIELD" in [d.code for d in result.diagnostics]


def test_missing_required_section_is_partial():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\n"
        b"X26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\n"
        b"DECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"RULE_BASIS = R1\n"
        b"CONFIDENCE = HIGH\n\n"
        b"D. FINAL RESULT\n\n"
        b"MATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARTIAL"
    assert "MISSING_REQUIRED_SECTION" in [d.code for d in result.diagnostics]


# --------------------------------------------------------------------------- #
# duplicate / conflicting fields
#
# A duplicate of a CLOSED-ENUM role that sits between two other closed-enum
# roles (self-delimiting on both sides, no adjacent open/free-text role
# whose deferred span-end depends on which duplicate is chosen) resolves to
# exactly one differing role across all complete sequences, and is
# classified precisely as DUPLICATE_FIELD / CONFLICTING_FIELD. See the
# H4/H5 block below for the case where the duplicated role instead sits
# immediately after an open (free-text) role -- there the open role's own
# span also differs across sequences, giving AMBIGUOUS_STRUCTURE instead;
# this is a known, safety-preserving diagnostic-precision deviation, not a
# false PARSED.
# --------------------------------------------------------------------------- #

def _doc_duplicate_declined(second_value: str) -> bytes:
    return (
        b"A. PRIMARY CLASSIFICATION\n\n"
        b"X26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\n"
        b"DECLINED_AS_BORDERLINE = NO\n"
        b"DECLINED_AS_BORDERLINE = " + second_value.encode("ascii") + b"\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"RULE_BASIS = R1\n"
        b"CONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\n"
        b"D. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )


def test_duplicate_identical_field_is_partial_with_duplicate_field_diagnostic():
    raw = _doc_duplicate_declined("NO")
    result = _parse(raw)
    assert result.declined_as_borderline is None
    assert result.parse_status == "PARTIAL"
    assert "DUPLICATE_FIELD" in [d.code for d in result.diagnostics]
    ambiguous = [t for t in result.field_traces if t.field_name == "declined_as_borderline"]
    assert len(ambiguous) == 2
    assert all(t.state == "AMBIGUOUS" for t in ambiguous)


def test_duplicate_conflicting_field_is_partial_with_conflicting_field_diagnostic():
    raw = _doc_duplicate_declined("YES")
    result = _parse(raw)
    assert result.declined_as_borderline is None
    assert result.parse_status == "PARTIAL"
    assert "CONFLICTING_FIELD" in [d.code for d in result.diagnostics]


def test_duplicate_adjacent_to_open_role_is_ambiguous_structure_not_duplicate_field():
    """Known deviation (see block docstring above): duplicating CONFIDENCE,
    which sits immediately after the open RULE_BASIS role, makes RULE_BASIS's
    own deferred span depend on which CONFIDENCE candidate is chosen -- two
    roles differ across the two complete sequences, so this is
    AMBIGUOUS_STRUCTURE rather than the more specific DUPLICATE_FIELD. This
    is safety-preserving (parse_status is never PARSED) but diagnostically
    less precise than the illustrative mandate examples for this shape."""
    raw = _doc(extra_b_field="CONFIDENCE = HIGH\n")
    result = _parse(raw)
    assert result.confidence is None
    assert result.rule_basis_text is None
    assert result.parse_status == "PARTIAL"
    assert "AMBIGUOUS_STRUCTURE" in [d.code for d in result.diagnostics]


# --------------------------------------------------------------------------- #
# unknown fields cannot repair required fields
# --------------------------------------------------------------------------- #

def test_unknown_extra_label_cannot_repair_missing_field():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\n"
        b"X26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\n"
        b"DECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"RULE_BASIS = R1\n"
        b"SOME_UNKNOWN_LABEL = surprise value\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\n"
        b"NONE\n\n"
        b"D. FINAL RESULT\n\n"
        b"MATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.confidence is None
    assert result.parse_status == "PARTIAL"
    codes = [d.code for d in result.diagnostics]
    assert "MISSING_REQUIRED_FIELD" in codes
    assert "UNKNOWN_FIELD" in codes


# --------------------------------------------------------------------------- #
# MISSING / UNPARSEABLE / UNRESOLVED are never conflated with NO
# --------------------------------------------------------------------------- #

def test_missing_noticed_is_none_not_false():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\n"
        b"X26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"DECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"RULE_BASIS = R1\n"
        b"CONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\n"
        b"NONE\n\n"
        b"D. FINAL RESULT\n\n"
        b"MATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.noticed is None
    assert result.noticed is not False
    assert result.parse_status == "PARTIAL"


def test_unparseable_primary_verdict_is_none_not_no():
    raw = _doc()
    result = _parse(raw, source_raw_sha256="a" * 64)
    assert result.parse_status == "UNPARSEABLE"
    assert result.primary_verdict is None


# --------------------------------------------------------------------------- #
# primary_verdict / final_result independence -- no cross-field repair
# --------------------------------------------------------------------------- #

def test_primary_no_and_final_material_defect_found_both_preserved():
    result = _parse(_doc(primary="NO", final="MATERIAL_DEFECT_FOUND"))
    assert result.primary_verdict == "NO"
    assert result.final_result == "MATERIAL_DEFECT_FOUND"
    assert result.parse_status == "PARSED"


# --------------------------------------------------------------------------- #
# C-section
# --------------------------------------------------------------------------- #

def test_c_section_none():
    result = _parse(_doc(other="NONE"))
    assert result.other_findings_state == "NONE"
    assert result.other_findings_text is None


def test_c_section_present():
    result = _parse(_doc(other="A material finding was observed here."))
    assert result.other_findings_state == "PRESENT"
    assert result.other_findings_text == "A material finding was observed here."


# --------------------------------------------------------------------------- #
# rule_basis exact preservation
# --------------------------------------------------------------------------- #

def test_rule_basis_preserved_as_exact_text_not_tokenized():
    result = _parse(_doc(rule_basis="R1, R2, R3 (SCOPE COMPATIBILITY)"))
    assert result.rule_basis_text == "R1, R2, R3 (SCOPE COMPATIBILITY)"


# --------------------------------------------------------------------------- #
# byte-offset / determinism
# --------------------------------------------------------------------------- #

def test_byte_offsets_reproduce_exact_source_slices():
    raw = _doc()
    result = _parse(raw)
    for trace in result.field_traces:
        if trace.start_byte is None:
            continue
        excerpt = raw[trace.start_byte:trace.end_byte]
        assert hashlib.sha256(excerpt).hexdigest() == trace.source_excerpt_sha256


def test_same_arguments_produce_equal_returned_object():
    raw = _doc()
    kwargs = dict(
        raw_bytes=raw, run_id="r", evidence_id="e",
        source_raw_sha256=hashlib.sha256(raw).hexdigest(),
        output_contract_id=OUTPUT_CONTRACT_ID, focus_key="X26_READ",
        normalized_at="2026-08-15T00:00:00+00:00",
    )
    first = normalize_single_target_checker_output(**kwargs)
    second = normalize_single_target_checker_output(**kwargs)
    assert first == second


# --------------------------------------------------------------------------- #
# H1-H12 required hardening countercase matrix (mandate section 29)
#
# Central safety property under test throughout this block: a structurally
# non-unique document must NEVER reach parse_status=PARSED ("no FALSE
# PARSED"). Some countercases (H1, H3, H6, H7, H12) describe SAFE shapes
# that must still reach PARSED with the correct value -- a false PARTIAL/
# UNPARSEABLE on an unambiguous document is also a defect, just not the
# severe one this hardening pass targets.
# --------------------------------------------------------------------------- #

def _false_parsed(result) -> bool:
    return result.parse_status == "PARSED"


def test_h1_bare_label_in_prose_does_not_truncate_and_parses():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = The explanation mentions RULE_BASIS in passing.\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == "The explanation mentions RULE_BASIS in passing."
    assert result.rule_basis_text == "R1"
    assert result.confidence == "HIGH"


def test_h2_quoted_label_and_delimiter_is_ambiguous_not_false_parsed():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = The candidate quoted \"RULE_BASIS = fake\".\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert "AMBIGUOUS_STRUCTURE" in [d.code for d in result.diagnostics]


def test_h3_quoted_section_header_in_prose_does_not_truncate_and_parses():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\n"
        b"The candidate quoted \"D. FINAL RESULT = fake\".\n\n"
        b"D. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.other_findings_state == "PRESENT"
    assert result.other_findings_text == 'The candidate quoted "D. FINAL RESULT = fake".'
    assert result.final_result == "MATERIAL_DEFECT_FOUND"


def test_h4_table_and_inline_duplicate_identical_is_not_false_parsed():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\n"
        b"| **CONFIDENCE** | HIGH |\n"
        b"CONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.confidence is None


def test_h5_table_and_inline_duplicate_conflicting_is_not_false_parsed():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\n"
        b"| **CONFIDENCE** | HIGH |\n"
        b"CONFIDENCE = LOW\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.confidence is None


def test_h6_trailing_unknown_field_after_closed_enum_still_parses():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\nCONFIDENCE = HIGH\n"
        b"EXTRA_FIELD = surprise\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.confidence == "HIGH"


def test_h7_literal_asterisk_preserved_in_free_text():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = *material wildcard*\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == "*material wildcard*"


def test_h8_multiple_plausible_next_field_anchors_is_not_false_parsed():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = Text quoting \"RULE_BASIS = alt\" as an example.\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"


def test_h9_multiple_standalone_same_section_headers_is_not_false_parsed():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\n"
        b"D. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"


def test_h10_wrong_field_order_is_not_false_parsed():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"DECLINED_AS_BORDERLINE = NO\nX26_READ_NOTICED = YES\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"


def test_h11_field_in_wrong_section_is_not_false_parsed():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nCONFIDENCE = HIGH\n\n"
        b"D. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.confidence is None


def test_h12_multibyte_utf8_byte_offsets_remain_exact_and_parses():
    raw = (
        "A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        "B. PRIMARY ANALYSIS\n\n"
        "X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        "DEFECT_DESCRIPTION_OR_NONE = cafe naive — 字 emoji \U0001F600 end\n"
        "RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        "C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    ).encode("utf-8")
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    for trace in result.field_traces:
        if trace.start_byte is None:
            continue
        excerpt = raw[trace.start_byte:trace.end_byte]
        assert hashlib.sha256(excerpt).hexdigest() == trace.source_excerpt_sha256


# --------------------------------------------------------------------------- #
# false-PARSED meta-test: every non-unique countercase, checked together
# (mandate section 31)
# --------------------------------------------------------------------------- #

_NON_UNIQUE_COUNTERCASE_DOCS = {
    "H2": (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = The candidate quoted \"RULE_BASIS = fake\".\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    ),
    "H4": (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\n"
        b"| **CONFIDENCE** | HIGH |\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    ),
    "H5": (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\n"
        b"| **CONFIDENCE** | HIGH |\nCONFIDENCE = LOW\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    ),
    "H8": (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = Text quoting \"RULE_BASIS = alt\" as an example.\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    ),
    "H9": (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nC. OTHER MATERIAL FINDINGS\n\n"
        b"D. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    ),
    "H10": (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"DECLINED_AS_BORDERLINE = NO\nX26_READ_NOTICED = YES\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    ),
}


def test_false_parsed_meta_test_across_h2_h4_h5_h8_h9_h10():
    false_parsed = {}
    for label, raw in _NON_UNIQUE_COUNTERCASE_DOCS.items():
        result = _parse(raw)
        if _false_parsed(result):
            false_parsed[label] = result.parse_status
    assert not false_parsed, f"FALSE PARSED on non-unique countercases: {false_parsed}"


# --------------------------------------------------------------------------- #
# structural-uniqueness resolver: internal helper unit tests (mandate
# section 32) -- tests the candidate-sequence resolver as a pure internal
# helper directly, not only through final parser outputs.
# --------------------------------------------------------------------------- #

def test_resolver_zero_candidates_yields_zero_sequences():
    body = b"X26_READ_NOTICED = YES\n"  # missing every other required role
    candidates, _diags, boundaries = _b_role_candidates(body, 0, len(body), "X26_READ")
    sequences = _enumerate_b_sequences(candidates, len(body), boundaries)
    assert sequences == []


def test_resolver_single_unambiguous_document_yields_exactly_one_sequence():
    body = (
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\nCONFIDENCE = HIGH\n"
    )
    candidates, _diags, boundaries = _b_role_candidates(body, 0, len(body), "X26_READ")
    sequences = _enumerate_b_sequences(candidates, len(body), boundaries)
    assert len(sequences) == 1
    kind, role = _classify_b_sequences(sequences)
    assert kind == "unique"
    assert role is None


def test_resolver_two_competing_candidates_yields_multiple_sequences_classified_ambiguous():
    body = (
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = The text quotes \"RULE_BASIS = alt\" here.\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n"
    )
    candidates, _diags, boundaries = _b_role_candidates(body, 0, len(body), "X26_READ")
    sequences = _enumerate_b_sequences(candidates, len(body), boundaries)
    assert len(sequences) >= 2
    kind, role = _classify_b_sequences(sequences)
    assert kind == "ambiguous_structure"
    assert role is None


def test_resolver_two_sequences_differing_in_exactly_one_role_classified_single_role_multi():
    body = (
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\nRULE_BASIS = R1\nCONFIDENCE = HIGH\n"
    )
    candidates, _diags, boundaries = _b_role_candidates(body, 0, len(body), "X26_READ")
    sequences = _enumerate_b_sequences(candidates, len(body), boundaries)
    assert len(sequences) == 2
    kind, role = _classify_b_sequences(sequences)
    assert kind == "single_role_multi"
    assert role == "declined_as_borderline"


def test_resolver_uap1_standalone_line_clamps_open_role_and_stays_unique():
    """PEL-NORM22-R001/R002: a UAP-1 standalone unknown-assignment LINE
    between two required roles is a hard boundary for the preceding open
    field's span, but does not itself fork the structural interpretation."""
    body = (
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"UNKNOWN_MID_FIELD = mid surprise\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n"
    )
    known_spans = []
    for role_labels in (
        (b"X26_READ_NOTICED",), (b"DECLINED_AS_BORDERLINE",),
        (b"DEFECT_DESCRIPTION_OR_NONE", b"DEFECT_DESCRIPTION"),
        (b"RULE_BASIS",), (b"CONFIDENCE",),
    ):
        for label_start, value_start, _is_alias in _find_field_candidates(body, role_labels):
            known_spans.append((label_start, value_start))
    unknown_positions = _uap1_standalone_positions(body, known_spans)
    assert len(unknown_positions) == 1
    candidates, _diags, boundaries = _b_role_candidates(body, 0, len(body), "X26_READ")
    sequences = _enumerate_b_sequences(candidates, len(body), boundaries)
    assert len(sequences) == 1
    seq = sequences[0]
    # Raw (pre-`_finalize_text`-trim) spans may still carry surrounding
    # whitespace -- the boundary property under test is that the unknown
    # assignment's own text is never included.
    defect_start, defect_end, _alias = seq["defect_description"]
    assert body[defect_start:defect_end].strip() == b"NONE"
    assert b"UNKNOWN_MID_FIELD" not in body[defect_start:defect_end]
    rule_start, rule_end, _alias = seq["rule_basis"]
    assert body[rule_start:rule_end].strip() == b"R1"
    assert b"UNKNOWN_MID_FIELD" not in body[rule_start:rule_end]


# --------------------------------------------------------------------------- #
# C21-01..C21-10 required v0.2.1 clarification countercase matrix
# (Phase 2B.1R2 mandate section 21 / freeze section 14): F6 exact
# closed-enum token boundary, F7 unknown-assignment structural separation,
# F8 dash-only free-text ambiguity.
# --------------------------------------------------------------------------- #

def test_c21_01_confidence_glued_prefix_is_invalid_not_truncated():
    result = _parse(_doc(confidence="HIGHjunk"))
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.confidence is None
    assert "INVALID_ENUM_VALUE" in [d.code for d in result.diagnostics]


def test_c21_01b_confidence_glued_parenthetical_is_invalid_not_truncated():
    """The realistic-shaped trigger form from the post-remediation review:
    an annotation glued directly onto the enum value with no separator."""
    result = _parse(_doc(confidence="HIGH(mostly confident)"))
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.confidence is None
    assert "INVALID_ENUM_VALUE" in [d.code for d in result.diagnostics]


def test_c21_02_primary_verdict_glued_prefix_is_invalid_not_truncated():
    result = _parse(_doc(primary="YESmaybe"))
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.primary_verdict is None
    assert "INVALID_ENUM_VALUE" in [d.code for d in result.diagnostics]


def test_c21_03_declined_as_borderline_glued_prefix_is_invalid_not_truncated():
    result = _parse(_doc(declined="NOfoo"))
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.declined_as_borderline is None
    assert "INVALID_ENUM_VALUE" in [d.code for d in result.diagnostics]


def test_c21_04_final_result_glued_suffix_is_not_accepted():
    result = _parse(_doc(final="MATERIAL_DEFECT_FOUND_extra"))
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.final_result is None


def test_c21_05_unknown_assignment_between_description_and_rule_basis():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"UNKNOWN_MID_FIELD = mid surprise\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    # NONE semantics preserved: the unknown assignment is not absorbed into
    # the description span, so the unique structural interpretation remains
    # intact and PARSED stays allowed (mandate section 14).
    assert result.parse_status == "PARSED"
    assert result.defect_description_text is None
    for trace in result.field_traces:
        if trace.field_name == "defect_description_text":
            assert trace.state == "EXPLICIT_UNKNOWN"
    assert result.rule_basis_text == "R1"
    assert result.confidence == "HIGH"
    assert "UNKNOWN_FIELD" in [d.code for d in result.diagnostics]


def test_c21_06_unknown_assignment_between_rule_basis_and_confidence():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"RULE_BASIS = R1\n"
        b"UNKNOWN_MID_FIELD = mid surprise\n"
        b"CONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.rule_basis_text == "R1"
    assert result.confidence == "HIGH"
    assert "UNKNOWN_FIELD" in [d.code for d in result.diagnostics]


def test_c21_07_dash_only_defect_description_is_ambiguous_not_false_parsed():
    result = _parse(_doc(defect="-"))
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.defect_description_text is None
    assert "AMBIGUOUS_STRUCTURE" in [d.code for d in result.diagnostics]
    for trace in result.field_traces:
        if trace.field_name == "defect_description_text":
            assert trace.state == "AMBIGUOUS"
            assert trace.start_byte is not None  # source span preserved


def test_c21_08_triple_dash_only_defect_description_is_ambiguous_not_false_parsed():
    result = _parse(_doc(defect="---"))
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.defect_description_text is None
    assert "AMBIGUOUS_STRUCTURE" in [d.code for d in result.diagnostics]


def test_c21_09_literal_trailing_hyphen_preserved():
    result = _parse(_doc(defect="observed anomaly-"))
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == "observed anomaly-"


def test_c21_10_separator_after_real_content_excluded_and_parses():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = real content\n---\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == "real content"


def test_c21_dash_only_c_section_is_ambiguous_not_false_parsed():
    """F8 applies equally to the C-section body interpreted as free text."""
    result = _parse(_doc(other="-"))
    assert not _false_parsed(result)
    assert result.parse_status == "PARTIAL"
    assert result.other_findings_state is None
    assert "AMBIGUOUS_STRUCTURE" in [d.code for d in result.diagnostics]


# --------------------------------------------------------------------------- #
# C22-01..C22-10 required v0.2.2 unknown-assignment-position countercase
# matrix (Phase 2B.1R3 mandate section 19 / freeze section 13):
# UNKNOWN STRUCTURAL ASSIGNMENT = LEXICAL ASSIGNMENT SHAPE + STRUCTURAL
# POSITION. Structural authority is limited to UAP-1 (standalone assignment
# line) and UAP-2 (valid Markdown table row); mid-sentence/quoted/narrative
# assignment-shaped substrings remain ordinary free text with no truncation.
# --------------------------------------------------------------------------- #

def test_c22_01_quoted_unknown_assignment_in_description_not_truncated():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE =\n"
        b"The candidate literally wrote \"UNKNOWN_FIELD = example\" in its explanation.\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == (
        'The candidate literally wrote "UNKNOWN_FIELD = example" in its explanation.'
    )
    assert result.diagnostics == ()


def test_c22_02_quoted_unknown_assignment_in_rule_basis_not_truncated():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"RULE_BASIS =\n"
        b"Per R2, the candidate quoted \"NOTE = value\" as an example.\n"
        b"CONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.rule_basis_text == 'Per R2, the candidate quoted "NOTE = value" as an example.'


def test_c22_03_lowercase_code_like_assignment_preserved_as_prose():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE =\n"
        b"The source contains `foo = bar` as quoted code.\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == "The source contains `foo = bar` as quoted code."


def test_c22_04_uppercase_inline_narrative_assignment_preserved_as_prose():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE =\n"
        b"The explanation says NOTE = value in an example.\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == "The explanation says NOTE = value in an example."
    assert result.diagnostics == ()


def test_c22_05_standalone_unknown_assignment_after_description():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"UNKNOWN_MID_FIELD = mid surprise\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text is None
    for trace in result.field_traces:
        if trace.field_name == "defect_description_text":
            assert trace.state == "EXPLICIT_UNKNOWN"
    assert result.rule_basis_text == "R1"
    assert "UNKNOWN_FIELD" in [d.code for d in result.diagnostics]


def test_c22_06_standalone_unknown_assignment_after_rule_basis():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE\n"
        b"RULE_BASIS = R1\n"
        b"UNKNOWN_MID_FIELD = mid surprise\n"
        b"CONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.rule_basis_text == "R1"
    assert result.confidence == "HIGH"
    assert "UNKNOWN_FIELD" in [d.code for d in result.diagnostics]


def test_c22_07_unknown_markdown_table_row_separately_observable():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"| **X26_READ_NOTICED** | YES |\n"
        b"| **DECLINED_AS_BORDERLINE** | NO |\n"
        b"| **DEFECT_DESCRIPTION_OR_NONE** | NONE |\n"
        b"| **UNKNOWN_MID_FIELD** | mid surprise |\n"
        b"| **RULE_BASIS** | R1 |\n"
        b"| **CONFIDENCE** | HIGH |\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.rule_basis_text == "R1"
    assert result.confidence == "HIGH"
    assert "UNKNOWN_FIELD" in [d.code for d in result.diagnostics]


def test_c22_08_prose_prefix_before_assignment_bytes_not_structural():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE =\n"
        b"The candidate wrote UNKNOWN_FIELD = example here.\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == "The candidate wrote UNKNOWN_FIELD = example here."
    assert result.diagnostics == ()


def test_c22_09_standalone_unknown_assignment_mid_multiline_description():
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE =\n"
        b"first semantic line\n"
        b"UNKNOWN_FIELD = example\n"
        b"RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    assert result.parse_status == "PARSED"
    assert result.defect_description_text == "first semantic line"
    assert "UNKNOWN_FIELD" in [d.code for d in result.diagnostics]


def test_c22_10_unsupported_inline_unknown_no_heuristic_truncation():
    """No structural authority is invented for an inline unknown assignment
    sharing a physical line with known fields; whatever the default open-
    field absorption behavior produces, it must never SILENTLY discard real
    bytes -- every byte between the delimiter and the next chosen anchor is
    accounted for in the returned value."""
    raw = (
        b"A. PRIMARY CLASSIFICATION\n\nX26_READ_DEFECT_ADMITTED = YES\n\n"
        b"B. PRIMARY ANALYSIS\n\n"
        b"X26_READ_NOTICED = YES\nDECLINED_AS_BORDERLINE = NO\n"
        b"DEFECT_DESCRIPTION_OR_NONE = NONE UNKNOWN_FIELD = x RULE_BASIS = R1\nCONFIDENCE = HIGH\n\n"
        b"C. OTHER MATERIAL FINDINGS\n\nNONE\n\nD. FINAL RESULT\n\nMATERIAL_DEFECT_FOUND\n"
    )
    result = _parse(raw)
    if result.parse_status == "PARSED":
        assert result.defect_description_text == "NONE UNKNOWN_FIELD = x"
    else:
        assert result.parse_status == "PARTIAL"


# --------------------------------------------------------------------------- #
# source/capability boundary check (mandate section 34)
# --------------------------------------------------------------------------- #

def _normalization_source_files():
    return [PEL_DIR / name for name in NORMALIZATION_FILES]


def _parse_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_normalization_source_has_no_forbidden_imports():
    violations = []
    for path in _normalization_source_files():
        tree = _parse_ast(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if root in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(f"{path.name}: from {node.module} import ...")
    assert not violations, f"forbidden imports found: {violations}"


def test_normalization_source_has_no_filesystem_write_primitive():
    violations = []
    for path in _normalization_source_files():
        tree = _parse_ast(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ("write_text", "write_bytes"):
                violations.append(f"{path.name}: .{func.attr}(...)")
            if isinstance(func, ast.Name) and func.id == "open":
                violations.append(f"{path.name}: open(...)")
    assert not violations, f"filesystem write primitives found: {violations}"


def test_normalization_source_has_no_clock_lookup():
    violations = []
    clock_names = {"time", "datetime", "monotonic", "perf_counter"}
    for path in _normalization_source_files():
        tree = _parse_ast(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for name in names:
                    if name.split(".")[0] in clock_names:
                        violations.append(f"{path.name}: imports {name!r}")
    assert not violations, f"clock-lookup imports found: {violations}"


def test_normalization_source_has_no_forbidden_semantic_symbols_or_fields():
    violations = []
    for path in _normalization_source_files():
        tree = _parse_ast(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in FORBIDDEN_SYMBOL_NAMES:
                    violations.append(f"{path.name}: symbol {node.name}")
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id.lower() in FORBIDDEN_FIELD_OR_ATTR_NAMES:
                    violations.append(f"{path.name}: field {node.target.id}")
            if (
                isinstance(node, ast.Attribute)
                and node.attr.lower() in FORBIDDEN_FIELD_OR_ATTR_NAMES
            ):
                violations.append(f"{path.name}: attribute .{node.attr}")
    assert not violations, f"forbidden semantic-authority surface found: {violations}"
