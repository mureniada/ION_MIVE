"""Bounded contract test for the isolated VOE Response Composer (Gate 3 +
Gate 3B).

Scope is deliberately narrow: this proves VOEResponseComposer satisfies
ResponseComposerPort, reuses only the provider-agnostic backend primitive
(never IVE semantics), reads no filesystem/loader, builds a deterministic
composer-owned system instruction from the four verified VOERuntimeProfile
texts (in fixed order), builds a user payload containing only the approved
IVE projection fields (with NO evidence-identity value of any kind — Gate
3B), validates output fail-closed, normalizes backend failures into the
composer-local error boundary, and truthfully preserves raw execution facts
(provider/requested_model/tokens/usage_is_estimated/latency) into a separate
ResponseComposerResult rather than discarding them or mixing them into
ComposedResponse. No Core/container/runtime wiring is exercised or implied —
nothing here calls a live provider, computes a cost, or imports
PricingPort/PricingTable/ExecutionProfile/Settings.

Absence checks (no filesystem access, no IVE import, no pricing/execution-
profile/settings import) are structural — AST inspection of composer.py's
actual imports and calls — mirroring the convention already used by
test_voe_profile_loader_v0_1.py and test_response_evidence_projection_v0_1.py,
plus runtime instrumentation checks where a claim is dynamic as well as
static.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.ports import ResponseComposerPort
from app.modules.response_composer import (
    COMPOSER_RESPONSE_SCHEMA,
    ComposedResponse,
    ComposerClaimView,
    ComposerInput,
    ResponseComposerError,
    ResponseComposerOutputError,
    ResponseComposerProviderError,
    ResponseComposerResult,
    VOEResponseComposer,
    build_composer_system_instruction,
    build_composer_user_payload,
)
from app.modules.response_composer import composer as composer_module
from app.modules.response_composer import models as composer_models_module
from app.modules.voe_profile import VOEProfileBinding, VOERuntimeProfile

COMPOSER_SOURCE = Path(composer_module.__file__).read_text(encoding="utf-8")
COMPOSER_AST = ast.parse(COMPOSER_SOURCE)
COMPOSER_MODELS_SOURCE = Path(composer_models_module.__file__).read_text(encoding="utf-8")
COMPOSER_MODELS_AST = ast.parse(COMPOSER_MODELS_SOURCE)

_DEFAULT_PROVIDER = "gemini"
_DEFAULT_REQUESTED_MODEL = "gemini-3.5-flash-test"


# --------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------- #
def _profile_binding() -> VOEProfileBinding:
    return VOEProfileBinding(
        profile_id="VOE-DIALOGUE-PROFILE",
        profile_version="0.2",
        runtime_behavioral_fingerprint_sha256="a" * 64,
    )


def _runtime_profile(**overrides) -> VOERuntimeProfile:
    defaults = dict(
        binding=_profile_binding(),
        dialogue_profile_text="MARKER_DIALOGUE :: meet the person before the answer.",
        style_parameters_text='{"MARKER_STYLE": "warmth high"}',
        ethical_policy_text="MARKER_ETHICS :: do not humiliate or shame.",
        illustrative_reasoning_policy_text="MARKER_REASONING :: metaphor is a tool, not proof.",
    )
    defaults.update(overrides)
    return VOERuntimeProfile(**defaults)


def _claim_view(**overrides) -> ComposerClaimView:
    defaults = dict(
        statement="Money functions as a medium of exchange.",
        confidence=0.8,
    )
    defaults.update(overrides)
    return ComposerClaimView(**defaults)


def _composer_input(**overrides) -> ComposerInput:
    defaults = dict(
        question="What is money?",
        report_abstract="Money is a medium of exchange, unit of account, and store of value.",
        report_highlights=("medium of exchange", "store of value"),
        report_claims=(_claim_view(),),
        report_uncertainty=("Historical origin is debated.",),
        report_confidence=0.75,
        voe_profile=_runtime_profile(),
    )
    defaults.update(overrides)
    return ComposerInput(**defaults)


class _FakeBackend:
    """Duck-typed stand-in for GeminiBackend/OpenAIBackend: exposes only
    `generate(*, system, user, schema) -> object with .text` and,
    optionally, `.input_tokens`/`.output_tokens`/`.usage_is_estimated`,
    matching how a real GenerationResult may or may not report usage."""

    def __init__(
        self, *, texts=None, text=None, raises=None,
        input_tokens=None, output_tokens=None, usage_is_estimated=None,
    ):
        self.calls: list[dict] = []
        self._texts = list(texts) if texts is not None else None
        self._text = text
        self._raises = raises
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._usage_is_estimated = usage_is_estimated

    def generate(self, *, system, user, schema):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if self._raises is not None:
            raise self._raises
        if self._texts is not None:
            text = self._texts[len(self.calls) - 1]
        else:
            text = self._text
        kwargs = {"text": text}
        if self._input_tokens is not None:
            kwargs["input_tokens"] = self._input_tokens
        if self._output_tokens is not None:
            kwargs["output_tokens"] = self._output_tokens
        if self._usage_is_estimated is not None:
            kwargs["usage_is_estimated"] = self._usage_is_estimated
        return SimpleNamespace(**kwargs)


def _ok_text(composed_text: str = "A composed answer.") -> str:
    return json.dumps({"composed_text": composed_text})


def _make_composer(backend, **overrides) -> VOEResponseComposer:
    defaults = dict(provider=_DEFAULT_PROVIDER, requested_model=_DEFAULT_REQUESTED_MODEL)
    defaults.update(overrides)
    return VOEResponseComposer(backend=backend, **defaults)


# --------------------------------------------------------------------- #
# 1: VOEResponseComposer satisfies ResponseComposerPort structurally
# --------------------------------------------------------------------- #
def test_composer_satisfies_response_composer_port():
    composer = _make_composer(_FakeBackend(text=_ok_text()))
    assert isinstance(composer, ResponseComposerPort)


def test_composer_does_not_inherit_response_composer_port():
    """Matches GeminiIVE/OpenAIIVE's own convention: structural conformance,
    never explicit inheritance from the Protocol."""
    assert ResponseComposerPort not in VOEResponseComposer.__mro__


# --------------------------------------------------------------------- #
# 2: composer accepts only ComposerInput
# --------------------------------------------------------------------- #
def test_compose_signature_accepts_exactly_one_composer_input_argument():
    sig = inspect.signature(VOEResponseComposer.compose)
    params = [p for name, p in sig.parameters.items() if name != "self"]
    assert len(params) == 1
    assert params[0].annotation in ("ComposerInput", ComposerInput) or "ComposerInput" in str(
        params[0].annotation
    )


def test_compose_rejects_a_non_composer_input_argument():
    composer = _make_composer(_FakeBackend(text=_ok_text()))
    with pytest.raises(ResponseComposerError):
        composer.compose(SimpleNamespace(question="not a real ComposerInput"))


# --------------------------------------------------------------------- #
# 3: no profile filesystem read occurs during compose()
# --------------------------------------------------------------------- #
def test_no_filesystem_read_during_compose(monkeypatch):
    calls: list[Path] = []
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def counting_read_bytes(self, *a, **kw):
        calls.append(self)
        return original_read_bytes(self, *a, **kw)

    def counting_read_text(self, *a, **kw):
        calls.append(self)
        return original_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    monkeypatch.setattr(Path, "read_text", counting_read_text)

    composer = _make_composer(_FakeBackend(text=_ok_text()))
    composer.compose(_composer_input())

    assert calls == [], f"compose() touched the filesystem: {calls}"


def test_composer_source_calls_no_filesystem_read_operation():
    """Static counterpart to the dynamic proof above: no `open(`,
    `read_bytes`, `read_text`, `Path(` construction from an argument, etc.
    appears as a call anywhere in composer.py's actual code."""
    forbidden = {"open", "read_bytes", "read_text", "iterdir", "glob", "rglob", "listdir", "scandir"}
    called_names = {
        node.func.attr
        for node in ast.walk(COMPOSER_AST)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {
        node.func.id
        for node in ast.walk(COMPOSER_AST)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    overlap = called_names & forbidden
    assert overlap == set(), f"composer.py calls forbidden I/O operation(s): {overlap}"


# --------------------------------------------------------------------- #
# 4: no voe_profile loader function is called during compose()
# --------------------------------------------------------------------- #
def test_composer_source_imports_nothing_from_voe_profile_loader():
    imported_names: set[str] = set()
    for node in ast.walk(COMPOSER_AST):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "voe_profile" in node.module:
                imported_names |= {alias.name for alias in node.names}
        if isinstance(node, ast.Import):
            imported_names |= {
                alias.name for alias in node.names if "voe_profile" in alias.name
            }
    forbidden = {"load_voe_runtime_profile", "load_voe_profile_binding", "resolve_voe_profile"}
    assert imported_names & forbidden == set(), (
        f"composer.py imports a voe_profile loader entry point: {imported_names & forbidden}"
    )
    # No bare "voe_profile" import at all, in fact.
    assert not any("voe_profile" in (n.module or "") for n in ast.walk(COMPOSER_AST) if isinstance(n, ast.ImportFrom))


def test_no_loader_function_called_during_compose(monkeypatch):
    from app.modules import voe_profile as voe_profile_pkg

    def _explode(*a, **kw):
        raise AssertionError("a voe_profile loader function was called during compose()")

    monkeypatch.setattr(voe_profile_pkg, "load_voe_runtime_profile", _explode)
    monkeypatch.setattr(voe_profile_pkg, "load_voe_profile_binding", _explode)
    monkeypatch.setattr(voe_profile_pkg, "resolve_voe_profile", _explode)

    composer = _make_composer(_FakeBackend(text=_ok_text()))
    result = composer.compose(_composer_input())
    assert isinstance(result, ResponseComposerResult)


# --------------------------------------------------------------------- #
# 5 / 6: prompt uses all four verified texts, in deterministic order
# --------------------------------------------------------------------- #
def test_system_instruction_contains_all_four_behavioral_texts():
    profile = _runtime_profile()
    instruction = build_composer_system_instruction(profile)
    assert profile.dialogue_profile_text in instruction
    assert profile.style_parameters_text in instruction
    assert profile.ethical_policy_text in instruction
    assert profile.illustrative_reasoning_policy_text in instruction


def test_system_instruction_orders_the_four_texts_01_through_04():
    profile = _runtime_profile()
    instruction = build_composer_system_instruction(profile)
    i1 = instruction.index(profile.dialogue_profile_text)
    i2 = instruction.index(profile.style_parameters_text)
    i3 = instruction.index(profile.ethical_policy_text)
    i4 = instruction.index(profile.illustrative_reasoning_policy_text)
    assert i1 < i2 < i3 < i4


def test_system_instruction_is_deterministic_for_the_same_profile():
    profile = _runtime_profile()
    assert build_composer_system_instruction(profile) == build_composer_system_instruction(profile)


def test_system_instruction_no_longer_mentions_evidence_document_ids():
    """Gate 3B: the sentence instructing the model to treat
    evidence_document_ids as opaque labels is removed, not replaced by
    another evidence-id mechanism — it must not appear anywhere in the
    instruction text."""
    instruction = build_composer_system_instruction(_runtime_profile())
    assert "evidence_document_ids" not in instruction


def test_system_instruction_still_states_no_source_authority():
    instruction = build_composer_system_instruction(_runtime_profile())
    assert "source authority" in instruction.lower() or "source material" in instruction.lower()
    assert "citation" in instruction.lower() or "cite" in instruction.lower()


# --------------------------------------------------------------------- #
# 7 / 8: no IVE prompt reuse, no ModelGateway/IVEPort import
# --------------------------------------------------------------------- #
def test_system_instruction_does_not_contain_ive_system_prompt():
    from app.modules.ive_common import IVE_SYSTEM_PROMPT

    instruction = build_composer_system_instruction(_runtime_profile())
    assert IVE_SYSTEM_PROMPT not in instruction


def test_composer_source_imports_nothing_ive_or_gateway_shaped():
    imported_modules: set[str] = set()
    for node in ast.walk(COMPOSER_AST):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        if isinstance(node, ast.Import):
            imported_modules |= {alias.name for alias in node.names}
    forbidden_substrings = ("ive_common", "model_gateway", "gemini_ive", "openai_ive", "IVEPort")
    hits = [m for m in imported_modules for f in forbidden_substrings if f in m]
    assert hits == [], f"composer.py imports IVE/ModelGateway-shaped module(s): {hits}"


def test_composer_uses_its_own_schema_not_ive_response_schema():
    from app.modules.ive_common import IVE_RESPONSE_SCHEMA

    assert COMPOSER_RESPONSE_SCHEMA != IVE_RESPONSE_SCHEMA
    assert set(COMPOSER_RESPONSE_SCHEMA["properties"]) == {"composed_text"}


# --------------------------------------------------------------------- #
# 9 / 10 / 11: user payload boundary (Gate 3B: no evidence identity at all)
# --------------------------------------------------------------------- #
def test_user_payload_contains_only_approved_projection_fields():
    payload = json.loads(build_composer_user_payload(_composer_input()))
    assert set(payload.keys()) == {
        "question", "abstract", "highlights", "claims", "uncertainty", "confidence",
    }


def test_user_payload_claims_contain_only_statement_and_confidence():
    payload = json.loads(build_composer_user_payload(_composer_input()))
    assert set(payload["claims"][0].keys()) == {"statement", "confidence"}


def test_user_payload_has_no_evidence_content_or_identity_key_anywhere():
    payload_text = build_composer_user_payload(_composer_input())
    forbidden = (
        "evidence_document_ids", "candidate_id", "document_id", "source_id",
        "source_identity", "chunk_id", '"page"', '"content"', '"title"',
    )
    for token in forbidden:
        assert token not in payload_text, f"user payload contains forbidden token {token!r}"


def test_user_payload_serialization_is_deterministic():
    ci = _composer_input()
    assert build_composer_user_payload(ci) == build_composer_user_payload(ci)


# --------------------------------------------------------------------- #
# 12: successful structured output materializes ResponseComposerResult
# --------------------------------------------------------------------- #
def test_successful_compose_returns_response_composer_result_wrapping_composed_response():
    backend = _FakeBackend(text=_ok_text("The answer, composed."))
    composer = _make_composer(backend)
    result = composer.compose(_composer_input())
    assert isinstance(result, ResponseComposerResult)
    assert isinstance(result.response, ComposedResponse)
    assert result.response.composed_text == "The answer, composed."
    assert len(backend.calls) == 1
    assert backend.calls[0]["schema"] == COMPOSER_RESPONSE_SCHEMA


# --------------------------------------------------------------------- #
# 6 / 7 / 8: ResponseComposerResult shape
# --------------------------------------------------------------------- #
def test_response_composer_result_is_immutable():
    result = _make_composer(_FakeBackend(text=_ok_text())).compose(_composer_input())
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.provider = "different"


def test_response_composer_result_field_set_is_exactly_the_approved_execution_facts():
    field_names = {f.name for f in dataclasses.fields(ResponseComposerResult)}
    assert field_names == {
        "response", "provider", "requested_model",
        "input_tokens", "output_tokens", "usage_is_estimated", "latency_ms",
    }


def test_response_composer_result_carries_no_cost_status_turnrecord_or_transport_field():
    forbidden = {
        "estimated_cost", "cost", "status", "composer_status", "fallback_status",
        "turn_id", "request_id", "session_id", "rendered", "operational_metrics",
    }
    field_names = {f.name for f in dataclasses.fields(ResponseComposerResult)}
    assert field_names & forbidden == set()


# --------------------------------------------------------------------- #
# 9 / 10: explicit provider/requested_model identity, never inferred
# --------------------------------------------------------------------- #
def test_composer_requires_explicit_provider():
    with pytest.raises(TypeError):
        VOEResponseComposer(backend=_FakeBackend(text=_ok_text()), requested_model="x")


def test_composer_requires_explicit_requested_model():
    with pytest.raises(TypeError):
        VOEResponseComposer(backend=_FakeBackend(text=_ok_text()), provider="gemini")


def test_composer_rejects_empty_provider_or_requested_model():
    with pytest.raises(ResponseComposerError):
        _make_composer(_FakeBackend(text=_ok_text()), provider="")
    with pytest.raises(ResponseComposerError):
        _make_composer(_FakeBackend(text=_ok_text()), requested_model="")


def test_result_provider_and_model_are_exactly_the_constructor_values_not_inferred():
    class _GeminiBackendLookAlike:
        """Named and shaped like a real backend, with private attributes a
        naive implementation might be tempted to read — proving the
        composer never does."""

        _model = "gemini-INTERNAL-DO-NOT-USE"
        _api_key = "not-a-real-key"

        def generate(self, *, system, user, schema):
            return SimpleNamespace(text=_ok_text())

    composer = _make_composer(
        _GeminiBackendLookAlike(), provider="openai", requested_model="gpt-5.4-mini"
    )
    result = composer.compose(_composer_input())
    assert result.provider == "openai"
    assert result.requested_model == "gpt-5.4-mini"


def test_composer_source_never_reads_backend_private_attributes_or_type():
    """Static proof to accompany the behavioral one above: composer.py never
    accesses a PEP8-private (single-leading-underscore, non-dunder)
    attribute other than its own `_backend`/`_provider`/`_requested_model`,
    so it has no code path capable of inferring provider/model identity
    from a backend's private implementation details (e.g. `_model`,
    `_api_key`). Dunder attributes (`__name__`, `__class__`, ...) are a
    different category — legitimately used here for generic error-message
    type names on `composer_input`/`raw`, never on `backend` — and are
    excluded from this check."""
    allowed = {"_backend", "_provider", "_requested_model"}
    for node in ast.walk(COMPOSER_AST):
        if not isinstance(node, ast.Attribute):
            continue
        attr = node.attr
        is_dunder = attr.startswith("__") and attr.endswith("__")
        is_private = attr.startswith("_") and not is_dunder
        if is_private and attr not in allowed:
            pytest.fail(f"composer.py accesses a private-looking attribute: .{attr}")


# --------------------------------------------------------------------- #
# 11 / 12: usage preservation, truthful and unmodified
# --------------------------------------------------------------------- #
def test_reported_usage_survives_unchanged_into_result():
    backend = _FakeBackend(
        text=_ok_text(), input_tokens=123, output_tokens=45, usage_is_estimated=False,
    )
    result = _make_composer(backend).compose(_composer_input())
    assert result.input_tokens == 123
    assert result.output_tokens == 45
    assert result.usage_is_estimated is False


def test_estimated_usage_flag_survives_unchanged_into_result():
    backend = _FakeBackend(
        text=_ok_text(), input_tokens=10, output_tokens=2, usage_is_estimated=True,
    )
    result = _make_composer(backend).compose(_composer_input())
    assert result.usage_is_estimated is True


def test_unreported_usage_becomes_none_never_fabricated():
    """A backend that reports no usage at all (no input_tokens/output_tokens
    attributes) must yield None, never an invented number."""
    backend = _FakeBackend(text=_ok_text())
    result = _make_composer(backend).compose(_composer_input())
    assert result.input_tokens is None
    assert result.output_tokens is None
    assert result.usage_is_estimated is False


# --------------------------------------------------------------------- #
# 13: latency measured, monotonic, non-negative
# --------------------------------------------------------------------- #
def test_latency_ms_is_measured_and_non_negative():
    result = _make_composer(_FakeBackend(text=_ok_text())).compose(_composer_input())
    assert isinstance(result.latency_ms, float)
    assert result.latency_ms >= 0.0


def test_latency_ms_reflects_time_spent_in_backend_call(monkeypatch):
    import time as time_module

    class _SlowBackend:
        def generate(self, *, system, user, schema):
            time_module.sleep(0.02)
            return SimpleNamespace(text=_ok_text())

    result = _make_composer(_SlowBackend()).compose(_composer_input())
    assert result.latency_ms >= 15.0  # allow scheduling slack below the 20ms sleep


def test_composer_measures_latency_with_monotonic_clock():
    """Static proof: composer.py calls `time.monotonic`, not `time.time`
    (which is not monotonic and unsuitable for duration measurement)."""
    called = {
        node.func.attr
        for node in ast.walk(COMPOSER_AST)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "monotonic" in called
    assert "time" not in called  # i.e., no bare time.time() call


# --------------------------------------------------------------------- #
# 15-18: malformed output / provider failure still fail closed, no partial result
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_text,match",
    [
        (json.dumps({"composed_text": ""}), "non-empty string"),
        (json.dumps({"composed_text": "   "}), "non-empty string"),
        (json.dumps({"not_composed_text": "x"}), "unexpected key"),
        (json.dumps({}), "missing required key"),
        (json.dumps({"composed_text": 5}), "non-empty string"),
        (json.dumps({"composed_text": None}), "non-empty string"),
        (json.dumps(["not", "an", "object"]), "must be a JSON object"),
        (json.dumps("just a string"), "must be a JSON object"),
        ("not json at all {{{", "not valid JSON"),
        ("", "no text output"),
        (json.dumps({"composed_text": "ok", "extra": "field"}), "unexpected key"),
    ],
)
def test_malformed_output_fails_closed(bad_text, match):
    composer = _make_composer(_FakeBackend(text=bad_text))
    with pytest.raises(ResponseComposerOutputError, match=match):
        composer.compose(_composer_input())


def test_none_text_fails_closed():
    composer = _make_composer(_FakeBackend(text=None))
    with pytest.raises(ResponseComposerOutputError, match="no text output"):
        composer.compose(_composer_input())


def test_malformed_output_produces_no_partial_result():
    """A raised exception means no `return` statement executed — there is no
    code path in compose() that constructs a ResponseComposerResult before
    every validation check has passed, so this is a structural guarantee;
    this test just confirms no result object escapes via any side channel
    (there is none) by checking the call genuinely raises."""
    composer = _make_composer(_FakeBackend(text="not json"))
    with pytest.raises(ResponseComposerOutputError) as exc_info:
        composer.compose(_composer_input())
    assert not hasattr(exc_info.value, "response")


def test_backend_exception_is_normalized_to_provider_error():
    backend = _FakeBackend(raises=RuntimeError("network exploded"))
    composer = _make_composer(backend)
    with pytest.raises(ResponseComposerProviderError, match="network exploded"):
        composer.compose(_composer_input())


def test_provider_failure_produces_no_partial_result():
    backend = _FakeBackend(raises=RuntimeError("boom"))
    composer = _make_composer(backend)
    with pytest.raises(ResponseComposerProviderError) as exc_info:
        composer.compose(_composer_input())
    assert not hasattr(exc_info.value, "response")


def test_backend_is_called_exactly_once_no_retry_on_failure():
    backend = _FakeBackend(raises=RuntimeError("boom"))
    composer = _make_composer(backend)
    with pytest.raises(ResponseComposerProviderError):
        composer.compose(_composer_input())
    assert len(backend.calls) == 1


def test_backend_is_called_exactly_once_no_retry_on_malformed_output():
    backend = _FakeBackend(text="not json")
    composer = _make_composer(backend)
    with pytest.raises(ResponseComposerOutputError):
        composer.compose(_composer_input())
    assert len(backend.calls) == 1


def test_composer_construction_rejects_a_backend_without_generate():
    with pytest.raises(ResponseComposerError):
        _make_composer(object())


# --------------------------------------------------------------------- #
# 19 / 20: no citation/reference/telemetry surface on ComposedResponse itself
# --------------------------------------------------------------------- #
def test_composed_response_field_set_still_has_no_citation_or_telemetry_field():
    field_names = {f.name for f in dataclasses.fields(ComposedResponse)}
    assert field_names == {
        "composed_text",
        "response_composer_contract_id",
        "response_composer_version",
    }


def test_composer_source_imports_nothing_from_response_evidence():
    imported_modules: set[str] = set()
    for node in ast.walk(COMPOSER_AST):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not any("response_evidence" in m for m in imported_modules)


# --------------------------------------------------------------------- #
# 21 / 22 / 23: no cost, no pricing, no execution-profile/settings coupling
# --------------------------------------------------------------------- #
def test_no_cost_field_or_computation_anywhere_in_response_composer():
    for tree, label in ((COMPOSER_AST, "composer.py"), (COMPOSER_MODELS_AST, "models.py")):
        identifiers = {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
        } | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        } | {
            n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)
        }
        cost_identifiers = {i for i in identifiers if "cost" in i.lower()}
        assert cost_identifiers == set(), f"{label} defines/uses cost identifier(s): {cost_identifiers}"


