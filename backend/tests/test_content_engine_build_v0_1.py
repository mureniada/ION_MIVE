"""Content Engine build (E2.2 v0.1) — derived records bound to a Content Pack.

Covers the build proofs: the Content Pack is consumed unmodified and its identity
carried verbatim; declared identity reaches every derived record while the
provenance origin comes from the declared RELATIVE path (never from `source_id`,
never from an absolute machine path); fingerprints and provenance are present and
truthful on every record; `provenance_created_at` is an explicit build input that
the result binds; the build is deterministic, order-independent and root-
independent; a byte mismatch yields no successful result; no store, model,
network or clock is touched; and no index-, embedding- or activation-shaped field
exists anywhere.

Every test runs under `netguard`'s `guarded` decorator, with temporary corpora
built via `tempfile` so both `pytest` and the stdlib `run_tests.py` run them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.modules.content_engine import (
    CONTENT_ENGINE_CONTRACT_VERSION,
    CONTENT_ENGINE_VERSION,
    PROHIBITED_IDENTITY_FIELDS,
    RECORD_KEYS,
    ContentBuildResult,
    ContentEngineError,
    build_content,
    source_origin_for,
)
from app.modules.content_pack import ContentPack, SourceEntry
from app.modules.retrieval.evidence_fingerprint import (
    ALGORITHM as EVIDENCE_FINGERPRINT_ALGORITHM,
)
from app.modules.retrieval.evidence_fingerprint import (
    PROFILE_ID as EVIDENCE_FINGERPRINT_PROFILE_ID,
)
from app.modules.retrieval.evidence_fingerprint import compute_fingerprint_from_record
from app.modules.retrieval.ingest import _slug
from app.modules.retrieval.source_provenance import (
    KNOWN,
    SOURCE_FILE_SHA256_BASIS,
    SOURCE_ORIGIN_SCHEME,
    validate_source_provenance,
)
from tests.netguard import BLOCKED_MODULE_PREFIXES, guarded
from tests.util import raises

CREATED_AT = "2026-09-03T09:00:00Z"
OTHER_CREATED_AT = "2026-09-03T11:30:00Z"

TEXT_A = "Adaptive dialogue is a bounded runtime concern in ION. " * 60
TEXT_B = "Retrieval is not reasoning and evidence outranks confidence. " * 60


@contextmanager
def _corpus(*, relatives: dict[str, str] | None = None, **sources: str):
    """Real files under a nested layout, plus the pack declaring them.

    Relative paths and filenames deliberately differ from declared source ids, so
    any path- or filename-derived identity would be immediately visible.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        entries = []
        bindings = {}
        for source_id, text in sources.items():
            relative = (relatives or {}).get(source_id, f"research/{source_id}_file.txt")
            path = root.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            entries.append(
                SourceEntry(
                    source_id=source_id,
                    source_version="1.0.0",
                    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
            bindings[source_id] = relative
        pack = ContentPack.create(
            pack_id="ion_test_pack", pack_version="1.0.0", sources=entries
        )
        yield pack, bindings, root


def _build(pack, bindings, root, **kwargs) -> ContentBuildResult:
    kwargs.setdefault("provenance_created_at", CREATED_AT)
    return build_content(pack, bindings, source_root=root, **kwargs)


# --------------------------------------------------------------------------- #
# B1-B2, B22 — the Content Pack is input, and is left alone
# --------------------------------------------------------------------------- #
@guarded
def test_b1_content_pack_is_accepted_without_modification():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        before = dataclasses.asdict(pack)
        _build(pack, bindings, root)
        assert dataclasses.asdict(pack) == before


@guarded
def test_b2_and_b22_pack_canonical_fingerprint_and_object_remain_unchanged():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        fingerprint = pack.canonical_fingerprint
        result = _build(pack, bindings, root)
        assert pack.canonical_fingerprint == fingerprint
        assert result.pack_canonical_fingerprint == fingerprint

        with raises(dataclasses.FrozenInstanceError):
            pack.pack_version = "2.0.0"
        with raises(dataclasses.FrozenInstanceError):
            pack.sources[0].source_sha256 = "0" * 64


# --------------------------------------------------------------------------- #
# B3-B4, H — declared identity, never filename- or path-derived identity
# --------------------------------------------------------------------------- #
@guarded
def test_b3_and_h_declared_source_id_reaches_every_record():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        assert {r["source_id"] for r in result.records} == {"alpha", "beta"}
        for record in result.records:
            assert record["chunk_id"].startswith(record["source_id"] + "::")
            assert record["document_id"] == record["chunk_id"]
            assert record["title"] == record["source_id"]


@guarded
def test_b4_filename_slug_and_machine_path_are_never_used_as_authority():
    with _corpus(relatives={"alpha": "archive/Weird Name 42.TXT"}, alpha=TEXT_A) as (
        pack,
        bindings,
        root,
    ):
        slug = _slug("Weird Name 42")
        assert slug == "weird_name_42"          # what the legacy path would have minted

        result = _build(pack, bindings, root)
        for record in result.records:
            assert record["source_id"] == "alpha"
            blob = repr(record)
            assert slug not in blob, "a filename-derived identity reached the record"
            assert str(root) not in blob, "an absolute machine path reached the record"


# --------------------------------------------------------------------------- #
# A/B/C/G/I — origin comes from the relative path, and only from it
# --------------------------------------------------------------------------- #
@guarded
def test_a_source_id_and_source_origin_are_distinct():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        record = _build(pack, bindings, root).records[0]
        origin = record["ion_source_provenance"]["source_origin"]
        assert record["source_id"] == "alpha"
        assert origin == "corpus-file://research/alpha_file.txt"
        assert origin != record["source_id"]
        assert origin != SOURCE_ORIGIN_SCHEME + record["source_id"]


@guarded
def test_b_source_origin_is_built_from_the_relative_posix_binding_path():
    with _corpus(relatives={"alpha": "a/b/c/deep_file.txt"}, alpha=TEXT_A) as (
        pack,
        bindings,
        root,
    ):
        record = _build(pack, bindings, root).records[0]
        origin = record["ion_source_provenance"]["source_origin"]
        assert origin == source_origin_for("a/b/c/deep_file.txt")
        assert origin == "corpus-file://a/b/c/deep_file.txt"
        # The engine builds the scheme; the caller supplied only a relative path.
        assert bindings["alpha"] == "a/b/c/deep_file.txt"


@guarded
def test_c_an_absolute_binding_can_never_become_the_source_origin():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        absolute = "/" + (root / "research" / "alpha_file.txt").as_posix().lstrip("/")
        with raises(ContentEngineError):
            _build(pack, {"alpha": absolute}, root)
        # A caller cannot smuggle a prebuilt URI in either.
        with raises(ContentEngineError):
            _build(pack, {"alpha": "corpus-file://research/alpha_file.txt"}, root)


@guarded
def test_g_and_i_changing_the_machine_root_changes_neither_origin_nor_fingerprint():
    def _build_under(root: Path) -> ContentBuildResult:
        path = root / "research" / "alpha_file.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEXT_A, encoding="utf-8")
        pack = ContentPack.create(
            pack_id="ion_test_pack",
            pack_version="1.0.0",
            sources=[
                SourceEntry(
                    source_id="alpha",
                    source_version="1.0.0",
                    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            ],
        )
        return build_content(
            pack,
            {"alpha": "research/alpha_file.txt"},
            source_root=root,
            provenance_created_at=CREATED_AT,
        )

    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        a = _build_under(Path(first))
        b = _build_under(Path(second))
        assert a.records == b.records, "an absolute machine root leaked into the build"
        assert dataclasses.asdict(a) == dataclasses.asdict(b)
        assert [r["evidence_fingerprint"] for r in a.records] == [
            r["evidence_fingerprint"] for r in b.records
        ]


# --------------------------------------------------------------------------- #
# B5-B8 — fingerprints, provenance, checksum
# --------------------------------------------------------------------------- #
@guarded
def test_b5_every_record_carries_a_recomputable_evidence_fingerprint():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        for record in result.records:
            assert record["evidence_fingerprint_algorithm"] == EVIDENCE_FINGERPRINT_ALGORITHM
            assert record["evidence_fingerprint_profile_id"] == EVIDENCE_FINGERPRINT_PROFILE_ID
            assert record["evidence_fingerprint"] == compute_fingerprint_from_record(record)
        assert len({r["evidence_fingerprint"] for r in result.records}) == len(result.records)


@guarded
def test_b6_every_record_carries_required_source_provenance():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        for record in result.records:
            provenance = validate_source_provenance(record["ion_source_provenance"])
            assert provenance["source_id"] == "alpha"
            assert provenance["source_origin"] == "corpus-file://research/alpha_file.txt"
            assert provenance["source_file_sha256"] == record["checksum"]
            assert provenance["source_file_sha256_basis"] == SOURCE_FILE_SHA256_BASIS
            assert provenance["provenance_created_at_status"] == KNOWN
            assert provenance["provenance_created_at"] == CREATED_AT


@guarded
def test_b6_provenance_is_mandatory_not_an_optional_flag():
    """The legacy production omission cannot be reproduced here: there is no
    parameter that turns provenance off."""
    import inspect

    parameters = set(inspect.signature(build_content).parameters)
    assert "source_provenance_by_source" not in parameters
    assert "materialize_canonical" not in parameters
    assert "provenance_created_at" in parameters
    assert "source_root" in parameters

    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        assert all(r["ion_source_provenance"] for r in result.records)
        assert all(r["ion_canonical_provenance"] for r in result.records)


@guarded
def test_b7_canonical_provenance_is_materialized_and_validated():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        for record in result.records:
            canonical = record["ion_canonical_provenance"]
            assert canonical["evidence_id"] == record["document_id"]
            assert canonical["source_identity"] == "alpha"
            assert canonical["fingerprint"] == record["evidence_fingerprint"]
            assert canonical["fingerprint_algorithm"] == EVIDENCE_FINGERPRINT_ALGORITHM
            assert canonical["fingerprint_semantics_established"] is True
            assert canonical["provenance_authoritative"] is True
            assert canonical["provenance"]["origin"] == source_origin_for(
                "research/alpha_file.txt"
            )
            assert canonical["provenance"]["created_at"] == CREATED_AT


@guarded
def test_b8_checksum_equals_the_verified_pack_source_sha256():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        declared = {s.source_id: s.source_sha256 for s in pack.sources}
        result = _build(pack, bindings, root)
        for record in result.records:
            assert record["checksum"] == declared[record["source_id"]]


# --------------------------------------------------------------------------- #
# J/K/L — the temporal input is explicit, bound, and never minted
# --------------------------------------------------------------------------- #
@guarded
def test_j_provenance_created_at_is_required_explicitly():
    import inspect

    parameter = inspect.signature(build_content).parameters["provenance_created_at"]
    assert parameter.default is inspect.Parameter.empty, (
        "provenance_created_at must have no default: a build cannot invent a time"
    )

    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        for bad in ("", "   ", "not-a-timestamp", "2026-09-03 09:00:00",
                    "2026-09-03T09:00:00", "2026-09-03T09:00:00+02:00", None):
            with raises(ContentEngineError):
                build_content(
                    pack, bindings, source_root=root, provenance_created_at=bad
                )


@guarded
def test_k_the_engine_reads_no_clock():
    """Two builds separated in wall-clock time are byte-identical."""
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        first = _build(pack, bindings, root)
        second = _build(pack, bindings, root)
        assert dataclasses.asdict(first) == dataclasses.asdict(second)

        # The only thing that can move the timestamp is the caller supplying one.
        later = _build(pack, bindings, root, provenance_created_at=OTHER_CREATED_AT)
        assert later.provenance_created_at == OTHER_CREATED_AT
        assert later.records != first.records


@guarded
def test_l_content_build_result_binds_the_supplied_provenance_created_at_exactly():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        result = _build(pack, bindings, root, provenance_created_at=OTHER_CREATED_AT)
        assert result.provenance_created_at == OTHER_CREATED_AT
        for record in result.records:
            assert (
                record["ion_source_provenance"]["provenance_created_at"]
                == OTHER_CREATED_AT
            )

        # A result whose records disagree with the bound time cannot be built.
        divergent = [dict(r) for r in result.records]
        divergent[0]["ion_source_provenance"] = dict(divergent[0]["ion_source_provenance"])
        divergent[0]["ion_source_provenance"]["provenance_created_at"] = CREATED_AT
        with raises(ContentEngineError):
            ContentBuildResult(
                content_engine_contract_version=result.content_engine_contract_version,
                content_engine_version=result.content_engine_version,
                pack_id=result.pack_id,
                pack_version=result.pack_version,
                pack_canonical_fingerprint=result.pack_canonical_fingerprint,
                chunk_chars=result.chunk_chars,
                overlap=result.overlap,
                provenance_created_at=result.provenance_created_at,
                records=tuple(divergent),
            )


# --------------------------------------------------------------------------- #
# B9-B11, M — determinism
# --------------------------------------------------------------------------- #
@guarded
def test_b9_chunk_ordering_is_deterministic_and_source_ordered():
    with _corpus(gamma=TEXT_A, alpha=TEXT_B, beta=TEXT_A) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        source_order = [r["source_id"] for r in result.records]
        assert source_order == sorted(source_order), "records are not in canonical source order"

        for source_id in ("alpha", "beta", "gamma"):
            ordinals = [
                int(r["chunk_id"].rsplit("::c", 1)[1])
                for r in result.records
                if r["source_id"] == source_id
            ]
            assert ordinals == list(range(len(ordinals)))


@guarded
def test_b10_and_m_repeated_build_with_the_same_timestamp_is_deterministic():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        first = _build(pack, bindings, root)
        second = _build(pack, bindings, root)
        assert first.records == second.records
        assert dataclasses.asdict(first) == dataclasses.asdict(second)


@guarded
def test_b11_binding_map_order_does_not_affect_output():
    with _corpus(gamma=TEXT_A, alpha=TEXT_B, beta=TEXT_A) as (pack, bindings, root):
        forward = _build(pack, bindings, root)
        shuffled = {k: bindings[k] for k in reversed(list(bindings))}
        backward = _build(pack, shuffled, root)
        assert forward.records == backward.records


# --------------------------------------------------------------------------- #
# B12 — a byte mismatch yields nothing
# --------------------------------------------------------------------------- #
@guarded
def test_b12_source_byte_mismatch_produces_no_successful_build_result():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        beta_path = root.joinpath(*bindings["beta"].split("/"))
        with beta_path.open("ab") as handle:
            handle.write(b" ")
        with raises(ContentEngineError):
            _build(pack, bindings, root)


@guarded
def test_a_source_producing_zero_chunks_fails_closed():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        empty_path = root / "research" / "empty_file.txt"
        empty_path.write_text("", encoding="utf-8")
        empty_pack = ContentPack.create(
            pack_id="ion_test_pack",
            pack_version="1.0.0",
            sources=[
                SourceEntry(
                    source_id="beta",
                    source_version="1.0.0",
                    source_sha256=hashlib.sha256(empty_path.read_bytes()).hexdigest(),
                )
            ],
        )
        with raises(ContentEngineError):
            _build(empty_pack, {"beta": "research/empty_file.txt"}, root)


# --------------------------------------------------------------------------- #
# B13-B15 — no store, no model, no network
# --------------------------------------------------------------------------- #
@guarded
def test_b13_b14_b15_no_qdrant_embedding_or_network_is_reached():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        _build(pack, bindings, root)

    for prefix in BLOCKED_MODULE_PREFIXES:
        assert prefix not in sys.modules, f"{prefix} was imported during the build"

    engine_source = (
        Path(__file__).resolve().parent.parent
        / "app" / "modules" / "content_engine" / "engine.py"
    ).read_text(encoding="utf-8")
    executable = engine_source.split('"""')[-1]
    for banned in ("qdrant", "Qdrant", "embed", "upsert", "ensure_collection", "vector"):
        assert banned not in executable, f"{banned!r} appears in executable engine code"


# --------------------------------------------------------------------------- #
# B16-B17, N — no E2.3 / E3 identity anywhere
# --------------------------------------------------------------------------- #
@guarded
def test_b16_b17_and_n_no_index_embedding_or_activation_identity_exists():
    result_fields = {f.name for f in dataclasses.fields(ContentBuildResult)}
    assert result_fields == {
        "content_engine_contract_version",
        "content_engine_version",
        "pack_id",
        "pack_version",
        "pack_canonical_fingerprint",
        "chunk_chars",
        "overlap",
        "provenance_created_at",
        "records",
    }

    for prohibited in PROHIBITED_IDENTITY_FIELDS:
        assert prohibited not in result_fields
        assert prohibited not in RECORD_KEYS

    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        for record in result.records:
            assert set(record) == set(RECORD_KEYS)
            for prohibited in PROHIBITED_IDENTITY_FIELDS:
                assert prohibited not in record


# --------------------------------------------------------------------------- #
# B18-B21 — the result binds its pack, and its parameters
# --------------------------------------------------------------------------- #
@guarded
def test_b18_b19_b20_result_binds_pack_identity():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        assert result.pack_id == pack.pack_id
        assert result.pack_version == pack.pack_version
        assert result.pack_canonical_fingerprint == pack.canonical_fingerprint
        assert result.content_engine_contract_version == CONTENT_ENGINE_CONTRACT_VERSION
        assert result.content_engine_version == CONTENT_ENGINE_VERSION


@guarded
def test_b21_chunk_parameters_are_explicit_and_shape_the_build():
    with _corpus(alpha=TEXT_A) as (pack, bindings, root):
        coarse = _build(pack, bindings, root, chunk_chars=1200, overlap=200)
        fine = _build(pack, bindings, root, chunk_chars=200, overlap=50)

        assert (coarse.chunk_chars, coarse.overlap) == (1200, 200)
        assert (fine.chunk_chars, fine.overlap) == (200, 50)
        assert fine.record_count > coarse.record_count
        assert fine.records != coarse.records

        for chunk_chars, overlap in ((0, 0), (100, 100), (100, -1), (100, 150)):
            with raises(Exception):
                _build(pack, bindings, root, chunk_chars=chunk_chars, overlap=overlap)


@guarded
def test_derived_counts_are_conveniences_not_identity_fields():
    with _corpus(alpha=TEXT_A, beta=TEXT_B) as (pack, bindings, root):
        result = _build(pack, bindings, root)
        assert result.record_count == len(result.records)
        assert result.source_count == 2
        assert result.source_ids == ("alpha", "beta")
        assert "record_count" not in {f.name for f in dataclasses.fields(ContentBuildResult)}
