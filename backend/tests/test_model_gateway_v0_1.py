"""TASK 19.2 contract test: the Model Gateway v0.1 execution mechanism (T19-01..20).

Scope is deliberately narrow: this covers RESOLUTION AND ONE EXECUTION only —
that the Gateway runs exactly the target it was explicitly given, once, returns
what that target produced by identity, and refuses an identity it does not hold.

It asserts no governance, admission, provenance, comparison, telemetry or
transport semantics. Those stay owned and tested by the frozen modules, which
TASK 19.2 does not touch.

Every engine below is a plain local stand-in. Not one test in this file imports
a concrete provider adapter or a vendor library, which is itself the
replaceability proof (T19-18): the Gateway's Product interface is satisfied by
any object that states its own `engine_id` and exposes `run()`.

Two scanning disciplines are used below, deliberately asymmetric:

    A VENDOR NAME is forbidden in RAW SOURCE, prose included. A provider name
    written even in a comment is a leak of exactly the knowledge this boundary
    exists to hold back, so T19-14 reads the file verbatim.

    A CAPABILITY is checked against EXECUTABLE SOURCE, with comments and
    docstrings removed, plus the live namespace and the public surface. What
    matters there is that the module cannot price, report, repeat, choose or
    adjudicate — not that it never explains, in words, that it does not. A raw
    scan would forbid the documentation of the very laws being proven.
"""

from __future__ import annotations

import ast
import inspect
import io
import tokenize
from pathlib import Path

import pytest

from app.core.errors import ConfigurationError, IonError, ProviderError
from app.modules import model_gateway
from app.modules.model_gateway import ModelGateway
from app.modules.model_gateway import gateway as gateway_module

GATEWAY_PACKAGE = Path(model_gateway.__file__).resolve().parent
THIS_FILE = Path(__file__).resolve()


# --------------------------------------------------------------------- #
# stand-ins. Nothing here reasons, retrieves or governs; each records the
# calls it received, so the assertions observe execution, not behaviour.
# --------------------------------------------------------------------- #
class _Engine:
    """The whole execution surface the Gateway requires, and nothing else."""

    def __init__(self, engine_id, *, report=None, error=None):
        self.engine_id = engine_id
        self.calls = []
        self.report = object() if report is None else report
        self.error = error

    def run(self, context_pack):
        self.calls.append(context_pack)
        if self.error is not None:
            raise self.error
        return self.report


class _Pack:
    """Stands in for a ContextPack. Identity is the only thing asserted on it."""


def _gateway(*engines):
    return ModelGateway({engine.engine_id: engine for engine in engines})


def _source_files():
    files = sorted(GATEWAY_PACKAGE.rglob("*.py"))
    # a scan that silently inspected nothing would prove nothing
    assert len(files) >= 2, files
    return files


def _code_text(path):
    """The file's EXECUTABLE text: comments and string literals removed.

    Docstrings are string literals, so this leaves identifiers, keywords and
    operators only — what the module can actually do, with no prose to condemn
    or to hide behind.
    """
    source = path.read_text(encoding="utf-8")
    kept = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(token.string)
    return " ".join(kept).lower()


def _imported_modules(path):
    """Every absolute and relative module name the file imports."""
    absolute, relative = [], []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            absolute.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.append((node.level, node.module or ""))
            else:
                absolute.append(node.module or "")
    return absolute, relative


def _public_names(obj):
    return {name for name in dir(obj) if not name.startswith("_")}


# --------------------------------------------------------------------- #
# T19-01 .. T19-05  resolution and one execution of one explicit target
# --------------------------------------------------------------------- #
def test_t19_01_gateway_resolves_an_explicitly_requested_engine_id():
    engine = _Engine("alpha")
    report = _gateway(engine).execute("alpha", _Pack())

    assert engine.calls, "the explicitly requested engine was never executed"
    assert report is engine.report


