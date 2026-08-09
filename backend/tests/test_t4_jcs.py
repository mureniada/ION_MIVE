"""T4 canonicalizer tests — mandate section 4.2C Layer A and Layer B.

**Scope.** Conformance against the RFC's own vectors is T61 and T73, and lives in
`test_t4_rfc8785_conformance.py`. What is asserted *here* is the surrounding
behaviour: the input-validity rules, the escaping rule, the no-normalization rule,
two-path agreement over a corpus, and the Layer B value rule. Two-path agreement is
necessary but not sufficient for conformance (T61a) and is never described here as
more than it is.

Every test runs under `netguard`'s `guarded` decorator with credentials absent.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from t4 import jcs
from tests.netguard import guarded
from tests.util import raises

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# Input validity (section 4.2C "Input validity")
# --------------------------------------------------------------------------- #

@guarded
def test_duplicate_property_name_is_rejected_before_the_object_is_built():
    # Plain json.loads keeps the last value silently; the canonicalizer must not.
    with raises(jcs.DuplicatePropertyName):
        jcs.parse('{"a":1,"a":2}')
    # Nested, and with the duplicate not adjacent.
    with raises(jcs.DuplicatePropertyName):
        jcs.parse('{"outer":{"k":1,"z":2,"k":3}}')
    # The same name once is fine, and distinct names that merely look alike are fine.
    assert jcs.parse('{"a":1,"A":2}') == {"a": 1.0, "A": 2.0}


@guarded
def test_unpaired_surrogate_is_rejected_with_no_replacement_character():
    with raises(jcs.InvalidUnicode):
        jcs.parse('{"k":"\\ud800"}')
    with raises(jcs.InvalidUnicode):
        jcs.parse('{"\\udfff":"v"}')
    # A correctly paired surrogate pair is one supplementary code point, and passes.
    assert jcs.parse('{"k":"\\ud83d\\ude00"}')["k"] == "\U0001f600"


@guarded
def test_non_finite_values_are_rejected():
    for literal in ("NaN", "Infinity", "-Infinity"):
        with raises(jcs.NonFiniteNumber):
            jcs.parse('{"k":%s}' % literal)
    with raises(jcs.NonFiniteNumber):
        jcs.serialize({"k": float("nan")})
    with raises(jcs.NonFiniteNumber):
        jcs.serialize({"k": float("inf")})


@guarded
def test_malformed_json_is_a_canonicalization_error_not_a_crash():
    with raises(jcs.CanonicalizationError):
        jcs.parse("{")
    with raises(jcs.CanonicalizationError):
        jcs.parse(b"\xff\xfe not utf-8")


# --------------------------------------------------------------------------- #
# Ordering (section 4.2C item 1)
# --------------------------------------------------------------------------- #

@guarded
def test_property_names_sort_by_utf16_code_units_not_code_points():
    """The one case where UTF-16 order and code-point order disagree.

    U+1F600 is a supplementary code point: its UTF-16 form starts with the high
    surrogate 0xD83D, which is *below* a BMP code unit in U+E000..U+FFFF. So by
    code point the emoji sorts last, and by UTF-16 code unit it sorts before
    U+FB33. Asserting both halves keeps the test from passing for the wrong reason.
    """
    emoji, bmp = "\U0001f600", "דּ"
    assert ord(emoji) > ord(bmp), "premise: by code point the emoji is greater"

    text = jcs.to_canonical_text({bmp: 1, emoji: 2})
    assert text.index(emoji) < text.index(bmp), "by UTF-16 code unit the emoji is smaller"


@guarded
def test_key_order_in_the_input_cannot_survive_into_the_output():
    a = jcs.serialize({"b": 1, "a": 2, "é": 3})
    b = jcs.serialize({"é": 3, "a": 2, "b": 1})
    assert a == b
    assert jcs.canonicalize('{"b":1,"a":2}') == jcs.canonicalize('{"a":2,"b":1}')


# --------------------------------------------------------------------------- #
# Strings (section 4.2C items 2 and 3)
# --------------------------------------------------------------------------- #

@guarded
def test_no_unicode_normalization_is_applied():
    """Precomposed and decomposed forms are different strings and stay different."""
    precomposed, decomposed = "é", "é"  # NFC and NFD of the same glyph
    assert jcs.serialize(precomposed) != jcs.serialize(decomposed)
    # As property names too: normalization would collapse these into a duplicate.
    both = jcs.to_canonical_text({precomposed: 1, decomposed: 2})
    assert both.count(":") == 2
    # And non-ASCII is emitted literally, not escaped.
    assert jcs.serialize(precomposed) == '"é"'.encode("utf-8")


@guarded
def test_escaping_uses_two_character_forms_then_lowercase_u_escapes():
    assert jcs.to_canonical_text('"') == '"\\""'
    assert jcs.to_canonical_text("\\") == '"\\\\"'
    assert jcs.to_canonical_text("\b\f\n\r\t") == '"\\b\\f\\n\\r\\t"'
    # A C0 control with no two-character form: lowercase \u00xx.
    assert jcs.to_canonical_text("\x1f") == '"\\u001f"'
    assert jcs.to_canonical_text("\x00") == '"\\u0000"'
    # DEL is not a C0 control and is not escaped.
    assert jcs.to_canonical_text("\x7f") == '"\x7f"'


# --------------------------------------------------------------------------- #
# Numbers — value rules only; the serialization algorithm is unverified (T73)
# --------------------------------------------------------------------------- #

@guarded
def test_lexical_variants_of_one_value_produce_identical_bytes():
    """Section 4.2C Layer B: 1, 1.0 and 1e0 are one value, and -0 is zero."""
    one = jcs.canonicalize('{"k":1}')
    assert jcs.canonicalize('{"k":1.0}') == one
    assert jcs.canonicalize('{"k":1e0}') == one
    assert jcs.canonicalize('{"k":-0}') == jcs.canonicalize('{"k":0}')
    assert jcs.canonicalize('{"k":-0.0}') == b'{"k":0}'


@guarded
def test_integers_within_the_record_domain_serialize_exactly():
    # The section 4.9 bounds: the largest aggregate units value and the safe limit.
    assert jcs.to_canonical_text(1_024_000 * 10 ** 9) == "1024000000000000"
    assert jcs.to_canonical_text(2 * 10 ** 9) == "2000000000"
    assert jcs.to_canonical_text(0) == "0"
    assert jcs.to_canonical_text(-1) == "-1"


@guarded
def test_an_integer_no_double_holds_exactly_is_refused_not_rounded():
    """Object-input path only: refusing beats silently changing the caller's value."""
    unrepresentable = 2 ** 53 + 1
    assert float(unrepresentable) != unrepresentable, "premise: the double rounds it"
    with raises(jcs.UnrepresentableInteger):
        jcs.serialize({"k": unrepresentable})


