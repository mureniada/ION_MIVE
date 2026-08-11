from __future__ import annotations

import hashlib
import json

from app.modules.live1 import CoherenceRuleTableError, load_coherence_rule_table
from app.validation import SchemaValidationError
from tests.netguard import guarded
from tests.util import raises


def _table_doc(**overrides) -> dict:
    doc = {
        "rule_table_version": "synthetic-v0",
        "rules": [
            {
                "rule_id": "synthetic-rule-1",
                "r1": "SAME",
                "r2_counts": {"contradicted": {"max": 0}},
                "allowed_r6": ["MINOR_CHANGE"],
            },
        ],
        "integrity": {"sha256": "0" * 64},
    }
    doc.update(overrides)
    return doc


def _bytes_and_hash(doc: dict) -> tuple[bytes, str]:
    raw = json.dumps(doc, sort_keys=True).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()


# 1. valid table loading
@guarded
def test_valid_table_loads():
    raw, sha = _bytes_and_hash(_table_doc())
    table = load_coherence_rule_table(raw, expected_sha256=sha)
    assert table.rule_table_version == "synthetic-v0"
    assert len(table.rules) == 1
    assert table.rules[0].rule_id == "synthetic-rule-1"
    assert table.integrity["sha256"] == sha


# 11. SHA-256 mismatch rejected
@guarded
def test_sha256_mismatch_is_rejected():
    raw, _real_sha = _bytes_and_hash(_table_doc())
    with raises(CoherenceRuleTableError):
        load_coherence_rule_table(raw, expected_sha256="f" * 64)


# 7. invalid categorical enum rejected
@guarded
def test_invalid_r1_enum_is_rejected():
    doc = _table_doc(rules=[
        {"rule_id": "r1", "r1": "NOT_A_REAL_VALUE", "allowed_r6": ["MINOR_CHANGE"]},
    ])
    raw, sha = _bytes_and_hash(doc)
    with raises(SchemaValidationError):
        load_coherence_rule_table(raw, expected_sha256=sha)


@guarded
def test_invalid_allowed_r6_enum_is_rejected():
    doc = _table_doc(rules=[
        {"rule_id": "r1", "allowed_r6": ["NOT_A_REAL_R6_VALUE"]},
    ])
    raw, sha = _bytes_and_hash(doc)
    with raises(SchemaValidationError):
        load_coherence_rule_table(raw, expected_sha256=sha)


# 8. malformed count constraint rejected
@guarded
def test_malformed_count_constraint_is_rejected():
    doc = _table_doc(rules=[
        {"rule_id": "r1", "r2_counts": {"contradicted": {"min": -1}}, "allowed_r6": ["MINOR_CHANGE"]},
    ])
    raw, sha = _bytes_and_hash(doc)
    with raises(SchemaValidationError):
        load_coherence_rule_table(raw, expected_sha256=sha)


@guarded
def test_non_integer_count_constraint_is_rejected():
    doc = _table_doc(rules=[
        {"rule_id": "r1", "r2_counts": {"contradicted": {"min": "two"}}, "allowed_r6": ["MINOR_CHANGE"]},
    ])
    raw, sha = _bytes_and_hash(doc)
    with raises(SchemaValidationError):
        load_coherence_rule_table(raw, expected_sha256=sha)


# 9. min > max rejected (loader-level, not schema-level)
@guarded
def test_min_greater_than_max_is_rejected():
    doc = _table_doc(rules=[
        {"rule_id": "r1", "r2_counts": {"contradicted": {"min": 5, "max": 2}}, "allowed_r6": ["MINOR_CHANGE"]},
    ])
    raw, sha = _bytes_and_hash(doc)
    with raises(CoherenceRuleTableError):
        load_coherence_rule_table(raw, expected_sha256=sha)


# 10. duplicate rule_id rejected
@guarded
def test_duplicate_rule_id_is_rejected():
    doc = _table_doc(rules=[
        {"rule_id": "same-id", "allowed_r6": ["MINOR_CHANGE"]},
        {"rule_id": "same-id", "allowed_r6": ["MATERIAL_CHANGE"]},
    ])
    raw, sha = _bytes_and_hash(doc)
    with raises(CoherenceRuleTableError):
        load_coherence_rule_table(raw, expected_sha256=sha)


# missing required rule_id
@guarded
def test_missing_rule_id_is_rejected():
    doc = _table_doc(rules=[{"allowed_r6": ["MINOR_CHANGE"]}])
    raw, sha = _bytes_and_hash(doc)
    with raises(SchemaValidationError):
        load_coherence_rule_table(raw, expected_sha256=sha)


# malformed/empty rule collection
@guarded
def test_empty_rules_array_is_rejected():
    doc = _table_doc(rules=[])
    raw, sha = _bytes_and_hash(doc)
    with raises(SchemaValidationError):
        load_coherence_rule_table(raw, expected_sha256=sha)


# malformed allowed_r6 (must be a non-empty array of the real enum)
@guarded
def test_empty_allowed_r6_is_rejected():
    doc = _table_doc(rules=[{"rule_id": "r1", "allowed_r6": []}])
    raw, sha = _bytes_and_hash(doc)
    with raises(SchemaValidationError):
        load_coherence_rule_table(raw, expected_sha256=sha)


# invalid JSON
@guarded
def test_invalid_json_is_rejected():
    raw = b"{not valid json"
    sha = hashlib.sha256(raw).hexdigest()
    with raises(CoherenceRuleTableError):
        load_coherence_rule_table(raw, expected_sha256=sha)
