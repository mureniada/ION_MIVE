"""Authoritative RFC 8785 test vectors, read out of the RFC itself.

**Provenance, pinned.**

    file    t4/vectors/rfc8785.txt
    bytes   41879
    sha256  63d52294eb0e3f0014174288186d388b4ddbf2c67d1ce8af1d9726eb0c3ab240
    source  RFC 8785, "JSON Canonicalization Scheme (JCS)", Rundgren, Jordan,
            Erdtman, June 2020 — Independent Submission, Informational.
    fetched by the operator in a browser; not downloaded by the executor.

**Sections used.**

    section 3.2.2   the sample JSON object that is parsed (the vector's input)
    section 3.2.3   the property-sorting test data and its expected order
    section 3.2.4   the expected canonical output of the 3.2.2 sample,
                    given as explicit hexadecimal bytes
    appendix B      Table 1, IEEE 754 number serialization samples

**Why this module parses rather than transcribes.** Nothing here restates an
expected value. Every expectation is extracted from the RFC text at run time, and
the file's digest is verified first, so a vector cannot silently drift into
whatever this implementation happens to produce. Transcription is the failure mode
the mandate's rule of evidence names; parsing removes the opportunity.

The file is read only. It is never edited, and no expectation derived from it is
ever adjusted to make a test pass.
"""

from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

__all__ = [
    "SOURCE_SHA256",
    "VectorSourceError",
    "number_samples",
    "rejected_number_samples",
    "sorting_example",
    "source_path",
    "structural_example",
]

SOURCE_SHA256 = "63d52294eb0e3f0014174288186d388b4ddbf2c67d1ce8af1d9726eb0c3ab240"
SOURCE_BYTE_COUNT = 41879
_SOURCE = Path(__file__).resolve().parent / "vectors" / "rfc8785.txt"


class VectorSourceError(Exception):
    """The vector source is missing, altered, or does not carry a needed vector."""


def source_path() -> Path:
    return _SOURCE


def _text() -> str:
    if not _SOURCE.is_file():
        raise VectorSourceError(f"vector source is absent: {_SOURCE}")
    raw = _SOURCE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256 or len(raw) != SOURCE_BYTE_COUNT:
        raise VectorSourceError(
            f"vector source does not match its pinned provenance: "
            f"{len(raw)} bytes, sha256 {digest}"
        )
    return raw.decode("utf-8-sig")


def _lines() -> list[str]:
    return _text().split("\n")


def _index_of(lines: list[str], needle: str, start: int = 0) -> int:
    for index in range(start, len(lines)):
        if needle in lines[index]:
            return index
    raise VectorSourceError(f"vector source does not contain the marker: {needle!r}")


def _braced_block(lines: list[str], start: int) -> str:
    """Collect the indented ``{ ... }`` block that follows ``start``."""
    opened = None
    collected: list[str] = []
    depth = 0
    for index in range(start, len(lines)):
        line = lines[index]
        if opened is None:
            if "{" not in line:
                continue
            opened = index
        collected.append(line.strip())
        depth += line.count("{") - line.count("}")
        if depth == 0:
            return "".join(collected)
    raise VectorSourceError("no complete brace-delimited block after the marker")


# --------------------------------------------------------------------------- #
# Sections 3.2.2 and 3.2.4 — the structural vector, byte-exact
# --------------------------------------------------------------------------- #

_HEX_LINE = re.compile(r"\A\s*(?:[0-9a-f]{2}\s+)*[0-9a-f]{2}\s*\Z")


def structural_example() -> tuple[str, bytes]:
    """``(input_json, expected_canonical_bytes)`` from sections 3.2.2 and 3.2.4.

    The expectation is the RFC's own hexadecimal byte listing, so the comparison
    is at the level the mandate hashes at, not at the level of a rendered string.
    """
    lines = _lines()

    marker = _index_of(lines, "Assume the following JSON object is parsed:")
    document = _braced_block(lines, marker)

    marker = _index_of(lines, "following bytes, here shown in hexadecimal notation:")
    hex_parts: list[str] = []
    for index in range(marker + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            if hex_parts:
                break
            continue
        if not _HEX_LINE.match(line):
            break
        hex_parts.append(line.strip())
    if not hex_parts:
        raise VectorSourceError("section 3.2.4 carries no hexadecimal byte listing")

    expected = bytes.fromhex(" ".join(hex_parts).replace("  ", " "))
    return document, expected


# --------------------------------------------------------------------------- #
# Section 3.2.3 — the UTF-16 property-sorting vector
# --------------------------------------------------------------------------- #

def sorting_example() -> tuple[str, list[str]]:
    """``(input_json, expected_value_order)`` from section 3.2.3.

    The RFC states the expectation as the order of the *values* after the property
    names are sorted, which is what makes it checkable without restating any key.
    """
    lines = _lines()

    marker = _index_of(lines, "The following JSON test data can be used for verifying")
    document = _braced_block(lines, marker)

    marker = _index_of(lines, "Expected argument order after sorting property strings:",
                       marker)
    order: list[str] = []
    for index in range(marker + 1, len(lines)):
        line = lines[index].strip()
        if not line:
            if order:
                break
            continue
        match = re.fullmatch(r'"(.*)"', line)
        if match is None:
            break
        order.append(match.group(1))
    if not order:
        raise VectorSourceError("section 3.2.3 carries no expected argument order")
    return document, order


# --------------------------------------------------------------------------- #
# Appendix B — Table 1, IEEE 754 number serialization samples
# --------------------------------------------------------------------------- #

_TABLE_ROW = re.compile(r"\A\s*\|\s*([0-9a-f]{16})\s*\|(.*?)\|(.*?)\|\s*\Z")


def _appendix_b_rows() -> list[tuple[str, str, str]]:
    lines = _lines()
    start = _index_of(lines, "Appendix B.  Number Serialization Samples")
    rows: list[tuple[str, str, str]] = []
    for index in range(start, len(lines)):
        if "Table 1:" in lines[index]:
            break
        match = _TABLE_ROW.match(lines[index])
        if match is not None:
            rows.append((match.group(1), match.group(2).strip(), match.group(3).strip()))
    if not rows:
        raise VectorSourceError("appendix B carries no sample rows")
    return rows


def _double(ieee754_hex: str) -> float:
    return struct.unpack(">d", bytes.fromhex(ieee754_hex))[0]


def number_samples() -> list[tuple[str, float, str]]:
    """``(ieee754_hex, value, expected_json)`` for every serializable Appendix B row.

    Rows whose JSON Representation column is empty are the out-of-range values and
    are returned by :func:`rejected_number_samples` instead.
    """
    return [(h, _double(h), expected)
            for h, expected, _comment in _appendix_b_rows() if expected]


def rejected_number_samples() -> list[tuple[str, str]]:
    """``(ieee754_hex, comment)`` for the rows the RFC gives no serialization for.

    Section 3.2.2.3: NaN and Infinity MUST cause a compliant implementation to
    terminate with an error, and appendix B marks them by an empty representation.
    """
    return [(h, comment) for h, expected, comment in _appendix_b_rows() if not expected]
