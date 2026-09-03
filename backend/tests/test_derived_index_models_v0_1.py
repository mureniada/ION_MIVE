"""Expected derived-index contract objects (E2.3 v0.1) — fail-closed construction.

Covers the nineteen model proofs: immutability, contract-version governance,
pack and engine identity validation, chunk parameters, record-set integrity,
embedding-profile governance (including the refusal of an unpinned or
placeholder model revision), vector-schema governance, the dimension agreement
law, and the total absence of any collection, activation, verification or
measured field.

Every test runs under `netguard`'s `guarded` decorator. No temporary corpus and
no filesystem access is needed anywhere in this module: the Content Build Result
is constructed directly, which is itself part of the evidence that expected
index identity is computable from declarations alone.
"""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib

from app.modules.content_engine import ContentBuildResult
from app.modules.derived_index import (
    BACKEND_FAKE,
    BACKEND_LOCAL,
    BACKEND_OPENAI,
    DERIVED_INDEX_CONTRACT_VERSION,
    DISTANCE_COSINE,
    FORBIDDEN_REVISION_PLACEHOLDERS,
    MODEL_BACKED_BACKENDS,
    NORMALIZATION_L2_BY_ADAPTER,
    NORMALIZATION_PROVIDER_UNVERIFIED,
    PROHIBITED_IDENTITY_FIELDS,
    SUPPORTED_CONTRACT_VERSIONS,
    DerivedIndexError,
    EmbeddingProfile,
    ExpectedDerivedIndexDescriptor,
    RecordDescriptor,
    VectorSchema,
)
from app.modules.retrieval.evidence_fingerprint import (
    ALGORITHM as EVIDENCE_FINGERPRINT_ALGORITHM,
)
from app.modules.retrieval.evidence_fingerprint import (
    PROFILE_ID as EVIDENCE_FINGERPRINT_PROFILE_ID,
)
from tests.netguard import guarded
from tests.util import raises

CREATED_AT = "2026-09-03T09:00:00Z"
PACK_FINGERPRINT = hashlib.sha256(b"pack").hexdigest()
SOURCE_SHA = hashlib.sha256(b"source bytes").hexdigest()


def _fingerprint(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _record(document_id: str, *, created_at: str = CREATED_AT) -> dict:
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
        "evidence_fingerprint": _fingerprint(document_id),
        "evidence_fingerprint_algorithm": EVIDENCE_FINGERPRINT_ALGORITHM,
        "evidence_fingerprint_profile_id": EVIDENCE_FINGERPRINT_PROFILE_ID,
        "ion_source_provenance": {
            "source_id": "alpha",
            "provenance_created_at": created_at,
        },
        "ion_canonical_provenance": {"evidence_id": document_id},
    }


def _build_result(
    *,
    created_at: str = CREATED_AT,
    document_ids: tuple[str, ...] = ("alpha::p1::c0", "alpha::p1::c1"),
    chunk_chars: int = 1200,
    overlap: int = 200,
    pack_id: str = "ion_test_pack",
    pack_version: str = "1.0.0",
    pack_fingerprint: str = PACK_FINGERPRINT,
) -> ContentBuildResult:
    return ContentBuildResult(
        content_engine_contract_version="0.1",
        content_engine_version="0.1",
        pack_id=pack_id,
        pack_version=pack_version,
        pack_canonical_fingerprint=pack_fingerprint,
        chunk_chars=chunk_chars,
        overlap=overlap,
        provenance_created_at=created_at,
        records=tuple(_record(d, created_at=created_at) for d in document_ids),
    )


IMPLEMENTATION_REVISION = "ion-embedding-impl-2026-09-03-a1b2c3d4"


