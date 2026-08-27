from __future__ import annotations

import copy
import inspect
import os
import pathlib
import subprocess
import sys

import pytest

from app.modules.retrieval.canonical_provenance_materializer import (
    CanonicalProvenanceMaterializationError,
    materialize_canonical_provenance,
)
from app.modules.retrieval.evidence_fingerprint import (
    ALGORITHM,
    PROFILE_ID,
    compute_fingerprint_from_record,
)
from app.modules.retrieval.source_provenance import (
    COLLECTION_METHOD,
    KNOWN,
    METADATA_CONTRACT_ID,
    METADATA_CONTRACT_VERSION,
    PROVENANCE_PRODUCER,
    SOURCE_FILE_SHA256_ALGORITHM,
    SOURCE_FILE_SHA256_BASIS,
    SOURCE_TYPE,
    UNKNOWN,
)


def _provenance(*, unknown_collection: bool = False):
    return {
        "source_id": "source-a",
        "source_origin": "corpus-file://source-a.txt",
        "source_type": SOURCE_TYPE,
        "collection_method": COLLECTION_METHOD,
        "collector": None if unknown_collection else "operator",
        "collected_at": None if unknown_collection else "2026-08-20T12:00:00Z",
        "collected_at_status": UNKNOWN if unknown_collection else KNOWN,
        "provenance_producer": PROVENANCE_PRODUCER,
        "provenance_created_at": "2026-08-23T00:00:00Z",
        "provenance_created_at_status": KNOWN,
        "source_file_sha256": "a" * 64,
        "source_file_sha256_algorithm": SOURCE_FILE_SHA256_ALGORITHM,
        "source_file_sha256_basis": SOURCE_FILE_SHA256_BASIS,
        "metadata_contract_id": METADATA_CONTRACT_ID,
        "metadata_contract_version": METADATA_CONTRACT_VERSION,
    }


def _record(*, unknown_collection: bool = False):
    record = {
        "document_id": "source-a::p1::c0",
        "source_id": "source-a",
        "title": "Source A",
        "content": "Debt is a liability.",
        "page": 1,
        "chunk_id": "source-a::p1::c0",
        "checksum": "a" * 64,
        "ingestion_version": "v1",
        "ion_source_provenance": _provenance(
            unknown_collection=unknown_collection
        ),
    }
    record["evidence_fingerprint"] = compute_fingerprint_from_record(record)
    record["evidence_fingerprint_algorithm"] = ALGORITHM
    record["evidence_fingerprint_profile_id"] = PROFILE_ID
    return record


def _expected_package(record):
    return {
        "evidence_id": record["document_id"],
        "source_identity": record["source_id"],
        "fingerprint": record["evidence_fingerprint"],
        "fingerprint_algorithm": "SHA256",
        "provenance": {
            "origin": record["ion_source_provenance"]["source_origin"],
            "producer": record["ion_source_provenance"]["provenance_producer"],
            "created_at": record["ion_source_provenance"]["provenance_created_at"],
        },
        "fingerprint_semantics_established": True,
        "provenance_authoritative": True,
    }


def test_p5_18k_t01_valid_record_materializes_exact_package():
    record = _record()
    assert materialize_canonical_provenance(record) == _expected_package(record)


def test_p5_18k_t02_unknown_collection_metadata_can_materialize_without_rewrite():
    record = _record(unknown_collection=True)
    before = copy.deepcopy(record["ion_source_provenance"])
    result = materialize_canonical_provenance(record)
    assert result == _expected_package(record)
    assert record["ion_source_provenance"] == before
    assert record["ion_source_provenance"]["collected_at_status"] == UNKNOWN


def test_p5_18k_t03_materializer_is_deterministic():
    record = _record()
    assert materialize_canonical_provenance(record) == materialize_canonical_provenance(
        copy.deepcopy(record)
    )


def test_p5_18k_t04_input_record_is_not_mutated():
    record = _record()
    before = copy.deepcopy(record)
    materialize_canonical_provenance(record)
    assert record == before


def test_p5_18k_t05_exact_authorized_top_level_fields():
    result = materialize_canonical_provenance(_record())
    assert set(result) == {
        "evidence_id",
        "source_identity",
        "fingerprint",
        "fingerprint_algorithm",
        "provenance",
        "fingerprint_semantics_established",
        "provenance_authoritative",
    }


def test_p5_18k_t06_exact_authorized_provenance_fields():
    result = materialize_canonical_provenance(_record())
    assert set(result["provenance"]) == {"origin", "producer", "created_at"}


def test_p5_18k_t07_missing_evidence_fingerprint_rejected():
    record = _record()
    del record["evidence_fingerprint"]
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t08_wrong_fingerprint_algorithm_rejected():
    record = _record()
    record["evidence_fingerprint_algorithm"] = "MD5"
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t09_wrong_fingerprint_profile_rejected():
    record = _record()
    record["evidence_fingerprint_profile_id"] = "WRONG_PROFILE"
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t10_stored_fingerprint_mismatch_rejected():
    record = _record()
    record["evidence_fingerprint"] = "0" * 64
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t11_unknown_source_id_rejected():
    record = _record()
    record["source_id"] = "unknown"
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t12_missing_projection_field_rejected():
    record = _record()
    del record["content"]
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t13_source_checksum_cannot_substitute_for_evidence_fingerprint():
    record = _record()
    record["evidence_fingerprint"] = record["checksum"]
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t14_missing_source_provenance_rejected():
    record = _record()
    del record["ion_source_provenance"]
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t15_invalid_source_provenance_contract_rejected():
    record = _record()
    record["ion_source_provenance"]["source_type"] = "QDRANT"
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t16_source_provenance_source_id_mismatch_rejected():
    record = _record()
    record["ion_source_provenance"]["source_id"] = "source-b"
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t17_source_provenance_sha_mismatch_rejected():
    record = _record()
    record["ion_source_provenance"]["source_file_sha256"] = "b" * 64
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t18_unknown_provenance_created_at_rejected():
    record = _record()
    record["ion_source_provenance"]["provenance_created_at"] = None
    record["ion_source_provenance"]["provenance_created_at_status"] = UNKNOWN
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t19_invalid_provenance_created_at_rejected():
    record = _record()
    record["ion_source_provenance"]["provenance_created_at"] = "not-a-time"
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t20_wrong_provenance_producer_rejected():
    record = _record()
    record["ion_source_provenance"]["provenance_producer"] = "OTHER"
    with pytest.raises(CanonicalProvenanceMaterializationError):
        materialize_canonical_provenance(record)


def test_p5_18k_t21_no_chain_id_is_invented():
    result = materialize_canonical_provenance(_record())
    assert "chain_id" not in result["provenance"]


def test_p5_18k_t22_source_has_no_qdrant_network_or_wall_clock_activation_path():
    import app.modules.retrieval.canonical_provenance_materializer as module

    source = inspect.getsource(module).lower()
    forbidden = (
        "qdrant",
        "requests.",
        "urllib",
        "socket",
        "datetime.now",
        "utcnow",
        "time.time",
        "os.environ",
        "open(",
    )
    assert all(token not in source for token in forbidden)


def test_p5_18k_t23_result_is_in_memory_only_and_input_gets_no_canonical_key():
    record = _record()
    result = materialize_canonical_provenance(record)
    assert isinstance(result, dict)
    assert "ion_canonical_provenance" not in record


def test_p5_18k_t24_existing_p5_18g_suite_still_passes_under_module_presence():
    backend = pathlib.Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_production_provenance_materialization_v0_1.py",
        ],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "30 passed" in (proc.stdout + proc.stderr)
