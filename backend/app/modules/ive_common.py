"""Shared IVE helpers: prompt, provider response schema, and normalization.

This is a utility library shared by the two provider adapters. It is NOT a module
calling another module — it holds no provider SDK and no port. Each provider
adapter builds the same prompt and maps native JSON into the canonical IVEReport,
then validation guarantees the contract. Provider field names never leak past here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.errors import NormalizationError
from ..core.models import Claim, Concept, ContextPack, IVEReport, Relation, Usage
from ..validation import validate_ive_report


@dataclass
class GenerationResult:
    """Raw provider output plus usage. Providers return this from `.generate()`."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_is_estimated: bool = False


IVE_SYSTEM_PROMPT = (
    "You are an Intelligence Validation Engine (IVE). You interpret ONLY the "
    "provided Context Pack. Do not use outside knowledge. Ground every claim in "
    "the given documents by their document_id. Express uncertainty honestly; do "
    "not present confidence as proof. Return a single JSON object matching the "
    "requested schema and nothing else."
)

# Schema handed to the provider's structured-output feature. The adapter fills
# engine_id / provider / model / question itself — the model must not set them.
IVE_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "abstract",
        "highlights",
        "claims",
        "concepts",
        "relations",
        "evidence_mapping",
        "uncertainty",
        "confidence",
    ],
    "properties": {
        "abstract": {"type": "string"},
        "highlights": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["claim_id", "statement", "evidence_document_ids", "confidence"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "statement": {"type": "string"},
                    "evidence_document_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
            },
        },
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "description"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source", "relation", "target", "evidence_document_ids"],
                "properties": {
                    "source": {"type": "string"},
                    "relation": {"type": "string"},
                    "target": {"type": "string"},
                    "evidence_document_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "evidence_mapping": {
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
        },
        "uncertainty": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
}


def build_user_prompt(pack: ContextPack) -> str:
    """Deterministic prompt from the Context Pack. Same pack -> same prompt."""
    lines = [f"QUESTION:\n{pack.question}", "", "CONTEXT DOCUMENTS:"]
    for d in pack.documents:
        page = "" if d.page is None else f" (page {d.page})"
        lines.append(f"[{d.document_id}] {d.title}{page} — source: {d.source}")
        lines.append(d.content)
        lines.append("")
    lines.append(
        "Produce the JSON object. Use the bracketed document_id values above as "
        "evidence_document_ids. If evidence is missing for a claim, say so in "
        "`uncertainty` rather than inventing support."
    )
    return "\n".join(lines)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise NormalizationError(msg)


def _num(value, msg: str) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), msg)
    return float(value)


def parse_json(text: str) -> dict:
    """Parse the provider text into a JSON object, tolerating code fences."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        # drop an optional leading language tag line
        if "\n" in s:
            first, rest = s.split("\n", 1)
            if first.strip().lower() in {"json", ""}:
                s = rest
    try:
        data = json.loads(s)
    except json.JSONDecodeError as exc:
        raise NormalizationError(f"Provider output is not valid JSON: {exc}") from None
    _require(isinstance(data, dict), "Provider output must be a JSON object.")
    return data


def normalize(
    raw: dict,
    *,
    engine_id: str,
    provider: str,
    model: str,
    question: str,
    raw_text: str,
    usage: Usage,
) -> IVEReport:
    """Map provider JSON -> canonical IVEReport, or raise NormalizationError.

    Structural containers absent from the payload become empty (faithful 'none'),
    but semantic fields (abstract, claims, per-claim confidence, report confidence,
    uncertainty) are required — never fabricated.
    """
    _require("abstract" in raw, "Missing required field: abstract.")
    _require("claims" in raw, "Missing required field: claims.")
    _require("uncertainty" in raw, "Missing required field: uncertainty.")
    _require("confidence" in raw, "Missing required field: confidence.")

    abstract = raw["abstract"]
    _require(isinstance(abstract, str), "abstract must be a string.")

    confidence = _num(raw["confidence"], "confidence must be a number.")
    _require(0.0 <= confidence <= 1.0, "confidence must be in [0, 1].")

    highlights = list(raw.get("highlights", []) or [])
    _require(all(isinstance(h, str) for h in highlights), "highlights must be strings.")

    claims: list[Claim] = []
    _require(isinstance(raw["claims"], list), "claims must be an array.")
    for i, c in enumerate(raw["claims"]):
        _require(isinstance(c, dict), "each claim must be an object.")
        _require("statement" in c and isinstance(c["statement"], str),
                 f"claim[{i}] missing string statement.")
        cconf = _num(c.get("confidence"), f"claim[{i}] missing numeric confidence.")
        _require(0.0 <= cconf <= 1.0, f"claim[{i}] confidence must be in [0, 1].")
        ev = list(c.get("evidence_document_ids", []) or [])
        _require(all(isinstance(x, str) for x in ev),
                 f"claim[{i}] evidence_document_ids must be strings.")
        claims.append(
            Claim(
                claim_id=str(c.get("claim_id") or f"c{i+1}"),
                statement=c["statement"],
                evidence_document_ids=ev,
                confidence=cconf,
            )
        )

    concepts = [
        Concept(name=str(x["name"]), description=str(x.get("description", "")))
        for x in (raw.get("concepts", []) or [])
        if isinstance(x, dict) and "name" in x
    ]
    relations = [
        Relation(
            source=str(x["source"]),
            relation=str(x["relation"]),
            target=str(x["target"]),
            evidence_document_ids=list(x.get("evidence_document_ids", []) or []),
        )
        for x in (raw.get("relations", []) or [])
        if isinstance(x, dict) and {"source", "relation", "target"} <= set(x)
    ]

    evidence_mapping = {}
    for k, v in (raw.get("evidence_mapping", {}) or {}).items():
        evidence_mapping[str(k)] = [str(x) for x in (v or [])]

    uncertainty = list(raw.get("uncertainty", []) or [])
    _require(all(isinstance(u, str) for u in uncertainty), "uncertainty must be strings.")

    report = IVEReport(
        engine_id=engine_id,
        provider=provider,
        model=model,
        question=question,
        abstract=abstract,
        highlights=highlights,
        claims=claims,
        concepts=concepts,
        relations=relations,
        evidence_mapping=evidence_mapping,
        uncertainty=uncertainty,
        confidence=confidence,
        raw_response=raw_text,
        usage=usage,
    )

    # Final guarantee: the normalized report satisfies the canonical schema.
    validate_ive_report(report.to_contract_dict())
    return report
