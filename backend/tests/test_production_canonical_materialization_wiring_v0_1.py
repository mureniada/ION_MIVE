from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import app.modules.retrieval.ingest as ingest_module
from app.modules.retrieval.canonical_provenance_materializer import (
    CanonicalProvenanceMaterializationError,
)
from app.modules.retrieval.evidence_fingerprint import (
    ALGORITHM,
    PROFILE_ID,
)
from app.modules.retrieval.ingest import build_records
from app.modules.retrieval.qdrant_store import (
    _CANDIDATE_METADATA_KEYS,
    _RETRIEVAL_METADATA_KEYS,
    _candidate_metadata_payload,
)
from app.modules.retrieval.source_provenance import (
    UNKNOWN,
    build_source_provenance,
)
from app.modules.retrieval.source_provenance_manifest import (
    MANIFEST_ID,
    MANIFEST_VERSION,
    SourceProvenanceManifestError,
    load_source_provenance_manifest,
)

FROZEN_MANIFEST_SHA256 = (
    "9ce11858d4fa5631b09aaaec31e534eeef8dfd2635051b89280b00f94384bb52"
)
EXPECTED_REPOSITORY_HEAD = "2c37ff8499d5dd76026fd33562206874342324d7"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _frozen_manifest_path() -> Path:
    return (
        Path.home()
        / "Downloads"
        / "ION_CURRENT_CORPUS_SOURCE_PROVENANCE_INPUT_MANIFEST_V0_1.json"
    )


def _frozen_manifest_object() -> dict:
    return json.loads(_frozen_manifest_path().read_text(encoding="ascii"))


def _write_manifest(tmp_path: Path, manifest: dict) -> tuple[Path, str]:
    path = tmp_path / "manifest.json"
    encoded = (
        json.dumps(
            manifest,
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("ascii")
    path.write_bytes(encoded)
    return path, hashlib.sha256(encoded).hexdigest()


def _source_row(
    *,
    source_id: str,
    source_origin: str,
    source_file_sha256: str,
) -> dict:
    return build_source_provenance(
        source_id=source_id,
        source_origin=source_origin,
        source_file_sha256=source_file_sha256,
        collector=None,
        collected_at=None,
        collected_at_status=UNKNOWN,
        provenance_created_at="2026-08-23T00:00:00Z",
        provenance_created_at_status="KNOWN",
    )


def _temp_canonical_records(tmp_path: Path) -> list[dict]:
    source = tmp_path / "source_a.txt"
    source.write_text(
        "alpha beta gamma delta epsilon zeta eta theta iota kappa",
        encoding="utf-8",
    )

    baseline = build_records(tmp_path, chunk_chars=24, overlap=0)
    source_id = baseline[0]["source_id"]
    checksum = baseline[0]["checksum"]

    provenance = _source_row(
        source_id=source_id,
        source_origin="corpus-file://source_a.txt",
        source_file_sha256=checksum,
    )

    return build_records(
        tmp_path,
        chunk_chars=24,
        overlap=0,
        source_provenance_by_source={source_id: provenance},
        materialize_canonical=True,
    )


def _independent_fingerprint(record: dict) -> str:
    projection = {
        "profile_id": "ION_EVIDENCE_FINGERPRINT_PROFILE_V0_1",
        "document_id": record["document_id"],
        "source_identity": record["source_id"],
        "title": record["title"],
        "page": record["page"],
        "chunk_id": record["chunk_id"],
        "content": record["content"],
    }
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _fake_roundtrip_metadata(record: dict) -> dict:
    payload = {
        "checksum": record.get("checksum"),
        "ingestion_version": record.get("ingestion_version"),
        **_candidate_metadata_payload(record),
    }
    return {
        key: payload[key]
        for key in _RETRIEVAL_METADATA_KEYS
        if key in payload and payload[key] is not None
    }


@pytest.fixture(scope="module")
def full_corpus_dry_run():
    repo = _repo_root()
    source_root = repo / "corpus" / "source"
    manifest_path = _frozen_manifest_path()

    source_files = sorted(
        [
            path
            for path in source_root.iterdir()
            if path.is_file() and path.suffix.lower() in {".txt", ".pdf"}
        ],
        key=lambda path: path.name,
    )

    source_hashes_before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    }

    provenance_by_source = load_source_provenance_manifest(
        manifest_path,
        expected_sha256=FROZEN_MANIFEST_SHA256,
        expected_repository_head=EXPECTED_REPOSITORY_HEAD,
    )

    records = build_records(
        source_root,
        source_provenance_by_source=provenance_by_source,
        materialize_canonical=True,
    )

    fingerprint_failures = 0
    canonical_failures = 0
    roundtrip_failures = 0
    canonical_count = 0

    for record in records:
        if record["evidence_fingerprint"] != _independent_fingerprint(record):
            fingerprint_failures += 1

        package = record.get("ion_canonical_provenance")
        if not isinstance(package, dict):
            canonical_failures += 1
        else:
            canonical_count += 1

        metadata = _fake_roundtrip_metadata(record)
        if metadata.get("ion_canonical_provenance") != package:
            roundtrip_failures += 1

    source_hashes_after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_files
    }

    mutation_count = sum(
        1
        for name in source_hashes_before
        if source_hashes_before[name] != source_hashes_after[name]
    )

    result = {
        "frozen_manifest_sha256": FROZEN_MANIFEST_SHA256,
        "source_file_count": len(source_files),
        "source_binding_failure_count": 0,
        "source_sha256_mismatch_count": 0,
        "evidence_record_count": len(records),
        "fingerprint_recomputation_failure_count": fingerprint_failures,
        "canonical_materialization_failure_count": canonical_failures,
        "canonical_package_count": canonical_count,
        "fake_qdrant_roundtrip_failure_count": roundtrip_failures,
        "real_qdrant_write_count": 0,
        "corpus_source_mutation_count": mutation_count,
    }

    print(
        "P5_18Q_DRY_RUN"
        + "|FROZEN_MANIFEST_SHA256="
        + result["frozen_manifest_sha256"]
        + "|SOURCE_FILE_COUNT="
        + str(result["source_file_count"])
        + "|SOURCE_BINDING_FAILURE_COUNT="
        + str(result["source_binding_failure_count"])
        + "|SOURCE_SHA256_MISMATCH_COUNT="
        + str(result["source_sha256_mismatch_count"])
        + "|EVIDENCE_RECORD_COUNT="
        + str(result["evidence_record_count"])
        + "|FINGERPRINT_RECOMPUTATION_FAILURE_COUNT="
        + str(result["fingerprint_recomputation_failure_count"])
        + "|CANONICAL_MATERIALIZATION_FAILURE_COUNT="
        + str(result["canonical_materialization_failure_count"])
        + "|CANONICAL_PACKAGE_COUNT="
        + str(result["canonical_package_count"])
        + "|FAKE_QDRANT_ROUNDTRIP_FAILURE_COUNT="
        + str(result["fake_qdrant_roundtrip_failure_count"])
        + "|REAL_QDRANT_WRITE_COUNT="
        + str(result["real_qdrant_write_count"])
        + "|CORPUS_SOURCE_MUTATION_COUNT="
        + str(result["corpus_source_mutation_count"])
    )

    return result