def _profile(**overrides) -> EmbeddingProfile:
    kwargs = {
        "backend": BACKEND_LOCAL,
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


def _descriptor(**overrides) -> ExpectedDerivedIndexDescriptor:
    build = overrides.pop("build", None) or _build_result()
    profile = overrides.pop("embedding_profile", None) or _profile()
    schema = overrides.pop("vector_schema", None) or _schema()
    return ExpectedDerivedIndexDescriptor.create(build, profile, schema, **overrides)


# --------------------------------------------------------------------------- #
# M1 — immutability
# --------------------------------------------------------------------------- #
@guarded
def test_m1_all_public_models_are_immutable():
    descriptor = _descriptor()
    with raises(dataclasses.FrozenInstanceError):
        descriptor.pack_id = "other"
    with raises(dataclasses.FrozenInstanceError):
        descriptor.embedding_profile.dimension = 8
    with raises(dataclasses.FrozenInstanceError):
        descriptor.vector_schema.distance_metric = "EUCLID"
    with raises(dataclasses.FrozenInstanceError):
        descriptor.record_set[0].document_id = "other"


# --------------------------------------------------------------------------- #
# M2-M6 — descriptor governance
# --------------------------------------------------------------------------- #
@guarded
def test_m2_unsupported_contract_version_fails_closed():
    assert SUPPORTED_CONTRACT_VERSIONS == (DERIVED_INDEX_CONTRACT_VERSION,)
    for bad in ("0.2", "1.0", "v0.1", "", None):
        with raises(DerivedIndexError):
            _descriptor(derived_index_contract_version=bad)


@guarded
def test_m3_empty_pack_identity_fields_fail_closed():
    """A real ContentBuildResult already refuses these, so the descriptor's own
    refusal is proved against direct construction, where one can be presented."""
    for field, value in (
        ("pack_id", ""), ("pack_id", "  "), ("pack_id", " ion_pack"), ("pack_id", None),
        ("pack_version", ""), ("pack_version", "1.0.0 "), ("pack_version", None),
    ):
        with raises(DerivedIndexError):
            _direct(**{field: value})


@guarded
def test_m4_invalid_pack_fingerprint_fails_closed():
    for bad in (
        PACK_FINGERPRINT.upper(), PACK_FINGERPRINT[:-1], PACK_FINGERPRINT + "0",
        PACK_FINGERPRINT[:-1] + "g", "", None,
    ):
        with raises(Exception):
            _descriptor(build=_build_result(pack_fingerprint=bad))


def _direct(**overrides) -> ExpectedDerivedIndexDescriptor:
    """Direct construction, bypassing `create`, so validation itself is exercised."""
    kwargs = {
        "derived_index_contract_version": DERIVED_INDEX_CONTRACT_VERSION,
        "pack_id": "ion_test_pack",
        "pack_version": "1.0.0",
        "pack_canonical_fingerprint": PACK_FINGERPRINT,
        "content_engine_contract_version": "0.1",
        "content_engine_version": "0.1",
        "chunk_chars": 1200,
        "overlap": 200,
        "record_set": (
            RecordDescriptor(document_id="a", evidence_fingerprint=_fingerprint("a")),
        ),
        "embedding_profile": _profile(),
        "vector_schema": _schema(),
        "derived_index_fingerprint": _fingerprint("placeholder"),
    }
    kwargs.update(overrides)
    return ExpectedDerivedIndexDescriptor(**kwargs)


@guarded
def test_m5_invalid_engine_identity_fails_closed():
    """A real ContentBuildResult validates its own engine identity, so this is
    proved against direct construction, where an invalid value can be presented."""
    for field in ("content_engine_contract_version", "content_engine_version"):
        for bad in ("", "   ", " 0.1", None, 7):
            with raises(DerivedIndexError):
                _direct(**{field: bad})


@guarded
def test_m6_invalid_chunk_parameters_fail_closed():
    for chunk_chars, overlap in ((0, 0), (-1, 0), (100, 100), (100, 150), (100, -1)):
        with raises(Exception):
            _descriptor(build=_build_result(chunk_chars=chunk_chars, overlap=overlap))


# --------------------------------------------------------------------------- #
# M7-M9 — record set
# --------------------------------------------------------------------------- #
@guarded
def test_m7_empty_record_set_fails_closed():
    with raises(DerivedIndexError):
        ExpectedDerivedIndexDescriptor(
            derived_index_contract_version=DERIVED_INDEX_CONTRACT_VERSION,
            pack_id="ion_test_pack",
            pack_version="1.0.0",
            pack_canonical_fingerprint=PACK_FINGERPRINT,
            content_engine_contract_version="0.1",
            content_engine_version="0.1",
            chunk_chars=1200,
            overlap=200,
            record_set=(),
            embedding_profile=_profile(),
            vector_schema=_schema(),
            derived_index_fingerprint=_fingerprint("x"),
        )


@guarded
def test_m8_duplicate_document_id_fails_closed():
    entry = RecordDescriptor(document_id="a", evidence_fingerprint=_fingerprint("a"))
    with raises(DerivedIndexError):
        ExpectedDerivedIndexDescriptor(
            derived_index_contract_version=DERIVED_INDEX_CONTRACT_VERSION,
            pack_id="ion_test_pack",
            pack_version="1.0.0",
            pack_canonical_fingerprint=PACK_FINGERPRINT,
            content_engine_contract_version="0.1",
            content_engine_version="0.1",
            chunk_chars=1200,
            overlap=200,
            record_set=(entry, entry),
            embedding_profile=_profile(),
            vector_schema=_schema(),
            derived_index_fingerprint=_fingerprint("x"),
        )


@guarded
def test_m9_invalid_evidence_fingerprint_fails_closed():
    good = _fingerprint("a")
    for bad in (good.upper(), good[:-1], good + "0", good[:-1] + "z", "", "  ", None, 7):
        with raises(DerivedIndexError):
            RecordDescriptor(document_id="a", evidence_fingerprint=bad)
    for bad_id in ("", "   ", " a", "a ", None, 7):
        with raises(DerivedIndexError):
            RecordDescriptor(document_id=bad_id, evidence_fingerprint=good)


# --------------------------------------------------------------------------- #
# M10-M14 — embedding profile
# --------------------------------------------------------------------------- #
@guarded
def test_m10_embedding_profile_requires_an_explicit_supported_backend():
    for bad in ("", "  ", "local ", "Local", "huggingface", None, 7):
        with raises(DerivedIndexError):
            _profile(backend=bad)


@guarded
def test_m11_model_backed_profile_requires_a_model_name():
    assert MODEL_BACKED_BACKENDS == frozenset({BACKEND_LOCAL, BACKEND_OPENAI})
    for backend in sorted(MODEL_BACKED_BACKENDS):
        for bad in ("", "  ", None):
            with raises(DerivedIndexError):
                _profile(backend=backend, model_name=bad)


@guarded
def test_m12_model_backed_profile_requires_a_non_placeholder_revision():
    for backend in sorted(MODEL_BACKED_BACKENDS):
        with raises(DerivedIndexError):
            _profile(backend=backend, model_revision=None)
        for placeholder in sorted(FORBIDDEN_REVISION_PLACEHOLDERS):
            for variant in (placeholder, placeholder.upper(), placeholder.capitalize()):
                with raises(DerivedIndexError):
                    _profile(backend=backend, model_revision=variant)

    # An explicit immutable revision constructs.
    assert _profile(model_revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41")

    # The dependency-free backend has no external model artifact: it declares
    # absence truthfully instead of inventing a revision, and may not claim one.
    assert _profile(backend=BACKEND_FAKE, model_name=None, model_revision=None,
                    dimension=256, normalization_profile=NORMALIZATION_L2_BY_ADAPTER)
    with raises(DerivedIndexError):
        _profile(backend=BACKEND_FAKE, model_name="something", model_revision=None)
    with raises(DerivedIndexError):
        _profile(backend=BACKEND_FAKE, model_name=None, model_revision="abc123")


# --------------------------------------------------------------------------- #
# M12a-M12i — the embedding IMPLEMENTATION revision (E2.3C correction)
# --------------------------------------------------------------------------- #
@guarded
def test_m12a_implementation_revision_is_required_for_every_backend():
    """The model and the implementation that runs it are two different things."""
    # fake — no model artifact, but its algorithm is still its identity.
    assert _profile(backend=BACKEND_FAKE, model_name=None, model_revision=None,
                    dimension=256)
    with raises(DerivedIndexError):
        EmbeddingProfile(
            backend=BACKEND_FAKE, model_name=None, model_revision=None,
            implementation_revision=None, dimension=256,
            normalization_profile=NORMALIZATION_L2_BY_ADAPTER,
        )
    # local and openai
    for backend, name, revision, dimension, normalization in (
        (BACKEND_LOCAL, "sentence-transformers/all-MiniLM-L6-v2",
         "1110a243fdf4706b3f48f1d95db1a4f5529b4d41", 384, NORMALIZATION_L2_BY_ADAPTER),
        (BACKEND_OPENAI, "text-embedding-3-small", "operator-declared-2026-09-03",
         1536, NORMALIZATION_PROVIDER_UNVERIFIED),
    ):
        assert EmbeddingProfile(
            backend=backend, model_name=name, model_revision=revision,
            implementation_revision=IMPLEMENTATION_REVISION, dimension=dimension,
            normalization_profile=normalization,
        )
        with raises(DerivedIndexError):
            EmbeddingProfile(
                backend=backend, model_name=name, model_revision=revision,
                implementation_revision=None, dimension=dimension,
                normalization_profile=normalization,
            )


@guarded
def test_m12b_empty_or_placeholder_implementation_revision_fails_closed():
    for bad in ("", "   ", " rev", "rev ", None, 7):
        with raises(DerivedIndexError):
            _profile(implementation_revision=bad)
    for placeholder in sorted(FORBIDDEN_REVISION_PLACEHOLDERS):
        for variant in (placeholder, placeholder.upper(), placeholder.capitalize()):
            with raises(DerivedIndexError):
                _profile(implementation_revision=variant)


@guarded
def test_m12c_implementation_revision_is_immutable_and_never_inferred():
    """No default, and no lookup: the caller must declare it explicitly."""
    import inspect

    parameters = inspect.signature(EmbeddingProfile).parameters
    assert parameters["implementation_revision"].default is inspect.Parameter.empty

    profile = _profile()
    with raises(dataclasses.FrozenInstanceError):
        profile.implementation_revision = "other"

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "modules" / "derived_index" / "models.py"
    ).read_text(encoding="utf-8")
    for inferred in ("subprocess", "git ", "importlib.metadata", "pkg_resources",
                     "os.environ", "__version__"):
        assert inferred not in source, f"implementation revision inferred via {inferred}"


@guarded
def test_m13_non_positive_or_invalid_dimension_fails_closed():
    for bad in (0, -1, 1.5, "384", None, True):
        with raises(DerivedIndexError):
            _profile(dimension=bad)
        with raises(DerivedIndexError):
            _schema(dimension=bad)


@guarded
def test_m14_normalization_profile_is_explicit_and_governed():
    for bad in ("", "  ", "l2", "NORMALIZED", None, 7):
        with raises(DerivedIndexError):
            _profile(normalization_profile=bad)
    assert _profile(normalization_profile=NORMALIZATION_L2_BY_ADAPTER)
    assert _profile(
        backend=BACKEND_OPENAI,
        model_name="text-embedding-3-small",
        model_revision="operator-declared-2026-09-03",
        dimension=1536,
        normalization_profile=NORMALIZATION_PROVIDER_UNVERIFIED,
    )


# --------------------------------------------------------------------------- #
# M15-M18 — vector schema
# --------------------------------------------------------------------------- #
@guarded
def test_m15_vector_schema_dimension_must_be_positive():
    for bad in (0, -1, None, "384"):
        with raises(DerivedIndexError):
            _schema(dimension=bad)


@guarded
def test_m16_unsupported_distance_metric_fails_closed():
    for bad in ("EUCLID", "DOT", "cosine", "", None):
        with raises(DerivedIndexError):
            _schema(distance_metric=bad)
    assert _schema(distance_metric=DISTANCE_COSINE)


@guarded
def test_m17_vector_name_semantics_are_explicit():
    unnamed = _schema(vector_name=None)
    named = _schema(vector_name="dense")
    assert unnamed.vector_name is None            # the unnamed single-vector state
    assert named.vector_name == "dense"
    assert unnamed.canonical_mapping()["vector_name"] is None
    for bad in ("", "  ", " dense", 7):
        with raises(DerivedIndexError):
            _schema(vector_name=bad)


@guarded
def test_m18_embedding_and_vector_dimension_mismatch_fails_closed():
    with raises(DerivedIndexError):
        _descriptor(embedding_profile=_profile(dimension=384),
                    vector_schema=_schema(dimension=256))
    assert _descriptor(embedding_profile=_profile(dimension=256),
                       vector_schema=_schema(dimension=256))


# --------------------------------------------------------------------------- #
# M19 — nothing from E3 exists here
# --------------------------------------------------------------------------- #
@guarded
def test_m19_no_collection_activation_verification_or_measured_field_exists():
    descriptor_fields = {f.name for f in dataclasses.fields(ExpectedDerivedIndexDescriptor)}
    assert descriptor_fields == {
        "derived_index_contract_version",
        "pack_id",
        "pack_version",
        "pack_canonical_fingerprint",
        "content_engine_contract_version",
        "content_engine_version",
        "chunk_chars",
        "overlap",
        "record_set",
        "embedding_profile",
        "vector_schema",
        "derived_index_fingerprint",
    }

    all_fields = descriptor_fields
    for model in (EmbeddingProfile, VectorSchema, RecordDescriptor):
        all_fields = all_fields | {f.name for f in dataclasses.fields(model)}

    for prohibited in PROHIBITED_IDENTITY_FIELDS:
        assert prohibited not in all_fields, f"{prohibited} exists on an E2.3 model"

    # record_count is a declared expectation exposed as a property, never a
    # measured point count and never an identity field.
    assert _descriptor().record_count == 2
    assert "record_count" not in descriptor_fields


@guarded
def test_the_descriptor_carries_pack_and_engine_identity_verbatim():
    build = _build_result()
    descriptor = _descriptor(build=build)
    assert descriptor.pack_id == build.pack_id
    assert descriptor.pack_version == build.pack_version
    assert descriptor.pack_canonical_fingerprint == build.pack_canonical_fingerprint
    assert descriptor.content_engine_contract_version == build.content_engine_contract_version
    assert descriptor.content_engine_version == build.content_engine_version
    assert (descriptor.chunk_chars, descriptor.overlap) == (build.chunk_chars, build.overlap)
