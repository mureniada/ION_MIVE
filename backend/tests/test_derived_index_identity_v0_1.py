"""Expected derived-index identity (E2.3 v0.1) — determinism and exclusions.

Covers the nineteen identity proofs: determinism and order independence; the
canonical record ordering; every MUST-AFFECT input moving the fingerprint;
`provenance_created_at`, record order, machine paths and the collection name
being unable to move or enter it; the `t4.jcs` byte source and SHA-256 digest;
the refusal of an unchecked caller-supplied fingerprint; non-mutation of the
Content Build Result; and the absence of any store, embedder, filesystem,
network, clock, UUID, randomness or measured/activation semantics.

Every test runs under `netguard`'s `guarded` decorator, and the whole module
touches no filesystem — which is itself part of the evidence that expected index
identity is computable from declarations alone.
"""

from __future__ import annotations

import ast
import builtins
import dataclasses
import hashlib
import io
import json
import sys
from pathlib import Path

from app.modules.content_engine import ContentBuildResult
from app.modules.derived_index import (
    CANONICALIZATION_IMPLEMENTATION,
    CANONICALIZATION_PROFILE_ID,
    DERIVED_INDEX_CONTRACT_VERSION,
    DISTANCE_COSINE,
    FINGERPRINT_ALGORITHM,
    NORMALIZATION_L2_BY_ADAPTER,
    NORMALIZATION_PROVIDER_UNVERIFIED,
    PAYLOAD_KEYS,
    BACKEND_FAKE,
    BACKEND_OPENAI,
    DerivedIndexError,
    DerivedIndexIdentityError,
    EmbeddingProfile,
    ExpectedDerivedIndexDescriptor,
    RecordDescriptor,
    VectorSchema,
    canonical_bytes,
    canonical_payload,
    canonical_record_set,
    compute_derived_index_fingerprint,
)
from app.modules.retrieval.evidence_fingerprint import (
    ALGORITHM as EVIDENCE_FINGERPRINT_ALGORITHM,
)
from app.modules.retrieval.evidence_fingerprint import (
    PROFILE_ID as EVIDENCE_FINGERPRINT_PROFILE_ID,
)
from tests.netguard import BLOCKED_MODULE_PREFIXES, guarded
from tests.util import raises

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "app" / "modules" / "derived_index"

#: Everything the derived_index package may import from outside itself. `t4` is
#: the canonical serializer bound by E2.1 and reused here; the rest is stdlib.
PERMITTED_ABSOLUTE_IMPORTS = frozenset({
    "__future__", "collections", "dataclasses", "hashlib", "re", "t4", "typing",
})
PERMITTED_RELATIVE_IMPORTS = frozenset({"identity", "models"})

CREATED_AT = "2026-09-03T09:00:00Z"
OTHER_CREATED_AT = "2026-09-03T23:59:59Z"
PACK_FINGERPRINT = hashlib.sha256(b"pack").hexdigest()
OTHER_PACK_FINGERPRINT = hashlib.sha256(b"other pack").hexdigest()
SOURCE_SHA = hashlib.sha256(b"source bytes").hexdigest()


