"""RFC 8785 JSON Canonicalization Scheme — mandate section 4.2C.

Two layers, kept apart on purpose (mandate 4.2C):

**Layer A — the canonicalizer.** RFC 8785 over its own input domain, which is the
full finite IEEE-754 double range, not the integer subset a T4 record happens to
use. Key ordering is over UTF-16 code units; there is no Unicode normalization of
any kind; escaping is the ECMAScript ``JSON.stringify`` set with lowercase
``\\uXXXX``; numbers follow the ECMAScript ``Number::toString`` algorithm; the
hashed bytes are the UTF-8 encoding of the canonical text with no BOM and no
trailing newline.

**Layer B — the record's value rule.** Every number in a T4 record must have a
mathematical value that is an exact integer. ``require_integer_domain`` is that
check and nothing else: it is a claim about *values*, never about the lexical form
they arrived in, and no part of this module attributes a lexical guarantee to it.

**Conformance status.** The implementation below is written to the specification;
it is NOT verified against an authoritative RFC 8785 test vector, because no copy
of RFC 8785 is available offline on this host and no network access is authorized.
Agreement between two implementations is necessary but not sufficient (T61a), so
no conformance claim is made here or anywhere that uses this module.

Placement: outside ``backend/app/`` under D7.
"""

from __future__ import annotations

import json
import math
from typing import Any

__all__ = [
    "CanonicalizationError",
    "DuplicatePropertyName",
    "InvalidUnicode",
    "NonFiniteNumber",
    "NonIntegerValue",
    "UnrepresentableInteger",
    "UnsupportedType",
    "canonicalize",
    "parse",
    "require_integer_domain",
    "serialize",
    "to_canonical_text",
]


class CanonicalizationError(Exception):
    """Input could not be canonicalized. Terminal: no partial output is produced."""


class DuplicatePropertyName(CanonicalizationError):
    """An object carried the same property name twice.

    Detected on the *pairs* the parser hands back, i.e. before any dict is built,
    so the second value never gets the chance to silently win.
    """


class InvalidUnicode(CanonicalizationError):
    """A string carried an unpaired surrogate. No replacement character is used."""


class NonFiniteNumber(CanonicalizationError):
    """NaN or an infinity reached the canonicalizer."""


class UnrepresentableInteger(CanonicalizationError):
    """A Python ``int`` that no IEEE-754 double holds exactly.

    Deliberate deviation, and confined to the *object* input path. On the text
    path a JSON number is converted to a double as RFC 8785 requires, rounding
    included, because that is what the RFC's own domain says the value is. An
    ``int`` handed in from Python is not a JSON literal: the caller holds it
    exactly, so rounding it would silently change a value nobody asked to change.
    """


class NonIntegerValue(CanonicalizationError):
    """Layer B: a record number whose mathematical value is not an exact integer."""


class UnsupportedType(CanonicalizationError):
    """A Python object with no JSON data-model counterpart."""


# --------------------------------------------------------------------------- #
# Parsing — strict, and strict *before* anything is constructed
# --------------------------------------------------------------------------- #

def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise DuplicatePropertyName(f"duplicate property name: {key!r}")
        seen.add(key)
    return dict(pairs)


def _reject_constant(name: str) -> Any:
    raise NonFiniteNumber(f"non-finite JSON literal is not admissible: {name}")


def _int_to_double(literal: str) -> float:
    """A JSON integer literal is a double (RFC 8785 numeric domain)."""
    value = float(int(literal))
    if math.isinf(value):
        raise NonFiniteNumber(f"number literal overflows the double range: {literal}")
    return value


def _float_from_literal(literal: str) -> float:
    value = float(literal)
    if math.isinf(value) or math.isnan(value):
        raise NonFiniteNumber(f"number literal is not finite: {literal}")
    return value


def _has_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _assert_valid_strings(value: Any) -> None:
    """Reject unpaired surrogates anywhere, in keys as well as values.

    UTF-8 decoding already refuses encoded surrogates, so the only way one can
    arrive is a ``\\uD800``-style escape, which the JSON parser decodes happily.
    """
    if isinstance(value, str):
        if _has_surrogate(value):
            raise InvalidUnicode("string carries an unpaired surrogate")
    elif isinstance(value, dict):
        for key, item in value.items():
            if _has_surrogate(key):
                raise InvalidUnicode("property name carries an unpaired surrogate")
            _assert_valid_strings(item)
    elif isinstance(value, list):
        for item in value:
            _assert_valid_strings(item)


def parse(document: str | bytes) -> Any:
    """Parse JSON into the canonicalizer's data model, refusing invalid input.

    Refused: duplicate property names, unpaired surrogates, ``NaN``/``Infinity``,
    and any number literal that overflows the double range. No normalization of
    any kind is applied to any string.
    """
    if isinstance(document, (bytes, bytearray)):
        try:
            text = bytes(document).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidUnicode(f"input is not valid UTF-8: {exc}") from None
    else:
        text = document

    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
            parse_int=_int_to_double,
            parse_float=_float_from_literal,
        )
    except CanonicalizationError:
        raise
    except json.JSONDecodeError as exc:
        raise CanonicalizationError(f"input is not valid JSON: {exc}") from None

    _assert_valid_strings(value)
    return value


