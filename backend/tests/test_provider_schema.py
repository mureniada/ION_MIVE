"""Guard the provider-facing IVE schema against OpenAI strict-mode violations.

OpenAI Structured Outputs (strict) require every object to declare fixed
`properties`, `required` == all of those keys, and `additionalProperties: false`
(no dynamic-key maps). This regression test would have caught the evidence_mapping
defect the first live call surfaced.
"""

from __future__ import annotations

from app.core.models import Usage
from app.modules.ive_common import IVE_RESPONSE_SCHEMA, normalize


def _assert_strict(schema: dict, path: str = "root") -> None:
    t = schema.get("type")
    if t == "object":
        assert schema.get("additionalProperties") is False, \
            f"{path}: additionalProperties must be exactly False (no dynamic-key maps)"
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert required == props, f"{path}: required {required} must equal properties {props}"
        for key, sub in schema.get("properties", {}).items():
            _assert_strict(sub, f"{path}.{key}")
    elif t == "array":
        _assert_strict(schema.get("items", {}), f"{path}[]")


def test_provider_schema_is_openai_strict_compatible():
    _assert_strict(IVE_RESPONSE_SCHEMA)


def test_evidence_mapping_is_derived_from_claims_when_absent():
    raw = {
        "abstract": "a",
        "highlights": [],
        "claims": [
            {"claim_id": "c1", "statement": "s1",
             "evidence_document_ids": ["d1", "d2"], "confidence": 0.5},
            {"claim_id": "c2", "statement": "s2",
             "evidence_document_ids": [], "confidence": 0.4},
        ],
        "concepts": [],
        "relations": [],
        "uncertainty": [],
        "confidence": 0.6,
    }
    report = normalize(raw, engine_id="e", provider="p", model="m",
                       question="q", raw_text="{}", usage=Usage())
    assert report.evidence_mapping == {"c1": ["d1", "d2"], "c2": []}


def test_explicit_evidence_mapping_is_still_respected():
    raw = {
        "abstract": "a", "highlights": [],
        "claims": [{"claim_id": "c1", "statement": "s1",
                    "evidence_document_ids": ["d1"], "confidence": 0.5}],
        "concepts": [], "relations": [],
        "evidence_mapping": {"c1": ["d9"]},
        "uncertainty": [], "confidence": 0.6,
    }
    report = normalize(raw, engine_id="e", provider="p", model="m",
                       question="q", raw_text="{}", usage=Usage())
    assert report.evidence_mapping == {"c1": ["d9"]}