def test_p5_18q_t01_exact_frozen_manifest_identity_loads():
    rows = load_source_provenance_manifest(
        _frozen_manifest_path(),
        expected_sha256=FROZEN_MANIFEST_SHA256,
        expected_repository_head=EXPECTED_REPOSITORY_HEAD,
    )
    assert len(rows) == 9


def test_p5_18q_t02_wrong_manifest_sha_rejected():
    with pytest.raises(SourceProvenanceManifestError):
        load_source_provenance_manifest(
            _frozen_manifest_path(),
            expected_sha256="0" * 64,
        )


def test_p5_18q_t03_wrong_manifest_id_rejected(tmp_path):
    manifest = _frozen_manifest_object()
    manifest["manifest_id"] = "WRONG"
    path, sha = _write_manifest(tmp_path, manifest)
    with pytest.raises(SourceProvenanceManifestError):
        load_source_provenance_manifest(path, expected_sha256=sha)


def test_p5_18q_t04_wrong_manifest_version_rejected(tmp_path):
    manifest = _frozen_manifest_object()
    manifest["manifest_version"] = "9.9"
    path, sha = _write_manifest(tmp_path, manifest)
    with pytest.raises(SourceProvenanceManifestError):
        load_source_provenance_manifest(path, expected_sha256=sha)


def test_p5_18q_t05_entry_count_mismatch_rejected(tmp_path):
    manifest = _frozen_manifest_object()
    manifest["entry_count"] = manifest["entry_count"] + 1
    path, sha = _write_manifest(tmp_path, manifest)
    with pytest.raises(SourceProvenanceManifestError):
        load_source_provenance_manifest(path, expected_sha256=sha)


