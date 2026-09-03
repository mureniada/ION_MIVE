"""Declared-source resolution and raw-byte verification (Content Engine v0.1).

This is the gate every build must pass first:

    declared source_id
        -> declared relative POSIX source path
        -> source_root / relative path
        -> measured SHA-256
        -> compared with the declared source_sha256

    MEASURED SHA256 == DECLARED source_sha256, or nothing is built.

Three distinct things, kept distinct
------------------------------------
    source_id             the pack's declared logical identity. Never a path.
    relative_source_path  where the bytes live beneath the build's root, as a
                          relative POSIX path. Never an identity.
    source_root           this machine's location for that tree. A runtime fact
                          only: it enters no record, no fingerprint, no origin
                          and no Content Pack.

The binding maps `source_id -> relative POSIX path`. The caller never supplies a
provenance URI: the engine constructs the `corpus-file://` origin itself from the
relative path, so a caller cannot inject an absolute or invented origin.

Path safety is enforced here — absolute paths, drive letters, backslashes, `.`
and `..` segments, and anything resolving outside `source_root` are all refused —
because those are filesystem-resolution concerns. The frozen provenance contract
in `retrieval.source_provenance` independently re-validates the URI form of the
origin the engine builds; that logic is reused there, not restated here.

Hash basis is the one already frozen: SHA-256 over COMPLETE_RAW_SOURCE_FILE_BYTES,
read in binary with no normalization of any kind.

Ordering: verified sources are returned in the Content Pack's own canonical order
(lexicographic by `source_id`, closed by E2.1). The binding mapping's iteration
order has no effect on anything.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..retrieval.source_provenance import (
    SOURCE_FILE_SHA256_ALGORITHM,
    SOURCE_FILE_SHA256_BASIS,
)
from .models import ContentEngineError, VerifiedSource

#: Read size for streaming the digest. Chosen to match the repository's existing
#: source-hashing helpers; it cannot affect the resulting digest.
_READ_BLOCK = 65536

__all__ = [
    "SOURCE_FILE_SHA256_ALGORITHM",
    "SOURCE_FILE_SHA256_BASIS",
    "measure_source_bytes",
    "normalize_relative_source_path",
    "resolve_and_verify",
]


def measure_source_bytes(path: Path) -> str:
    """SHA-256 over the complete raw file bytes. No normalization, ever."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_READ_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_relative_source_path(value: Any, source_id: str) -> str:
    """Validate a declared relative POSIX source path. Refuses, never repairs.

    Refused: a non-string, an empty or whitespace-padded value, a backslash
    (Windows separator), a colon (drive letter or scheme), a leading `/`, an
    absolute POSIX path, and any `.` or `..` segment. The value is returned
    unchanged when it passes — nothing is trimmed, re-cased or re-joined.
    """
    if not isinstance(value, str) or not value:
        raise ContentEngineError(
            f"source binding for {source_id!r} must be a relative POSIX path string, "
            f"found {value!r}"
        )
    if value != value.strip():
        raise ContentEngineError(
            f"source binding for {source_id!r} must carry no leading/trailing "
            f"whitespace, found {value!r}"
        )
    if "\\" in value:
        raise ContentEngineError(
            f"source binding for {source_id!r} must use POSIX separators, "
            f"found a backslash in {value!r}"
        )
    if ":" in value:
        raise ContentEngineError(
            f"source binding for {source_id!r} must not carry a drive letter or "
            f"scheme, found {value!r}"
        )
    if value.startswith("/"):
        raise ContentEngineError(
            f"source binding for {source_id!r} must be relative, found absolute {value!r}"
        )

    if PurePosixPath(value).is_absolute():
        raise ContentEngineError(
            f"source binding for {source_id!r} must be relative, found absolute {value!r}"
        )

    # Segments are checked on the literal string, not on PurePosixPath.parts:
    # the latter silently collapses "", "." and doubled separators, which would
    # let "./a.txt" and "a//b.txt" through as if they had been written cleanly.
    # A path that needs normalizing is refused, never normalized.
    segments = value.split("/")
    if not segments:  # pragma: no cover - str.split never returns empty
        raise ContentEngineError(f"source binding for {source_id!r} is empty")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ContentEngineError(
                f"source binding for {source_id!r} must contain no traversal, empty "
                f"or redundant segment, found {value!r}"
            )

    return value


