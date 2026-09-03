"""Content Engine contract vocabulary (v0.1) — build objects only.

The Content Engine transforms a closed, canonical Content Pack plus an explicit
runtime binding into a derived, retrieval-ready record set. It states a BUILD,
and nothing else:

    IT BUILDS A DERIVED RECORD SET.
    IT DOES NOT EMBED, WRITE, INDEX, VERIFY OR ACTIVATE.

Boundaries this contract keeps
------------------------------
    CONTENT BUILD RESULT != DERIVED INDEX IDENTITY
    CONTENT BUILD RESULT != ACTIVATION RECEIPT
    SOURCE ORIGIN        != SOURCE IDENTITY
    PHYSICAL SOURCE PATH != CANONICAL SOURCE IDENTITY
    SOURCE ROOT          != CONTENT PACK IDENTITY
    QDRANT               =  DERIVED RETRIEVAL REPRESENTATION, never content authority

E2.3 owns pack-to-derived-index identity; E3 owns verify / activate / rollback.
Neither has a field here, and `RECORD_KEYS` is a closed set precisely so a
build-, index-, embedding- or activation-shaped field cannot appear in a record
without failing construction.

Identity, origin and location are three different things and stay that way. The
Content Pack states identity (`source_id`). The binding states a relative POSIX
location beneath a runtime `source_root`. The provenance origin is derived from
that relative location. No absolute machine path enters a record, a fingerprint,
this result, or the Content Pack.

Time
----
`provenance_created_at` is an explicit BUILD INPUT, supplied by the caller and
carried here verbatim. Nothing in this package reads a clock. It is the
provenance-materialization time of this build — not a source file's creation
time, not the pack's version time, and not an activation time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..retrieval.evidence_fingerprint import ALGORITHM as EVIDENCE_FINGERPRINT_ALGORITHM
from ..retrieval.evidence_fingerprint import PROFILE_ID as EVIDENCE_FINGERPRINT_PROFILE_ID
from ..retrieval.source_provenance import (
    SOURCE_FILE_SHA256_ALGORITHM,
    SOURCE_FILE_SHA256_BASIS,
)

CONTENT_ENGINE_CONTRACT_ID = "ION_CONTENT_ENGINE_V0_1"
CONTENT_ENGINE_CONTRACT_VERSION = "0.1"
CONTENT_ENGINE_VERSION = "0.1"

SUPPORTED_CONTRACT_VERSIONS: tuple[str, ...] = (CONTENT_ENGINE_CONTRACT_VERSION,)

#: The closed key set every derived record carries. Exactly these, always.
#: Nothing may be added here to accommodate a later lifecycle layer: an index
#: identity, an embedding identity, a build fingerprint or an activation state
#: has no place to go, and a record carrying one fails construction.
RECORD_KEYS: tuple[str, ...] = (
    "document_id",
    "source_id",
    "source_version",
    "title",
    "content",
    "page",
    "chunk_id",
    "checksum",
    "ingestion_version",
    "evidence_fingerprint",
    "evidence_fingerprint_algorithm",
    "evidence_fingerprint_profile_id",
    "ion_source_provenance",
    "ion_canonical_provenance",
)

#: Named here only so the prohibition is testable rather than argued. None of
#: these may appear as a result field or a record key at v0.1 (E2.3 / E3 own them).
PROHIBITED_IDENTITY_FIELDS: tuple[str, ...] = (
    "activation_state",
    "activation_timestamp",
    "activated_at",
    "build_fingerprint",
    "build_id",
    "collection",
    "derived_set_fingerprint",
    "embedding_identity",
    "embedding_model",
    "index_fingerprint",
    "index_id",
    "qdrant_collection",
    "rollback_id",
    "source_root",
    "verification_status",
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

__all__ = [
    "CONTENT_ENGINE_CONTRACT_ID",
    "CONTENT_ENGINE_CONTRACT_VERSION",
    "CONTENT_ENGINE_VERSION",
    "ContentBuildResult",
    "ContentEngineError",
    "PROHIBITED_IDENTITY_FIELDS",
    "RECORD_KEYS",
    "SUPPORTED_CONTRACT_VERSIONS",
    "VerifiedSource",
]


class ContentEngineError(ValueError):
    """Raised whenever a Content Engine object cannot be built as contracted.

    Every failure is closed. A missing binding, an extra binding, an absolute or
    escaping relative path, an absent file, a digest mismatch, a malformed record
    or a prohibited field raises here, and a build that raises produces no
    partial result: there is no "mostly built" content set.

    Module-local on purpose, in the same spirit as the Content Pack and
    Execution Profile contracts: no transport stage is introduced and nothing
    is mapped onto the core error taxonomy.
    """


def _shape_checked_text(value: Any, what: str) -> str:
    """Require a non-empty string carrying no leading/trailing whitespace."""
    if not isinstance(value, str) or not value:
        raise ContentEngineError(f"{what} must be a non-empty string, found {value!r}")
    if value != value.strip():
        raise ContentEngineError(
            f"{what} must carry no leading/trailing whitespace, found {value!r}"
        )
    return value


def _sha256_hex(value: Any, what: str) -> str:
    _shape_checked_text(value, what)
    if not _SHA256_HEX.fullmatch(value):
        raise ContentEngineError(
            f"{what} must be 64 lowercase hexadecimal characters "
            f"({SOURCE_FILE_SHA256_ALGORITHM} over {SOURCE_FILE_SHA256_BASIS}), "
            f"found {value!r}"
        )
    return value


@dataclass(frozen=True, kw_only=True)
class VerifiedSource:
    """One declared source, located beneath a runtime root and byte-verified.

    `source_id`, `source_version` and `source_sha256` are carried through from
    the Content Pack unchanged — this object never re-derives them.

    `relative_source_path` is the declared POSIX location beneath the build's
    `source_root`. It is where the bytes were found, never what the source *is*;
    the provenance origin is derived from it, and it is machine-independent by
    construction.

    `path` is the absolute physical location on this machine: a runtime fact,
    deliberately excluded from every identity, fingerprint, record and result.

    Constructing one asserts nothing about the file. `resolver.resolve_and_verify`
    is what establishes that the path stays inside the root, that the file exists,
    and that its complete raw bytes hash to the declared digest.
    """

    source_id: str
    source_version: str
    source_sha256: str
    relative_source_path: str
    path: Path

    def __post_init__(self) -> None:
        _shape_checked_text(self.source_id, "source_id")
        _shape_checked_text(self.source_version, "source_version")
        _sha256_hex(self.source_sha256, "source_sha256")
        _shape_checked_text(self.relative_source_path, "relative_source_path")
        if not isinstance(self.path, Path):
            raise ContentEngineError(
                f"path must be a pathlib.Path, found {type(self.path).__name__}"
            )


def _validate_record(record: Any, position: int, *, provenance_created_at: str) -> dict[str, Any]:
    where = f"records[{position}]"
    if not isinstance(record, Mapping):
        raise ContentEngineError(f"{where} must be a mapping, found {type(record).__name__}")
    if set(record.keys()) != set(RECORD_KEYS):
        missing = sorted(set(RECORD_KEYS) - set(record.keys()))
        extra = sorted(set(record.keys()) - set(RECORD_KEYS))
        raise ContentEngineError(
            f"{where} must carry exactly the closed record key set; "
            f"missing {missing}, unexpected {extra}"
        )

    _shape_checked_text(record["document_id"], f"{where}.document_id")
    _shape_checked_text(record["source_id"], f"{where}.source_id")
    _shape_checked_text(record["source_version"], f"{where}.source_version")
    _shape_checked_text(record["chunk_id"], f"{where}.chunk_id")
    _sha256_hex(record["checksum"], f"{where}.checksum")
    _sha256_hex(record["evidence_fingerprint"], f"{where}.evidence_fingerprint")

    if record["evidence_fingerprint_algorithm"] != EVIDENCE_FINGERPRINT_ALGORITHM:
        raise ContentEngineError(f"{where}.evidence_fingerprint_algorithm mismatch")
    if record["evidence_fingerprint_profile_id"] != EVIDENCE_FINGERPRINT_PROFILE_ID:
        raise ContentEngineError(f"{where}.evidence_fingerprint_profile_id mismatch")

    if not isinstance(record["content"], str) or not record["content"]:
        raise ContentEngineError(f"{where}.content must be a non-empty string")
    if not isinstance(record["title"], str):
        raise ContentEngineError(f"{where}.title must be a string")

    page = record["page"]
    if page is not None and (not isinstance(page, int) or isinstance(page, bool)):
        raise ContentEngineError(f"{where}.page must be an integer or null")

    for key in ("ion_source_provenance", "ion_canonical_provenance"):
        if not isinstance(record[key], Mapping) or not record[key]:
            raise ContentEngineError(
                f"{where}.{key} must be a non-empty mapping: provenance is "
                "mandatory inside the Content Engine, never optional"
            )

    # The bound build time is the one every record's provenance was materialized
    # under. A record claiming another time did not come from this build.
    record_created_at = record["ion_source_provenance"].get("provenance_created_at")
    if record_created_at != provenance_created_at:
        raise ContentEngineError(
            f"{where}.ion_source_provenance.provenance_created_at is "
            f"{record_created_at!r}, which does not match the build's explicit "
            f"provenance_created_at {provenance_created_at!r}"
        )

    return dict(record)


@dataclass(frozen=True, kw_only=True)
class ContentBuildResult:
    """One deterministic build of one Content Pack into derived records.

    It binds the derived records to the exact Content Pack they came from —
    `pack_id`, `pack_version` and `pack_canonical_fingerprint` are carried
    verbatim from that pack, never recomputed here — states the chunk parameters
    under which the records were produced, and binds the explicit
    `provenance_created_at` those records' mandatory provenance was materialized
    under.

    `provenance_created_at` is here because the build could not have produced its
    mandatory provenance without it; it is a bound input, not a minted fact, and
    is neither a source file time, a pack version time, nor an activation time.

    Deliberately absent, with no field to carry them: build id, build or
    derived-set fingerprint, index id or fingerprint, Qdrant collection,
    embedding or embedding-model identity, activation state or timestamp,
    verification status, rollback identity, and the machine `source_root`.
    Those belong to E2.3, to E3, or to nowhere at all.

    `record_count`, `source_count` and `source_ids` are derived conveniences
    computed from `records`; they are properties, not identity fields.
    """

    content_engine_contract_version: str
    content_engine_version: str
    pack_id: str
    pack_version: str
    pack_canonical_fingerprint: str
    chunk_chars: int
    overlap: int
    provenance_created_at: str
    records: tuple[dict[str, Any], ...] = field(default=())

    def __post_init__(self) -> None:
        _shape_checked_text(
            self.content_engine_contract_version, "content_engine_contract_version"
        )
        if self.content_engine_contract_version not in SUPPORTED_CONTRACT_VERSIONS:
            raise ContentEngineError(
                "content_engine_contract_version must be one of "
                f"{list(SUPPORTED_CONTRACT_VERSIONS)}, "
                f"found {self.content_engine_contract_version!r}"
            )
        _shape_checked_text(self.content_engine_version, "content_engine_version")
        if self.content_engine_version != CONTENT_ENGINE_VERSION:
            raise ContentEngineError(
                f"content_engine_version must be {CONTENT_ENGINE_VERSION!r}, "
                f"found {self.content_engine_version!r}"
            )

        _shape_checked_text(self.pack_id, "pack_id")
        _shape_checked_text(self.pack_version, "pack_version")
        _sha256_hex(self.pack_canonical_fingerprint, "pack_canonical_fingerprint")
        _shape_checked_text(self.provenance_created_at, "provenance_created_at")

        if not isinstance(self.chunk_chars, int) or isinstance(self.chunk_chars, bool):
            raise ContentEngineError("chunk_chars must be an integer")
        if not isinstance(self.overlap, int) or isinstance(self.overlap, bool):
            raise ContentEngineError("overlap must be an integer")
        if self.chunk_chars <= 0:
            raise ContentEngineError("chunk_chars must be > 0")
        if self.overlap < 0 or self.overlap >= self.chunk_chars:
            raise ContentEngineError("overlap must satisfy 0 <= overlap < chunk_chars")

        if not isinstance(self.records, tuple):
            raise ContentEngineError(
                f"records must be supplied as a tuple, found {type(self.records).__name__}"
            )
        if not self.records:
            raise ContentEngineError(
                "records must be non-empty: a build that derived nothing is not a build"
            )

        seen: set[str] = set()
        for position, record in enumerate(self.records):
            validated = _validate_record(
                record, position, provenance_created_at=self.provenance_created_at
            )
            document_id = validated["document_id"]
            if document_id in seen:
                raise ContentEngineError(f"duplicate document_id in records: {document_id!r}")
            seen.add(document_id)

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def source_count(self) -> int:
        return len({record["source_id"] for record in self.records})

    @property
    def source_ids(self) -> tuple[str, ...]:
        """Declared source ids present in the build, in canonical order."""
        return tuple(sorted({record["source_id"] for record in self.records}))
