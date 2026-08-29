"""TASK 20.2 contract test: the Model Execution Profile vocabulary (v0.1).

Scope is the PURE CONTRACT only: what an `ExecutionProfile` may hold, what it
refuses, and what it structurally cannot carry. It asserts no runtime wiring,
no Model Gateway, no provider, no MIVE, no Model Context, no Core, no
container, no Settings, no renderer and no Turn Record behaviour — TASK 20.2
does not touch any of those, and TASK 20.3 (runtime SINGLE wiring) is not yet
authorized.
"""

from __future__ import annotations

import ast
import dataclasses
import io
import tokenize
from pathlib import Path

import pytest

from app.modules import execution_profile
from app.modules.execution_profile import models as models_module
from app.modules.execution_profile import profiles as profiles_module
from app.modules.execution_profile import (
    EXECUTION_PROFILE_CONTRACT_ID,
    EXECUTION_PROFILE_CONTRACT_VERSION,
    STANDARD_GEMINI,
    ExecutionMode,
    ExecutionProfile,
    ExecutionProfileError,
)

PACKAGE_DIR = Path(execution_profile.__file__).resolve().parent
MODULE_PATHS = (
    Path(models_module.__file__).resolve(),
    Path(profiles_module.__file__).resolve(),
    Path(execution_profile.__file__).resolve(),
)


def _profile(**overrides) -> ExecutionProfile:
    kwargs = dict(
        profile_id="STANDARD_GEMINI",
        profile_version="0.1",
        mode=ExecutionMode.SINGLE,
        engine_ids=("gemini",),
    )
    kwargs.update(overrides)
    return ExecutionProfile(**kwargs)


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute, relative = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.add((node.level, node.module or ""))
            else:
                absolute.add(node.module or "")
    return absolute, relative


def _identifiers(path: Path) -> set[str]:
    """Every identifier the parsed module actually uses. Docstrings excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return names


def _code_text(path: Path) -> str:
    """The file's EXECUTABLE text: comments and string literals removed."""
    source = path.read_text(encoding="utf-8")
    kept = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(token.string)
    return " ".join(kept).lower()


def _public_names(obj) -> set[str]:
    return {name for name in dir(obj) if not name.startswith("_")}


# --------------------------------------------------------------------- #
# T20-01  contract identity
# --------------------------------------------------------------------- #
def test_t20_01_contract_identity_values_are_exact():
    assert EXECUTION_PROFILE_CONTRACT_ID == "ION_MODEL_EXECUTION_PROFILE_V0_1"
    assert EXECUTION_PROFILE_CONTRACT_VERSION == "0.1"


# --------------------------------------------------------------------- #
# T20-02 / T20-03  execution mode vocabulary
# --------------------------------------------------------------------- #
def test_t20_02_execution_mode_contains_single():
    assert {m.name for m in ExecutionMode} == {"SINGLE"}
    assert {m.value for m in ExecutionMode} == {"SINGLE"}
    assert ExecutionMode.SINGLE == "SINGLE"


def test_t20_03_execution_mode_declares_no_unimplemented_future_modes():
    for absent in ("DUAL", "VERIFY", "MIVE", "FALLBACK", "AUTO", "ROUTED", "ADAPTIVE"):
        assert not hasattr(ExecutionMode, absent), absent


