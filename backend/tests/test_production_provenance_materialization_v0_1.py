from __future__ import annotations

import base64
import copy
import hashlib
import inspect
from dataclasses import dataclass

import pytest

from app.modules.retrieval import qdrant_store
from app.modules.retrieval.evidence_fingerprint import (
    ALGORITHM,
    PROFILE_ID,
    canonicalize_projection,
    compute_fingerprint_from_record,
    fingerprint_projection,
    recompute_evidence_fingerprint,
)
from app.modules.retrieval.ingest import build_records
from app.modules.retrieval.qdrant_store import (
    _CANDIDATE_METADATA_KEYS,
    _RETRIEVAL_METADATA_KEYS,
    _candidate_metadata_payload,
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
    build_source_provenance,
    source_provenance_complete,
    validate_source_provenance,
)


V01_B64 = "eyJjaHVua19pZCI6InNvdXJjZS1hOjpwMTo6YzAiLCJjb250ZW50IjoiRGVidCBpcyBhIGxpYWJpbGl0eS4iLCJkb2N1bWVudF9pZCI6InNvdXJjZS1hOjpwMTo6YzAiLCJwYWdlIjoxLCJwcm9maWxlX2lkIjoiSU9OX0VWSURFTkNFX0ZJTkdFUlBSSU5UX1BST0ZJTEVfVjBfMSIsInNvdXJjZV9pZGVudGl0eSI6InNvdXJjZS1hIiwidGl0bGUiOiJTb3VyY2UgQSJ9"
V01_SHA = "33eee34cadc9fe27b14ce28d64a489d6b17e2a9235b1b19e04a5486d86e0df28"

V02_B64 = "eyJjaHVua19pZCI6Im5vdGU6OnBhbGw6OmMyIiwiY29udGVudCI6ImxpbmUgb25lXG5saW5lIHR3byIsImRvY3VtZW50X2lkIjoibm90ZTo6cGFsbDo6YzIiLCJwYWdlIjpudWxsLCJwcm9maWxlX2lkIjoiSU9OX0VWSURFTkNFX0ZJTkdFUlBSSU5UX1BST0ZJTEVfVjBfMSIsInNvdXJjZV9pZGVudGl0eSI6Im5vdGUiLCJ0aXRsZSI6IlBsYWluIE5vdGUifQ=="
V02_SHA = "79593d85e554d38e751eb764ee8562b395f2253dcdb5752403b39e1766c0b14b"

V03_B64 = "eyJjaHVua19pZCI6InJ1OjpwMTI6OmMzIiwiY29udGVudCI6ItCU0L7QutCw0LfQsNGC0LXQu9GM0YHRgtCy0L46IFwiQVxcXFxCXCJcbtGB0YLRgNC+0LrQsCAyIiwiZG9jdW1lbnRfaWQiOiJydTo6cDEyOjpjMyIsInBhZ2UiOjEyLCJwcm9maWxlX2lkIjoiSU9OX0VWSURFTkNFX0ZJTkdFUlBSSU5UX1BST0ZJTEVfVjBfMSIsInNvdXJjZV9pZGVudGl0eSI6InJ1IiwidGl0bGUiOiLQotC10YHRgiJ9"
V03_SHA = "f6502154ae94a1549662f4a763d9df5de503cb5970a2daade08bfab31d57e655"


def _projection():
    return {
        "profile_id": PROFILE_ID,
        "document_id": "source-a::p1::c0",
        "source_identity": "source-a",
        "title": "Source A",
        "page": 1,
        "chunk_id": "source-a::p1::c0",
        "content": "Debt is a liability.",
    }


def _projection_v02():
    return {
        "profile_id": PROFILE_ID,
        "document_id": "note::pall::c2",
        "source_identity": "note",
        "title": "Plain Note",
        "page": None,
        "chunk_id": "note::pall::c2",
        "content": "line one\nline two",
    }