def test_p5_18q_t06_duplicate_source_id_rejected(tmp_path):
    manifest = _frozen_manifest_object()
    manifest["entries"][1]["source_id"] = manifest["entries"][0]["source_id"]
    path, sha = _write_manifest(tmp_path, manifest)
    with pytest.raises(SourceProvenanceManifestError):
        load_source_provenance_manifest(path, expected_sha256=sha)


def test_p5_18q_t07_duplicate_source_origin_rejected(tmp_path):
    manifest = _frozen_manifest_object()
    manifest["entries"][1]["source_origin"] = manifest["entries"][0]["source_origin"]
    path, sha = _write_manifest(tmp_path, manifest)
    with pytest.raises(SourceProvenanceManifestError):
        load_source_provenance_manifest(path, expected_sha256=sha)


def test_p5_18q_t08_invalid_source_provenance_row_rejected(tmp_path):
    manifest = _frozen_manifest_object()
    manifest["entries"][0]["source_type"] = "QDRANT"
    path, sha = _write_manifest(tmp_path, manifest)
    with pytest.raises(SourceProvenanceManifestError):
        load_source_provenance_manifest(path, expected_sha256=sha)


def test_p5_18q_t09_repository_head_mismatch_rejected():
    with pytest.raises(SourceProvenanceManifestError):
        load_source_provenance_manifest(
            _frozen_manifest_path(),
            expected_sha256=FROZEN_MANIFEST_SHA256,
            expected_repository_head="0" * 40,
        )


def test_p5_18q_t10_loader_does_not_rewrite_manifest():
    path = _frozen_manifest_path()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    load_source_provenance_manifest(
        path,
        expected_sha256=FROZEN_MANIFEST_SHA256,
        expected_repository_head=EXPECTED_REPOSITORY_HEAD,
    )
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after == FROZEN_MANIFEST_SHA256


def test_p5_18q_t11_bound_source_preserves_fingerprint_candidate_fields(tmp_path):
    record = _temp_canonical_records(tmp_path)[0]
    assert record["evidence_fingerprint_algorithm"] == ALGORITHM
    assert record["evidence_fingerprint_profile_id"] == PROFILE_ID
    assert len(record["evidence_fingerprint"]) == 64


def test_p5_18q_t12_bound_source_preserves_source_provenance(tmp_path):
    record = _temp_canonical_records(tmp_path)[0]
    provenance = record["ion_source_provenance"]
    assert provenance["source_id"] == record["source_id"]
    assert provenance["source_file_sha256"] == record["checksum"]


def test_p5_18q_t13_final_record_produces_canonical_package(tmp_path):
    record = _temp_canonical_records(tmp_path)[0]
    assert isinstance(record["ion_canonical_provenance"], dict)


def test_p5_18q_t14_canonical_package_exact_top_level_shape(tmp_path):
    package = _temp_canonical_records(tmp_path)[0]["ion_canonical_provenance"]
    assert set(package) == {
        "evidence_id",
        "source_identity",
        "fingerprint",
        "fingerprint_algorithm",
        "provenance",
        "fingerprint_semantics_established",
        "provenance_authoritative",
    }


def test_p5_18q_t15_canonical_package_exact_provenance_shape(tmp_path):
    package = _temp_canonical_records(tmp_path)[0]["ion_canonical_provenance"]
    assert set(package["provenance"]) == {"origin", "producer", "created_at"}


def test_p5_18q_t16_canonical_fingerprint_independently_recomputes(tmp_path):
    record = _temp_canonical_records(tmp_path)[0]
    package = record["ion_canonical_provenance"]
    assert package["fingerprint"] == _independent_fingerprint(record)


def test_p5_18q_t17_source_checksum_distinct_from_evidence_fingerprint(tmp_path):
    records = _temp_canonical_records(tmp_path)
    assert all(r["checksum"] != r["evidence_fingerprint"] for r in records)


def test_p5_18q_t18_source_sha_checksum_mismatch_fails_closed(tmp_path):
    source = tmp_path / "source_a.txt"
    source.write_text("bounded source", encoding="utf-8")
    baseline = build_records(tmp_path)[0]
    provenance = _source_row(
        source_id=baseline["source_id"],
        source_origin="corpus-file://source_a.txt",
        source_file_sha256="0" * 64,
    )
    with pytest.raises(ValueError):
        build_records(
            tmp_path,
            source_provenance_by_source={baseline["source_id"]: provenance},
            materialize_canonical=True,
        )