# --------------------------------------------------------------------------- #
# Numbers — ECMAScript Number::toString, radix 10
# --------------------------------------------------------------------------- #

def _shortest_digits(magnitude: float) -> tuple[str, int]:
    """Return ``(s, n)`` where ``s`` is the shortest round-trip digit string with
    no leading or trailing zeros, and the value is ``s * 10**(n - len(s))``.

    ``repr`` supplies the shortest round-tripping decimal; this only re-reads its
    position of the decimal point. It never re-derives the digits themselves.
    """
    text = repr(magnitude)
    if "e" in text or "E" in text:
        mantissa, _, exponent_text = text.partition("e" if "e" in text else "E")
        exponent = int(exponent_text)
    else:
        mantissa, exponent = text, 0

    integer_part, _, fraction_part = mantissa.partition(".")
    raw = integer_part + fraction_part
    stripped = raw.lstrip("0")
    leading_zeros = len(raw) - len(stripped)
    n = len(integer_part) + exponent - leading_zeros
    return stripped.rstrip("0"), n


def _es6_number_to_string(value: float) -> str:
    """ECMA-262 ``Number::toString`` for a finite, non-zero double."""
    sign = "-" if value < 0 else ""
    s, n = _shortest_digits(abs(value))
    k = len(s)

    if k <= n <= 21:
        return sign + s + "0" * (n - k)
    if 0 < n <= 21:
        return sign + s[:n] + "." + s[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + s
    # n <= -6 or n > 21: exponential notation.
    exponent = n - 1
    exponent_text = ("+" if exponent >= 0 else "-") + str(abs(exponent))
    if k == 1:
        return sign + s + "e" + exponent_text
    return sign + s[0] + "." + s[1:] + "e" + exponent_text


def _number_text(value: float | int) -> str:
    if isinstance(value, int):
        as_double = float(value)
        if math.isinf(as_double) or int(as_double) != value:
            raise UnrepresentableInteger(
                f"integer {value} is not exactly representable as a double"
            )
        value = as_double
    if math.isnan(value) or math.isinf(value):
        raise NonFiniteNumber("NaN and Infinity are not admissible")
    if value == 0:
        return "0"  # also the canonical form of negative zero
    return _es6_number_to_string(value)


# --------------------------------------------------------------------------- #
# Strings
# --------------------------------------------------------------------------- #

_TWO_CHARACTER_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _quote(text: str) -> str:
    out = ['"']
    for ch in text:
        escape = _TWO_CHARACTER_ESCAPES.get(ch)
        if escape is not None:
            out.append(escape)
            continue
        code_point = ord(ch)
        if code_point < 0x20:
            out.append("\\u%04x" % code_point)
        elif 0xD800 <= code_point <= 0xDFFF:
            raise InvalidUnicode("string carries an unpaired surrogate")
        else:
            out.append(ch)  # literal: no normalization, no non-ASCII escaping
    out.append('"')
    return "".join(out)


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #

def _utf16_key(key: str) -> bytes:
    """Sort key: the property name as an array of UTF-16 code units.

    Big-endian UTF-16 bytes compare exactly as the code-unit sequence does, which
    is what makes a supplementary-plane name (leading high surrogate, 0xD800..)
    sort *before* a BMP name in U+E000..U+FFFF — the case where code-unit order
    and code-point order disagree.
    """
    if _has_surrogate(key):
        raise InvalidUnicode("property name carries an unpaired surrogate")
    return key.encode("utf-16-be")


def _write(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(_quote(value))
    elif isinstance(value, (int, float)):
        out.append(_number_text(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _write(item, out)
        out.append("]")
    elif isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise UnsupportedType(f"property name is not a string: {key!r}")
        out.append("{")
        for index, key in enumerate(sorted(value, key=_utf16_key)):
            if index:
                out.append(",")
            out.append(_quote(key))
            out.append(":")
            _write(value[key], out)
        out.append("}")
    else:
        raise UnsupportedType(f"no JSON data-model counterpart: {type(value).__name__}")


def to_canonical_text(value: Any) -> str:
    """Canonical JSON text. Array order is stored order; there is no whitespace."""
    out: list[str] = []
    _write(value, out)
    return "".join(out)


def serialize(value: Any) -> bytes:
    """The bytes a digest covers: UTF-8, no BOM, no trailing newline."""
    return to_canonical_text(value).encode("utf-8")


def canonicalize(document: str | bytes) -> bytes:
    """Parse strictly, then serialize canonically."""
    return serialize(parse(document))


# --------------------------------------------------------------------------- #
# Layer B — the record's value rule
# --------------------------------------------------------------------------- #

def require_integer_domain(value: Any, path: str = "<root>") -> None:
    """Every number reachable from ``value`` must have an exact integer value.

    A claim about values only: ``1``, ``1.0`` and ``1e0`` are the same value and
    all pass; ``1.5`` does not; ``-0`` is zero. Nothing here can see, or says
    anything about, the lexical form the number was written in.
    """
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise NonFiniteNumber(f"{path}: NaN and Infinity are not admissible")
        if not value.is_integer():
            raise NonIntegerValue(f"{path}: value is not an exact integer: {value!r}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            require_integer_domain(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            require_integer_domain(item, f"{path}.{key}")
        return
    raise UnsupportedType(f"{path}: no JSON data-model counterpart: {type(value).__name__}")