def test_t19_02_exactly_one_engine_is_called_exactly_once():
    alpha, beta = _Engine("alpha"), _Engine("beta")
    _gateway(alpha, beta).execute("alpha", _Pack())

    assert len(alpha.calls) == 1
    assert len(beta.calls) == 0
    # one request in, one execution out — never a second attempt of any kind
    assert len(alpha.calls) + len(beta.calls) == 1


def test_t19_03_the_same_context_pack_object_reaches_the_selected_engine():
    engine = _Engine("alpha")
    pack = _Pack()
    _gateway(engine).execute("alpha", pack)

    # identity, not equality: nothing is copied, rebuilt or re-serialized
    assert engine.calls[0] is pack


def test_t19_04_the_exact_report_object_is_returned_by_identity():
    sentinel = object()
    engine = _Engine("alpha", report=sentinel)

    assert _gateway(engine).execute("alpha", _Pack()) is sentinel


def test_t19_05_an_unselected_engine_is_never_called():
    alpha, beta = _Engine("alpha"), _Engine("beta")
    gateway = _gateway(alpha, beta)

    gateway.execute("beta", _Pack())
    gateway.execute("beta", _Pack())

    assert alpha.calls == []
    assert len(beta.calls) == 2


# --------------------------------------------------------------------- #
# T19-06 .. T19-08  an unknown identity fails closed; there is no default
# --------------------------------------------------------------------- #
def test_t19_06_unknown_engine_id_raises_configuration_error():
    gateway = _gateway(_Engine("alpha"))

    with pytest.raises(ConfigurationError) as excinfo:
        gateway.execute("beta", _Pack())

    # the EXISTING error model: no new stage entered the runtime vocabulary
    assert isinstance(excinfo.value, IonError)
    assert excinfo.value.stage == "configuration"


def test_t19_07_unknown_engine_id_causes_zero_engine_calls():
    alpha, beta = _Engine("alpha"), _Engine("beta")
    gateway = _gateway(alpha, beta)

    for unknown in ("gamma", "", "ALPHA", "alpha ", None, 7, ("alpha",)):
        with pytest.raises(ConfigurationError):
            gateway.execute(unknown, _Pack())

    # nothing near-matched, nothing was coerced, nothing stood in
    assert alpha.calls == []
    assert beta.calls == []


def test_t19_08_no_default_engine_exists():
    # a single registered engine is still not reachable under another identity
    alpha = _Engine("alpha")
    gateway = _gateway(alpha)
    with pytest.raises(ConfigurationError):
        gateway.execute("beta", _Pack())
    assert alpha.calls == []

    # an empty registry resolves nothing at all, rather than inventing a target
    with pytest.raises(ConfigurationError):
        ModelGateway({}).execute("alpha", _Pack())

    # execute() has no defaulted engine parameter to fall through
    parameters = inspect.signature(ModelGateway.execute).parameters
    assert list(parameters) == ["self", "engine_id", "context_pack"]
    for name in ("engine_id", "context_pack"):
        assert parameters[name].default is inspect.Parameter.empty


# --------------------------------------------------------------------- #
# T19-09 / T19-10  failure and success both pass through untouched
# --------------------------------------------------------------------- #
def test_t19_09_provider_error_propagates_as_the_same_exception_object():
    boom = ProviderError("engine call failed", stage="alpha")
    gateway = _gateway(_Engine("alpha", error=boom))

    with pytest.raises(ProviderError) as excinfo:
        gateway.execute("alpha", _Pack())

    assert excinfo.value is boom          # identity, not merely the same type
    assert excinfo.value.stage == "alpha"  # the engine's own stage survives
    assert excinfo.value.__cause__ is None  # nothing re-raised it "from" anything


def test_t19_10_the_gateway_does_not_wrap_the_report():
    class _Report:
        pass

    produced = _Report()
    returned = _gateway(_Engine("alpha", report=produced)).execute("alpha", _Pack())

    assert returned is produced
    assert type(returned) is _Report
    # no envelope was introduced anywhere in the module's export surface
    assert set(model_gateway.__all__) == {
        "MODEL_GATEWAY_CONTRACT_ID",
        "MODEL_GATEWAY_VERSION",
        "ModelGateway",
    }