def _projection_v03():
    return {
        "profile_id": PROFILE_ID,
        "document_id": "ru::p12::c3",
        "source_identity": "ru",
        "title": "\u0422\u0435\u0441\u0442",
        "page": 12,
        "chunk_id": "ru::p12::c3",
        "content": "\u0414\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u043e: \"A\\\\B\"\n\u0441\u0442\u0440\u043e\u043a\u0430 2",
    }


def _record():
    return {
        "document_id": "source-a::p1::c0",
        "source_id": "source-a",
        "title": "Source A",
        "page": 1,
        "chunk_id": "source-a::p1::c0",
        "content": "Debt is a liability.",
    }


def _valid_provenance(source_id="source-a", source_origin="corpus-file://source-a.txt"):
    return {
        "source_id": source_id,
        "source_origin": source_origin,
        "source_type": SOURCE_TYPE,
        "collection_method": COLLECTION_METHOD,
        "collector": "operator",
        "collected_at": "2026-08-20T12:00:00Z",
        "collected_at_status": KNOWN,
        "provenance_producer": PROVENANCE_PRODUCER,
        "provenance_created_at": "2026-08-23T00:00:00Z",
        "provenance_created_at_status": KNOWN,
        "source_file_sha256": "a" * 64,
        "source_file_sha256_algorithm": SOURCE_FILE_SHA256_ALGORITHM,
        "source_file_sha256_basis": SOURCE_FILE_SHA256_BASIS,
        "metadata_contract_id": METADATA_CONTRACT_ID,
        "metadata_contract_version": METADATA_CONTRACT_VERSION,
    }


@dataclass
class _Evidence:
    document_id: str
    source_id: str
    title: str
    page: int | None
    chunk_id: str
    content: str
    metadata: dict
    score: float = 0.5


def test_p5_18g_t01_frozen_vector_v01_exact_bytes_and_sha256():
    actual = canonicalize_projection(_projection())
    assert base64.b64encode(actual).decode("ascii") == V01_B64
    assert hashlib.sha256(actual).hexdigest() == V01_SHA


def test_p5_18g_t02_frozen_vector_v02_exact_bytes_and_sha256():
    actual = canonicalize_projection(_projection_v02())
    assert base64.b64encode(actual).decode("ascii") == V02_B64
    assert hashlib.sha256(actual).hexdigest() == V02_SHA


def test_p5_18g_t03_frozen_vector_v03_exact_bytes_and_sha256():
    actual = canonicalize_projection(_projection_v03())
    assert base64.b64encode(actual).decode("ascii") == V03_B64
    assert hashlib.sha256(actual).hexdigest() == V03_SHA


def test_p5_18g_t04_exact_projection_is_deterministic():
    p = _projection()
    assert fingerprint_projection(p) == fingerprint_projection(copy.deepcopy(p))


def test_p5_18g_t05_document_id_mutation_changes_fingerprint():
    p = _projection()
    baseline = fingerprint_projection(p)
    p["document_id"] = "changed"
    assert fingerprint_projection(p) != baseline


def test_p5_18g_t06_source_identity_mutation_changes_fingerprint():
    p = _projection()
    baseline = fingerprint_projection(p)
    p["source_identity"] = "source-b"
    assert fingerprint_projection(p) != baseline


def test_p5_18g_t07_title_mutation_changes_fingerprint():
    p = _projection()
    baseline = fingerprint_projection(p)
    p["title"] = "Changed"
    assert fingerprint_projection(p) != baseline


def test_p5_18g_t08_page_mutation_changes_fingerprint():
    p = _projection()
    baseline = fingerprint_projection(p)
    p["page"] = 2
    assert fingerprint_projection(p) != baseline


def test_p5_18g_t09_chunk_id_mutation_changes_fingerprint():
    p = _projection()
    baseline = fingerprint_projection(p)
    p["chunk_id"] = "source-a::p1::c1"
    assert fingerprint_projection(p) != baseline