def _fingerprint(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _record(document_id: str, *, created_at: str = CREATED_AT, seed: str | None = None) -> dict:
    return {
        "document_id": document_id,
        "source_id": "alpha",
        "source_version": "1.0.0",
        "title": "alpha",
        "content": f"content for {document_id}",
        "page": None,
        "chunk_id": document_id,
        "checksum": SOURCE_SHA,
        "ingestion_version": "v1",
        "evidence_fingerprint": _fingerprint(seed or document_id),
        "evidence_fingerprint_algorithm": EVIDENCE_FINGERPRINT_ALGORITHM,
        "evidence_fingerprint_profile_id": EVIDENCE_FINGERPRINT_PROFILE_ID,
        "ion_source_provenance": {
            "source_id": "alpha",
            "provenance_created_at": created_at,
        },
        "ion_canonical_provenance": {"evidence_id": document_id},
    }


def _build_result(*, created_at: str = CREATED_AT, records: tuple[dict, ...] | None = None,
                  **overrides) -> ContentBuildResult:
    kwargs = {
        "content_engine_contract_version": "0.1",
        "content_engine_version": "0.1",
        "pack_id": "ion_test_pack",
        "pack_version": "1.0.0",
        "pack_canonical_fingerprint": PACK_FINGERPRINT,
        "chunk_chars": 1200,
        "overlap": 200,
    }
    kwargs.update(overrides)
    if records is None:
        records = tuple(
            _record(d, created_at=created_at)
            for d in ("alpha::p1::c0", "alpha::p1::c1", "beta::pall::c0")
        )
    return ContentBuildResult(provenance_created_at=created_at, records=records, **kwargs)


IMPLEMENTATION_REVISION = "ion-embedding-impl-2026-09-03-a1b2c3d4"
OTHER_IMPLEMENTATION_REVISION = "ion-embedding-impl-2026-09-04-99887766"


def _profile(**overrides) -> EmbeddingProfile:
    kwargs = {
        "backend": "local",
        "model_name": "sentence-transformers/all-MiniLM-L6-v2",
        "model_revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        "implementation_revision": IMPLEMENTATION_REVISION,
        "dimension": 384,
        "normalization_profile": NORMALIZATION_L2_BY_ADAPTER,
    }
    kwargs.update(overrides)
    return EmbeddingProfile(**kwargs)


def _schema(**overrides) -> VectorSchema:
    kwargs = {"dimension": 384, "distance_metric": DISTANCE_COSINE, "vector_name": None}
    kwargs.update(overrides)
    return VectorSchema(**kwargs)


def _describe(build=None, profile=None, schema=None) -> ExpectedDerivedIndexDescriptor:
    return ExpectedDerivedIndexDescriptor.create(
        build or _build_result(), profile or _profile(), schema or _schema()
    )


# --------------------------------------------------------------------------- #
# I1-I3 — determinism and canonical ordering
# --------------------------------------------------------------------------- #
@guarded
def test_i1_identical_inputs_produce_identical_fingerprints():
    values = {_describe().derived_index_fingerprint for _ in range(20)}
    assert len(values) == 1
    value = values.pop()
    assert len(value) == 64 and value == value.lower()
    assert all(ch in "0123456789abcdef" for ch in value)


@guarded
def test_i2_input_record_order_does_not_affect_the_fingerprint():
    ids = ("alpha::p1::c0", "alpha::p1::c1", "beta::pall::c0")
    orderings = (
        ids,
        tuple(reversed(ids)),
        (ids[1], ids[0], ids[2]),
        (ids[2], ids[0], ids[1]),
    )
    fingerprints = {
        _describe(build=_build_result(records=tuple(_record(d) for d in order)))
        .derived_index_fingerprint
        for order in orderings
    }
    assert len(fingerprints) == 1, f"record order moved the fingerprint: {fingerprints}"


@guarded
def test_i3_canonical_record_ordering_is_by_document_id():
    entries = [
        {"document_id": "gamma", "evidence_fingerprint": _fingerprint("g")},
        {"document_id": "alpha", "evidence_fingerprint": _fingerprint("a")},
        {"document_id": "beta", "evidence_fingerprint": _fingerprint("b")},
    ]
    ordered = canonical_record_set(entries)
    assert [e["document_id"] for e in ordered] == ["alpha", "beta", "gamma"]
    assert canonical_record_set(list(ordered)) == ordered
    assert canonical_record_set(list(reversed(ordered))) == ordered

    descriptor = _describe()
    assert [e.document_id for e in descriptor.record_set] == sorted(
        e.document_id for e in descriptor.record_set
    )

    with raises(DerivedIndexIdentityError):
        canonical_record_set([entries[0], entries[0]])
    with raises(DerivedIndexIdentityError):
        canonical_record_set([])


# --------------------------------------------------------------------------- #
# I4 — build provenance time is not an index identity input
# --------------------------------------------------------------------------- #
@guarded
def test_i4_provenance_created_at_alone_does_not_affect_the_fingerprint():
    early = _describe(build=_build_result(created_at=CREATED_AT))
    late = _describe(build=_build_result(created_at=OTHER_CREATED_AT))

    assert early.derived_index_fingerprint == late.derived_index_fingerprint
    # ...while the builds themselves genuinely differ.
    assert CREATED_AT != OTHER_CREATED_AT
    assert CREATED_AT not in canonical_bytes(**_payload_kwargs()).decode("utf-8")
    assert "provenance_created_at" not in canonical_bytes(**_payload_kwargs()).decode("utf-8")


def _payload_kwargs(**overrides):
    kwargs = {
        "derived_index_contract_version": DERIVED_INDEX_CONTRACT_VERSION,
        "pack_id": "ion_test_pack",
        "pack_version": "1.0.0",
        "pack_canonical_fingerprint": PACK_FINGERPRINT,
        "content_engine_contract_version": "0.1",
        "content_engine_version": "0.1",
        "chunk_chars": 1200,
        "overlap": 200,
        "record_set": [{"document_id": "a", "evidence_fingerprint": _fingerprint("a")}],
        "embedding_profile": _profile().canonical_mapping(),
        "vector_schema": _schema().canonical_mapping(),
    }
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------- #
# I5 — every MUST-AFFECT input moves the fingerprint
# --------------------------------------------------------------------------- #
@guarded
def test_i5_every_must_affect_input_moves_the_fingerprint():
    base = compute_derived_index_fingerprint(**_payload_kwargs())

    moved = {
        "pack_id": _payload_kwargs(pack_id="ion_other_pack"),
        "pack_version": _payload_kwargs(pack_version="2.0.0"),
        "pack_canonical_fingerprint": _payload_kwargs(
            pack_canonical_fingerprint=OTHER_PACK_FINGERPRINT
        ),
        "content_engine_contract_version": _payload_kwargs(
            content_engine_contract_version="0.2"
        ),
        "content_engine_version": _payload_kwargs(content_engine_version="0.2"),
        "chunk_chars": _payload_kwargs(chunk_chars=900),
        "overlap": _payload_kwargs(overlap=150),
        "record document_id": _payload_kwargs(
            record_set=[{"document_id": "b", "evidence_fingerprint": _fingerprint("a")}]
        ),
        "record evidence_fingerprint": _payload_kwargs(
            record_set=[{"document_id": "a", "evidence_fingerprint": _fingerprint("z")}]
        ),
        "embedding backend": _payload_kwargs(
            embedding_profile=_profile(
                backend=BACKEND_FAKE, model_name=None, model_revision=None
            ).canonical_mapping()
        ),
        "embedding model_name": _payload_kwargs(
            embedding_profile=_profile(model_name="other/model").canonical_mapping()
        ),
        "embedding model_revision": _payload_kwargs(
            embedding_profile=_profile(model_revision="deadbeef").canonical_mapping()
        ),
        "embedding implementation_revision": _payload_kwargs(
            embedding_profile=_profile(
                implementation_revision=OTHER_IMPLEMENTATION_REVISION
            ).canonical_mapping()
        ),
        "embedding dimension": _payload_kwargs(
            embedding_profile=_profile(dimension=256).canonical_mapping()
        ),
        "embedding normalization_profile": _payload_kwargs(
            embedding_profile=_profile(
                backend=BACKEND_OPENAI,
                model_name="text-embedding-3-small",
                model_revision="operator-declared-2026-09-03",
                normalization_profile=NORMALIZATION_PROVIDER_UNVERIFIED,
            ).canonical_mapping()
        ),
        "vector dimension": _payload_kwargs(
            vector_schema=_schema(dimension=256).canonical_mapping()
        ),
        "vector_name": _payload_kwargs(
            vector_schema=_schema(vector_name="dense").canonical_mapping()
        ),
    }

    for label, kwargs in moved.items():
        assert compute_derived_index_fingerprint(**kwargs) != base, (
            f"{label} did not move the derived index fingerprint"
        )

    # Named vs unnamed are different schemas, not the same one.
    named = compute_derived_index_fingerprint(
        **_payload_kwargs(vector_schema=_schema(vector_name="dense").canonical_mapping())
    )
    other_named = compute_derived_index_fingerprint(
        **_payload_kwargs(vector_schema=_schema(vector_name="sparse").canonical_mapping())
    )
    assert named != other_named != base


@guarded
def test_embedding_implementation_revision_participates_in_identity():
    """E2.3C: a changed implementation must change the expected index, even when
    the model artifact is identical — and even where there is no model at all."""
    raw = canonical_bytes(**_payload_kwargs()).decode("utf-8")
    assert "implementation_revision" in raw
    assert IMPLEMENTATION_REVISION in raw

    base = compute_derived_index_fingerprint(**_payload_kwargs())
    moved = compute_derived_index_fingerprint(
        **_payload_kwargs(
            embedding_profile=_profile(
                implementation_revision=OTHER_IMPLEMENTATION_REVISION
            ).canonical_mapping()
        )
    )
    assert moved != base

    # Same for the model-free backend, whose algorithm IS its identity.
    fake = _profile(backend=BACKEND_FAKE, model_name=None, model_revision=None,
                    dimension=256)
    fake_other = _profile(backend=BACKEND_FAKE, model_name=None, model_revision=None,
                          dimension=256,
                          implementation_revision=OTHER_IMPLEMENTATION_REVISION)
    schema = _schema(dimension=256).canonical_mapping()
    assert compute_derived_index_fingerprint(
        **_payload_kwargs(embedding_profile=fake.canonical_mapping(), vector_schema=schema)
    ) != compute_derived_index_fingerprint(
        **_payload_kwargs(
            embedding_profile=fake_other.canonical_mapping(), vector_schema=schema
        )
    )

    # An identical declaration stays deterministic.
    assert len({
        compute_derived_index_fingerprint(**_payload_kwargs()) for _ in range(10)
    }) == 1

    # A profile missing the field cannot be canonicalized at all.
    incomplete = dict(_profile().canonical_mapping())
    del incomplete["implementation_revision"]
    with raises(DerivedIndexIdentityError):
        compute_derived_index_fingerprint(**_payload_kwargs(embedding_profile=incomplete))


@guarded
def test_distance_metric_participates_in_identity():
    """Only COSINE is supported today, so this is proved at the payload layer,
    where an alternative metric can be presented."""
    base = compute_derived_index_fingerprint(**_payload_kwargs())
    other = compute_derived_index_fingerprint(
        **_payload_kwargs(
            vector_schema={"dimension": 384, "distance_metric": "EUCLID", "vector_name": None}
        )
    )
    assert other != base


# --------------------------------------------------------------------------- #
# I6-I7 — machine facts and deployment configuration cannot enter identity
# --------------------------------------------------------------------------- #
@guarded
def test_i6_and_i7_no_machine_path_or_collection_name_can_enter_identity():
    raw = canonical_bytes(**_payload_kwargs()).decode("utf-8")
    payload = json.loads(raw)

    assert set(payload) == set(PAYLOAD_KEYS)
    for absent in (
        "source_root", "path", "relative_source_path", "collection",
        "qdrant", "ion_corpus_v1", "point_id", "point_count", "activation",
        "verified", "verification", "measured", "rollback", "provenance_created_at",
    ):
        assert absent not in raw, f"{absent!r} leaked into the identity payload"

    descriptor_fields = {f.name for f in dataclasses.fields(ExpectedDerivedIndexDescriptor)}
    for absent in ("qdrant_collection", "collection", "source_root", "point_count"):
        assert absent not in descriptor_fields


# --------------------------------------------------------------------------- #
# I8-I9 — the byte source and the digest
# --------------------------------------------------------------------------- #
@guarded
def test_i8_and_i9_t4_jcs_is_the_byte_source_and_sha256_is_the_digest():
    from t4 import jcs

    assert CANONICALIZATION_PROFILE_ID == "ION_JCS_V0_1"
    assert CANONICALIZATION_IMPLEMENTATION == "t4.jcs.serialize"
    assert FINGERPRINT_ALGORITHM == "SHA256"

    payload = canonical_payload(**_payload_kwargs())
    raw = canonical_bytes(**_payload_kwargs())
    assert raw == jcs.serialize(payload)
    assert compute_derived_index_fingerprint(**_payload_kwargs()) == (
        hashlib.sha256(raw).hexdigest()
    )

    text = raw.decode("utf-8")
    assert not text.endswith("\n") and " " not in text
    assert json.loads(text) == payload
    # The fingerprint is never an input to its own computation.
    assert "derived_index_fingerprint" not in text


# --------------------------------------------------------------------------- #
# I10-I12 — measured identity, never an unverified declaration
# --------------------------------------------------------------------------- #
@guarded
def test_i10_caller_cannot_supply_an_unchecked_fingerprint():
    import inspect

    parameters = set(inspect.signature(ExpectedDerivedIndexDescriptor.create).parameters)
    assert "derived_index_fingerprint" not in parameters

    descriptor = _describe()
    rebuilt = ExpectedDerivedIndexDescriptor(
        derived_index_contract_version=descriptor.derived_index_contract_version,
        pack_id=descriptor.pack_id,
        pack_version=descriptor.pack_version,
        pack_canonical_fingerprint=descriptor.pack_canonical_fingerprint,
        content_engine_contract_version=descriptor.content_engine_contract_version,
        content_engine_version=descriptor.content_engine_version,
        chunk_chars=descriptor.chunk_chars,
        overlap=descriptor.overlap,
        record_set=descriptor.record_set,
        embedding_profile=descriptor.embedding_profile,
        vector_schema=descriptor.vector_schema,
        derived_index_fingerprint=descriptor.derived_index_fingerprint,
    )
    assert rebuilt == descriptor

    fp = descriptor.derived_index_fingerprint
    for wrong in (_fingerprint("not this index"),
                  fp[:-1] + ("0" if fp[-1] != "0" else "1"), "", None):
        with raises(DerivedIndexError):
            ExpectedDerivedIndexDescriptor(
                derived_index_contract_version=descriptor.derived_index_contract_version,
                pack_id=descriptor.pack_id,
                pack_version=descriptor.pack_version,
                pack_canonical_fingerprint=descriptor.pack_canonical_fingerprint,
                content_engine_contract_version=descriptor.content_engine_contract_version,
                content_engine_version=descriptor.content_engine_version,
                chunk_chars=descriptor.chunk_chars,
                overlap=descriptor.overlap,
                record_set=descriptor.record_set,
                embedding_profile=descriptor.embedding_profile,
                vector_schema=descriptor.vector_schema,
                derived_index_fingerprint=wrong,
            )


@guarded
def test_i11_recomputation_is_deterministic():
    values = {compute_derived_index_fingerprint(**_payload_kwargs()) for _ in range(25)}
    assert len(values) == 1


@guarded
def test_i12_content_build_result_is_not_mutated():
    build = _build_result()
    before = dataclasses.asdict(build)
    _describe(build=build)
    assert dataclasses.asdict(build) == before


# --------------------------------------------------------------------------- #
# I13-I18 — no store, embedder, filesystem, network, clock or randomness
# --------------------------------------------------------------------------- #
@guarded
def test_i13_i14_no_qdrant_or_embedder_is_imported_or_constructed():
    _describe()
    for prefix in BLOCKED_MODULE_PREFIXES:
        assert prefix not in sys.modules, f"{prefix} was imported during identity computation"


@guarded
def test_i13_to_i18_the_package_source_reaches_nothing_it_must_not():
    modules = sorted(PACKAGE_DIR.glob("*.py"))
    assert modules, f"no modules found under {PACKAGE_DIR}"

    for path in modules:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
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
            "numpy",
        }
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}"

        unexpected = absolute - PERMITTED_ABSOLUTE_IMPORTS
        assert not unexpected, f"{path.name} imports unreviewed module(s) {sorted(unexpected)}"

        unexpected_relative = relative - PERMITTED_RELATIVE_IMPORTS
        assert not unexpected_relative, (
            f"{path.name} reaches unreviewed sibling(s) {sorted(unexpected_relative)}"
        )

        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "open" not in calls, f"{path.name} calls open()"

        for banned in ("datetime.now", "utcnow", "time.time", "uuid4", "random.",
                       "QdrantRetrieval", "point_id_for", "embed(", "build_embedder"):
            assert banned not in source, f"{path.name} reaches {banned}"