def test_response_composer_imports_neither_pricing_port_nor_pricing_table():
    for tree, label in ((COMPOSER_AST, "composer.py"), (COMPOSER_MODELS_AST, "models.py")):
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported |= {alias.name for alias in node.names}
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
        hits = {m for m in imported if "pricing" in m.lower() or "PricingPort" in m or "PricingTable" in m}
        assert hits == set(), f"{label} imports pricing-shaped name(s): {hits}"


def test_response_composer_imports_neither_execution_profile_nor_settings():
    for tree, label in ((COMPOSER_AST, "composer.py"), (COMPOSER_MODELS_AST, "models.py")):
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported |= {alias.name for alias in node.names}
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
        hits = {
            m for m in imported
            if "execution_profile" in m.lower() or m == "Settings" or "core.config" in m
        }
        assert hits == set(), f"{label} imports execution-profile/Settings-shaped name(s): {hits}"


# --------------------------------------------------------------------- #
# N (optional): same authority, different profile -> only composed content moves
# --------------------------------------------------------------------- #
def test_different_voe_profile_text_changes_only_composed_text_not_report_projection():
    ci = _composer_input()

    profile_a = _runtime_profile(dialogue_profile_text="MARKER_A :: warm and gentle.")
    profile_b = _runtime_profile(dialogue_profile_text="MARKER_B :: direct and plain.")

    def backend_echoing_marker():
        def _generate(*, system, user, schema):
            marker = "MARKER_A" if "MARKER_A" in system else ("MARKER_B" if "MARKER_B" in system else "NONE")
            return SimpleNamespace(text=json.dumps({"composed_text": f"answer under {marker}"}))
        return SimpleNamespace(generate=_generate)

    composer = _make_composer(backend_echoing_marker())

    result_a = composer.compose(dataclasses.replace(ci, voe_profile=profile_a))
    result_b = composer.compose(dataclasses.replace(ci, voe_profile=profile_b))

    assert result_a.response.composed_text != result_b.response.composed_text
    assert "MARKER_A" in result_a.response.composed_text
    assert "MARKER_B" in result_b.response.composed_text

    # The report projection itself was never touched: same object, same
    # values, both times — proving the composer mutates nothing upstream.
    assert ci.report_abstract == "Money is a medium of exchange, unit of account, and store of value."
    assert ci.report_claims[0].statement == "Money functions as a medium of exchange."
    assert ci.report_confidence == 0.75
