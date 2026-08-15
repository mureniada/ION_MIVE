"""ION PEL Phase 2B.1R3 — final clarified hardened deterministic parser for
the frozen ``ION_PEL_SINGLE_TARGET_DEFECT_ADMISSION_V0_2_2`` checker-output
contract.

Implements exactly the rules frozen by
`ION_PEL_PHASE2B0_2_HARDENED_OUTPUT_CONTRACT_FREEZE_v0.2.md`, the
clarification successor
`ION_PEL_PHASE2B0_3_CONTRACT_CLARIFICATION_FREEZE_v0.2.1.md`, and the final
positional clarification
`ION_PEL_PHASE2B0_4_UNKNOWN_ASSIGNMENT_POSITION_CLARIFICATION_FREEZE_v0.2.2.md`.
Byte offsets are authoritative; all structural matching operates on
``bytes``, never on decoded text. No filesystem access, no clock lookup, no
network, no app/t4 dependency, no hidden state. For identical arguments the
returned object is equal.

Central v0.2 invariant, replacing the v0.1 "recognizable bytes -> choose
boundaries -> normalize" model:

    recognizable bytes
    -> enumerate admissible structural occurrences
    -> enumerate complete ordered interpretations
    -> require structural uniqueness
    -> normalize

``PARSED`` is returned only when exactly one complete structural
interpretation exists for the required sections and, within B, for the
required field roles. A hash-correct span is necessary but never sufficient:
a source-backed field supports ``PARSED`` only when its span is also part of
the unique structural interpretation.

v0.2.1 clarification (PEL-NORM21-R001/R004/R005) additionally requires that
a unique structural interpretation preserve the FULL LEXICAL EXTENT of
every closed-enum token (no allowed-prefix acceptance -- PEL-NORM21-R001)
and of every semantic free-text value: a free-text value that reduces
entirely to a standalone dash run is genuinely ambiguous between literal
content and a presentation separator and must never be silently deleted or
silently accepted (PEL-NORM21-R004), while a literal hyphen inside otherwise
non-empty text, or a separator trailing already-established real content,
remains preserved (PEL-NORM21-R005).

v0.2.2 clarification (PEL-NORM22-R001/R002/R003) narrows unknown-assignment
structural authority to STRUCTURAL POSITION, not lexical shape alone: an
unknown, label-shaped assignment inside section B is a structural boundary
that a required open field's span may never absorb only when it occupies a
standalone assignment line (PEL-NORM22-R002) or a valid Markdown table row
(PEL-NORM22-R003) -- never when it is mid-sentence, quoted, or otherwise
embedded inside ordinary narrative prose (PEL-NORM22-R001). No
natural-language quote parsing is performed; safety comes entirely from
line/row position.
"""

from __future__ import annotations

import re

from .integrity import sha256_bytes
from .normalization_contract import (
    CONFIDENCE_VALUES,
    FINAL_RESULTS,
    OUTPUT_CONTRACT_ID,
    PARSER_ID,
    PARSER_VERSION,
    PRIMARY_VERDICTS,
)
from .normalization_models import FieldTrace, NormalizedJudgmentV0_2_2, ParserDiagnostic

__all__ = ["normalize_single_target_checker_output"]

# --------------------------------------------------------------------------- #
# byte-level primitives
# --------------------------------------------------------------------------- #

_HWS = frozenset(b" \t")
_WS = frozenset(b" \t\r\n")
_IDENT_CHARS = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
)


def _trim_ws(raw: bytes, start: int, end: int) -> tuple[int, int]:
    while start < end and raw[start] in _WS:
        start += 1
    while end > start and raw[end - 1] in _WS:
        end -= 1
    return start, end


def _trim_section_body_end(raw: bytes, start: int, end: int) -> int:
    """Strip trailing whitespace and a trailing standalone horizontal-rule
    or bullet-marker run (``-`` repeated, sitting alone at the start of its
    line) from a boundary. A horizontal rule remains permitted
    section-separator presentation (PEL-NORM2-R015); this is distinct from,
    and does not reintroduce, the removed unconditional '*' stripping --
    only literal '-' runs that are demonstrably standalone (preceded by a
    newline or the start of the span) are ever touched here. Used both for
    whole SECTION BODY boundaries and, via `_finalize_text`, for open
    (deferred-close) field spans that can inherit a leading list-bullet
    artifact from the next field's own line."""
    while end > start:
        if raw[end - 1] in _WS:
            end -= 1
            continue
        if raw[end - 1] == 0x2D:  # '-'
            run_start = end
            while run_start > start and raw[run_start - 1] == 0x2D:
                run_start -= 1
            if run_start == start or raw[run_start - 1] == 0x0A:
                end = run_start
                continue
        break
    return end


def _strip_bold_wrapper(raw: bytes, start: int, end: int) -> tuple[int, int]:
    """Strip a single, fully-matched leading+trailing ``**`` pair. Used only
    where the grammar establishes ``**`` as a presentation wrapper around an
    entire token (a label, a closed-enum token, or the explicit ``NONE``
    sentinel) -- never applied to free-text field values in general."""
    if end - start >= 4 and raw[start:start + 2] == b"**" and raw[end - 2:end] == b"**":
        return start + 2, end - 2
    return start, end


def _excerpt_sha256(raw: bytes, start: int, end: int) -> str:
    return sha256_bytes(raw[start:end])


def _decode(raw: bytes, start: int, end: int) -> str:
    return raw[start:end].decode("utf-8", errors="strict")


def _is_word_boundary_match(body: bytes, idx: int, length: int) -> bool:
    """True only if the match at [idx, idx+length) is not a substring of a
    longer identifier -- prevents an unrecognized `DEFECT_DESCRIPTION_NOTES`
    from being mistaken for the frozen `DEFECT_DESCRIPTION` alias, and a
    `NO_MATERIAL_DEFECT_FOUND` prefix from double-matching
    `MATERIAL_DEFECT_FOUND`."""
    if idx > 0 and body[idx - 1] in _IDENT_CHARS:
        return False
    end = idx + length
    if end < len(body) and body[end] in _IDENT_CHARS:
        return False
    return True


# --------------------------------------------------------------------------- #
# PEL-NORM2-R003 / R004: standalone structural section-header lines
# --------------------------------------------------------------------------- #

def _section_header_pattern(text: str) -> re.Pattern:
    escaped = re.escape(text.encode("ascii")).replace(rb"\ ", rb"\s+")
    # A standalone line: optional leading h-whitespace, optional #/##
    # heading marker, optional **, the exact label, optional matching **,
    # optional trailing h-whitespace, and NOTHING else on that line.
    return re.compile(
        rb"^[ \t]*#{0,3}[ \t]*\*{0,2}[ \t]*" + escaped + rb"[ \t]*\*{0,2}[ \t]*\r?$",
        re.MULTILINE,
    )