@guarded
def test_i15_no_filesystem_access_occurs_during_identity_computation():
    def _denied(*_args, **_kwargs):
        raise AssertionError("identity computation attempted to open a file")

    original_builtin, original_io = builtins.open, io.open
    builtins.open = _denied
    io.open = _denied
    try:
        descriptor = _describe()
        value = compute_derived_index_fingerprint(**_payload_kwargs())
    finally:
        builtins.open = original_builtin
        io.open = original_io

    assert len(descriptor.derived_index_fingerprint) == 64
    assert len(value) == 64


# --------------------------------------------------------------------------- #
# I19 — expected is not measured
# --------------------------------------------------------------------------- #
@guarded
def test_i19_no_activation_or_measured_identity_semantics_exist():
    descriptor = _describe()
    names = set(dir(descriptor))
    for absent in (
        "measured_index_fingerprint", "actual_point_count", "measured_point_count",
        "point_count", "verification_status", "verified_at", "activation_state",
        "activated_at", "rollback_id", "qdrant_collection", "verify", "activate",
        "rollback", "measure",
    ):
        assert absent not in names, f"{absent} exists on the expected descriptor"

    # record_count is a DECLARED expectation, and says so: it counts declared
    # records, never points in a store.
    assert descriptor.record_count == len(descriptor.record_set) == 3