# --------------------------------------------------------------------- #
# T19-11 / T19-12  the registry is isolated and truthful
# --------------------------------------------------------------------- #
def test_t19_11_source_registry_mutation_does_not_alter_resolution():
    alpha, beta = _Engine("alpha"), _Engine("beta")
    source = {"alpha": alpha}
    gateway = ModelGateway(source)

    source["beta"] = beta          # added after construction
    source["alpha"] = beta         # rebound after construction
    source.clear()                 # emptied after construction

    # resolution still reflects the mapping exactly as it was supplied
    assert gateway.execute("alpha", _Pack()) is alpha.report
    assert len(alpha.calls) == 1
    with pytest.raises(ConfigurationError):
        gateway.execute("beta", _Pack())
    assert beta.calls == []


def test_t19_12_registry_key_must_agree_with_the_engine_identity():
    # a key that disagrees with the engine behind it is refused, not reconciled
    with pytest.raises(ConfigurationError) as excinfo:
        ModelGateway({"alpha": _Engine("beta")})
    assert excinfo.value.stage == "configuration"

    class _Anonymous:
        """States no identity of its own."""

        def run(self, context_pack):  # pragma: no cover - never executed
            raise AssertionError("must not be reached")

    class _Inert:
        """States an identity but cannot execute."""

        engine_id = "alpha"

    for refused in (
        {"alpha": _Anonymous()},
        {"alpha": _Inert()},
        {"": _Engine("")},
        {7: _Engine("alpha")},
    ):
        with pytest.raises(ConfigurationError):
            ModelGateway(refused)

    # and the registry itself must be a mapping, not some other collection
    with pytest.raises(ConfigurationError):
        ModelGateway([_Engine("alpha")])


# --------------------------------------------------------------------- #
# T19-13 .. T19-17  what the module is structurally closed against
# --------------------------------------------------------------------- #
def test_t19_13_no_provider_module_or_vendor_library_is_imported():
    allowed_absolute = {"__future__", "collections.abc"}
    allowed_relative = {
        (3, "core.errors"),
        (3, "core.models"),
        (3, "core.ports"),
        (1, "gateway"),
    }

    for path in _source_files():
        absolute, relative = _imported_modules(path)
        for module in absolute:
            assert module in allowed_absolute, (path.name, module)
        for level, module in relative:
            assert (level, module) in allowed_relative, (path.name, level, module)

    # nothing vendor-shaped is reachable through the live package namespace
    for module in (model_gateway, gateway_module):
        for name in (
            "GeminiIVE", "OpenAIIVE", "GeminiBackend", "OpenAIBackend",
            "genai", "openai", "google", "ive_common", "build_user_prompt",
            "IVE_SYSTEM_PROMPT", "build_core", "Core", "Settings",
        ):
            assert not hasattr(module, name), (module.__name__, name)


def test_t19_14_no_provider_specific_name_appears_in_gateway_source():
    """RAW source, prose included — see this module's docstring."""
    for path in _source_files():
        source = path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "gemini", "openai", "gpt-", "google", "genai", "anthropic",
            "claude", "vertex", "azure", "api_key", "http",
        ):
            assert forbidden not in source, (path.name, forbidden)

    # the control: the scan CAN detect a token that is genuinely present
    assert any("modelgateway" in p.read_text(encoding="utf-8").lower()
               for p in _source_files())


def test_t19_15_no_pricing_or_cost_dependency_exists():
    for path in _source_files():
        code = _code_text(path)
        for forbidden in ("pricing", "cost", "token", "usage", "latency", "price"):
            assert forbidden not in code, (path.name, forbidden)

    for module in (model_gateway, gateway_module):
        for name in ("PricingTable", "PricingPort", "PRICING_AS_OF", "ProviderMetrics"):
            assert not hasattr(module, name), (module.__name__, name)


