from __future__ import annotations

import json
from types import SimpleNamespace

from app.core.errors import ProviderError
from app.modules.gemini_ive import GeminiIVE
from app.modules.model_context import (
    DISPOSITION_ADMITTED,
    CandidateContentProjection,
    build_model_context,
)
from app.modules.openai_ive import OpenAIIVE
from app.validation import validate_ive_report
from tests.fakes import FakeBackend, make_ive_json
from tests.util import raises

# HARNESS FIDELITY (TASK 19.3): provider adapters now receive the governed
# `ModelContextAssembly`, never the upstream `ContextPack` (D19-11). This
# builds one through the real, frozen `build_model_context` -- the identical
# production path `Core.ask()` uses -- over a structural governed-basis
# stand-in, so the assembly under test is genuinely the product of the real
# join logic, not a hand-shaped substitute for it.
def _pack():
    projection = CandidateContentProjection(
        document_id="doc1", content="money is credit", title="Debt",
        source_identity="src1", page=None, chunk_id=None,
    )
    governed_basis = SimpleNamespace(
        question_id="Q-TEST",
        context_pack_id="cp_test",
        admitted=(
            SimpleNamespace(candidate_id="doc1", disposition=DISPOSITION_ADMITTED),
        ),
    )
    return build_model_context(
        governed_basis=governed_basis,
        candidate_projections=[projection],
        question="What is money?",
    )


def test_gemini_valid_output_normalizes_and_validates():
    ive = GeminiIVE(FakeBackend(make_ive_json()), model="gemini-3.1-flash-lite")
    report = ive.run(_pack())
    assert report.provider == "gemini"
    assert report.engine_id == "gemini"
    assert report.model == "gemini-3.1-flash-lite"
    assert report.usage.input_tokens == 1000 and report.usage.output_tokens == 300
    assert report.usage.latency_ms is not None
    validate_ive_report(report.to_contract_dict())


def test_openai_valid_output_normalizes_and_validates():
    ive = OpenAIIVE(FakeBackend(make_ive_json()), model="gpt-5.4-mini")
    report = ive.run(_pack())
    assert report.provider == "openai"
    validate_ive_report(report.to_contract_dict())


def test_prompt_contains_pack_and_not_other_engine_output():
    backend = FakeBackend(make_ive_json())
    GeminiIVE(backend, model="gemini-3.1-flash-lite").run(_pack())
    assert "What is money?" in backend.last_prompt
    assert "money is credit" in backend.last_prompt      # evidence content present


def test_invalid_json_is_precise_provider_error():
    ive = GeminiIVE(FakeBackend("this is not json"), model="m")
    with raises(ProviderError):
        ive.run(_pack())


def test_missing_required_field_is_provider_error():
    bad = json.dumps({"abstract": "x", "highlights": [], "claims": []})  # no confidence/uncertainty
    with raises(ProviderError):
        OpenAIIVE(FakeBackend(bad), model="m").run(_pack())


def test_confidence_out_of_range_is_provider_error():
    bad = make_ive_json(confidence=1.5)
    with raises(ProviderError):
        GeminiIVE(FakeBackend(bad), model="m").run(_pack())


def test_backend_exception_is_provider_error_with_stage():
    ive = OpenAIIVE(FakeBackend("", error=RuntimeError("network down")), model="m")
    try:
        ive.run(_pack())
        assert False, "expected ProviderError"
    except ProviderError as exc:
        assert exc.stage == "openai"