# --------------------------------------------------------------------------- #
# Layer B — the record's value rule (a claim about values, never about lexis)
# --------------------------------------------------------------------------- #

@guarded
def test_integer_domain_accepts_every_lexical_form_of_an_integer_value():
    for literal in ("1", "1.0", "1e0", "-0", "0"):
        jcs.require_integer_domain(jcs.parse('{"k":%s}' % literal))


@guarded
def test_integer_domain_rejects_a_genuinely_non_integral_value():
    with raises(jcs.NonIntegerValue):
        jcs.require_integer_domain(jcs.parse('{"k":1.5}'))
    with raises(jcs.NonIntegerValue):
        jcs.require_integer_domain({"a": [1, {"b": 0.7}]})


# --------------------------------------------------------------------------- #
# Whole-output properties, and two-path agreement
# --------------------------------------------------------------------------- #

CORPUS = [
    "{}",
    "[]",
    '{"a":[1,2,{"b":null,"c":true}]}',
    '{"\\u00f6":"Latin","\\u20ac":"Euro","\\r":"CR","1":"One"}',
    '{"nested":[[{"z":1,"a":2}],[]],"empty_string":"","zero":0}',
    '[{"basis_kind":"absence","content":null,"dimension":"prompt",'
    '"key_set_variant":null,"parameters":[]}]',
]


@guarded
def test_two_path_agreement_over_the_corpus():
    """Necessary but not sufficient for conformance (T61a); asserted as no more."""
    for document in CORPUS:
        via_text = jcs.canonicalize(document)
        via_model = jcs.serialize(jcs.parse(document))
        assert via_text == via_model, document


@guarded
def test_canonicalization_is_idempotent_over_the_corpus():
    for document in CORPUS:
        once = jcs.canonicalize(document)
        assert jcs.canonicalize(once) == once, document


@guarded
def test_output_carries_no_bom_no_whitespace_and_no_trailing_newline():
    out = jcs.canonicalize('{ "a" : 1 , "b" : [ 1 , 2 ] }')
    assert out == b'{"a":1,"b":[1,2]}'
    assert not out.startswith(b"\xef\xbb\xbf")
    assert not out.endswith(b"\n")


# --------------------------------------------------------------------------- #
# Evidence discipline
# --------------------------------------------------------------------------- #

@guarded
def test_conformance_vectors_come_from_the_rfc_and_are_never_self_generated():
    """Guards the rule of evidence: an authoritative vector is never self-made.

    Provenance, not absence. `t4/vectors/` holds exactly one file, the operator's
    unedited copy of RFC 8785, pinned by digest; every expectation is parsed out of
    it at run time. If a hand-written expectation file ever appears beside it, or
    the RFC is altered, this fails — which is the point.
    """
    from t4 import rfc8785_vectors

    vectors_dir = REPO_ROOT / "backend" / "t4" / "vectors"
    contents = sorted(p.name for p in vectors_dir.iterdir() if p.is_file())
    assert contents == ["rfc8785.txt"], (
        f"t4/vectors/ must hold only the pinned RFC; found {contents}"
    )

    raw = rfc8785_vectors.source_path().read_bytes()
    assert hashlib.sha256(raw).hexdigest() == rfc8785_vectors.SOURCE_SHA256

    # The expectations are extracted, not stored: the module carries no literal
    # copy of any expected byte string beyond the digest that pins the source.
    source = (REPO_ROOT / "backend" / "t4" / "rfc8785_vectors.py").read_text(encoding="utf-8")
    for smuggled in ("9.999999999999997e+22", "295147905179352830000", "1e+23"):
        assert smuggled not in source, (
            f"an appendix B expectation is transcribed into the extractor: {smuggled}"
        )
