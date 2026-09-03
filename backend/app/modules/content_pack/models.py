"""Canonical generic Content Pack contract vocabulary (v0.1).

A `ContentPack` is a DECLARED CONTENT IDENTITY object. It states, for one
immutable release, which sources the pack consists of and what those sources
measured. It is data, not a mechanism:

    IT IDENTIFIES DECLARED CONTENT.
    IT DOES NOT RETRIEVE, INGEST, INDEX OR ACTIVATE IT.

Boundaries this contract keeps
------------------------------
    CONTENT PACK  !=  QDRANT          nothing here imports, names or needs a
                                      vector store; identity is computable and
                                      verifiable with no Qdrant in existence.
    CONTENT PACK  !=  CONTEXT PACK    a Context Pack is per-question and its id
                                      derives from the question; a Content Pack
                                      is per-release and its identity derives
                                      from declared source bytes alone.
    PACK IDENTITY !=  INDEX IDENTITY  no index fingerprint, embedding model,
                                      chunk id or point id has a field here.
    DIRECTORY CONTENTS != DECLARED PACK CONTENTS
                                      this object accepts an explicit inventory
                                      and cannot discover one. It never scans a
                                      directory, reads the material registry,
                                      opens a source file or invokes ingestion,
                                      so a pack cannot silently acquire identity
                                      from whatever files happen to be present.

Translating an authorized registry or corpus into `SourceEntry` values, and
reconciling declared identity against measured bytes on disk, is an adapter
boundary. That adapter is deliberately absent at v0.1.

Measured, not declared
----------------------
`canonical_fingerprint` is never taken on trust. `ContentPack.create` computes
it, and `__post_init__` recomputes and requires exact equality on every
construction path, so a caller cannot assert an identity its own inventory does
not produce:

    MEASURED IDENTITY  !=  UNVERIFIED DECLARATION

Consequently `pack_id` + `pack_version` cannot lawfully bind to two different
fingerprints: any material source change moves the fingerprint, and the release
identity must move with it rather than silently standing over new content.

This module imports the standard library, its sibling `identity` module, and
the repository's canonical serializer through it. No Core, container, Settings,
retrieval, Qdrant, local layer, evidence provenance, model gateway, session or
turn-record entry point is reachable from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from .identity import (
    FINGERPRINT_ALGORITHM,
    ContentPackIdentityError,
    compute_canonical_fingerprint,
)

CONTENT_PACK_CONTRACT_ID = "ION_CONTENT_PACK_V0_1"
CONTENT_PACK_CONTRACT_VERSION = "0.1"

#: Exactly one contract version exists at v0.1. An unrecognized version is
#: refused rather than accepted-and-ignored: a pack whose contract this code
#: does not implement cannot be given a meaning it may not have.
SUPPORTED_CONTRACT_VERSIONS: tuple[str, ...] = (CONTENT_PACK_CONTRACT_VERSION,)

#: Declared logical source identity. The alphabet is the repository's existing
#: registered-material precedent (`local_layer.registry` material ids), reused
#: rather than reinvented. It is deliberately NOT a filename-derived slug, NOT
#: a Qdrant identity, and NOT a filesystem path.
SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")

#: The literal that already means "unidentified" elsewhere in this repository.
#: It is a non-identity and is refused as a governed source id.
UNGOVERNED_SOURCE_ID = "unknown"

#: SHA-256 over the COMPLETE RAW SOURCE FILE BYTES, lowercase hexadecimal.
#: The basis is the one already frozen in the retrieval source-provenance
#: contract; no text normalization enters source-byte identity, so the same
#: exact bytes always give the same value and any byte change gives another.
SOURCE_SHA256_ALGORITHM = FINGERPRINT_ALGORITHM
SOURCE_SHA256_BASIS = "COMPLETE_RAW_SOURCE_FILE_BYTES"
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

__all__ = [
    "CONTENT_PACK_CONTRACT_ID",
    "CONTENT_PACK_CONTRACT_VERSION",
    "ContentPack",
    "ContentPackError",
    "SOURCE_ID_PATTERN",
    "SOURCE_SHA256_ALGORITHM",
    "SOURCE_SHA256_BASIS",
    "SUPPORTED_CONTRACT_VERSIONS",
    "SourceEntry",
    "UNGOVERNED_SOURCE_ID",
]


class ContentPackError(ValueError):
    """Raised whenever a Content Pack object cannot be constructed as contracted.

    Every failure is closed. A missing, malformed, blank, whitespace-padded,
    duplicated, mis-ordered or unverifiable value raises here; none is silently
    trimmed, defaulted, reordered or coerced.

    Module-local on purpose, in the same spirit as the Execution Profile
    contract: no transport stage is introduced and nothing is mapped onto the
    core error taxonomy. How a caller responds to a pack that fails to
    construct is a later wiring decision, not this contract's business.
    """


def _shape_checked_text(value: Any, what: str) -> str:
    """Require a non-empty string carrying no leading/trailing whitespace."""
    if not isinstance(value, str) or not value:
        raise ContentPackError(f"{what} must be a non-empty string, found {value!r}")
    if value != value.strip():
        raise ContentPackError(
            f"{what} must carry no leading/trailing whitespace, found {value!r}"
        )
    return value


@dataclass(frozen=True, kw_only=True)
class SourceEntry:
    """One declared source in a Content Pack's inventory.

    Minimum field set only. Deliberately absent, with no field to carry them: a
    filesystem path, a filename, a title, an mtime, a collection timestamp, an
    operator or collector name, a byte length, a chunk count, an embedding
    model, a Qdrant collection or point id, an activation state, and any
    retrieval score. Those belong to other lifecycle or derived-state layers.

    The three fields present are the whole of E2.1 source provenance: which
    logical source this is, which declared version of it, and what its complete
    raw bytes measured.
    """

    source_id: str
    source_version: str
    source_sha256: str

    def __post_init__(self) -> None:
        _shape_checked_text(self.source_id, "source_id")
        if self.source_id == UNGOVERNED_SOURCE_ID:
            raise ContentPackError(
                f"source_id {UNGOVERNED_SOURCE_ID!r} is a non-identity and is not governed"
            )
        if not SOURCE_ID_PATTERN.fullmatch(self.source_id):
            raise ContentPackError(
                "source_id must be a declared logical identity matching "
                f"{SOURCE_ID_PATTERN.pattern!r} — not a filename, path or store "
                f"identity — found {self.source_id!r}"
            )

        _shape_checked_text(self.source_version, "source_version")

        _shape_checked_text(self.source_sha256, "source_sha256")
        if not _SHA256_HEX.fullmatch(self.source_sha256):
            raise ContentPackError(
                "source_sha256 must be 64 lowercase hexadecimal characters "
                f"({SOURCE_SHA256_ALGORITHM} over {SOURCE_SHA256_BASIS}), "
                f"found {self.source_sha256!r}"
            )

    def canonical_mapping(self) -> dict[str, str]:
        """This entry as the plain mapping the identity layer canonicalizes."""
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True, kw_only=True)
class ContentPack:
    """One immutable, deterministically identified Content Pack release.

    Minimum field set only. Deliberately absent, with no field to carry them: a
    source directory, a registry reference, a created-at timestamp, an author, a
    Qdrant collection, an index fingerprint, an embedding model, chunk or point
    lineage, an activation or publication state, and a dialogue or execution
    profile binding. Source-to-chunk-to-embedding-to-point lineage is a later,
    separately authorized layer's concern and is not stated, implied or
    reserved here.

    `sources` must already stand in canonical order — lexicographic by
    `source_id`. Direct construction refuses a mis-ordered inventory rather than
    quietly reordering it, so the canonical order stays a checked property of
    the object instead of a side effect nobody observed; `create` is the
    ordering path for callers holding an arbitrary sequence.
    """

    contract_version: str
    pack_id: str
    pack_version: str
    sources: tuple[SourceEntry, ...]
    canonical_fingerprint: str

    def __post_init__(self) -> None:
        _shape_checked_text(self.contract_version, "contract_version")
        if self.contract_version not in SUPPORTED_CONTRACT_VERSIONS:
            raise ContentPackError(
                "contract_version must be one of "
                f"{list(SUPPORTED_CONTRACT_VERSIONS)}, found {self.contract_version!r}"
            )

        _shape_checked_text(self.pack_id, "pack_id")
        _shape_checked_text(self.pack_version, "pack_version")

        if not isinstance(self.sources, tuple):
            raise ContentPackError(
                f"sources must be supplied as a tuple, found {type(self.sources).__name__}"
            )
        if not self.sources:
            raise ContentPackError(
                "sources must be non-empty: a pack declaring no source identifies no content"
            )
        for position, entry in enumerate(self.sources):
            if not isinstance(entry, SourceEntry):
                raise ContentPackError(
                    f"sources[{position}] must be a SourceEntry, found "
                    f"{type(entry).__name__}"
                )

        source_ids = [entry.source_id for entry in self.sources]
        seen: set[str] = set()
        for source_id in source_ids:
            if source_id in seen:
                raise ContentPackError(f"duplicate source_id in sources: {source_id!r}")
            seen.add(source_id)

        if source_ids != sorted(source_ids):
            raise ContentPackError(
                "sources must stand in canonical order (lexicographic by source_id); "
                f"found {source_ids!r}. Use ContentPack.create to order an "
                "arbitrary inventory."
            )

        _shape_checked_text(self.canonical_fingerprint, "canonical_fingerprint")
        measured = self._measure(
            contract_version=self.contract_version,
            pack_id=self.pack_id,
            pack_version=self.pack_version,
            sources=self.sources,
        )
        if self.canonical_fingerprint != measured:
            raise ContentPackError(
                "canonical_fingerprint does not match the identity measured from "
                f"this pack's own inventory: declared {self.canonical_fingerprint!r}, "
                f"measured {measured!r}"
            )

    @staticmethod
    def _measure(
        *,
        contract_version: str,
        pack_id: str,
        pack_version: str,
        sources: Sequence[SourceEntry],
    ) -> str:
        try:
            return compute_canonical_fingerprint(
                contract_version=contract_version,
                pack_id=pack_id,
                pack_version=pack_version,
                sources=[entry.canonical_mapping() for entry in sources],
            )
        except ContentPackIdentityError as exc:
            raise ContentPackError(f"canonical identity could not be measured: {exc}") from exc

    @classmethod
    def create(
        cls,
        *,
        pack_id: str,
        pack_version: str,
        sources: Sequence[SourceEntry],
        contract_version: str = CONTENT_PACK_CONTRACT_VERSION,
    ) -> "ContentPack":
        """Build a pack from an explicit inventory, measuring its identity here.

        The caller supplies the declared inventory in any order and supplies no
        fingerprint at all: there is no parameter through which an unverified
        identity could be introduced.
        """
        if isinstance(sources, (str, bytes)):
            raise ContentPackError(
                f"sources must be a sequence of SourceEntry, found {type(sources).__name__}"
            )
        entries = tuple(sources)
        for position, entry in enumerate(entries):
            if not isinstance(entry, SourceEntry):
                raise ContentPackError(
                    f"sources[{position}] must be a SourceEntry, found "
                    f"{type(entry).__name__}"
                )
        ordered = tuple(sorted(entries, key=lambda entry: entry.source_id))

        return cls(
            contract_version=contract_version,
            pack_id=pack_id,
            pack_version=pack_version,
            sources=ordered,
            canonical_fingerprint=cls._measure(
                contract_version=contract_version,
                pack_id=pack_id,
                pack_version=pack_version,
                sources=ordered,
            ),
        )