# --------------------------------------------------------------------- #
# T20-04 / T20-05  immutability and determinism
# --------------------------------------------------------------------- #
def test_t20_04_execution_profile_is_frozen():
    profile = _profile()
    for field, value in (
        ("profile_id", "OTHER"),
        ("profile_version", "0.2"),
        ("mode", ExecutionMode.SINGLE),
        ("engine_ids", ("openai",)),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(profile, field, value)


def test_t20_05_same_values_produce_structural_equality():
    first, second = _profile(), _profile()
    assert first is not second
    assert first == second
    assert hash(first) == hash(second)


# --------------------------------------------------------------------- #
# T20-06 / T20-07  profile_id shape
# --------------------------------------------------------------------- #
def test_t20_06_profile_id_empty_rejected():
    for refused in ("", None, 7):
        with pytest.raises(ExecutionProfileError):
            _profile(profile_id=refused)


def test_t20_07_profile_id_surrounding_whitespace_rejected():
    for refused in (" STANDARD_GEMINI", "STANDARD_GEMINI ", "\tSTANDARD_GEMINI\n"):
        with pytest.raises(ExecutionProfileError):
            _profile(profile_id=refused)


# --------------------------------------------------------------------- #
# T20-08 / T20-09  profile_version shape
# --------------------------------------------------------------------- #
def test_t20_08_profile_version_empty_rejected():
    for refused in ("", None, 7):
        with pytest.raises(ExecutionProfileError):
            _profile(profile_version=refused)


def test_t20_09_profile_version_surrounding_whitespace_rejected():
    for refused in (" 0.1", "0.1 ", "\t0.1\n"):
        with pytest.raises(ExecutionProfileError):
            _profile(profile_version=refused)


# --------------------------------------------------------------------- #
# T20-10 .. T20-14  engine_ids shape
# --------------------------------------------------------------------- #
def test_t20_10_engine_ids_must_be_tuple():
    for refused in (["gemini"], {"gemini"}, "gemini", None):
        with pytest.raises(ExecutionProfileError):
            _profile(engine_ids=refused, mode=ExecutionMode.SINGLE)


def test_t20_11_empty_engine_ids_rejected():
    with pytest.raises(ExecutionProfileError):
        ExecutionProfile(
            profile_id="X", profile_version="0.1", mode=ExecutionMode.SINGLE, engine_ids=()
        )


def test_t20_12_empty_engine_id_rejected():
    with pytest.raises(ExecutionProfileError):
        _profile(engine_ids=("",))


def test_t20_13_engine_id_surrounding_whitespace_rejected():
    for refused in ((" gemini",), ("gemini ",), ("\tgemini\n",)):
        with pytest.raises(ExecutionProfileError):
            _profile(engine_ids=refused)


def test_t20_14_duplicate_engine_ids_rejected():
    with pytest.raises(ExecutionProfileError):
        ExecutionProfile(
            profile_id="X",
            profile_version="0.1",
            mode=ExecutionMode.SINGLE,
            engine_ids=("gemini", "gemini"),
        )


# --------------------------------------------------------------------- #
# T20-15  the SINGLE invariant
# --------------------------------------------------------------------- #
def test_t20_15_single_requires_exactly_one_engine():
    with pytest.raises(ExecutionProfileError):
        _profile(engine_ids=("gemini", "openai"))
    with pytest.raises(ExecutionProfileError):
        ExecutionProfile(
            profile_id="X", profile_version="0.1", mode=ExecutionMode.SINGLE, engine_ids=()
        )
    # exactly one is legal
    assert _profile(engine_ids=("gemini",)).engine_ids == ("gemini",)


# --------------------------------------------------------------------- #
# T20-16 .. T20-20  STANDARD_GEMINI
# --------------------------------------------------------------------- #
def test_t20_16_standard_gemini_is_an_execution_profile():
    assert isinstance(STANDARD_GEMINI, ExecutionProfile)


def test_t20_17_standard_gemini_profile_id():
    assert STANDARD_GEMINI.profile_id == "STANDARD_GEMINI"


def test_t20_18_standard_gemini_profile_version():
    assert STANDARD_GEMINI.profile_version == "0.1"


def test_t20_19_standard_gemini_mode():
    assert STANDARD_GEMINI.mode == ExecutionMode.SINGLE


def test_t20_20_standard_gemini_engine_ids():
    assert STANDARD_GEMINI.engine_ids == ("gemini",)


# --------------------------------------------------------------------- #
# T20-21 / T20-22  closed dependency surface
# --------------------------------------------------------------------- #
def test_t20_21_package_imports_only_stdlib_or_own_package_dependencies():
    allowed_absolute = {"__future__", "dataclasses", "enum"}
    own_modules = {"models", "profiles"}

    for path in MODULE_PATHS:
        absolute, relative = _imports(path)
        for module in absolute:
            assert module.split(".")[0] in allowed_absolute, (path.name, module)
        for level, module in relative:
            assert level == 1, (path.name, level, module)
            assert module in own_modules, (path.name, module)


def test_t20_22_no_environment_filesystem_network_time_random_or_uuid_dependency():
    for path in MODULE_PATHS:
        used = _identifiers(path)
        for forbidden in (
            "os", "environ", "getenv",
            "open", "read_text", "read_bytes", "write_text", "write_bytes", "Path",
            "socket", "requests", "httpx", "urlopen",
            "now", "utcnow", "now_iso", "monotonic", "sleep", "time", "datetime",
            "uuid", "uuid4", "uuid5", "random",
        ):
            assert forbidden not in used, (path.name, forbidden)


# --------------------------------------------------------------------- #
# T20-23  no execution-mechanism dependency
# --------------------------------------------------------------------- #
def test_t20_23_no_gateway_provider_mive_core_container_or_config_dependency():
    for path in MODULE_PATHS:
        code = _code_text(path)
        for forbidden in (
            "model_gateway", "modelgateway", "gemini_ive", "openai_ive",
            "geminiive", "openaiive", "geminibackend", "openaibackend",
            "mive", "model_context", "modelcontextassembly",
            "governed_evidence", "governedevidenceset",
            "core_adapter", "coreadapter",
            "turn_record", "turnrecord",
            "renderer", "telemetry", "pricingtable",
            "container", "build_core", "settings",
            "genai", "openai", "google",
        ):
            assert forbidden not in code, (path.name, forbidden)

    for module in (execution_profile, models_module, profiles_module):
        for name in (
            "ModelGateway", "GeminiIVE", "OpenAIIVE", "MIVEComparator",
            "ModelContextAssembly", "build_model_context", "GovernedEvidenceSet",
            "CoreAdapter", "Core", "build_core", "Settings",
            "DeterministicRenderer", "PricingTable", "TurnRecord",
        ):
            assert not hasattr(module, name), (module.__name__, name)


# --------------------------------------------------------------------- #
# T20-24  no retry/fallback/routing/default-engine surface
# --------------------------------------------------------------------- #
def test_t20_24_no_retry_fallback_routing_or_default_engine_surface():
    for path in MODULE_PATHS:
        code = _code_text(path)
        for forbidden in (
            "retry", "fallback", "routing", "route", "timeout", "backoff",
            "temperature", "top_p", "max_output", "system_prompt", "api_key",
        ):
            assert forbidden not in code, (path.name, forbidden)

    for name in _public_names(ExecutionProfile) | _public_names(execution_profile):
        lowered = name.lower()
        for forbidden in ("retry", "fallback", "rout", "select", "choose", "default"):
            assert forbidden not in lowered, (name, forbidden)


# --------------------------------------------------------------------- #
# T20-25  no evidence/governance/authority vocabulary in contract fields
# --------------------------------------------------------------------- #
def test_t20_25_no_evidence_governance_or_authority_vocabulary_in_fields():
    field_names = {f.name for f in dataclasses.fields(ExecutionProfile)}
    assert field_names == {"profile_id", "profile_version", "mode", "engine_ids"}

    for absent in (
        "admitted", "rejected", "unknown", "evidence", "provenance",
        "confidence", "authority", "authoritative", "sufficiency", "sufficient",
        "retrieval_score", "score", "content_activation", "activation",
        "comparison_mode", "provider", "model", "requested_model",
        "retry", "fallback", "timeout", "generation_controls", "system_prompt",
        "pricing", "credentials", "api_key", "content_profile", "dialogue_profile",
        "session_id", "turn_id",
    ):
        assert absent not in field_names, absent


# --------------------------------------------------------------------- #
# T20-26  no mutable profile registry exists
# --------------------------------------------------------------------- #
def test_t20_26_no_mutable_profile_registry_exists():
    for name in (
        "PROFILE_REGISTRY", "register_profile", "discover_profiles",
        "list_profiles", "default_profile", "ProfileRegistry", "REGISTRY",
    ):
        assert not hasattr(execution_profile, name), name
        assert not hasattr(profiles_module, name), name

    # exactly one canonical profile is exported, and it is a plain instance
    assert execution_profile.__all__.count("STANDARD_GEMINI") == 1
    assert isinstance(STANDARD_GEMINI, ExecutionProfile)
    assert not isinstance(STANDARD_GEMINI, (dict, list, set))


# --------------------------------------------------------------------- #
# public surface is closed
# --------------------------------------------------------------------- #
def test_public_exports_are_exact_and_closed():
    assert set(execution_profile.__all__) == {
        "EXECUTION_PROFILE_CONTRACT_ID",
        "EXECUTION_PROFILE_CONTRACT_VERSION",
        "ExecutionMode",
        "ExecutionProfile",
        "ExecutionProfileError",
        "STANDARD_GEMINI",
    }
    assert len(execution_profile.__all__) == len(set(execution_profile.__all__))
    for name in execution_profile.__all__:
        assert hasattr(execution_profile, name), name
