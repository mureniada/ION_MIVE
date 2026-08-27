from __future__ import annotations

CONTEXT_PACK_ADAPTER_SCHEMA_V0_1 = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "ION_CONTEXT_PACK_ADAPTER_JSON_SCHEMA_V0_1",
    "title": "ION Context Pack Evidence Admission Adapter Schema v0.1",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "context_pack_id",
        "context_pack_version",
        "question_id",
        "evidence_references",
        "metadata",
    ],
    "properties": {
        "context_pack_id": {"type": "string", "minLength": 1},
        "context_pack_version": {"type": "string", "minLength": 1},
        "question_id": {"type": "string", "minLength": 1},
        "evidence_references": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/EvidenceReference"},
        },
        "metadata": {"$ref": "#/$defs/AdapterMetadata"},
    },
    "$defs": {
        "EvidenceReference": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "evidence_id",
                "source_identity",
                "fingerprint",
                "fingerprint_algorithm",
                "provenance",
            ],
            "properties": {
                "evidence_id": {"type": "string", "minLength": 1},
                "source_identity": {"type": "string", "minLength": 1},
                "fingerprint": {"type": "string", "minLength": 1},
                "fingerprint_algorithm": {
                    "type": "string",
                    "enum": ["SHA256"],
                },
                "provenance": {"$ref": "#/$defs/ProvenanceRecord"},
            },
        },
        "ProvenanceRecord": {
            "type": "object",
            "additionalProperties": False,
            "required": ["origin", "producer", "created_at"],
            "properties": {
                "origin": {"type": "string", "minLength": 1},
                "producer": {"type": "string", "minLength": 1},
                "created_at": {"type": "string", "format": "date-time"},
                "chain_id": {"type": ["string", "null"]},
            },
        },
        "AdapterMetadata": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "producer",
                "created_at",
                "schema_version",
                "adapter_version",
            ],
            "properties": {
                "producer": {"type": "string", "minLength": 1},
                "created_at": {"type": "string", "format": "date-time"},
                "schema_version": {"type": "string", "const": "0.1"},
                "adapter_version": {"type": "string", "const": "0.1"},
            },
        },
    },
}
