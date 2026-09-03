"""Content Pack contract objects (E2.1 v0.1) — fail-closed construction evidence.

Covers E2.1B §11 invariants 1-9 and 18, plus the contract's own minimality and
immutability claims. Invariants 10-17, 19 and 20 are proved in
`test_content_pack_identity_v0_1.py`.

Every test runs under `netguard`'s `guarded` decorator: credentials absent,
cloud SDK imports denied, outbound sockets denied. Plain test functions, so both
`pytest` and the stdlib `run_tests.py` collect them.
"""

from __future__ import annotations

import dataclasses
import hashlib

from app.modules.content_pack import (
    CONTENT_PACK_CONTRACT_VERSION,
    SUPPORTED_CONTRACT_VERSIONS,
    UNGOVERNED_SOURCE_ID,
    ContentPack,
    ContentPackError,
    SourceEntry,
)
from tests.netguard import guarded
from tests.util import raises

SHA_A = hashlib.sha256(b"source alpha bytes").hexdigest()
SHA_B = hashlib.sha256(b"source beta bytes").hexdigest()


def _entry(source_id: str = "alpha", version: str = "1.0.0", sha: str = SHA_A) -> SourceEntry:
    return SourceEntry(source_id=source_id, source_version=version, source_sha256=sha)


def _pack(**overrides) -> ContentPack:
    kwargs = {
        "pack_id": "ion_working_pack",
        "pack_version": "1.0.0",
        "sources": (_entry(),),
    }
    kwargs.update(overrides)
    return ContentPack.create(**kwargs)


# --------------------------------------------------------------------------- #
# §11.1-3 — pack-level identity fields
# --------------------------------------------------------------------------- #
@guarded
def test_i1_empty_pack_id_is_rejected():
    for value in ("", "   ", " ion_pack", "ion_pack ", None, 7):
        with raises(ContentPackError):
            _pack(pack_id=value)


@guarded
def test_i2_empty_pack_version_is_rejected():
    for value in ("", "   ", " 1.0.0", "1.0.0 ", None, 1):
        with raises(ContentPackError):
            _pack(pack_version=value)


@guarded
def test_i3_unsupported_contract_version_is_rejected():
    assert SUPPORTED_CONTRACT_VERSIONS == (CONTENT_PACK_CONTRACT_VERSION,)
    for value in ("0.2", "1.0", "v0.1", "", None):
        with raises(ContentPackError):
            _pack(contract_version=value)

    # The supported version constructs, and is what `create` defaults to.
    assert _pack().contract_version == CONTENT_PACK_CONTRACT_VERSION


# --------------------------------------------------------------------------- #
# §11.4-5 — the inventory itself
# --------------------------------------------------------------------------- #
@guarded
def test_i4_empty_source_inventory_is_rejected():
    with raises(ContentPackError):
        _pack(sources=())
    with raises(ContentPackError):
        _pack(sources=[])


@guarded
def test_i5_duplicate_source_id_is_rejected():
    # Same id, different bytes: the pack would otherwise describe two different
    # contents under one identity.
    with raises(ContentPackError):
        _pack(sources=(_entry("alpha", sha=SHA_A), _entry("alpha", sha=SHA_B)))
    # Same id, identical entry: still refused, never silently deduplicated.
    with raises(ContentPackError):
        _pack(sources=(_entry("alpha"), _entry("alpha")))


# --------------------------------------------------------------------------- #
# §11.6-9 — source entry fields
# --------------------------------------------------------------------------- #
@guarded
def test_i6_invalid_or_empty_source_id_is_rejected():
    for value in ("", "   ", " alpha", "alpha ", "Alpha", "alpha-1", "alpha.txt",
                  "_alpha", "corpus/alpha", "C:\\corpus\\alpha", None, 3):
        with raises(ContentPackError):
            _entry(source_id=value)

    # Declared logical identities in the registered-material alphabet construct.
    for value in ("alpha", "a", "a1", "sacred_economics_book_text", "x_9_y"):
        assert _entry(source_id=value).source_id == value


@guarded
def test_i7_source_id_unknown_is_rejected():
    assert UNGOVERNED_SOURCE_ID == "unknown"
    with raises(ContentPackError):
        _entry(source_id=UNGOVERNED_SOURCE_ID)


@guarded
def test_i8_empty_source_version_is_rejected():
    for value in ("", "   ", " 1.0.0", "1.0.0 ", None, 1.0):
        with raises(ContentPackError):
            _entry(version=value)


