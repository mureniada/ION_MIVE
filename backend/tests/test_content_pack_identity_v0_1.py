"""Canonical Content Pack identity (E2.1 v0.1) — determinism and independence.

Covers E2.1B §11 invariants 10-17, 19 and 20, plus the canonical payload's own
closure: exactly four payload fields, exactly three source fields, and no
filesystem, network, store or clock input anywhere in the computation.

Independence is proved by mechanism, not by the absence of an error:

* structurally, over the package's own source, so a future import that reaches
  for Qdrant, a socket, the filesystem or `app.modules.retrieval` fails this
  test rather than passing unnoticed;
* at runtime, with `builtins.open` and `io.open` replaced by a raiser while the
  fingerprint is computed, and with `netguard` denying cloud imports, outbound
  sockets and cloud credentials for every test in this module.

Plain test functions, so both `pytest` and the stdlib `run_tests.py` collect them.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import io
import json
import sys
from pathlib import Path

from app.modules.content_pack import (
    CANONICALIZATION_IMPLEMENTATION,
    CANONICALIZATION_PROFILE_ID,
    CONTENT_PACK_CONTRACT_VERSION,
    FINGERPRINT_ALGORITHM,
    PAYLOAD_KEYS,
    SOURCE_ENTRY_KEYS,
    ContentPack,
    ContentPackIdentityError,
    SourceEntry,
    canonical_bytes,
    canonical_payload,
    canonical_source_order,
    compute_canonical_fingerprint,
)
from tests.netguard import BLOCKED_MODULE_PREFIXES, guarded
from tests.util import raises

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "app" / "modules" / "content_pack"

#: Everything the content_pack package may import from outside itself. `t4` is
#: the repository's canonical serializer, bound deliberately (E2.1B §7); every
#: other entry is standard library.
PERMITTED_ABSOLUTE_IMPORTS = frozenset({
    "__future__", "collections", "dataclasses", "hashlib", "re", "t4", "typing",
})

SHA_A = hashlib.sha256(b"source alpha bytes").hexdigest()
SHA_B = hashlib.sha256(b"source beta bytes").hexdigest()
SHA_C = hashlib.sha256(b"source gamma bytes").hexdigest()


def _entry(source_id: str = "alpha", version: str = "1.0.0", sha: str = SHA_A) -> SourceEntry:
    return SourceEntry(source_id=source_id, source_version=version, source_sha256=sha)


def _fingerprint(**overrides) -> str:
    kwargs = {
        "contract_version": CONTENT_PACK_CONTRACT_VERSION,
        "pack_id": "ion_working_pack",
        "pack_version": "1.0.0",
        "sources": [_entry().canonical_mapping()],
    }
    kwargs.update(overrides)
    return compute_canonical_fingerprint(**kwargs)


# --------------------------------------------------------------------------- #
# §11.10-11 — ordering
# --------------------------------------------------------------------------- #
@guarded
def test_i10_input_source_ordering_does_not_alter_the_fingerprint():
    a, b, c = (
        _entry("alpha", sha=SHA_A).canonical_mapping(),
        _entry("beta", "2.1", SHA_B).canonical_mapping(),
        _entry("gamma", "0.0.1", SHA_C).canonical_mapping(),
    )
    orderings = ([a, b, c], [c, b, a], [b, a, c], [c, a, b], [b, c, a], [a, c, b])
    fingerprints = {_fingerprint(sources=order) for order in orderings}
    assert len(fingerprints) == 1, f"input order moved the fingerprint: {fingerprints}"

    # Same property through the contract object.
    packs = {
        ContentPack.create(
            pack_id="ion_working_pack",
            pack_version="1.0.0",
            sources=[_entry(e["source_id"], e["source_version"], e["source_sha256"])
                     for e in order],
        ).canonical_fingerprint
        for order in orderings
    }
    assert packs == fingerprints


@guarded
def test_i11_canonical_source_ordering_is_stable_and_lexicographic_by_source_id():
    entries = [
        _entry("gamma", sha=SHA_C).canonical_mapping(),
        _entry("alpha", sha=SHA_A).canonical_mapping(),
        _entry("beta", sha=SHA_B).canonical_mapping(),
        _entry("alpha_2", sha=SHA_A).canonical_mapping(),
    ]
    ordered = canonical_source_order(entries)
    assert [e["source_id"] for e in ordered] == ["alpha", "alpha_2", "beta", "gamma"]

    # Stable: ordering an already-ordered inventory changes nothing, repeatedly.
    assert canonical_source_order(list(ordered)) == ordered
    assert canonical_source_order(list(reversed(ordered))) == ordered

    # A duplicated source id fails closed rather than resolving to a winner.
    with raises(ContentPackIdentityError):
        canonical_source_order([entries[0], entries[0]])


# --------------------------------------------------------------------------- #
# §11.12-16 — every identity-bearing field moves the fingerprint
# --------------------------------------------------------------------------- #
@guarded
def test_i12_any_source_sha256_change_alters_the_fingerprint():
    base = _fingerprint()
    changed = _fingerprint(sources=[_entry(sha=SHA_B).canonical_mapping()])
    assert changed != base

    # A single hexadecimal character is enough.
    nudged = SHA_A[:-1] + ("0" if SHA_A[-1] != "0" else "1")
    assert _fingerprint(sources=[_entry(sha=nudged).canonical_mapping()]) != base


@guarded
def test_i13_source_id_change_alters_the_fingerprint():
    assert _fingerprint(sources=[_entry("beta").canonical_mapping()]) != _fingerprint()


@guarded
def test_i14_source_version_change_alters_the_fingerprint():
    assert _fingerprint(sources=[_entry(version="1.0.1").canonical_mapping()]) != _fingerprint()


@guarded
def test_i15_pack_id_change_alters_the_fingerprint():
    assert _fingerprint(pack_id="ion_other_pack") != _fingerprint()


@guarded
def test_i16_pack_version_change_alters_the_fingerprint():
    assert _fingerprint(pack_version="1.0.1") != _fingerprint()


# --------------------------------------------------------------------------- #
# §11.17 — determinism
# --------------------------------------------------------------------------- #
@guarded
def test_i17_canonical_fingerprint_recomputation_is_deterministic():
    values = {_fingerprint() for _ in range(25)}
    assert len(values) == 1
    value = values.pop()
    assert len(value) == 64 and value == value.lower()
    assert all(ch in "0123456789abcdef" for ch in value)

    # The digest is exactly SHA-256 over the canonical bytes — recomputable
    # from the bytes alone, with nothing else mixed in.
    raw = canonical_bytes(
        contract_version=CONTENT_PACK_CONTRACT_VERSION,
        pack_id="ion_working_pack",
        pack_version="1.0.0",
        sources=[_entry().canonical_mapping()],
    )
    assert hashlib.sha256(raw).hexdigest() == value
    assert FINGERPRINT_ALGORITHM == "SHA256"


# --------------------------------------------------------------------------- #
# §11.19-20 — independence from Qdrant, filesystem and network
# --------------------------------------------------------------------------- #
@guarded
def test_i19_no_qdrant_or_cloud_sdk_is_imported_or_required():
    _fingerprint()
    ContentPack.create(pack_id="ion_working_pack", pack_version="1.0.0", sources=[_entry()])

    for prefix in BLOCKED_MODULE_PREFIXES:
        assert prefix not in sys.modules, f"{prefix} was imported during identity computation"
    assert "qdrant_client" in BLOCKED_MODULE_PREFIXES  # the guard really covers it


@guarded
def test_i19_the_package_source_reaches_no_store_network_or_product_module():
    modules = sorted(PACKAGE_DIR.glob("*.py"))
    assert modules, f"no modules found under {PACKAGE_DIR}"

    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        absolute: set[str] = set()
        relative: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                absolute.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    absolute.add(node.module.split(".")[0])
                else:
                    relative.add(node.module or "")

        forbidden = absolute & {
            "app", "os", "io", "pathlib", "shutil", "subprocess", "socket", "http",
            "urllib", "requests", "httpx", "ssl", "time", "datetime", "random",
            "uuid", "openai", "google", "qdrant_client", "sentence_transformers",
        }
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}"

        unexpected = absolute - PERMITTED_ABSOLUTE_IMPORTS
        assert not unexpected, f"{path.name} imports unreviewed module(s) {sorted(unexpected)}"

        # Relative imports stay inside this package: no reach into a sibling
        # module such as retrieval, local_layer or evidence_provenance.
        assert relative <= {"identity", "models"}, f"{path.name} reaches {sorted(relative)}"

        # No file is opened anywhere in the package.
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "open" not in calls, f"{path.name} calls open()"


@guarded
def test_i20_no_filesystem_access_occurs_during_identity_calculation():
    """`open` is removed for the duration; the computation must not notice."""

    def _denied(*_args, **_kwargs):
        raise AssertionError("identity calculation attempted to open a file")

    original_builtin, original_io = builtins.open, io.open
    builtins.open = _denied
    io.open = _denied
    try:
        value = _fingerprint()
        pack = ContentPack.create(
            pack_id="ion_working_pack", pack_version="1.0.0", sources=[_entry()]
        )
    finally:
        builtins.open = original_builtin
        io.open = original_io

    assert pack.canonical_fingerprint == value


# --------------------------------------------------------------------------- #
# Payload closure and the canonicalization profile binding
# --------------------------------------------------------------------------- #
@guarded
def test_the_fingerprint_payload_carries_exactly_the_contracted_fields():
    payload = canonical_payload(
        contract_version=CONTENT_PACK_CONTRACT_VERSION,
        pack_id="ion_working_pack",
        pack_version="1.0.0",
        sources=[_entry().canonical_mapping()],
    )
    assert set(payload) == set(PAYLOAD_KEYS) == {
        "contract_version", "pack_id", "pack_version", "sources",
    }
    assert set(payload["sources"][0]) == set(SOURCE_ENTRY_KEYS) == {
        "source_id", "source_version", "source_sha256",
    }

    # Nothing from another lifecycle layer can be present, because there is no
    # field for it: assert the closure explicitly rather than trusting review.
    serialized = canonical_bytes(
        contract_version=CONTENT_PACK_CONTRACT_VERSION,
        pack_id="ion_working_pack",
        pack_version="1.0.0",
        sources=[_entry().canonical_mapping()],
    ).decode("utf-8")
    for absent in (
        "path", "mtime", "created_at", "collector", "operator", "collection",
        "point_id", "chunk", "embedding", "index", "activation", "qdrant",
    ):
        assert absent not in serialized, f"{absent!r} leaked into the canonical payload"


@guarded
def test_an_unexpected_or_missing_source_field_fails_closed():
    good = _entry().canonical_mapping()
    with raises(ContentPackIdentityError):
        canonical_source_order([{**good, "path": "corpus/alpha.txt"}])
    with raises(ContentPackIdentityError):
        canonical_source_order([{k: v for k, v in good.items() if k != "source_version"}])
    with raises(ContentPackIdentityError):
        canonical_source_order([{**good, "source_id": ""}])
    with raises(ContentPackIdentityError):
        canonical_source_order([])
    with raises(ContentPackIdentityError):
        canonical_source_order(good)          # a mapping is not an inventory
    with raises(ContentPackIdentityError):
        canonical_source_order("alpha")


@guarded
def test_the_canonicalization_profile_is_internal_and_names_its_implementation():
    assert CANONICALIZATION_PROFILE_ID == "ION_JCS_V0_1"
    assert CANONICALIZATION_IMPLEMENTATION == "t4.jcs.serialize"

    # The binding is real: the profile's bytes ARE the bound serializer's bytes.
    from t4 import jcs

    payload = canonical_payload(
        contract_version=CONTENT_PACK_CONTRACT_VERSION,
        pack_id="ion_working_pack",
        pack_version="1.0.0",
        sources=[_entry("beta", "2.0", SHA_B).canonical_mapping(),
                 _entry("alpha", "1.0", SHA_A).canonical_mapping()],
    )
    raw = canonical_bytes(
        contract_version=CONTENT_PACK_CONTRACT_VERSION,
        pack_id="ion_working_pack",
        pack_version="1.0.0",
        sources=[_entry("beta", "2.0", SHA_B).canonical_mapping(),
                 _entry("alpha", "1.0", SHA_A).canonical_mapping()],
    )
    assert raw == jcs.serialize(payload)

    # Canonical bytes: sorted property names, no whitespace, no trailing newline,
    # and the declared source order preserved as the array's own order.
    text = raw.decode("utf-8")
    assert not text.endswith("\n") and " " not in text
    assert text.index('"alpha"') < text.index('"beta"')
    assert json.loads(text) == payload
