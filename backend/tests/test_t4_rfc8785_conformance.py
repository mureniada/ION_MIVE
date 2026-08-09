"""T61 and T73 — RFC 8785 conformance against the RFC's own vectors.

The expectations are read out of `t4/vectors/rfc8785.txt` at run time by
`t4.rfc8785_vectors`, which verifies that file's SHA-256 first. Nothing is
transcribed here, so no expectation can drift toward whatever the implementation
under test happens to produce, and a failing vector is a finding about the
canonicalizer.

    source  RFC 8785 (Rundgren, Jordan, Erdtman, June 2020)
    sha256  63d52294eb0e3f0014174288186d388b4ddbf2c67d1ce8af1d9726eb0c3ab240
    T61(a)  sections 3.2.2 (input) and 3.2.4 (expected bytes, hexadecimal)
    T61(c)  section 3.2.3 (property-sorting test data and expected order)
    T73     appendix B, Table 1 (IEEE 754 serialization samples)

Every test runs under `netguard`'s `guarded` decorator with credentials absent.
"""

from __future__ import annotations

import hashlib
import struct

from t4 import jcs
from t4 import rfc8785_vectors as vectors
from tests.netguard import guarded
from tests.util import raises

# The counts the RFC's own tables carry. Asserted so that a silently truncated
# parse cannot pass as a full run.
APPENDIX_B_SERIALIZABLE_ROWS = 24
APPENDIX_B_REJECTED_ROWS = 2
SORTING_EXAMPLE_PROPERTIES = 7


@guarded
def test_the_vector_source_is_the_pinned_rfc_and_is_unaltered():
    path = vectors.source_path()
    assert path.is_file(), f"vector source is absent: {path}"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == vectors.SOURCE_SHA256
    assert len(raw) == vectors.SOURCE_BYTE_COUNT
    text = raw.decode("utf-8-sig")
    assert "Request for Comments: 8785" in text
    assert "JSON Canonicalization Scheme (JCS)" in text


# --------------------------------------------------------------------------- #
# T73 — number conformance over the full finite domain
# --------------------------------------------------------------------------- #

@guarded
def test_t73_number_serialization_matches_appendix_b_for_every_sample():
    """Every serializable Appendix B row, compared to the RFC's own expectation.

    Covers what T73 names: fractional values, exponent input, the largest and
    smallest magnitudes, the exact-integer boundary, and negative zero — whose
    output comes from the table rather than from any assumption made here.
    """
    samples = vectors.number_samples()
    assert len(samples) == APPENDIX_B_SERIALIZABLE_ROWS, \
        f"expected {APPENDIX_B_SERIALIZABLE_ROWS} rows, parsed {len(samples)}"

    mismatches = []
    for ieee754_hex, value, expected in samples:
        produced = jcs.to_canonical_text(value)
        if produced != expected:
            mismatches.append(f"{ieee754_hex}: expected {expected!r}, got {produced!r}")
    assert not mismatches, "canonicalizer disagrees with RFC 8785 appendix B:\n" + \
        "\n".join(mismatches)


@guarded
def test_t73_negative_zero_and_the_integer_boundary_come_from_the_table():
    """The two rows most often got wrong, asserted against the table explicitly."""
    by_hex = {h: expected for h, _value, expected in vectors.number_samples()}
    minus_zero = struct.unpack(">d", bytes.fromhex("8000000000000000"))[0]
    assert struct.pack(">d", minus_zero).hex() == "8000000000000000", "premise: this is -0.0"
    assert jcs.to_canonical_text(minus_zero) == by_hex["8000000000000000"]
    # 2**53, the largest exactly representable integer boundary in the table.
    assert jcs.to_canonical_text(
        struct.unpack(">d", bytes.fromhex("4340000000000000"))[0]
    ) == by_hex["4340000000000000"]


@guarded
def test_t73_nan_and_infinity_terminate_with_an_error():
    """Section 3.2.2.3: appendix B gives these rows no serialization at all."""
    rejected = vectors.rejected_number_samples()
    assert len(rejected) == APPENDIX_B_REJECTED_ROWS
    for ieee754_hex, _comment in rejected:
        value = struct.unpack(">d", bytes.fromhex(ieee754_hex))[0]
        with raises(jcs.NonFiniteNumber):
            jcs.to_canonical_text(value)


# --------------------------------------------------------------------------- #
# T61 — structural conformance
# --------------------------------------------------------------------------- #

@guarded
def test_t61a_structural_vector_matches_the_rfc_byte_for_byte():
    """Section 3.2.2 parsed, serialized, and compared to section 3.2.4's bytes.

    The expectation is the RFC's own hexadecimal listing, so the comparison is at
    the level a digest covers. This is the assertion that two-path agreement
    cannot substitute for.
    """
    document, expected = vectors.structural_example()
    produced = jcs.canonicalize(document)
    assert produced == expected, (
        f"expected {expected!r}\n"
        f"got      {produced!r}"
    )
    # The vector exercises the parts it is meant to: exponent input, trailing
    # zeros, a rounded value, a literal non-ASCII code point, and both escape forms.
    assert b"1e+30" in produced and b"4.5" in produced and b"0.002" in produced
    assert b"333333333.3333333" in produced
    assert "€".encode("utf-8") in produced
    assert b"\\u000f" in produced and b"\\n" in produced


@guarded
def test_t61c_property_sorting_matches_the_rfc_expected_order():
    """A supplementary-plane name against a BMP name in U+E000..U+FFFF.

    U+1F600 sorts *before* U+FB33 under UTF-16 code units and *after* it by code
    point; the RFC's expected order settles which is right, and both halves of the
    premise are asserted so the test cannot pass for the wrong reason.
    """
    document, expected_order = vectors.sorting_example()
    parsed = jcs.parse(document)
    assert len(parsed) == SORTING_EXAMPLE_PROPERTIES
    assert "\U0001f600" in parsed and "\ufb33" in parsed
    assert ord("\U0001f600") > ord("\ufb33"), "premise: by code point the emoji is greater"

    produced_order = [parsed[key] for key in sorted(parsed, key=lambda k: k.encode("utf-16-be"))]
    assert produced_order == expected_order

    # And the canonical text places them in that same order.
    text = jcs.to_canonical_text(parsed)
    positions = [text.index('"%s"' % value) for value in expected_order]
    assert positions == sorted(positions)


@guarded
def test_t61e_input_validity_rejections_are_terminal():
    """The three rejections T61(e) names, on the parse path."""
    with raises(jcs.DuplicatePropertyName):
        jcs.parse('{"a":1,"a":2}')
    with raises(jcs.InvalidUnicode):
        jcs.parse('{"k":"\\udead"}')  # the RFC's own example of a lone surrogate
    with raises(jcs.NonFiniteNumber):
        jcs.parse('{"k":NaN}')