def test_t19_16_no_progress_callback_or_event_dependency_exists():
    for path in _source_files():
        code = _code_text(path)
        for forbidden in ("progress", "callback", "emit", "event", "stream", "sse"):
            assert forbidden not in code, (path.name, forbidden)

    # execute() takes no progress channel, so it cannot become one
    assert "progress" not in inspect.signature(ModelGateway.execute).parameters
    for module in (model_gateway, gateway_module):
        assert not hasattr(module, "ProgressCallback")


def test_t19_17_no_execution_policy_surface_exists():
    for path in _source_files():
        code = _code_text(path)
        for forbidden in (
            "retry", "fallback", "routing", "profile", "timeout", "attempt",
            "backoff", "temperature", "top_p", "max_output", "sleep",
        ):
            assert forbidden not in code, (path.name, forbidden)

    for name in _public_names(ModelGateway) | _public_names(model_gateway):
        lowered = name.lower()
        for forbidden in (
            "retry", "fallback", "rout", "profile", "policy", "select",
            "choose", "default", "order", "each", "every",
        ):
            assert forbidden not in lowered, (name, forbidden)


# --------------------------------------------------------------------- #
# T19-18 / T19-19  replaceability, and the absence of a bulk surface
# --------------------------------------------------------------------- #
def test_t19_18_a_fake_non_vendor_engine_satisfies_the_boundary():
    """The whole Product interface, satisfied by a class defined right here."""

    class _Report:
        def __init__(self):
            self.engine_id = "fake-1"

    class _FakeEngine:
        engine_id = "fake-1"

        def __init__(self):
            self.produced = _Report()

        def run(self, context_pack):
            return self.produced

    engine = _FakeEngine()
    pack = _Pack()

    returned = ModelGateway({"fake-1": engine}).execute("fake-1", pack)

    assert returned is engine.produced      # the fake's own real report
    assert returned.engine_id == "fake-1"

    # and reaching this point required no provider module: this test file
    # imports none, which is what makes the claim observable rather than
    # asserted. (The Gateway package's own closure is proven by T19-13.)
    absolute, relative = _imported_modules(THIS_FILE)
    for module in absolute:
        assert "gemini_ive" not in module and "openai_ive" not in module, module
        assert not module.startswith(("openai", "google")), module
    assert relative == []


def test_t19_19_no_execute_all_enumerate_or_default_behaviour_is_public():
    gateway = _gateway(_Engine("alpha"), _Engine("beta"))

    assert _public_names(ModelGateway) == {"execute"}
    for absent in (
        "engines", "engine_ids", "keys", "items", "list_engines", "all_engines",
        "execute_all", "execute_default", "execute_profile", "run_all",
        "default_engine", "first", "__iter__", "__len__", "__contains__",
        "__getitem__",
    ):
        assert not hasattr(gateway, absent), absent


# --------------------------------------------------------------------- #
# T19-20  the Gateway creates no epistemic authority
# --------------------------------------------------------------------- #
def test_t19_20_no_epistemic_admission_or_sufficiency_authority_is_introduced():
    for path in _source_files():
        code = _code_text(path)
        for forbidden in (
            "admit", "admission", "reject", "sufficien", "disposition",
            "fingerprint", "provenance", "retriev", "promote", "verdict",
            "confidence", "score", "evidence", "govern", "session",
        ):
            assert forbidden not in code, (path.name, forbidden)

    for module in (model_gateway, gateway_module):
        for name in (
            "GovernedEvidenceSet", "GovernanceDisposition", "CoreAdapter",
            "run_runtime_admission_gate", "materialize_governed_evidence_set",
            "build_model_context", "ModelContextAssembly", "MIVEComparator",
            "DeterministicRenderer", "QdrantRetrieval",
        ):
            assert not hasattr(module, name), (module.__name__, name)

    # what an engine produced is returned untouched: the Gateway neither reads
    # nor re-labels it, so model output cannot be promoted to anything here
    class _Opaque:
        def __getattr__(self, name):
            raise AssertionError(f"the Gateway inspected the report: {name}")

    produced = _Opaque()
    assert _gateway(_Engine("alpha", report=produced)).execute("alpha", _Pack()) is produced