def test_p5_18g_t10_content_mutation_changes_fingerprint():
    p = _projection()
    baseline = fingerprint_projection(p)
    p["content"] += " changed"
    assert fingerprint_projection(p) != baseline


def test_p5_18g_t11_unknown_source_identity_rejected():
    p = _projection()
    p["source_identity"] = "unknown"
    with pytest.raises(ValueError):
        fingerprint_projection(p)


def test_p5_18g_t12_missing_or_invalid_required_fingerprint_field_rejected():
    p = _projection()
    del p["chunk_id"]
    with pytest.raises(ValueError):
        fingerprint_projection(p)
    p = _projection()
    p["page"] = True
    with pytest.raises(ValueError):
        fingerprint_projection(p)


def test_p5_18g_t13_source_file_checksum_does_not_influence_fingerprint():
    r1 = _record()
    r2 = _record()
    r1["checksum"] = "a" * 64
    r2["checksum"] = "b" * 64
    assert compute_fingerprint_from_record(r1) == compute_fingerprint_from_record(r2)


def test_p5_18g_t14_retrieval_score_does_not_influence_fingerprint():
    e1 = _Evidence(**_record(), metadata={}, score=0.1)
    e2 = _Evidence(**_record(), metadata={}, score=0.9)
    assert recompute_evidence_fingerprint(e1) == recompute_evidence_fingerprint(e2)


def test_p5_18g_t15_provenance_metadata_does_not_influence_fingerprint():
    e1 = _Evidence(**_record(), metadata={"provenance": {"origin": "a"}})
    e2 = _Evidence(**_record(), metadata={"provenance": {"origin": "b"}})
    assert recompute_evidence_fingerprint(e1) == recompute_evidence_fingerprint(e2)


def test_p5_18g_t16_valid_fully_known_source_provenance_is_complete():
    assert source_provenance_complete(_valid_provenance()) is True


def test_p5_18g_t17_unknown_collected_at_requires_null():
    p = _valid_provenance()
    p["collected_at_status"] = UNKNOWN
    with pytest.raises(ValueError):
        validate_source_provenance(p)


def test_p5_18g_t18_known_collected_at_requires_valid_explicit_timestamp():
    p = _valid_provenance()
    p["collected_at"] = "not-a-time"
    with pytest.raises(ValueError):
        validate_source_provenance(p)


def test_p5_18g_t19_unknown_is_never_upgraded_to_known():
    p = _valid_provenance()
    p["collector"] = None
    p["collected_at"] = None
    p["collected_at_status"] = UNKNOWN
    validated = validate_source_provenance(p)
    assert validated["collected_at_status"] == UNKNOWN
    assert validated["collected_at"] is None
    assert source_provenance_complete(validated) is False


def test_p5_18g_t20_collector_is_not_inferred_from_producer():
    p = build_source_provenance(
        source_id="source-a",
        source_origin="corpus-file://source-a.txt",
        source_file_sha256="a" * 64,
        collector=None,
        collected_at=None,
        collected_at_status=UNKNOWN,
        provenance_created_at="2026-08-23T00:00:00Z",
        provenance_created_at_status=KNOWN,
    )
    assert p["collector"] is None
    assert p["provenance_producer"] == PROVENANCE_PRODUCER


def test_p5_18g_t21_source_type_qdrant_rejected():
    p = _valid_provenance()
    p["source_type"] = "QDRANT"
    with pytest.raises(ValueError):
        validate_source_provenance(p)


def test_p5_18g_t22_invalid_source_origin_rejected():
    p = _valid_provenance()
    p["source_origin"] = "C:\\secret\\source-a.txt"
    with pytest.raises(ValueError):
        validate_source_provenance(p)


def test_p5_18g_t23_source_file_sha256_algorithm_and_basis_enforced():
    p = _valid_provenance()
    p["source_file_sha256_algorithm"] = "MD5"
    with pytest.raises(ValueError):
        validate_source_provenance(p)
    p = _valid_provenance()
    p["source_file_sha256_basis"] = "CHUNK_BYTES"
    with pytest.raises(ValueError):
        validate_source_provenance(p)