def _section_header_runon_pattern(text: str, next_label_alts: list[bytes]) -> re.Pattern:
    """A section header immediately followed, on the same line, by the
    opening label of one of its OWN required fields (e.g.
    "B. PRIMARY ANALYSIS X26_READ_NOTICED = YES ...", the historical
    compact-inline presentation form) is still a valid structural anchor --
    the match ends before the field label (a lookahead), so the section
    body begins exactly at that label. This is narrowly scoped to a
    recognized field opener immediately following (only whitespace between)
    and is what distinguishes it from arbitrary trailing prose such as
    "D. FINAL RESULT was quoted by the candidate", which matches neither
    this pattern nor the standalone one."""
    escaped = re.escape(text.encode("ascii")).replace(rb"\ ", rb"\s+")
    alt = b"|".join(re.escape(a) for a in next_label_alts)
    return re.compile(
        rb"^[ \t]*#{0,3}[ \t]*\*{0,2}[ \t]*" + escaped + rb"[ \t]*\*{0,2}[ \t]+"
        rb"(?=(?:" + alt + rb")(?![A-Za-z0-9_]))",
        re.MULTILINE,
    )


_STANDALONE_SECTION_PATTERNS = {
    "A": _section_header_pattern("A. PRIMARY CLASSIFICATION"),
    "B": _section_header_pattern("B. PRIMARY ANALYSIS"),
    "C": _section_header_pattern("C. OTHER MATERIAL FINDINGS"),
    "D": _section_header_pattern("D. FINAL RESULT"),
}
_SECTION_ORDER = ("A", "B", "C", "D")

_B_ROLE_LABEL_VARIANTS_FOR_RUNON = (
    b"DECLINED_AS_BORDERLINE",
    b"DEFECT_DESCRIPTION_OR_NONE",
    b"DEFECT_DESCRIPTION",
    b"RULE_BASIS",
    b"CONFIDENCE",
)


def _section_patterns_for(focus_key: str) -> dict[str, list[re.Pattern]]:
    focus_admitted = f"{focus_key}_DEFECT_ADMITTED".encode("utf-8")
    focus_noticed = f"{focus_key}_NOTICED".encode("utf-8")
    return {
        "A": [
            _STANDALONE_SECTION_PATTERNS["A"],
            _section_header_runon_pattern("A. PRIMARY CLASSIFICATION", [focus_admitted]),
        ],
        "B": [
            _STANDALONE_SECTION_PATTERNS["B"],
            _section_header_runon_pattern(
                "B. PRIMARY ANALYSIS", [focus_noticed, *_B_ROLE_LABEL_VARIANTS_FOR_RUNON]
            ),
        ],
        "C": [_STANDALONE_SECTION_PATTERNS["C"]],
        "D": [_STANDALONE_SECTION_PATTERNS["D"]],
    }


class _SectionResolution:
    __slots__ = ("anchors", "candidate_counts", "unique", "any_found")

    def __init__(self, anchors, candidate_counts, unique, any_found):
        self.anchors = anchors  # name -> re.Match or None (only when usable)
        self.candidate_counts = candidate_counts  # name -> int
        self.unique = unique  # bool: True iff exactly 1 candidate each, in order
        self.any_found = any_found


def _resolve_sections(raw: bytes, focus_key: str) -> _SectionResolution:
    patterns = _section_patterns_for(focus_key)
    candidates: dict[str, list[re.Match]] = {}
    for name in _SECTION_ORDER:
        matches: list[re.Match] = []
        for pattern in patterns[name]:
            matches.extend(pattern.finditer(raw))
        matches.sort(key=lambda m: m.start())
        candidates[name] = matches
    counts = {name: len(ms) for name, ms in candidates.items()}
    any_found = any(counts[n] > 0 for n in _SECTION_ORDER)

    unique = all(counts[n] == 1 for n in _SECTION_ORDER)
    if unique:
        positions = [candidates[n][0].start() for n in _SECTION_ORDER]
        unique = positions == sorted(positions) and len(set(positions)) == 4

    anchors: dict[str, re.Match | None] = {}
    for name in _SECTION_ORDER:
        # Best-effort per-section usability: usable only when exactly one
        # candidate exists for that section, regardless of overall
        # uniqueness -- lets partially-recoverable documents still populate
        # individual field diagnostics without ever claiming PARSED.
        anchors[name] = candidates[name][0] if counts[name] == 1 else None

    return _SectionResolution(anchors, counts, unique, any_found)


# --------------------------------------------------------------------------- #
# PEL-NORM2-R006: field-candidate discovery (label + wrapper + delimiter)
# --------------------------------------------------------------------------- #

def _find_label_occurrences(body: bytes, label_variants: tuple[bytes, ...]) -> list[tuple[int, int, bool]]:
    """Return (label_start, label_end, is_alias) for every word-boundary
    occurrence of any variant, de-duplicating an alias match that is really
    a prefix of a longer, already-found primary-label match."""
    found: list[tuple[int, int, bool]] = []
    primary_starts: set[int] = set()
    for i, variant in enumerate(label_variants):
        pos = 0
        while True:
            idx = body.find(variant, pos)
            if idx == -1:
                break
            pos = idx + 1
            if not _is_word_boundary_match(body, idx, len(variant)):
                continue
            if i == 0:
                primary_starts.add(idx)
                found.append((idx, idx + len(variant), False))
            elif idx not in primary_starts:
                found.append((idx, idx + len(variant), True))
    return found


def _resolve_delimiter(body: bytes, label_start: int, label_end: int) -> int | None:
    """Locate the permitted delimiter ('=' or ':') following a label match
    and return the position where the value begins, or None if no permitted
    delimiter is present (-> not a structural field candidate at all).

    A label's own bold wrapper (open before the label, close immediately
    after the delimiter -- the "**LABEL:**" form) is recognized and
    consumed as label presentation. A value's own leading characters
    (including a literal '*') are never consumed here: free-text values
    preserve literal asterisks by default (PEL-NORM2-R021)."""
    label_has_open_wrapper = label_start >= 2 and body[label_start - 2:label_start] == b"**"
    i, n = label_end, len(body)
    while i < n and body[i] in (0x2A, 0x20, 0x09):  # '*' or h-whitespace
        i += 1
    if i >= n or body[i] not in (0x3D, 0x3A):  # '=' or ':'
        return None
    i += 1
    if label_has_open_wrapper and body[i:i + 2] == b"**":
        i += 2
    while i < n and body[i] in (0x20, 0x09, 0x0A, 0x0D):  # whitespace only
        i += 1
    return i


