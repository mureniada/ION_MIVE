"""Canonical Content Pack identity — the measured half of pack identity (E2.1).

This module answers exactly one question: given a declared source inventory,
what are its canonical bytes, and what is their digest? It is pure computation
over values the caller supplies.

    IT MEASURES A DECLARED INVENTORY.
    IT DOES NOT DISCOVER ONE.

Nothing here scans a directory, reads the local material registry, opens a
source file, invokes ingestion, or touches Qdrant. No value is derived from a
wall clock, a UUID, a random source, an environment variable or the filesystem.
The only inputs are the arguments passed in, so the same arguments always
produce the same bytes and the same digest on any machine.

Canonicalization profile
------------------------
`CANONICALIZATION_PROFILE` is an INTERNAL deterministic-profile identity, bound
for this version to `t4.jcs.serialize`. It is deliberately NOT a claim of
external RFC 8785 conformance: it names the byte rule this repository commits
to, so that a later change of implementation is a visible profile change rather
than a silent drift in identity.

Ordering
--------
Canonical source ordering is lexicographic by `source_id`. The governed
`source_id` alphabet (see `models.SOURCE_ID_PATTERN`) is a subset of ASCII, so
code-point order, UTF-16 code-unit order and byte order coincide on it and the
ordering rule cannot be read two ways. Payload property names are likewise
fixed ASCII, which is the domain on which the serializer's own UTF-16 key
ordering is unambiguous.

Division of responsibility with `models.py`
-------------------------------------------
This module validates only what determinism requires: the exact key set, string
values, and unique source ids. Governance semantics — the `source_id` alphabet,
the refusal of the literal "unknown", SHA-256 hexadecimal shape, supported
contract versions — belong to `models.py` and are not duplicated here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from t4 import jcs

#: Internal deterministic-profile identity. NOT an external conformance claim.
CANONICALIZATION_PROFILE = "ION_CONTENT_PACK_CANONICALIZATION_PROFILE_V0_1"
CANONICALIZATION_PROFILE_ID = "ION_JCS_V0_1"
CANONICALIZATION_IMPLEMENTATION = "t4.jcs.serialize"

FINGERPRINT_ALGORITHM = "SHA256"

#: The three fields that identify one source. Exactly these, in the canonical
#: entry; a fourth field would change the measured identity of every pack.
SOURCE_ENTRY_KEYS: tuple[str, ...] = ("source_id", "source_version", "source_sha256")

#: The four fields the fingerprint payload carries (E2.1B §6). Filesystem path,
#: mtime, timestamps, operator, Qdrant collection, point ids, chunk ids,
#: embedding model, index identity and activation state are deliberately absent
#: and have nowhere here to enter.
PAYLOAD_KEYS: tuple[str, ...] = ("contract_version", "pack_id", "pack_version", "sources")

__all__ = [
    "CANONICALIZATION_IMPLEMENTATION",
    "CANONICALIZATION_PROFILE",
    "CANONICALIZATION_PROFILE_ID",
    "ContentPackIdentityError",
    "FINGERPRINT_ALGORITHM",
    "PAYLOAD_KEYS",
    "SOURCE_ENTRY_KEYS",
    "canonical_bytes",
    "canonical_payload",
    "canonical_source_order",
    "compute_canonical_fingerprint",
]


class ContentPackIdentityError(ValueError):
    """Raised whenever a canonical identity cannot be computed as contracted.

    Every failure is closed. A missing field, an unexpected field, a non-string
    value, a whitespace-padded value or a duplicated source id is refused; none
    is trimmed, defaulted, deduplicated or coerced into a legal-looking value,
    because a repaired input would yield a digest that measures something the
    caller never declared.

    Module-local on purpose: this introduces no transport stage and no mapping
    onto the core error taxonomy.
    """


def _identity_text(value: Any, what: str) -> str:
    """Require a non-empty string carrying no leading/trailing whitespace."""
    if not isinstance(value, str) or not value:
        raise ContentPackIdentityError(f"{what} must be a non-empty string, found {value!r}")
    if value != value.strip():
        raise ContentPackIdentityError(
            f"{what} must carry no leading/trailing whitespace, found {value!r}"
        )
    return value


def _canonical_entry(source: Any, position: int) -> dict[str, str]:
    where = f"sources[{position}]"
    if not isinstance(source, Mapping):
        raise ContentPackIdentityError(
            f"{where} must be a mapping of the canonical source fields, "
            f"found {type(source).__name__}"
        )
    if set(source.keys()) != set(SOURCE_ENTRY_KEYS):
        raise ContentPackIdentityError(
            f"{where} must carry exactly the fields {list(SOURCE_ENTRY_KEYS)}, "
            f"found {sorted(source.keys())}"
        )
    return {key: _identity_text(source[key], f"{where}.{key}") for key in SOURCE_ENTRY_KEYS}


def canonical_source_order(sources: Sequence[Any]) -> tuple[dict[str, str], ...]:
    """Return the declared sources in canonical order: lexicographic by source_id.

    The input sequence's own order carries no identity: two callers that declare
    the same inventory in different orders measure the same pack. A duplicated
    `source_id` fails closed rather than resolving to a last-one-wins winner,
    since an inventory that names one source twice does not describe one set.
    """
    if isinstance(sources, (str, bytes, Mapping)):
        raise ContentPackIdentityError(
            f"sources must be a sequence of source mappings, found {type(sources).__name__}"
        )
    entries = [_canonical_entry(source, i) for i, source in enumerate(sources)]
    if not entries:
        raise ContentPackIdentityError(
            "sources must be non-empty: a pack declaring no source measures no content"
        )

    seen: set[str] = set()
    for entry in entries:
        source_id = entry["source_id"]
        if source_id in seen:
            raise ContentPackIdentityError(f"duplicate source_id in sources: {source_id!r}")
        seen.add(source_id)

    return tuple(sorted(entries, key=lambda entry: entry["source_id"]))


def canonical_payload(
    *,
    contract_version: str,
    pack_id: str,
    pack_version: str,
    sources: Sequence[Any],
) -> dict[str, Any]:
    """The exact structure the fingerprint covers — nothing more, nothing less."""
    payload = {
        "contract_version": _identity_text(contract_version, "contract_version"),
        "pack_id": _identity_text(pack_id, "pack_id"),
        "pack_version": _identity_text(pack_version, "pack_version"),
        "sources": [dict(entry) for entry in canonical_source_order(sources)],
    }
    # Structural assertion, not decoration: the payload key set IS the contract.
    if set(payload.keys()) != set(PAYLOAD_KEYS):  # pragma: no cover - unreachable by construction
        raise ContentPackIdentityError("canonical payload key set does not match the contract")
    return payload


def canonical_bytes(
    *,
    contract_version: str,
    pack_id: str,
    pack_version: str,
    sources: Sequence[Any],
) -> bytes:
    """The bytes the digest covers, under `CANONICALIZATION_PROFILE_ID`."""
    return jcs.serialize(
        canonical_payload(
            contract_version=contract_version,
            pack_id=pack_id,
            pack_version=pack_version,
            sources=sources,
        )
    )


def compute_canonical_fingerprint(
    *,
    contract_version: str,
    pack_id: str,
    pack_version: str,
    sources: Sequence[Any],
) -> str:
    """SHA-256, lowercase hexadecimal, over the canonical payload bytes."""
    return hashlib.sha256(
        canonical_bytes(
            contract_version=contract_version,
            pack_id=pack_id,
            pack_version=pack_version,
            sources=sources,
        )
    ).hexdigest()
