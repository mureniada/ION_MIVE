"""ION PEL Phase-2B.1R3 final clarified normalization data-model tests (FieldTrace,
ParserDiagnostic, NormalizedJudgmentV0_2_2).

Plain test functions, collected by both `pytest` and `backend/run_tests.py`.
"""

from __future__ import annotations

import dataclasses

from pel.normalization_contract import PARSER_ID, PARSER_VERSION
from pel.normalization_models import FieldTrace, NormalizedJudgmentV0_2_2, ParserDiagnostic
from tests.util import raises

VALID_SHA = "a" * 64


def _trace(**overrides) -> FieldTrace:
    fields = dict(
        field_name="primary_verdict",
        trace_kind="EXACT_EXTRACT",
        start_byte=10,
        end_byte=13,
        source_excerpt_sha256=VALID_SHA,
        rule_id=None,
        state="PRESENT",
    )
    fields.update(overrides)
    return FieldTrace(**fields)


def _diagnostic(**overrides) -> ParserDiagnostic:
    fields = dict(
        code="MISSING_REQUIRED_FIELD",
        message="confidence: no source occurrence found",
        start_byte=None,
        end_byte=None,
    )
    fields.update(overrides)
    return ParserDiagnostic(**fields)


def _judgment(**overrides) -> NormalizedJudgmentV0_2_2:
    fields = dict(
        run_id="run-1",
        evidence_id="ev-1",
        source_raw_sha256=VALID_SHA,
        output_contract_id="ION_PEL_SINGLE_TARGET_DEFECT_ADMISSION_V0_2_2",
        focus_key="X26_READ",
        parser_id=PARSER_ID,
        parser_version=PARSER_VERSION,
        primary_verdict="YES",
        noticed=True,
        declined_as_borderline=False,
        defect_description_text="some text",
        rule_basis_text="R3",
        confidence="HIGH",
        other_findings_state="NONE",
        other_findings_text=None,
        final_result="MATERIAL_DEFECT_FOUND",
        parse_status="PARSED",
        field_traces=(_trace(),),
        diagnostics=(),
        normalized_at="2026-08-15T00:00:00+00:00",
    )
    fields.update(overrides)
    return NormalizedJudgmentV0_2_2(**fields)


# --------------------------------------------------------------------------- #
# frozen dataclasses
# --------------------------------------------------------------------------- #

def test_field_trace_is_frozen():
    trace = _trace()
    with raises(dataclasses.FrozenInstanceError):
        trace.field_name = "other"


def test_parser_diagnostic_is_frozen():
    diag = _diagnostic()
    with raises(dataclasses.FrozenInstanceError):
        diag.code = "INVALID_UTF8"


def test_normalized_judgment_is_frozen():
    judgment = _judgment()
    with raises(dataclasses.FrozenInstanceError):
        judgment.run_id = "other"


# --------------------------------------------------------------------------- #
# FieldTrace validation
# --------------------------------------------------------------------------- #

def test_valid_field_trace():
    trace = _trace()
    assert trace.state == "PRESENT"


def test_field_trace_rejects_invalid_trace_kind():
    with raises(ValueError):
        _trace(trace_kind="NOT_A_KIND")


def test_field_trace_rejects_invalid_state():
    with raises(ValueError):
        _trace(state="NOT_A_STATE")


def test_field_trace_rejects_one_sided_offsets():
    with raises(ValueError):
        _trace(start_byte=10, end_byte=None)
    with raises(ValueError):
        _trace(start_byte=None, end_byte=13)


def test_field_trace_rejects_invalid_excerpt_sha():
    with raises(ValueError):
        _trace(source_excerpt_sha256="not-a-digest")


def test_field_trace_contract_map_without_rule_id_rejected():
    with raises(ValueError):
        _trace(trace_kind="CONTRACT_MAP", rule_id=None)


def test_field_trace_contract_map_with_rule_id_accepted():
    trace = _trace(trace_kind="CONTRACT_MAP", rule_id="PEL-NORM-R007")
    assert trace.rule_id == "PEL-NORM-R007"