def resolve_and_verify(
    pack: Any,
    bindings: Mapping[str, Any],
    *,
    source_root: Any,
) -> tuple[VerifiedSource, ...]:
    """Reconcile a Content Pack against an explicit binding and verify the bytes.

    `pack` is consumed read-only: nothing here mutates it, re-derives its
    identity, or recomputes its fingerprint. `source_root` is a runtime location
    only and is carried into nothing.

    Fails closed on: a missing binding, an unexpected binding, an absolute or
    traversing relative path, a path resolving outside `source_root`, an absent
    file, a path that is not a regular file, two declared sources resolving to
    the same physical file, and any digest that does not equal the declared
    `source_sha256`. On any failure no verified source is returned at all —
    there is no partially verified inventory.
    """
    sources = getattr(pack, "sources", None)
    if not isinstance(sources, tuple) or not sources:
        raise ContentEngineError("pack must carry a non-empty tuple of declared sources")
    if not isinstance(bindings, Mapping):
        raise ContentEngineError(
            f"bindings must be a mapping of source_id -> relative POSIX path, "
            f"found {type(bindings).__name__}"
        )
    if not isinstance(source_root, (str, Path)) or (
        isinstance(source_root, str) and not source_root.strip()
    ):
        raise ContentEngineError(
            f"source_root must be a filesystem path, found {source_root!r}"
        )

    root = Path(source_root)
    if not root.is_dir():
        raise ContentEngineError(f"source_root is not a directory: {root}")
    resolved_root = root.resolve()

    declared_ids = {source.source_id for source in sources}
    binding_ids = set(bindings.keys())
    missing = sorted(declared_ids - binding_ids)
    unexpected = sorted(binding_ids - declared_ids)
    if missing or unexpected:
        raise ContentEngineError(
            "source bindings must match the declared pack inventory exactly; "
            f"missing binding(s) {missing}, unexpected binding(s) {unexpected}"
        )

    verified: list[VerifiedSource] = []
    resolved_files: dict[str, str] = {}
    for source in sources:
        source_id = source.source_id
        relative = normalize_relative_source_path(bindings[source_id], source_id)

        candidate = root.joinpath(*PurePosixPath(relative).parts)
        resolved = candidate.resolve()
        if resolved != resolved_root and resolved_root not in resolved.parents:
            raise ContentEngineError(
                f"source binding for {source_id!r} resolves outside source_root: "
                f"{relative!r}"
            )

        if not resolved.is_file():
            raise ContentEngineError(
                f"declared source {source_id!r} is not bound to a readable file: {relative!r}"
            )

        key = str(resolved)
        if key in resolved_files:
            raise ContentEngineError(
                f"declared sources {resolved_files[key]!r} and {source_id!r} resolve to "
                "the same physical file; one file cannot be two declared sources"
            )
        resolved_files[key] = source_id

        measured = measure_source_bytes(resolved)
        if measured != source.source_sha256:
            raise ContentEngineError(
                f"declared source {source_id!r} failed raw-byte verification: declared "
                f"{source.source_sha256}, measured {measured} "
                f"({SOURCE_FILE_SHA256_ALGORITHM} over {SOURCE_FILE_SHA256_BASIS})"
            )

        verified.append(
            VerifiedSource(
                source_id=source_id,
                source_version=source.source_version,
                source_sha256=source.source_sha256,
                relative_source_path=relative,
                path=resolved,
            )
        )

    return tuple(verified)
