"""VOE Dialogue Profile runtime loader (v0.1, Gate 2 + Gate 2A).

Loads and fail-closed validates the exact, pinned, four-file runtime
behavioral payload for VOE-DIALOGUE-PROFILE v0.3, and materializes the
result as a `VOERuntimeProfile` — one verified `VOEProfileBinding` identity
plus the actual verified behavioral text a composer needs. It does not
decide whether the loaded profile is ever wired into a Response Composer, a
Model Context, or any live turn — that is later, separately authorized work.

    PROFILE PACKAGE ON DISK
            -> EXACT RUNTIME BEHAVIORAL SUBSET
            -> BYTE / HASH / IDENTITY VALIDATION
            -> VOERuntimeProfile (binding + verified text)
            -> READY / NOT READY

`load_voe_runtime_profile()` is the ONE load pass: each of the four files is
read exactly once, its byte count and SHA-256 verified against that single
read's own bytes, and — only for bytes that already passed both checks —
strict-UTF-8-decoded into the text `VOERuntimeProfile` carries. No file is
ever re-read after verification, no behavioral text is ever reconstructed
from a constant, and no text reaches `VOERuntimeProfile` by any path other
than decoding the exact bytes that were just hash-verified.
`load_voe_profile_binding()` is a thin, zero-extra-I/O projection of that
same single pass — never a second, independently implemented loader — kept
only so a caller wanting identity alone need not depend on the text fields.

Exactly four files may ever be opened by this module, by fixed filename,
never by directory listing: `01-VOE-DIALOGUE-PROFILE-v0.3.md`,
`02-VOE-STYLE-PARAMETERS-v0.2.json`,
`03-VOE-ETHICAL-INTERACTION-POLICY-v0.1.md`,
`04-VOE-ILLUSTRATIVE-REASONING-POLICY-v0.1.md`. No other file in a supplied
bundle directory is ever read, however many other files that directory
contains — this module has no `iterdir`, `glob`, `listdir`, or `scandir`
call anywhere, so a calibration, checklist, audit-brief, provenance, or
manifest/checksum file has no code path into this module even if physically
present alongside the four it does read.

The runtime behavioral fingerprint reuses, unmodified, the SAME
canonicalization rule the source preparation pack's own
`99-PREPARATION-RECEIPT.md` already defines for its whole-pack
`canonical_payload_fingerprint_sha256`: SHA-256 over the UTF-8, path-sorted,
LF-terminated concatenation of `PATH\tBYTES\tSHA256` rows — restricted here
to exactly the four runtime files, never the full fourteen-file preparation
payload and never the packaging-level pack/zip hash. Those two wider values
are deliberately never accepted here (see the VOE Gate 2 Bundle Identity
Audit, "Correct Runtime Identity"): they cover process, calibration and
audit-brief content this module never loads, so a change to any of THOSE
files must never move this module's own identity, and this module's
identity must never be satisfiable by either of them.

`profile_id` and `profile_version` are independently verified against the
values embedded in the runtime style-parameters file itself
(`02-VOE-STYLE-PARAMETERS-v0.2.json`), never merely asserted — a mismatch
there is a real, contentful failure, not a comparison of one hardcoded
constant against another.

Every failure is closed: a missing file, a byte-count mismatch, a per-file
hash mismatch, an identity mismatch, a version mismatch, or a runtime
fingerprint mismatch each raise `VOEProfileLoadError`, and none ever
constructs a partial `VOEProfileBinding`. This is a module-local error on
purpose: it introduces no transport stage and no mapping onto the core error
taxonomy — exactly the same closure `execution_profile/profiles.py` already
keeps against `app.core.errors`. Mapping this onto a transport-facing
readiness failure is a later, separately authorized composition-time
concern, not this loader's business.

This module imports the standard library only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import VOEProfileBinding, VOEProfileBindingError, VOERuntimeProfile

VOE_PROFILE_LOADER_ID = "ION_VOE_PROFILE_LOADER_V0_1"
VOE_PROFILE_LOADER_VERSION = "0.1"

# The exact, pinned, ordered runtime behavioral payload for
# VOE-DIALOGUE-PROFILE v0.3 — (filename, expected byte count, expected
# SHA-256). v0.3 (operator-approved 2026-09-29, VOE client-experience
# refinement) is a NEW version beside v0.2: 01 and 02 are new files; 03 and
# 04 are the unchanged v0.1 files. Already sorted by path — "01-..." <
# "02-..." < "03-..." < "04-..." both ordinally and numerically — so this
# literal tuple order IS the canonicalization order; nothing here re-sorts it.
#
# Historical (no longer loaded; files kept byte-identical in assets/):
# v0.2 = 01-VOE-DIALOGUE-PROFILE-v0.2.md 13140 a5d96b96…4298,
#        02-VOE-STYLE-PARAMETERS-v0.1.json 1384 389bee95…f364,
#        same 03/04; runtime fingerprint 432dd52a…70f5.
RUNTIME_BEHAVIORAL_FILES: tuple[tuple[str, int, str], ...] = (
    (
        "01-VOE-DIALOGUE-PROFILE-v0.3.md",
        16586,
        "be87fb34783f5d85e605757e13de4147cdbc2725c792b3a849c65419b1225287",
    ),
    (
        "02-VOE-STYLE-PARAMETERS-v0.2.json",
        1931,
        "1428ba1b11091700495b99e4b9f09eeeb8606cd4d45528bd39344c79807eee61",
    ),
    (
        "03-VOE-ETHICAL-INTERACTION-POLICY-v0.1.md",
        2422,
        "538bf8bf8427aefd33aeac73e4659ac07f5f8c0fd3b2964efc93ffdf64cbadc5",
    ),
    (
        "04-VOE-ILLUSTRATIVE-REASONING-POLICY-v0.1.md",
        1498,
        "8d56f1038b3bf2cee1eebe31e197bdc6493439f4fdce0e8ca324ce92e9001638",
    ),
)

# The one file, of the four, whose own content also states the profile's
# identity — checked against content, never merely asserted against itself.
_IDENTITY_SOURCE_FILE = "02-VOE-STYLE-PARAMETERS-v0.2.json"

# Which VOERuntimeProfile text field each runtime file's decoded content
# becomes. Exhaustive and fixed for exactly this one pinned bundle — not a
# general schema, just the one mapping this contract needs.
_TEXT_FIELD_BY_FILENAME = {
    "01-VOE-DIALOGUE-PROFILE-v0.3.md": "dialogue_profile_text",
    "02-VOE-STYLE-PARAMETERS-v0.2.json": "style_parameters_text",
    "03-VOE-ETHICAL-INTERACTION-POLICY-v0.1.md": "ethical_policy_text",
    "04-VOE-ILLUSTRATIVE-REASONING-POLICY-v0.1.md": "illustrative_reasoning_policy_text",
}

EXPECTED_PROFILE_ID = "VOE-DIALOGUE-PROFILE"
EXPECTED_PROFILE_VERSION = "0.3"

# Computed from RUNTIME_BEHAVIORAL_FILES via `_runtime_behavioral_fingerprint`
# below (v0.3, 2026-09-29; v0.2 was 432dd52a…70f5). Deliberately NOT
# `canonical_payload_fingerprint_sha256` (the fourteen-file preparation-pack
# fingerprint) and NOT `PACK_ZIP_SHA256` (the whole-archive hash) — see this
# module's docstring.
EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256 = (
    "e9966bd07fe723b68e6d10112ffa8651983649c255859fd95d55abd9a90fbbee"
)


class VOEProfileLoadError(ValueError):
    """Raised whenever the runtime behavioral payload cannot be loaded and
    validated exactly as pinned.

    Every failure named in this module's docstring raises here, and none is
    ever downgraded into a partially populated `VOEProfileBinding`.

    This is a module-local error on purpose. This module stays closed
    against `app.core.errors`, exactly as `execution_profile/profiles.py`
    stays closed against it: mapping a load failure onto a transport-facing
    readiness failure is a later, separately authorized composition-time
    concern, not this loader's business.
    """


def _read_and_check_file(
    bundle_dir: Path, filename: str, expected_bytes: int, expected_sha256: str
) -> bytes:
    """Read exactly one pinned file by fixed name, or fail closed.

    Never lists, globs, or scans `bundle_dir` — only ever opens the single
    path `bundle_dir / filename` this call was given.
    """
    path = bundle_dir / filename
    if not path.is_file():
        raise VOEProfileLoadError(
            f"required runtime behavioral file is missing: {filename!r} "
            f"(expected at {path})"
        )
    content = path.read_bytes()
    if len(content) != expected_bytes:
        raise VOEProfileLoadError(
            f"{filename!r} has {len(content)} bytes, expected {expected_bytes}"
        )
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise VOEProfileLoadError(
            f"{filename!r} SHA-256 mismatch: expected {expected_sha256}, "
            f"found {actual_sha256}"
        )
    return content


def _runtime_behavioral_fingerprint(rows: tuple[tuple[str, int, str], ...]) -> str:
    """SHA-256 over the UTF-8, LF-terminated `PATH\\tBYTES\\tSHA256` rows,
    supplied already in sorted-by-path order.

    The same rule `99-PREPARATION-RECEIPT.md` states for the whole
    fourteen-file preparation payload, applied here to exactly the four rows
    this module reads — never the wider fourteen-file or whole-archive
    scope.
    """
    body = "".join(f"{path}\t{size}\t{sha}\n" for path, size, sha in rows)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _verify_embedded_identity(style_json_bytes: bytes) -> None:
    """Verify profile_id/profile_version against the values embedded in the
    style-parameters file's own JSON content — a real, contentful check,
    never a comparison of one hardcoded constant against another."""
    try:
        data = json.loads(style_json_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VOEProfileLoadError(
            f"{_IDENTITY_SOURCE_FILE!r} is not valid UTF-8 JSON: {exc}"
        ) from None
    if not isinstance(data, dict):
        raise VOEProfileLoadError(
            f"{_IDENTITY_SOURCE_FILE!r} must decode to a JSON object"
        )

    found_id = data.get("profile_id")
    if found_id != EXPECTED_PROFILE_ID:
        raise VOEProfileLoadError(
            "profile identity mismatch: expected profile_id "
            f"{EXPECTED_PROFILE_ID!r}, found {found_id!r} in "
            f"{_IDENTITY_SOURCE_FILE!r}"
        )

    found_version = data.get("profile_version")
    if found_version != EXPECTED_PROFILE_VERSION:
        raise VOEProfileLoadError(
            "profile version mismatch: expected profile_version "
            f"{EXPECTED_PROFILE_VERSION!r}, found {found_version!r} in "
            f"{_IDENTITY_SOURCE_FILE!r}"
        )


def load_voe_runtime_profile(bundle_dir: Path | str) -> VOERuntimeProfile:
    """Load, fail-closed validate, and materialize the exact pinned
    VOE-DIALOGUE-PROFILE v0.3 runtime behavioral payload from `bundle_dir`.

    This is THE load pass — the one place any file this module reads is
    opened. Opens exactly the four files named in `RUNTIME_BEHAVIORAL_FILES`,
    by fixed filename, in that fixed order — never by listing `bundle_dir`'s
    contents, so no other file it may contain (calibration, checklist,
    audit brief, provenance, manifest, checksum) is ever read.

    For each file, in order: read its bytes exactly once
    (`_read_and_check_file`); verify its byte count; verify its SHA-256;
    only then strict-UTF-8-decode those SAME already-verified bytes into the
    text this file's field carries. No file is read a second time for any
    reason — not to re-verify, not to decode, not to check identity — and no
    text is ever synthesized from `RUNTIME_BEHAVIORAL_FILES`' pinned
    constants instead of the bytes actually read this call.

    Every check must pass before any `VOERuntimeProfile` is constructed; the
    first failure raises `VOEProfileLoadError` and stops immediately — a
    missing file, a byte-count mismatch, a per-file hash mismatch, a UTF-8
    decode failure, an embedded identity mismatch, or a runtime fingerprint
    mismatch, in that order per file, then the two whole-payload checks.
    """
    root = Path(bundle_dir)
    rows: list[tuple[str, int, str]] = []
    texts: dict[str, str] = {}
    style_json_bytes: bytes | None = None

    for filename, expected_bytes, expected_sha256 in RUNTIME_BEHAVIORAL_FILES:
        # The one and only read of this file: bytes verified against the
        # pinned byte count and SHA-256 before this call returns.
        content = _read_and_check_file(root, filename, expected_bytes, expected_sha256)
        rows.append((filename, expected_bytes, expected_sha256))

        # Decode the SAME verified bytes — never a re-read, never a
        # reconstruction. No normalization, no stripping, no line-ending
        # change: `str.decode("utf-8")` on the exact verified bytes only.
        try:
            texts[filename] = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VOEProfileLoadError(
                f"{filename!r} is not valid UTF-8: {exc}"
            ) from None

        if filename == _IDENTITY_SOURCE_FILE:
            style_json_bytes = content

    assert style_json_bytes is not None  # RUNTIME_BEHAVIORAL_FILES always names it
    _verify_embedded_identity(style_json_bytes)

    fingerprint = _runtime_behavioral_fingerprint(tuple(rows))
    if fingerprint != EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256:
        raise VOEProfileLoadError(
            "runtime behavioral fingerprint mismatch: expected "
            f"{EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256}, computed "
            f"{fingerprint}"
        )

    try:
        binding = VOEProfileBinding(
            profile_id=EXPECTED_PROFILE_ID,
            profile_version=EXPECTED_PROFILE_VERSION,
            runtime_behavioral_fingerprint_sha256=fingerprint,
        )
        return VOERuntimeProfile(
            binding=binding,
            **{
                _TEXT_FIELD_BY_FILENAME[filename]: text
                for filename, text in texts.items()
            },
        )
    except VOEProfileBindingError as exc:
        raise VOEProfileLoadError(
            f"loaded runtime behavioral payload failed identity binding: {exc}"
        ) from exc


def load_voe_profile_binding(bundle_dir: Path | str) -> VOEProfileBinding:
    """Identity-only projection of `load_voe_runtime_profile`.

    Performs the exact same single load pass — there is no second,
    independently implemented loader — and returns only `.binding` of the
    result, for a caller that needs identity but not behavioral text.
    """
    return load_voe_runtime_profile(bundle_dir).binding


def resolve_voe_profile(
    *, enabled: bool, bundle_dir: Path | str | None
) -> VOERuntimeProfile | None:
    """The enable/disable law, and nothing else.

    `enabled=False`: returns `None` immediately. No file in `bundle_dir` is
    opened, no hash is computed, no identity is checked — `bundle_dir` is
    not even required to exist or be well-formed, because it is never
    inspected on this path.

    `enabled=True`: `bundle_dir` must be supplied and is passed straight to
    `load_voe_runtime_profile`, whose fail-closed validation is this
    function's entire "true" behavior. Any failure there propagates
    unchanged — never caught, never downgraded into a `None`/disabled-
    lookalike result, so a caller cannot mistake a validation failure for a
    deliberately disabled profile.
    """
    if not enabled:
        return None
    if not bundle_dir:
        raise VOEProfileLoadError(
            "VOE profile is enabled but no runtime bundle directory was supplied"
        )
    return load_voe_runtime_profile(bundle_dir)