def test_p5_18g_t24_historical_missing_collection_facts_remain_incomplete():
    p = _valid_provenance()
    p["collector"] = None
    p["collected_at"] = None
    p["collected_at_status"] = UNKNOWN
    assert source_provenance_complete(p) is False


def test_p5_18g_t25_build_records_distinct_chunk_fingerprints_same_source_checksum(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("abcdefghijklmnopqrstuvwxyz0123456789", encoding="utf-8")
    records = build_records(tmp_path, chunk_chars=12, overlap=0)
    assert len(records) >= 2
    assert len({r["evidence_fingerprint"] for r in records}) == len(records)
    assert len({r["checksum"] for r in records}) == 1
    assert all(r["evidence_fingerprint_algorithm"] == ALGORITHM for r in records)
    assert all(r["evidence_fingerprint_profile_id"] == PROFILE_ID for r in records)


def test_p5_18g_t26_build_record_fingerprint_recomputes_from_final_record(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("one two three four five six", encoding="utf-8")
    record = build_records(tmp_path, chunk_chars=200, overlap=0)[0]
    assert record["evidence_fingerprint"] == compute_fingerprint_from_record(record)


def test_p5_18g_t27_valid_explicit_source_provenance_attached_without_rewrite(tmp_path):
    path = tmp_path / "source_a.txt"
    path.write_text("bounded text", encoding="utf-8")
    base = build_records(tmp_path, chunk_chars=200, overlap=0)[0]
    provenance = _valid_provenance(
        source_id=base["source_id"],
        source_origin="corpus-file://source_a.txt",
    )
    provenance["source_file_sha256"] = base["checksum"]
    records = build_records(
        tmp_path,
        chunk_chars=200,
        overlap=0,
        source_provenance_by_source={base["source_id"]: provenance},
    )
    assert records[0]["ion_source_provenance"] == provenance


def test_p5_18g_t28_build_records_never_emits_canonical_provenance_key(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("bounded text", encoding="utf-8")
    records = build_records(tmp_path, chunk_chars=200, overlap=0)
    assert all("ion_canonical_provenance" not in record for record in records)


def test_p5_18g_t29_qdrant_candidate_metadata_round_trip_is_exact():
    record = {
        "checksum": "c" * 64,
        "ingestion_version": "v1",
        "evidence_fingerprint": "f" * 64,
        "evidence_fingerprint_algorithm": "SHA256",
        "evidence_fingerprint_profile_id": PROFILE_ID,
        "ion_source_provenance": _valid_provenance(),
    }
    payload = {
        "checksum": record["checksum"],
        "ingestion_version": record["ingestion_version"],
        **_candidate_metadata_payload(record),
    }
    metadata = {
        k: payload[k]
        for k in _RETRIEVAL_METADATA_KEYS
        if k in payload and payload[k] is not None
    }
    assert tuple(_CANDIDATE_METADATA_KEYS) == (
        "evidence_fingerprint",
        "evidence_fingerprint_algorithm",
        "evidence_fingerprint_profile_id",
        "ion_source_provenance",
    )
    assert metadata == record


def test_p5_18g_t30_qdrant_transport_has_no_authority_activation_or_network_call():
    source = inspect.getsource(qdrant_store)
    assert "ion_canonical_provenance" not in source
    assert "fingerprint_semantics_established" not in source
    assert "provenance_authoritative" not in source
    sample = {
        "evidence_fingerprint": "f" * 64,
        "evidence_fingerprint_algorithm": "SHA256",
        "evidence_fingerprint_profile_id": PROFILE_ID,
        "ion_source_provenance": _valid_provenance(),
    }
    transported = _candidate_metadata_payload(sample)
    assert set(transported) == set(_CANDIDATE_METADATA_KEYS)