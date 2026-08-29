"""Shared IVE helpers: prompt, provider response schema, and normalization.

This is a utility library shared by the two provider adapters. It is NOT a module
calling another module — it holds no provider SDK and no port. Each provider
adapter builds the same prompt and maps native JSON into the canonical IVEReport,
then validation guarantees the contract. Provider field names never leak past here.

Prompt formatting has exactly ONE implementation, `_render_user_prompt`. Two
thin builders feed it from two different sources:

    `build_model_input_prompt(ModelContextAssembly)` — the LIVE Product path.
    Every live provider execution reaches the model boundary through this one
    (TASK 19.3).

    `build_user_prompt(ContextPack)` — a LEGACY shim kept callable only for the
    unwired `modules/live1/` experimental executor (D19-16). No live Product
    orchestration path calls it any longer.

Both delegate to the same formatter, so their output cannot silently drift
apart: an equivalent question and document set renders byte-identical text
through either entry point.

`ModelContextAssembly` is read STRUCTURALLY here, by attribute — exactly as
TASK 17 already reads a Model Context evidence item — so this module needs no
runtime import of the Model Context package and cannot reach anything beyond
the values a model may already see. `build_model_input_prompt` creates no
evidence authority: it serializes an already-authorized assembly. It does not
decide admission, rank, size, truncate, judge sufficiency, infer provenance,
rewrite evidence or invent evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.errors import NormalizationError
from ..core.models import Claim, Concept, ContextPack, IVEReport, Relation, Usage
from ..validation import validate_ive_report

# `ModelContextAssembly` is named only as a quoted forward reference below,
# with NO import anywhere in this module: the six values this module reads
# from it are read structurally, by attribute, so this module stays closed
# against the Product package that defines the type, exactly as TASK 17
# already reads a Model Context evidence item without importing TASK 16.


@dataclass
class GenerationResult:
    """Raw provider output plus usage. Providers return this from `.generate()`."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_is_estimated: bool = False
    reported_model: str | None = None


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
        "uncertainty": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
}


@dataclass(frozen=True)
class _PromptItem:
    """One document's prompt-facing values, normalized from either a
    `ContextPack` document or a `ModelContextAssembly` evidence item. Exists
    only so both sources can feed the ONE formatting implementation below."""

    id: str
    title: str
    page: str | int | None
    source: str
    content: str


def _render_user_prompt(*, question: str, items: list[_PromptItem]) -> str:
    """THE single prompt-formatting implementation. Same question and items ->
    same prompt, byte for byte, regardless of which builder below called it."""
    lines = [f"QUESTION:\n{question}", "", "CONTEXT DOCUMENTS:"]
    for item in items:
        page = "" if item.page is None else f" (page {item.page})"
        lines.append(f"[{item.id}] {item.title}{page} — source: {item.source}")
        lines.append(item.content)
        lines.append("")
    lines.append(
        "Produce the JSON object. Use the bracketed document_id values above as "
        "evidence_document_ids. If evidence is missing for a claim, say so in "
        "`uncertainty` rather than inventing support."
    )
    return "\n".join(lines)


def build_model_input_prompt(model_input: "ModelContextAssembly") -> str:
    """THE live prompt serializer: the only prompt construction on the live
    Product provider-execution path. See the module docstring."""
    items = [
        _PromptItem(
            id=item.candidate_id, title=item.title, page=item.page,
            source=item.source_identity, content=item.content,
        )
        for item in model_input.evidence
    ]
    return _render_user_prompt(question=model_input.question, items=items)


def build_user_prompt(pack: ContextPack) -> str:
    """LEGACY shim for `modules/live1/` only — see the module docstring.
    Deterministic: same pack -> same prompt."""
    items = [
        _PromptItem(id=d.document_id, title=d.title, page=d.page, source=d.source, content=d.content)
        for d in pack.documents
    ]
    return _render_user_prompt(question=pack.question, items=items)


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

    raw_map = raw.get("evidence_mapping")
    if isinstance(raw_map, dict) and raw_map:
        evidence_mapping = {str(k): [str(x) for x in (v or [])] for k, v in raw_map.items()}
    else:
        # Not requested from providers (OpenAI strict mode forbids dynamic-key objects);
        # derive faithfully from each claim's cited evidence — a restatement, not fabrication.
        evidence_mapping = {c.claim_id: list(c.evidence_document_ids) for c in claims}

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