def _find_field_candidates(
    body: bytes, label_variants: tuple[bytes, ...]
) -> list[tuple[int, int, bool]]:
    """Return (label_start, value_start, is_alias) for every structural
    field candidate: a word-boundary label occurrence followed by a
    permitted delimiter. A bare label mention with no delimiter is not a
    structural candidate at all (PEL-NORM2-R006)."""
    out = []
    for label_start, label_end, is_alias in _find_label_occurrences(body, label_variants):
        value_start = _resolve_delimiter(body, label_start, label_end)
        if value_start is not None:
            out.append((label_start, value_start, is_alias))
    return out


# --------------------------------------------------------------------------- #
# Markdown table candidate discovery (unified into the same candidate pool)
# --------------------------------------------------------------------------- #

_TABLE_ROW_RE = re.compile(rb"^\|([^|\n]*)\|([^|\n]*)\|[ \t]*\r?$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(rb"^:?-+:?$")


def _table_field_candidates(
    raw: bytes, body_start: int, body_end: int, label_variants: tuple[bytes, ...]
) -> list[tuple[int, int, int, bool]]:
    """Return (label_start, value_start, value_end, is_alias) for every
    two-column Markdown table row whose (debolded, trimmed) first cell
    exactly matches one of label_variants. Table cells are self-delimiting:
    value_end is the cell boundary, never dependent on any other candidate."""
    out = []
    for m in _TABLE_ROW_RE.finditer(raw, body_start, body_end):
        label_start, label_end = m.start(1), m.end(1)
        label_start, label_end = _trim_ws(raw, label_start, label_end)
        label_start, label_end = _strip_bold_wrapper(raw, label_start, label_end)
        if label_start >= label_end:
            continue
        label_bytes = raw[label_start:label_end]
        if _TABLE_SEP_RE.fullmatch(label_bytes):
            continue
        value_start, value_end = m.start(2), m.end(2)
        value_start, value_end = _trim_ws(raw, value_start, value_end)
        for i, variant in enumerate(label_variants):
            if label_bytes == variant:
                out.append((m.start(1), value_start, value_end, i > 0))
                break
    return out


# --------------------------------------------------------------------------- #
# closed-enum token extraction (PEL-NORM2-R014 span discipline;
# PEL-NORM21-R001 exact full-lexical-token boundary)
# --------------------------------------------------------------------------- #

# A closed-enum token is terminated only by contract-supported separation:
# horizontal whitespace or a line break before the next structural material,
# a Markdown wrapper closure ('*') around the token, or a table-cell
# boundary ('|'). Anything else immediately adjacent to the token (glued
# alphanumerics, digits, punctuation, brackets/parens) is part of the same
# lexical value token, not trailing noise to discard.
_ENUM_TERMINATOR_BYTES = frozenset(b" \t\r\n*|")


def _extract_enum_token(raw: bytes, start: int, upper_bound: int) -> tuple[int, int] | None:
    """From `start`, skip whitespace/'*' wrapper noise, then capture the
    full lexical value token: a maximal run of bytes that are not a
    contract-supported terminator, not extending past `upper_bound`. The
    returned span covers the ENTIRE candidate token -- deliberately
    including any glued non-uppercase content -- so that downstream enum
    membership validation (`_finalize_enum`) correctly rejects a prefix
    match such as `HIGHjunk` or `YESmaybe` as INVALID_ENUM_VALUE rather than
    silently truncating to a clean allowed value (PEL-NORM21-R001: a parser
    may not accept an enum prefix and silently discard immediately-adjacent
    source bytes). This closes F4 (no trailing-content absorption beyond the
    token) together with F6 (no allowed-prefix acceptance)."""
    i = start
    while i < upper_bound and raw[i] in (0x2A, 0x20, 0x09, 0x0A, 0x0D):
        i += 1
    if i >= upper_bound:
        return None
    j = i
    while j < upper_bound and raw[j] not in _ENUM_TERMINATOR_BYTES:
        j += 1
    return i, j


# --------------------------------------------------------------------------- #
# unknown structural-looking assignment discovery (PEL-NORM22-R001/R002/R003)
#
# Central v0.2.2 clarification: LEXICAL ASSIGNMENT SHAPE + STRUCTURAL
# POSITION = UNKNOWN STRUCTURAL ASSIGNMENT. Lexical shape alone (an
# ALL-CAPS label-shaped token immediately followed by a permitted
# delimiter, found ANYWHERE in the raw bytes) is no longer sufficient --
# that was the v0.2.1 defect (a quoted/mid-sentence "UNKNOWN_FIELD = x"
# inside ordinary narrative prose silently truncated the containing
# field). An unknown assignment gains structural-boundary authority only
# at two frozen positions:
#
#   UAP-1 -- a standalone assignment LINE: no ordinary prose precedes the
#            label on that physical line (line-start anchored).
#   UAP-2 -- a valid Markdown table ROW, using the identical structural
#            table-validity rule already used for known fields.
#
# No natural-language quote/prose understanding is performed anywhere --
# safety comes entirely from line/row position, never from guessing intent.
# --------------------------------------------------------------------------- #

_UAP1_STANDALONE_ASSIGNMENT_RE = re.compile(
    rb"^[ \t]*(?:-[ \t]+)?([A-Z][A-Z0-9_]{2,})[ \t]*[:=][^\n]*\r?$",
    re.MULTILINE,
)


def _uap1_standalone_positions(
    body: bytes, known_label_spans: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Return (label_start, label_end) -- relative to `body` -- for every
    UAP-1 standalone unknown-assignment line: the label is the first
    non-whitespace/bullet content on its physical line (PEL-NORM22-R002)."""
    out = []
    for m in _UAP1_STANDALONE_ASSIGNMENT_RE.finditer(body):
        s, e = m.start(1), m.end(1)
        if any(s >= ks and e <= ke for ks, ke in known_label_spans):
            continue
        out.append((s, e))
    return out


def _uap2_table_row_positions(
    raw: bytes, body_start: int, body_end: int, known_label_variants: frozenset
) -> list[tuple[int, int]]:
    """Return (label_start, label_end) -- ABSOLUTE positions in `raw` -- for
    every UAP-2 unknown Markdown table row: a syntactically valid B-section
    table row (the same `_TABLE_ROW_RE` structural rule used for known
    fields) whose (debolded, trimmed) first cell is label-shaped but is not
    one of the frozen known field labels (PEL-NORM22-R003). Arbitrary pipe
    characters inside ordinary prose never match `_TABLE_ROW_RE` at all, so
    no separate "is this really a table" heuristic is needed."""
    out = []
    for m in _TABLE_ROW_RE.finditer(raw, body_start, body_end):
        label_start, label_end = m.start(1), m.end(1)
        label_start, label_end = _trim_ws(raw, label_start, label_end)
        label_start, label_end = _strip_bold_wrapper(raw, label_start, label_end)
        if label_start >= label_end:
            continue
        label_bytes = raw[label_start:label_end]
        if _TABLE_SEP_RE.fullmatch(label_bytes):
            continue
        if label_bytes in known_label_variants:
            continue
        if not re.fullmatch(rb"[A-Z][A-Z0-9_]{2,}", label_bytes):
            continue
        out.append((label_start, label_end))
    return out


def _unknown_field_diagnostics(
    raw: bytes, unknown_positions_absolute: list[tuple[int, int]]
) -> list[ParserDiagnostic]:
    return [
        ParserDiagnostic(
            code="UNKNOWN_FIELD",
            message=(
                f"unrecognized label-shaped token: {raw[s:e]!r} "
                "(structural boundary per PEL-NORM22-R002/R003)"
            ),
            start_byte=s,
            end_byte=e,
        )
        for s, e in unknown_positions_absolute
    ]


# --------------------------------------------------------------------------- #
# single-role resolution (section A: primary_verdict; section D: final_result)
# --------------------------------------------------------------------------- #

class _RoleOutcome:
    __slots__ = ("kind", "value", "span", "code")
    # kind: "unique" | "missing" | "ambiguous_duplicate" | "ambiguous_conflict" | "ambiguous_structure"

    def __init__(self, kind, value=None, span=None, code=None):
        self.kind = kind
        self.value = value
        self.span = span
        self.code = code


def _resolve_single_enum_role(spans: list[tuple[int, int]]) -> _RoleOutcome:
    """spans: list of (token_start, token_end) already-resolved closed-enum
    candidate spans (values not yet decoded). Classifies by count."""
    if not spans:
        return _RoleOutcome("missing")
    if len(spans) == 1:
        return _RoleOutcome("unique", span=spans[0])
    return _RoleOutcome("ambiguous", span=spans)


# --------------------------------------------------------------------------- #
# the public parser
# --------------------------------------------------------------------------- #

_B_ROLE_ORDER = (
    "noticed",
    "declined_as_borderline",
    "defect_description",
    "rule_basis",
    "confidence",
)
_B_ROLE_KIND = {
    "noticed": "enum",
    "declined_as_borderline": "enum",
    "defect_description": "text",
    "rule_basis": "text",
    "confidence": "enum",
}
_B_ROLE_ENUM_VALUES = {
    "noticed": ("YES", "NO"),
    "declined_as_borderline": ("YES", "NO"),
    "confidence": CONFIDENCE_VALUES,
}
_B_ROLE_RULE_ID = {
    "noticed": "PEL-NORM2-R009",
    "declined_as_borderline": "PEL-NORM2-R010",
    "defect_description": "PEL-NORM2-R011",
    "rule_basis": "PEL-NORM2-R012",
    "confidence": "PEL-NORM2-R013",
}


class _Candidate:
    __slots__ = ("label_start", "value_start", "is_alias", "closed_end")

    def __init__(self, label_start, value_start, is_alias, closed_end):
        self.label_start = label_start
        self.value_start = value_start
        self.is_alias = is_alias
        self.closed_end = closed_end  # None for open (inline free-text) candidates


def _b_role_candidates(
    raw: bytes, body_start: int, body_end: int, focus_key: str
) -> dict[str, list[_Candidate]]:
    focus_noticed = f"{focus_key}_NOTICED".encode("utf-8")
    label_variants = {
        "noticed": (focus_noticed,),
        "declined_as_borderline": (b"DECLINED_AS_BORDERLINE",),
        "defect_description": (b"DEFECT_DESCRIPTION_OR_NONE", b"DEFECT_DESCRIPTION"),
        "rule_basis": (b"RULE_BASIS",),
        "confidence": (b"CONFIDENCE",),
    }
    known_label_variants = frozenset(
        variant for variants in label_variants.values() for variant in variants
    )
    body = raw[body_start:body_end]
    candidates: dict[str, list[_Candidate]] = {role: [] for role in _B_ROLE_ORDER}
    known_label_spans: list[tuple[int, int]] = []

    # inline / same-line / Markdown-wrapped candidates
    for role in _B_ROLE_ORDER:
        for label_start, value_start, is_alias in _find_field_candidates(body, label_variants[role]):
            abs_label_start = body_start + label_start
            abs_value_start = body_start + value_start
            known_label_spans.append((label_start, value_start))
            if _B_ROLE_KIND[role] == "enum":
                token = _extract_enum_token(raw, abs_value_start, body_end)
                if token is None:
                    continue  # not a valid closed-token candidate; discard
                candidates[role].append(_Candidate(abs_label_start, token[0], is_alias, token[1]))
            else:
                candidates[role].append(_Candidate(abs_label_start, abs_value_start, is_alias, None))

    # Markdown-table candidates (unified into the SAME pool -- closes F3)
    for role in _B_ROLE_ORDER:
        for label_start, value_start, value_end, is_alias in _table_field_candidates(
            raw, body_start, body_end, label_variants[role]
        ):
            if _B_ROLE_KIND[role] == "enum":
                token = _extract_enum_token(raw, value_start, value_end)
                if token is None:
                    continue
                candidates[role].append(_Candidate(label_start, token[0], is_alias, token[1]))
            else:
                candidates[role].append(_Candidate(label_start, value_start, is_alias, value_end))

    for role in candidates:
        candidates[role].sort(key=lambda c: c.label_start)

    uap1_positions = _uap1_standalone_positions(body, known_label_spans)
    uap1_absolute = [(body_start + s, body_start + e) for s, e in uap1_positions]
    uap2_absolute = _uap2_table_row_positions(raw, body_start, body_end, known_label_variants)
    unknown_positions_absolute = sorted(uap1_absolute + uap2_absolute)

    diagnostics = _unknown_field_diagnostics(raw, unknown_positions_absolute)
    unknown_boundaries = [s for s, _e in unknown_positions_absolute]
    return candidates, diagnostics, unknown_boundaries


def _nearest_unknown_boundary(unknown_boundaries: list[int], after: int, at_or_before: int) -> int | None:
    """First unknown-assignment label-start strictly after `after` and at or
    before `at_or_before`, else None. `unknown_boundaries` is sorted."""
    for pos in unknown_boundaries:
        if pos <= after:
            continue
        if pos > at_or_before:
            break
        return pos
    return None


def _enumerate_b_sequences(
    candidates: dict[str, list[_Candidate]],
    section_end: int,
    unknown_boundaries: list[int] = (),
):
    """Backtracking enumeration of every complete, correctly-ordered B-role
    interpretation. An "open" (inline free-text) candidate's span end is
    resolved lazily, using whichever candidate the sequence chooses for the
    NEXT role -- this is what makes a bare/undelimited mention harmless
    (H1) while an alternative *delimiter-resolved* later occurrence
    produces a genuinely competing sequence (H2). PEL-NORM21-R002/R003: an
    open role's resolved span additionally never extends past the nearest
    unknown structural-looking assignment that falls inside it -- such
    material is a hard structural boundary, not absorbable free text."""
    sequences: list[dict[str, tuple[int, int, bool]]] = []

    def close_open(pending_start: int, hard_end: int) -> int:
        boundary = _nearest_unknown_boundary(unknown_boundaries, pending_start, hard_end)
        return boundary if boundary is not None else hard_end

    def recurse(role_idx, prev_end, pending_role, pending_start, pending_alias, chosen):
        if role_idx == len(_B_ROLE_ORDER):
            final_chosen = dict(chosen)
            if pending_role is not None:
                end = close_open(pending_start, section_end)
                final_chosen[pending_role] = (pending_start, end, pending_alias)
            sequences.append(final_chosen)
            return
        role = _B_ROLE_ORDER[role_idx]
        for cand in candidates[role]:
            if cand.label_start <= prev_end:
                continue
            new_chosen = dict(chosen)
            if pending_role is not None:
                end = close_open(pending_start, cand.label_start)
                new_chosen[pending_role] = (pending_start, end, pending_alias)
            if cand.closed_end is not None:
                new_chosen[role] = (cand.value_start, cand.closed_end, cand.is_alias)
                recurse(role_idx + 1, cand.closed_end, None, None, None, new_chosen)
            else:
                recurse(role_idx + 1, cand.value_start, role, cand.value_start, cand.is_alias, new_chosen)

    recurse(0, -1, None, None, None, {})
    return sequences


def _classify_b_sequences(sequences: list[dict]) -> tuple[str, str | None]:
    """Given >=2 complete sequences, classify as ('duplicate'|'conflict'
    |'ambiguous_structure', role_or_None)."""
    if len(sequences) < 2:
        return "unique", None
    first = sequences[0]
    differing_roles = set()
    for seq in sequences[1:]:
        for role in _B_ROLE_ORDER:
            if seq[role] != first[role]:
                differing_roles.add(role)
    if len(differing_roles) == 1:
        role = next(iter(differing_roles))
        values = {seq[role][:2] for seq in sequences}  # compare (start,end) pairs is wrong for value equality
        return "single_role_multi", role
    return "ambiguous_structure", None


def normalize_single_target_checker_output(
    *,
    raw_bytes: bytes,
    run_id: str,
    evidence_id: str,
    source_raw_sha256: str,
    output_contract_id: str,
    focus_key: str,
    normalized_at: str,
) -> NormalizedJudgmentV0_2_2:
    def _unparseable(diag: ParserDiagnostic, echo_contract_id: str) -> NormalizedJudgmentV0_2_2:
        return NormalizedJudgmentV0_2_2(
            run_id=run_id,
            evidence_id=evidence_id,
            source_raw_sha256=source_raw_sha256,
            output_contract_id=echo_contract_id,
            focus_key=focus_key,
            parser_id=PARSER_ID,
            parser_version=PARSER_VERSION,
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
            diagnostics=(diag,),
            normalized_at=normalized_at,
        )

    # -- trusted source identity check (before any parsing) --
    if sha256_bytes(raw_bytes) != source_raw_sha256:
        return _unparseable(
            ParserDiagnostic(
                code="SOURCE_EVIDENCE_MISMATCH",
                message="SHA-256(raw_bytes) does not match the supplied source_raw_sha256",
                start_byte=None, end_byte=None,
            ),
            output_contract_id,
        )

    # -- output contract selection --
    if output_contract_id != OUTPUT_CONTRACT_ID:
        return _unparseable(
            ParserDiagnostic(
                code="UNSUPPORTED_OUTPUT_CONTRACT",
                message=f"unsupported output_contract_id {output_contract_id!r}",
                start_byte=None, end_byte=None,
            ),
            output_contract_id,
        )

    # -- UTF-8 strict decode boundary --
    try:
        raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _unparseable(
            ParserDiagnostic(
                code="INVALID_UTF8",
                message="raw_bytes is not valid strict UTF-8",
                start_byte=None, end_byte=None,
            ),
            OUTPUT_CONTRACT_ID,
        )

    raw = raw_bytes
    sections = _resolve_sections(raw, focus_key)
    if not sections.any_found:
        return _unparseable(
            ParserDiagnostic(
                code="MISSING_REQUIRED_SECTION",
                message="no recognizable standalone A/B/C/D section-header structure found",
                start_byte=None, end_byte=None,
            ),
            OUTPUT_CONTRACT_ID,
        )

    field_traces: list[FieldTrace] = []
    diagnostics: list[ParserDiagnostic] = []
    downgraded = False

    for name in _SECTION_ORDER:
        count = sections.candidate_counts[name]
        if count == 0:
            diagnostics.append(ParserDiagnostic(
                code="MISSING_REQUIRED_SECTION",
                message=f"section {name} standalone header not found",
                start_byte=None, end_byte=None,
            ))
            downgraded = True
        elif count > 1:
            diagnostics.append(ParserDiagnostic(
                code="AMBIGUOUS_STRUCTURE",
                message=f"section {name} has {count} standalone header candidates",
                start_byte=None, end_byte=None,
            ))
            downgraded = True
    if not sections.unique:
        downgraded = True

    def _section_body(name: str, next_name: str | None) -> tuple[int, int] | None:
        anchor = sections.anchors[name]
        if anchor is None:
            return None
        if next_name and sections.anchors[next_name] is not None:
            end = sections.anchors[next_name].start()
        else:
            end = len(raw)
        return anchor.end(), end

    focus_admitted_label = f"{focus_key}_DEFECT_ADMITTED".encode("utf-8")

    # -- section A: primary_verdict --
    primary_verdict = None
    body_a = _section_body("A", "B")
    if body_a is not None:
        start_a, end_a = body_a
        cands = _find_field_candidates(raw[start_a:end_a], (focus_admitted_label,))
        spans = []
        alias_map = {}
        for label_start, value_start, is_alias in cands:
            token = _extract_enum_token(raw, start_a + value_start, end_a)
            if token is not None:
                spans.append(token)
                alias_map[token] = is_alias
        outcome = _resolve_single_enum_role(spans)
        if outcome.kind == "missing":
            field_traces.append(_missing_trace("primary_verdict"))
            diagnostics.append(_missing_diagnostic("primary_verdict"))
            downgraded = True
        elif outcome.kind == "unique":
            s, e = outcome.span
            primary_verdict, trace, diag = _finalize_enum(
                raw, "primary_verdict", s, e, PRIMARY_VERDICTS,
                is_alias=alias_map[outcome.span], rule_id="PEL-NORM2-R008",
            )
            field_traces.append(trace)
            if diag is not None:
                diagnostics.append(diag)
                downgraded = True
        else:  # ambiguous (>=2 candidates)
            traces, diag = _classify_and_trace_role_ambiguity(
                raw, "primary_verdict", outcome.span, alias_map, rule_id="PEL-NORM2-R008"
            )
            field_traces.extend(traces)
            diagnostics.append(diag)
            downgraded = True
    else:
        field_traces.append(_missing_trace("primary_verdict"))

    # -- section B --
    noticed = declined_as_borderline = confidence = None
    defect_description_text = rule_basis_text = None
    body_b = _section_body("B", "C")
    if body_b is not None:
        start_b, end_b = body_b
        candidates, unknown_diags, unknown_boundaries = _b_role_candidates(
            raw, start_b, end_b, focus_key
        )
        diagnostics.extend(unknown_diags)

        sequences = _enumerate_b_sequences(candidates, end_b, unknown_boundaries)
        if len(sequences) == 1:
            seq = sequences[0]
            for role in _B_ROLE_ORDER:
                s, e, is_alias = seq[role]
                if _B_ROLE_KIND[role] == "enum":
                    allowed = _B_ROLE_ENUM_VALUES[role]
                    value, trace, diag = _finalize_enum(
                        raw, role, s, e, allowed, is_alias=is_alias, rule_id=_B_ROLE_RULE_ID[role]
                    )
                    field_traces.append(trace)
                    if diag is not None:
                        diagnostics.append(diag)
                        downgraded = True
                    if role == "noticed":
                        noticed = None if value is None else value == "YES"
                    elif role == "declined_as_borderline":
                        declined_as_borderline = None if value is None else value == "YES"
                    else:
                        confidence = value
                else:
                    text_value, trace, dash_ambiguous = _finalize_text(raw, role, s, e, is_alias)
                    field_traces.append(trace)
                    if dash_ambiguous:
                        downgraded = True
                        diagnostics.append(ParserDiagnostic(
                            code="AMBIGUOUS_STRUCTURE",
                            message=(
                                f"{trace.field_name}: value reduces to a standalone dash run, "
                                "ambiguous between literal content and presentation separator "
                                "(PEL-NORM21-R004)"
                            ),
                            start_byte=trace.start_byte, end_byte=trace.end_byte,
                        ))
                    if role == "defect_description":
                        defect_description_text = text_value
                    else:
                        rule_basis_text = text_value
        elif len(sequences) == 0:
            # No complete sequence: fall back to independent per-role
            # diagnosis, purely for informative diagnostics. parse_status
            # is already guaranteed non-PARSED via `downgraded`.
            downgraded = True
            for role in _B_ROLE_ORDER:
                cands = candidates[role]
                if not cands:
                    field_traces.append(_missing_trace(_role_field_name(role)))
                    diagnostics.append(_missing_diagnostic(_role_field_name(role)))
                elif len(cands) == 1:
                    c = cands[0]
                    if c.closed_end is not None:
                        end = c.closed_end
                    else:
                        boundary = _nearest_unknown_boundary(unknown_boundaries, c.value_start, end_b)
                        end = boundary if boundary is not None else end_b
                    if _B_ROLE_KIND[role] == "enum":
                        allowed = _B_ROLE_ENUM_VALUES[role]
                        value, trace, diag = _finalize_enum(
                            raw, role, c.value_start, end, allowed,
                            is_alias=c.is_alias, rule_id=_B_ROLE_RULE_ID[role],
                        )
                        field_traces.append(trace)
                        if diag is not None:
                            diagnostics.append(diag)
                        if role == "noticed":
                            noticed = None if value is None else value == "YES"
                        elif role == "declined_as_borderline":
                            declined_as_borderline = None if value is None else value == "YES"
                        else:
                            confidence = value
                    else:
                        text_value, trace, dash_ambiguous = _finalize_text(
                            raw, role, c.value_start, end, c.is_alias
                        )
                        field_traces.append(trace)
                        if dash_ambiguous:
                            diagnostics.append(ParserDiagnostic(
                                code="AMBIGUOUS_STRUCTURE",
                                message=(
                                    f"{trace.field_name}: value reduces to a standalone dash run, "
                                    "ambiguous between literal content and presentation separator "
                                    "(PEL-NORM21-R004)"
                                ),
                                start_byte=trace.start_byte, end_byte=trace.end_byte,
                            ))
                        if role == "defect_description":
                            defect_description_text = text_value
                        else:
                            rule_basis_text = text_value
                else:
                    spans_for_diag = [
                        (c.value_start, c.closed_end if c.closed_end is not None else end_b, c.is_alias)
                        for c in cands
                    ]
                    traces, diag = _ambiguous_field_traces(
                        raw, _role_field_name(role), spans_for_diag, rule_id=_B_ROLE_RULE_ID[role]
                    )
                    field_traces.extend(traces)
                    diagnostics.append(diag)
        else:
            downgraded = True
            kind, role = _classify_b_sequences(sequences)
            if kind == "single_role_multi":
                spans_for_diag = [(seq[role][0], seq[role][1], seq[role][2]) for seq in sequences]
                # de-duplicate identical spans across sequences
                seen = set()
                unique_spans = []
                for sp in spans_for_diag:
                    if sp not in seen:
                        seen.add(sp)
                        unique_spans.append(sp)
                traces, diag = _ambiguous_field_traces(
                    raw, _role_field_name(role), unique_spans, rule_id=_B_ROLE_RULE_ID.get(role)
                )
                field_traces.extend(traces)
                diagnostics.append(diag)
            else:
                diagnostics.append(ParserDiagnostic(
                    code="AMBIGUOUS_STRUCTURE",
                    message="more than one complete structural B-section interpretation exists",
                    start_byte=None, end_byte=None,
                ))
    else:
        for role in _B_ROLE_ORDER:
            field_traces.append(_missing_trace(_role_field_name(role)))

    # -- section C: other material findings --
    other_findings_state = other_findings_text = None
    body_c = _section_body("C", "D")
    if body_c is not None:
        start_c, end_c = body_c
        start_c, end_c = _trim_ws(raw, start_c, end_c)
        had_content_c = start_c < end_c
        trimmed_end_c = _trim_section_body_end(raw, start_c, end_c)
        if had_content_c and trimmed_end_c <= start_c:
            # PEL-NORM21-R004: the entire C-section body reduced to a
            # standalone dash run -- ambiguous between literal content and
            # a presentation separator; never silently deleted or accepted.
            downgraded = True
            diagnostics.append(ParserDiagnostic(
                code="AMBIGUOUS_STRUCTURE",
                message=(
                    "other_findings: value reduces to a standalone dash run, "
                    "ambiguous between literal content and presentation separator "
                    "(PEL-NORM21-R004)"
                ),
                start_byte=start_c, end_byte=end_c,
            ))
            field_traces.append(FieldTrace(
                field_name="other_findings", trace_kind="EXACT_EXTRACT",
                start_byte=start_c, end_byte=end_c,
                source_excerpt_sha256=_excerpt_sha256(raw, start_c, end_c),
                rule_id=None, state="AMBIGUOUS",
            ))
        elif start_c >= trimmed_end_c:
            field_traces.append(_missing_trace("other_findings"))
            diagnostics.append(_missing_diagnostic("other_findings"))
            downgraded = True
        else:
            end_c = trimmed_end_c
            cand_s, cand_e = _strip_bold_wrapper(raw, start_c, end_c)
            text = _decode(raw, cand_s, cand_e).strip()
            if text == "NONE":
                other_findings_state = "NONE"
                other_findings_text = None
                field_traces.append(FieldTrace(
                    field_name="other_findings", trace_kind="EXACT_EXTRACT",
                    start_byte=cand_s, end_byte=cand_e,
                    source_excerpt_sha256=_excerpt_sha256(raw, cand_s, cand_e),
                    rule_id=None, state="EXPLICIT_UNKNOWN",
                ))
            else:
                other_findings_state = "PRESENT"
                other_findings_text = _decode(raw, start_c, end_c)
                field_traces.append(FieldTrace(
                    field_name="other_findings", trace_kind="EXACT_EXTRACT",
                    start_byte=start_c, end_byte=end_c,
                    source_excerpt_sha256=_excerpt_sha256(raw, start_c, end_c),
                    rule_id=None, state="PRESENT",
                ))
    else:
        field_traces.append(_missing_trace("other_findings"))

    # -- section D: final_result --
    final_result = None
    body_d = _section_body("D", None)
    if body_d is not None:
        start_d, end_d = body_d
        body = raw[start_d:end_d]
        occ_by_token: list[tuple[int, int, str]] = []
        for token in ("NO_MATERIAL_DEFECT_FOUND", "MATERIAL_DEFECT_FOUND", "UNRESOLVED"):
            token_bytes = token.encode("ascii")
            pos = 0
            while True:
                idx = body.find(token_bytes, pos)
                if idx == -1:
                    break
                pos = idx + 1
                if not _is_word_boundary_match(body, idx, len(token_bytes)):
                    continue
                occ_by_token.append((start_d + idx, start_d + idx + len(token_bytes), token))
        occ_by_token.sort(key=lambda o: o[0])
        if not occ_by_token:
            field_traces.append(_missing_trace("final_result"))
            diagnostics.append(_missing_diagnostic("final_result"))
            downgraded = True
        elif len(occ_by_token) == 1:
            s, e, token = occ_by_token[0]
            final_result = token
            state = "EXPLICIT_UNKNOWN" if token == "UNRESOLVED" else "PRESENT"
            field_traces.append(FieldTrace(
                field_name="final_result", trace_kind="EXACT_EXTRACT",
                start_byte=s, end_byte=e,
                source_excerpt_sha256=_excerpt_sha256(raw, s, e),
                rule_id=None, state=state,
            ))
            downgraded = downgraded  # no change
        else:
            downgraded = True
            values = {t for _s, _e, t in occ_by_token}
            spans_for_diag = [(s, e, False) for s, e, _t in occ_by_token]
            if len(values) == 1:
                traces, diag = _ambiguous_field_traces(
                    raw, "final_result", spans_for_diag, rule_id=None
                )
                field_traces.extend(traces)
                diagnostics.append(diag)
            else:
                diagnostics.append(ParserDiagnostic(
                    code="AMBIGUOUS_STRUCTURE",
                    message="more than one structurally plausible final-result assertion exists",
                    start_byte=None, end_byte=None,
                ))
                for s, e, _t in occ_by_token:
                    field_traces.append(FieldTrace(
                        field_name="final_result", trace_kind="EXACT_EXTRACT",
                        start_byte=s, end_byte=e,
                        source_excerpt_sha256=_excerpt_sha256(raw, s, e),
                        rule_id=None, state="AMBIGUOUS",
                    ))
    else:
        field_traces.append(_missing_trace("final_result"))

    parse_status = "PARTIAL" if downgraded else "PARSED"

    return NormalizedJudgmentV0_2_2(
        run_id=run_id,
        evidence_id=evidence_id,
        source_raw_sha256=source_raw_sha256,
        output_contract_id=OUTPUT_CONTRACT_ID,
        focus_key=focus_key,
        parser_id=PARSER_ID,
        parser_version=PARSER_VERSION,
        primary_verdict=primary_verdict,
        noticed=noticed,
        declined_as_borderline=declined_as_borderline,
        defect_description_text=defect_description_text,
        rule_basis_text=rule_basis_text,
        confidence=confidence,
        other_findings_state=other_findings_state,
        other_findings_text=other_findings_text,
        final_result=final_result,
        parse_status=parse_status,
        field_traces=tuple(field_traces),
        diagnostics=tuple(diagnostics),
        normalized_at=normalized_at,
    )


# --------------------------------------------------------------------------- #
# shared finalization helpers
# --------------------------------------------------------------------------- #

def _role_field_name(role: str) -> str:
    return "defect_description_text" if role == "defect_description" else (
        "rule_basis_text" if role == "rule_basis" else role
    )


def _missing_trace(field_name: str) -> FieldTrace:
    return FieldTrace(
        field_name=field_name, trace_kind="NO_SOURCE_VALUE",
        start_byte=None, end_byte=None, source_excerpt_sha256=None,
        rule_id=None, state="MISSING",
    )


def _missing_diagnostic(field_name: str) -> ParserDiagnostic:
    return ParserDiagnostic(
        code="MISSING_REQUIRED_FIELD",
        message=f"{field_name}: no source occurrence found",
        start_byte=None, end_byte=None,
    )


def _finalize_enum(
    raw: bytes, field_name: str, start: int, end: int, allowed: tuple[str, ...],
    *, is_alias: bool, rule_id: str,
) -> tuple[str | None, FieldTrace, ParserDiagnostic | None]:
    try:
        text = _decode(raw, start, end)
    except UnicodeDecodeError:
        text = ""
    trace_kind = "CONTRACT_MAP" if is_alias else "EXACT_EXTRACT"
    if text in allowed:
        state = "EXPLICIT_UNKNOWN" if text == "UNRESOLVED" else "PRESENT"
        trace = FieldTrace(
            field_name=field_name, trace_kind=trace_kind,
            start_byte=start, end_byte=end,
            source_excerpt_sha256=_excerpt_sha256(raw, start, end),
            rule_id=rule_id if is_alias else None, state=state,
        )
        return text, trace, None
    trace = FieldTrace(
        field_name=field_name, trace_kind=trace_kind,
        start_byte=start, end_byte=end,
        source_excerpt_sha256=_excerpt_sha256(raw, start, end),
        rule_id=rule_id if is_alias else None, state="INVALID_VALUE",
    )
    diag = ParserDiagnostic(
        code="INVALID_ENUM_VALUE",
        message=f"{field_name}: {text!r} is not one of {allowed} (PEL-NORM21-R001)",
        start_byte=start, end_byte=end,
    )
    return None, trace, diag


def _finalize_text(
    raw: bytes, role: str, start: int, end: int, is_alias: bool
) -> tuple[str | None, FieldTrace, bool]:
    """Returns (text_value, trace, dash_only_ambiguous). When
    `dash_only_ambiguous` is True the caller MUST downgrade parse_status and
    emit AMBIGUOUS_STRUCTURE (PEL-NORM21-R004) -- the candidate value
    reduced entirely to a standalone dash run, genuinely ambiguous between
    literal semantic content and a Markdown presentation separator, and may
    be neither silently deleted nor silently accepted as literal."""
    field_name = _role_field_name(role)
    start, end = _trim_ws(raw, start, end)
    had_content = start < end
    # An open (deferred-close) field's span runs up to the next chosen
    # candidate's label_start, which can leave a trailing presentation
    # artifact belonging to that next line (e.g. a markdown bullet marker
    # "- " immediately before the next field's label) inside this field's
    # captured text. Strip it the same way a section-body boundary does:
    # only a standalone '-' run preceded by a newline (or span start) is
    # ever touched here -- never a hyphen glued to real content
    # (PEL-NORM21-R005).
    trimmed_end = _trim_section_body_end(raw, start, end)
    if had_content and trimmed_end <= start:
        # PEL-NORM21-R004: the ENTIRE candidate value was a standalone dash
        # run (e.g. "-", "---") -- the source span is preserved for the
        # trace, but the field is neither populated nor silently discarded.
        return None, FieldTrace(
            field_name=field_name, trace_kind="EXACT_EXTRACT",
            start_byte=start, end_byte=end,
            source_excerpt_sha256=_excerpt_sha256(raw, start, end),
            rule_id=None, state="AMBIGUOUS",
        ), True
    end = trimmed_end
    trace_kind = "CONTRACT_MAP" if is_alias else "EXACT_EXTRACT"
    rule_id = _B_ROLE_RULE_ID[role] if (is_alias and role == "defect_description") else None
    if start >= end:
        # empty value after trimming -- structurally present but empty;
        # treat as MISSING content per closed-field-empty convention.
        return None, FieldTrace(
            field_name=field_name, trace_kind="NO_SOURCE_VALUE",
            start_byte=None, end_byte=None, source_excerpt_sha256=None,
            rule_id=None, state="MISSING",
        ), False
    cand_s, cand_e = _strip_bold_wrapper(raw, start, end)
    candidate_text = _decode(raw, cand_s, cand_e).strip()
    if role == "defect_description" and candidate_text == "NONE":
        return None, FieldTrace(
            field_name=field_name, trace_kind=trace_kind,
            start_byte=cand_s, end_byte=cand_e,
            source_excerpt_sha256=_excerpt_sha256(raw, cand_s, cand_e),
            rule_id=rule_id, state="EXPLICIT_UNKNOWN",
        ), False
    # Free-text value: preserve literal content verbatim, including any
    # leading/trailing '*' (PEL-NORM2-R021) and any embedded hyphen
    # (PEL-NORM21-R005) -- no further stripping.
    text = _decode(raw, start, end)
    return text, FieldTrace(
        field_name=field_name, trace_kind=trace_kind,
        start_byte=start, end_byte=end,
        source_excerpt_sha256=_excerpt_sha256(raw, start, end),
        rule_id=rule_id, state="PRESENT",
    ), False


def _ambiguous_field_traces(
    raw: bytes, field_name: str, spans: list[tuple[int, int, bool]], *, rule_id: str | None
) -> tuple[list[FieldTrace], ParserDiagnostic]:
    values = []
    for s, e, _is_alias in spans:
        try:
            values.append(_decode(raw, s, e).strip())
        except UnicodeDecodeError:
            values.append(None)
    identical = len(set(values)) <= 1
    code = "DUPLICATE_FIELD" if identical else "CONFLICTING_FIELD"
    traces = [
        FieldTrace(
            field_name=field_name,
            trace_kind="CONTRACT_MAP" if is_alias else "EXACT_EXTRACT",
            start_byte=s, end_byte=e,
            source_excerpt_sha256=_excerpt_sha256(raw, s, e),
            rule_id=rule_id if is_alias else None, state="AMBIGUOUS",
        )
        for s, e, is_alias in spans
    ]
    diagnostic = ParserDiagnostic(
        code=code, message=f"{field_name}: {len(spans)} structural occurrences found",
        start_byte=None, end_byte=None,
    )
    return traces, diagnostic


def _classify_and_trace_role_ambiguity(
    raw: bytes, field_name: str, spans: list[tuple[int, int]], alias_map: dict, *, rule_id: str
) -> tuple[list[FieldTrace], ParserDiagnostic]:
    full_spans = [(s, e, alias_map[(s, e)]) for s, e in spans]
    return _ambiguous_field_traces(raw, field_name, full_spans, rule_id=rule_id)
