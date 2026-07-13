"""Shared test doubles: fake provider backends, sample IVE JSON, synthetic reports."""

from __future__ import annotations

import json

from app.core.models import Claim, IVEReport, Usage
from app.modules.ive_common import GenerationResult


class FakeBackend:
    """Stands in for a provider backend. Returns canned text or raises."""

    def __init__(self, text: str, *, input_tokens=1000, output_tokens=300, error=None):
        self._text = text
        self._in = input_tokens
        self._out = output_tokens
        self._error = error
        self.last_prompt = None
        self.calls = 0

    def generate(self, *, system: str, user: str, schema: dict) -> GenerationResult:
        self.calls += 1
        self.last_prompt = user
        if self._error is not None:
            raise self._error
        return GenerationResult(
            text=self._text, input_tokens=self._in, output_tokens=self._out
        )


def make_ive_json(
    *,
    abstract="Money is a socially constructed medium of exchange.",
    claims=None,
    concepts=None,
    relations=None,
    evidence_mapping=None,
    uncertainty=None,
    confidence=0.7,
    highlights=None,
) -> str:
    claims = claims if claims is not None else [
        {"claim_id": "c1", "statement": "Money functions as a medium of exchange.",
         "evidence_document_ids": ["doc1"], "confidence": 0.8},
    ]
    payload = {
        "abstract": abstract,
        "highlights": highlights if highlights is not None else ["Medium of exchange."],
        "claims": claims,
        "concepts": concepts if concepts is not None else [
            {"name": "Medium of exchange", "description": "A good used to intermediate trade."}
        ],
        "relations": relations if relations is not None else [],
        "evidence_mapping": evidence_mapping if evidence_mapping is not None else {"c1": ["doc1"]},
        "uncertainty": uncertainty if uncertainty is not None else ["Origins of money are debated."],
        "confidence": confidence,
    }
    return json.dumps(payload)


class DummyClock:
    def __init__(self):
        self._t = 0.0

    def now_iso(self) -> str:
        return "2026-07-13T00:00:00+00:00"

    def monotonic_ms(self) -> float:
        self._t += 1.0
        return self._t


def synthetic_report(engine_id: str, provider: str, *, claims, uncertainty=None,
                     confidence=0.7, question="What is money?") -> IVEReport:
    return IVEReport(
        engine_id=engine_id,
        provider=provider,
        model=f"{provider}-test",
        question=question,
        abstract="synthetic",
        highlights=[],
        claims=[Claim(**c) for c in claims],
        concepts=[],
        relations=[],
        evidence_mapping={},
        uncertainty=uncertainty if uncertainty is not None else [],
        confidence=confidence,
        raw_response=None,
        usage=Usage(input_tokens=100, output_tokens=50, latency_ms=1.0),
    )