def test_field_trace_no_source_value_with_offsets_rejected():
    with raises(ValueError):
        _trace(
            trace_kind="NO_SOURCE_VALUE",
            start_byte=0,
            end_byte=1,
            source_excerpt_sha256=VALID_SHA,
            state="MISSING",
        )


def test_field_trace_no_source_value_missing_accepted():
    trace = _trace(
        trace_kind="NO_SOURCE_VALUE",
        start_byte=None,
        end_byte=None,
        source_excerpt_sha256=None,
        rule_id=None,
        state="MISSING",
    )
    assert trace.trace_kind == "NO_SOURCE_VALUE"


def test_field_trace_exact_extract_requires_span():
    with raises(ValueError):
        _trace(
            trace_kind="EXACT_EXTRACT",
            start_byte=None,
            end_byte=None,
            source_excerpt_sha256=None,
        )


# --------------------------------------------------------------------------- #
# ParserDiagnostic validation
# --------------------------------------------------------------------------- #

def test_valid_parser_diagnostic():
    diag = _diagnostic()
    assert diag.code == "MISSING_REQUIRED_FIELD"


def test_parser_diagnostic_rejects_invalid_code():
    with raises(ValueError):
        _diagnostic(code="NOT_A_CODE")


def test_parser_diagnostic_accepts_ambiguous_structure_code():
    diag = _diagnostic(code="AMBIGUOUS_STRUCTURE", message="B: 2 complete structural interpretations")
    assert diag.code == "AMBIGUOUS_STRUCTURE"


def test_parser_diagnostic_rejects_empty_message():
    with raises(ValueError):
        _diagnostic(message="")


def test_parser_diagnostic_rejects_one_sided_offsets():
    with raises(ValueError):
        _diagnostic(start_byte=5, end_byte=None)


# --------------------------------------------------------------------------- #
# NormalizedJudgmentV0_2_2 validation
# --------------------------------------------------------------------------- #

def test_valid_normalized_judgment():
    judgment = _judgment()
    assert judgment.parse_status == "PARSED"


def test_normalized_judgment_rejects_invalid_primary_verdict():
    with raises(ValueError):
        _judgment(primary_verdict="MAYBE")


def test_normalized_judgment_rejects_invalid_confidence():
    with raises(ValueError):
        _judgment(confidence="VERY_HIGH")


def test_normalized_judgment_rejects_invalid_final_result():
    with raises(ValueError):
        _judgment(final_result="SOMETHING_ELSE")


def test_normalized_judgment_rejects_invalid_parse_status():
    with raises(ValueError):
        _judgment(parse_status="NOT_A_STATUS")


def test_normalized_judgment_rejects_invalid_raw_sha():
    with raises(ValueError):
        _judgment(source_raw_sha256="not-a-digest")


def test_normalized_judgment_rejects_wrong_parser_id():
    with raises(ValueError):
        _judgment(parser_id="some-other-parser")


def test_normalized_judgment_rejects_wrong_parser_version():
    with raises(ValueError):
        _judgment(parser_version="9.9")


def test_normalized_judgment_accepts_null_fields_for_unparseable_shape():
    judgment = _judgment(
        primary_verdict=None,
        noticed=None,
        declined_as_borderline=None,
        defect_description_text=None,
        rule_basis_text=None,
        confidence=None,
        other_findings_state=None,
        other_findings_text=None,
        final_result=None,
        parse_status="UNPARSEABLE",
        field_traces=(),
        diagnostics=(_diagnostic(),),
    )
    assert judgment.parse_status == "UNPARSEABLE"


# --------------------------------------------------------------------------- #
# to_dict()
# --------------------------------------------------------------------------- #

def test_to_dict_produces_schema_compatible_nested_structures():
    judgment = _judgment(diagnostics=(_diagnostic(),))
    d = judgment.to_dict()
    assert isinstance(d["field_traces"], list)
    assert isinstance(d["field_traces"][0], dict)
    assert d["field_traces"][0]["field_name"] == "primary_verdict"
    assert isinstance(d["diagnostics"], list)
    assert isinstance(d["diagnostics"][0], dict)
    assert d["diagnostics"][0]["code"] == "MISSING_REQUIRED_FIELD"
    assert d["noticed"] is True
    assert d["parser_id"] == PARSER_ID
    assert d["parser_version"] == PARSER_VERSION