@guarded
def test_i9_source_sha256_must_be_exact_valid_sha256_hex():
    for value in (
        "",
        "  ",
        SHA_A.upper(),            # uppercase hex is not the canonical form
        SHA_A[:-1],               # 63 characters
        SHA_A + "0",              # 65 characters
        SHA_A[:-1] + "g",         # non-hexadecimal character
        "0x" + SHA_A[2:],
        " " + SHA_A,
        None,
        0,
    ):
        with raises(ContentPackError):
            _entry(sha=value)

    assert _entry(sha=SHA_B).source_sha256 == SHA_B


# --------------------------------------------------------------------------- #
# §11.18 — measured identity, never an unverified declaration
# --------------------------------------------------------------------------- #
@guarded
def test_i18_supplied_fingerprint_mismatch_fails_closed():
    pack = _pack()

    # Direct construction accepts a fingerprint, and verifies it by recomputing.
    rebuilt = ContentPack(
        contract_version=pack.contract_version,
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        sources=pack.sources,
        canonical_fingerprint=pack.canonical_fingerprint,
    )
    assert rebuilt == pack

    for wrong in (
        hashlib.sha256(b"not this pack").hexdigest(),
        pack.canonical_fingerprint[:-1] + ("0" if pack.canonical_fingerprint[-1] != "0" else "1"),
        "",
        None,
    ):
        with raises(ContentPackError):
            ContentPack(
                contract_version=pack.contract_version,
                pack_id=pack.pack_id,
                pack_version=pack.pack_version,
                sources=pack.sources,
                canonical_fingerprint=wrong,
            )


@guarded
def test_create_offers_no_route_for_an_unverified_fingerprint():
    """There is no parameter through which a caller could assert an identity."""
    import inspect

    parameters = inspect.signature(ContentPack.create).parameters
    assert "canonical_fingerprint" not in parameters
    assert set(parameters) == {"pack_id", "pack_version", "sources", "contract_version"}


# --------------------------------------------------------------------------- #
# Contract shape: minimal, immutable, canonically ordered
# --------------------------------------------------------------------------- #
@guarded
def test_the_declared_field_sets_are_exactly_the_contracted_minimum():
    assert [f.name for f in dataclasses.fields(SourceEntry)] == [
        "source_id",
        "source_version",
        "source_sha256",
    ]
    assert [f.name for f in dataclasses.fields(ContentPack)] == [
        "contract_version",
        "pack_id",
        "pack_version",
        "sources",
        "canonical_fingerprint",
    ]


@guarded
def test_both_objects_are_frozen():
    entry = _entry()
    pack = _pack()
    with raises(dataclasses.FrozenInstanceError):
        entry.source_sha256 = SHA_B
    with raises(dataclasses.FrozenInstanceError):
        pack.pack_version = "2.0.0"


@guarded
def test_create_orders_an_arbitrary_inventory_and_direct_construction_refuses_disorder():
    unordered = (_entry("gamma", sha=SHA_B), _entry("alpha", sha=SHA_A), _entry("beta", sha=SHA_B))
    pack = _pack(sources=unordered)
    assert [e.source_id for e in pack.sources] == ["alpha", "beta", "gamma"]

    # Direct construction refuses a mis-ordered inventory rather than repairing it.
    with raises(ContentPackError):
        ContentPack(
            contract_version=pack.contract_version,
            pack_id=pack.pack_id,
            pack_version=pack.pack_version,
            sources=tuple(reversed(pack.sources)),
            canonical_fingerprint=pack.canonical_fingerprint,
        )


@guarded
def test_sources_must_be_a_tuple_of_source_entries():
    with raises(ContentPackError):
        _pack(sources=({"source_id": "alpha", "source_version": "1", "source_sha256": SHA_A},))
    with raises(ContentPackError):
        _pack(sources="alpha")
    with raises(ContentPackError):
        ContentPack(
            contract_version=CONTENT_PACK_CONTRACT_VERSION,
            pack_id="ion_working_pack",
            pack_version="1.0.0",
            sources=[_entry()],           # a list, not the contracted tuple
            canonical_fingerprint=_pack().canonical_fingerprint,
        )


@guarded
def test_one_pack_id_and_version_cannot_stand_over_two_different_contents():
    """§5: a material source change must move the fingerprint, so the immutable
    release identity cannot silently remain the same over different content."""
    original = _pack(sources=(_entry("alpha", sha=SHA_A),))
    changed = _pack(sources=(_entry("alpha", sha=SHA_B),))

    assert original.pack_id == changed.pack_id
    assert original.pack_version == changed.pack_version
    assert original.canonical_fingerprint != changed.canonical_fingerprint

    # And the old identity cannot be re-asserted over the new inventory.
    with raises(ContentPackError):
        ContentPack(
            contract_version=changed.contract_version,
            pack_id=changed.pack_id,
            pack_version=changed.pack_version,
            sources=changed.sources,
            canonical_fingerprint=original.canonical_fingerprint,
        )
