"""Canonical byte rule for E3 derived-index lifecycle receipts (v0.1).

Every lifecycle receipt — candidate materialization, measured store state,
structural verification, activation, rollback — binds a fingerprint over its
own declared/measured fields. This module supplies the one byte rule all of
them share:

    RECEIPT FINGERPRINT = SHA256(t4.jcs.serialize(canonical_payload))

`CANONICALIZATION_PROFILE_ID` is the same internal deterministic-profile
identity `derived_index.identity` already established (`ION_JCS_V0_1`), reused
here rather than reinvented — this is the "no new canonicalizer" rule: this
module contains no field-shape validation of its own, because the payload it
serializes has already been validated by the dataclass in `models.py` that
calls it.

    RECEIPT IDENTITY != EXPECTED DERIVED-INDEX IDENTITY

A receipt fingerprint (candidate, measured, verification, activation,
rollback) is an EVENT/AUDIT identity: several of these payloads legitimately
include their own event timestamp. It is never confused with, and never
substitutes for, `derived_index.ExpectedDerivedIndexDescriptor.derived_index_fingerprint`.

Nothing here opens a store, constructs an embedder, calls a provider, touches
the filesystem, reads a clock, or mints a UUID.
"""

from __future__ import annotations

import hashlib
from typing import Any

from t4 import jcs

#: Internal deterministic-profile identity, reused from `derived_index.identity`.
#: NOT an external conformance claim.
CANONICALIZATION_PROFILE = "ION_DERIVED_INDEX_LIFECYCLE_CANONICALIZATION_PROFILE_V0_1"
CANONICALIZATION_PROFILE_ID = "ION_JCS_V0_1"
CANONICALIZATION_IMPLEMENTATION = "t4.jcs.serialize"

FINGERPRINT_ALGORITHM = "SHA256"

__all__ = [
    "CANONICALIZATION_IMPLEMENTATION",
    "CANONICALIZATION_PROFILE",
    "CANONICALIZATION_PROFILE_ID",
    "FINGERPRINT_ALGORITHM",
    "canonical_bytes",
    "compute_fingerprint",
]


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """The exact bytes a lifecycle receipt fingerprint covers.

    `payload` must already be a plain, JSON-shaped mapping of already-validated
    values (the caller's dataclass owns validation); this function only applies
    the shared canonicalization rule.
    """
    return jcs.serialize(payload)


def compute_fingerprint(payload: dict[str, Any]) -> str:
    """SHA-256, lowercase hexadecimal, over the canonical payload bytes."""
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()