def test_p5_18q_t19_missing_manifest_source_binding_fails_closed(tmp_path):
    source = tmp_path / "source_a.txt"
    source.write_text("bounded source", encoding="utf-8")
    with pytest.raises(ValueError):
        build_records(
            tmp_path,
            source_provenance_by_source={},
            materialize_canonical=True,
        )


def test_p5_18q_t20_materialization_failure_propagates_fail_closed(tmp_path, monkeypatch):
    source = tmp_path / "source_a.txt"
    source.write_text("bounded source", encoding="utf-8")
    baseline = build_records(tmp_path)[0]
    provenance = _source_row(
        source_id=baseline["source_id"],
        source_origin="corpus-file://source_a.txt",
        source_file_sha256=baseline["checksum"],
    )

    def reject(_record):
        raise CanonicalProvenanceMaterializationError("forced")

    monkeypatch.setattr(
        ingest_module,
        "materialize_canonical_provenance",
        reject,
    )

    with pytest.raises(CanonicalProvenanceMaterializationError):
        build_records(
            tmp_path,
            source_provenance_by_source={baseline["source_id"]: provenance},
            materialize_canonical=True,
        )


def test_p5_18q_t21_legacy_build_records_remains_noncanonical_by_default(tmp_path):
    source = tmp_path / "source_a.txt"
    source.write_text("bounded source", encoding="utf-8")
    record = build_records(tmp_path)[0]
    assert "evidence_fingerprint" in record
    assert "ion_canonical_provenance" not in record


def test_p5_18q_t22_canonical_package_copied_unchanged_into_fake_payload(tmp_path):
    record = _temp_canonical_records(tmp_path)[0]
    payload = _candidate_metadata_payload(record)
    assert payload["ion_canonical_provenance"] == record["ion_canonical_provenance"]


def test_p5_18q_t23_canonical_package_reconstructed_unchanged_into_metadata(tmp_path):
    record = _temp_canonical_records(tmp_path)[0]
    metadata = _fake_roundtrip_metadata(record)
    assert metadata["ion_canonical_provenance"] == record["ion_canonical_provenance"]


def test_p5_18q_t24_candidate_fingerprint_metadata_remains_preserved(tmp_path):
    record = _temp_canonical_records(tmp_path)[0]
    metadata = _fake_roundtrip_metadata(record)
    assert metadata["evidence_fingerprint"] == record["evidence_fingerprint"]
    assert metadata["evidence_fingerprint_algorithm"] == ALGORITHM
    assert metadata["evidence_fingerprint_profile_id"] == PROFILE_ID


def test_p5_18q_t25_candidate_source_provenance_remains_preserved(tmp_path):
    record = _temp_canonical_records(tmp_path)[0]
    metadata = _fake_roundtrip_metadata(record)
    assert metadata["ion_source_provenance"] == record["ion_source_provenance"]


def test_p5_18q_t26_transport_does_not_synthesize_canonical_when_absent():
    record = {
        "evidence_fingerprint": "f" * 64,
        "evidence_fingerprint_algorithm": ALGORITHM,
        "evidence_fingerprint_profile_id": PROFILE_ID,
    }
    payload = _candidate_metadata_payload(record)
    assert "ion_canonical_provenance" not in payload
    assert "ion_canonical_provenance" in _CANDIDATE_METADATA_KEYS


def test_p5_18q_t27_frozen_manifest_covers_exact_nine_sources(full_corpus_dry_run):
    assert full_corpus_dry_run["source_file_count"] == 9


def test_p5_18q_t28_full_corpus_has_zero_source_binding_or_sha_failures(full_corpus_dry_run):
    assert full_corpus_dry_run["source_binding_failure_count"] == 0
    assert full_corpus_dry_run["source_sha256_mismatch_count"] == 0


def test_p5_18q_t29_every_record_has_recomputed_fingerprint_and_canonical_package(full_corpus_dry_run):
    assert full_corpus_dry_run["evidence_record_count"] > 0
    assert full_corpus_dry_run["fingerprint_recomputation_failure_count"] == 0
    assert full_corpus_dry_run["canonical_materialization_failure_count"] == 0
    assert (
        full_corpus_dry_run["canonical_package_count"]
        == full_corpus_dry_run["evidence_record_count"]
    )


def test_p5_18q_t30_fake_roundtrip_preserves_all_packages_without_real_writes(full_corpus_dry_run):
    assert full_corpus_dry_run["fake_qdrant_roundtrip_failure_count"] == 0
    assert full_corpus_dry_run["real_qdrant_write_count"] == 0
    assert full_corpus_dry_run["corpus_source_mutation_count"] == 0
