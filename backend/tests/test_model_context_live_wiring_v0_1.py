"""TASK 19.3 contract test: governed Model Context LIVE WIRING (T19-3-01..26).

Scope is deliberately narrow: this covers the LIVE PRODUCT PATH wiring only —
that `Core.ask()` materializes a `ModelContextAssembly` from the governed basis
immediately after the governed-evidence gate and strictly before any engine
call, that ONLY admitted content reaches a provider, that neither the Gateway
nor a provider adapter ever receives a `ContextPack`, and that the live and
legacy prompt serializers agree byte-for-byte.

Admission, provenance and fingerprint semantics stay owned and tested by the
frozen governance modules; nothing here re-asserts them. Every governance
object below is a stand-in shaped exactly like the identical helper used in
the sibling TASK 14 / TASK 18 orchestrator suites, so a passing run proves the
WIRING law, not the governance one.

`LIVE_PRODUCT_PATH_ONLY`: TASK 19.3 (D19-16) leaves `modules/live1/` on the
legacy `ContextPack` shim deliberately. Every "no ContextPack" proof below is
scoped to the live Gateway / IVEPort / provider-adapter boundary, never to the
whole repository.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core.orchestrator as orch
import app.modules.core_adapter.facade as facade
from app.core import errors
from app.core.errors import ConfigurationError, ContextPackError, ProviderError
from app.core.models import ContextDocument, ContextPack
from app.modules import ive_common as ic
from app.modules import model_gateway, response_evidence
from app.modules.core_adapter import CoreAdapter
from app.modules.gemini_ive import GeminiIVE
from app.modules.model_context import (
    DISPOSITION_ADMITTED,
    CandidateContentProjection,
    ModelContextAssembly,
    ModelContextBuildError,
    build_model_context,
)
from app.modules.openai_ive import OpenAIIVE
from app.modules.turn_record import TurnClosureState
from tests.fakes import FakeBackend, make_ive_json

BACKEND_ROOT = Path(__file__).resolve().parents[1]

VERIFIED = "VERIFIED"
PENDING = "PENDING"
PASS = "PASS"


# --------------------------------------------------------------------- #
# T19-3-01 / T19-3-02  the projection mapping is exact, and leaks nothing
# --------------------------------------------------------------------- #
def test_t19_3_01_context_document_to_projection_mapping_is_exact():
    pack = ContextPack(
        context_pack_id="CP-MAP",
        question="a question",
        documents=[
            ContextDocument(
                document_id="D1", title="Title-1", content="Content-1",
                source="Source-1", page=7, chunk_id="c1",
            ),
            ContextDocument(
                document_id="D2", title="Title-2", content="Content-2",
                source="Source-2", page=None, chunk_id=None,
            ),
        ],
    )
    governed_basis = SimpleNamespace(
        question_id="Q-MAP",
        context_pack_id=pack.context_pack_id,
        admitted=(
            SimpleNamespace(candidate_id="D1", disposition=DISPOSITION_ADMITTED),
            SimpleNamespace(candidate_id="D2", disposition=DISPOSITION_ADMITTED),
        ),
    )

    core = orch.Core.__new__(orch.Core)
    assembly = core._materialize_model_context(governed_basis, pack, pack.question)

    assert isinstance(assembly, ModelContextAssembly)
    assert len(assembly.evidence) == 2
    d1, d2 = pack.documents
    e1, e2 = assembly.evidence
    for document, item in ((d1, e1), (d2, e2)):
        assert item.candidate_id == document.document_id
        assert item.content == document.content
        assert item.title == document.title
        assert item.source_identity == document.source
        assert item.page == document.page
        assert item.chunk_id == document.chunk_id
    assert assembly.question == pack.question
    assert assembly.context_pack_id == pack.context_pack_id
    assert assembly.question_id == "Q-MAP"


def test_t19_3_02_no_projection_metadata_score_or_provenance_leakage():
    """The projection carries exactly the six model-facing fields — nothing
    from `Evidence` (score, metadata, source_id) or from governance has any
    channel into it, because `CandidateContentProjection` has no such field."""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(CandidateContentProjection)}
    assert field_names == {"document_id", "content", "title", "source_identity", "page", "chunk_id"}

    pack = ContextPack(
        context_pack_id="CP-LEAK",
        question="q",
        documents=[ContextDocument(document_id="D1", title="T", content="C", source="S")],
    )
    governed_basis = SimpleNamespace(
        question_id="Q-LEAK", context_pack_id=pack.context_pack_id,
        admitted=(SimpleNamespace(candidate_id="D1", disposition=DISPOSITION_ADMITTED),),
    )
    core = orch.Core.__new__(orch.Core)
    assembly = core._materialize_model_context(governed_basis, pack, pack.question)
    item = assembly.evidence[0]
    evidence_field_names = {f.name for f in dataclasses.fields(type(item))}
    assert evidence_field_names == {
        "candidate_id", "content", "title", "source_identity", "page", "chunk_id",
    }
    for forbidden in ("score", "metadata", "disposition", "confidence", "authority"):
        assert not hasattr(item, forbidden)


# --------------------------------------------------------------------- #
# stand-ins for the live-`Core.ask()` sections below. Shaped identically to
# the equivalent helpers in the sibling TASK 14 / TASK 18 orchestrator suites,
# so a real `CoreAdapter` and the real frozen materializers run genuinely.
# --------------------------------------------------------------------- #
class _Clock:
    def __init__(self):
        self.value = 0

    def monotonic_ms(self):
        self.value += 1
        return float(self.value)

    def now_iso(self):
        return "2026-08-29T00:00:00Z"


class _Retrieval:
    def __init__(self, document_ids):
        self._document_ids = tuple(document_ids)

    def retrieve(self, question, top_k):
        return [SimpleNamespace(document_id=did, content="body") for did in self._document_ids]


class _Builder:
    def __init__(self, pack):
        self.pack = pack

    def build(self, question, evidence):
        return self.pack


class _Bridge:
    backend_id = "TEST-BACKEND"
    mapping_profile_id = "TEST-PROFILE"

    def resolve(self, evidence):
        return ()

    def build_request(self, *args, **kwargs):
        return SimpleNamespace(accepted=True, request=SimpleNamespace(), reasons=())


def _adapter():
    adapter = CoreAdapter.__new__(CoreAdapter)
    adapter._bridge = _Bridge()
    return adapter


def _native_for(candidate_ids):
    """Shaped exactly as the real `RuntimeAdmissionGateResult` (mirrors the
    identical helper in the sibling TASK 14 / TASK 18 orchestrator suites)."""
    return SimpleNamespace(
        records=tuple(
            SimpleNamespace(
                evidence_id=cid, status=VERIFIED, validation_id="VAL-" + cid,
                fingerprint=SimpleNamespace(algorithm="SHA256", hash="FP-" + cid, content_id=cid),
            )
            for cid in candidate_ids
        ),
        validations=tuple(
            SimpleNamespace(
                validation_id="VAL-" + cid, evidence_id=cid, result=PASS,
                blocking_reasons=(), evidence_fingerprint_hash="FP-" + cid,
            )
            for cid in candidate_ids
        ),
        transitions=tuple(
            SimpleNamespace(
                transition_id="TR-" + cid, evidence_id=cid,
                from_status=PENDING, to_status=VERIFIED, validation_id="VAL-" + cid,
            )
            for cid in candidate_ids
        ),
    )


class _Engine:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        self.calls = []

    def run(self, model_input):
        self.calls.append(model_input)
        return SimpleNamespace(
            engine_id=self.engine_id, provider=self.engine_id, model=self.engine_id + "-model",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, latency_ms=1.0, usage_is_estimated=False),
            to_contract_dict=lambda: {"engine_id": self.engine_id},
        )


class _Mive:
    def __init__(self):
        self.calls = 0

    def compare(self, reports):
        self.calls += 1
        return SimpleNamespace(to_dict=lambda: {"overall_status": "compared"})


class _Renderer:
    def render(self, **kwargs):
        return {"primary_answer": "answer"}


class _Pricing:
    def estimate_cost(self, model, input_tokens, output_tokens):
        return 0.0


def _pack_for(document_ids):
    return SimpleNamespace(
        context_pack_id="CP-LIVE",
        documents=[
            SimpleNamespace(
                document_id=did, content="body-" + did, title="Title-" + did,
                source="SRC-" + did, page=None, chunk_id=None,
            )
            for did in document_ids
        ],
        metadata={},
    )


def _core(document_ids=("D1", "D2")):
    pack = _pack_for(document_ids)
    core = orch.Core.__new__(orch.Core)
    core._settings = SimpleNamespace(
        default_top_k=1, context_char_budget=60000, qdrant_collection="ion_corpus_v1",
    )
    core._clock = _Clock()
    core._retrieval = _Retrieval(document_ids)
    core._build = _Builder(pack)
    core._core_adapter = _adapter()
    engines = {"gemini": _Engine("gemini"), "openai": _Engine("openai")}
    from app.modules.model_gateway import ModelGateway
    core._model_gateway = ModelGateway(engines)
    core._mive = _Mive()
    core._renderer = _Renderer()
    core._pricing = _Pricing()
    return core, pack, engines


def _patch_gate(monkeypatch, document_ids):
    monkeypatch.setattr(facade, "run_runtime_admission_gate", lambda **kw: _native_for(document_ids))


# --------------------------------------------------------------------- #
# T19-3-03 .. T19-3-05  materialization order, and one shared, non-pack object
# --------------------------------------------------------------------- #
def test_t19_3_03_build_model_context_runs_after_ges_and_before_any_engine(monkeypatch):
    core, pack, engines = _core()
    _patch_gate(monkeypatch, ("D1", "D2"))
    order = []

    real_build = orch.build_model_context

    def spy_build(**kwargs):
        order.append("model_context")
        return real_build(**kwargs)

    real_governed = orch.materialize_governed_evidence_set

    def spy_governed(source):
        order.append("governed_evidence")
        return real_governed(source)

    monkeypatch.setattr(orch, "build_model_context", spy_build)
    monkeypatch.setattr(orch, "materialize_governed_evidence_set", spy_governed)

    original_run_engine = orch.Core._run_engine

    def spy_run_engine(self, engine_id, model_input, stage, emit):
        order.append(engine_id)
        return original_run_engine(self, engine_id, model_input, stage, emit)

    monkeypatch.setattr(orch.Core, "_run_engine", spy_run_engine)

    core.ask("Question", top_k=1)

    assert order.index("governed_evidence") < order.index("model_context")
    assert order.index("model_context") < order.index("gemini")
    assert order.index("model_context") < order.index("openai")


def test_t19_3_04_both_engines_receive_the_same_model_context_object(monkeypatch):
    core, pack, engines = _core()
    _patch_gate(monkeypatch, ("D1", "D2"))

    core.ask("Question", top_k=1)

    gemini_input = engines["gemini"].calls[0]
    openai_input = engines["openai"].calls[0]
    assert gemini_input is openai_input
    assert isinstance(gemini_input, ModelContextAssembly)


def test_t19_3_05_neither_engine_receives_the_original_context_pack(monkeypatch):
    core, pack, engines = _core()
    _patch_gate(monkeypatch, ("D1", "D2"))

    core.ask("Question", top_k=1)

    for engine in engines.values():
        assert engine.calls[0] is not pack
        assert not isinstance(engine.calls[0], SimpleNamespace)


# --------------------------------------------------------------------- #
# T19-3-06 .. T19-3-11  builder failure blocks execution and closes truthfully
# --------------------------------------------------------------------- #
def _failing_core(monkeypatch, *, document_ids=("D1", "D2")):
    core, pack, engines = _core(document_ids)
    _patch_gate(monkeypatch, document_ids)
    boom = ModelContextBuildError("deliberate T19-3 failure")

    def explode(**kwargs):
        raise boom

    monkeypatch.setattr(orch, "build_model_context", explode)
    return core, pack, engines, boom


def test_t19_3_06_builder_failure_causes_zero_gateway_executions(monkeypatch):
    core, pack, engines, boom = _failing_core(monkeypatch)
    calls = []
    original_execute = core._model_gateway.execute

    def spy_execute(engine_id, model_input):
        calls.append(engine_id)
        return original_execute(engine_id, model_input)

    core._model_gateway.execute = spy_execute

    with pytest.raises(ContextPackError):
        core.ask("Question", top_k=1)

    assert calls == []


def test_t19_3_07_builder_failure_causes_zero_provider_executions(monkeypatch):
    core, pack, engines, boom = _failing_core(monkeypatch)

    with pytest.raises(ContextPackError):
        core.ask("Question", top_k=1)

    for engine in engines.values():
        assert engine.calls == []


def test_t19_3_08_builder_failure_causes_zero_mive_executions(monkeypatch):
    core, pack, engines, boom = _failing_core(monkeypatch)

    with pytest.raises(ContextPackError):
        core.ask("Question", top_k=1)

    assert core._mive.calls == 0


def test_t19_3_09_builder_failure_maps_to_context_pack_error(monkeypatch):
    core, pack, engines, boom = _failing_core(monkeypatch)

    with pytest.raises(ContextPackError) as excinfo:
        core.ask("Question", top_k=1)

    assert excinfo.value.stage == errors.STAGE_CONTEXT_PACK
    assert "Model context materialization failed" in str(excinfo.value)


def test_t19_3_10_original_build_error_preserved_as_cause(monkeypatch):
    core, pack, engines, boom = _failing_core(monkeypatch)

    with pytest.raises(ContextPackError) as excinfo:
        core.ask("Question", top_k=1)

    assert excinfo.value.__cause__ is boom


def test_t19_3_11_one_failed_turn_record_closes_the_builder_failure_turn(monkeypatch):
    core, pack, engines, boom = _failing_core(monkeypatch)
    outputs = []
    real_failed = orch.materialize_failed_turn_record

    def spy_failed(**kwargs):
        produced = real_failed(**kwargs)
        outputs.append(produced)
        return produced

    monkeypatch.setattr(orch, "materialize_failed_turn_record", spy_failed)
    completed_spy_calls = []
    real_completed = orch.materialize_turn_record

    def spy_completed(**kwargs):
        completed_spy_calls.append(kwargs)
        return real_completed(**kwargs)

    monkeypatch.setattr(orch, "materialize_turn_record", spy_completed)

    with pytest.raises(ContextPackError):
        core.ask("Question", top_k=1)

    assert completed_spy_calls == []
    assert len(outputs) == 1
    record = outputs[0]
    assert record.closure_state is TurnClosureState.FAILED
    assert record.model_executions == ()
    assert record.mive_overall_status is None
    assert record.failure.error_type == "ContextPackError"
    assert record.failure.error_stage == errors.STAGE_CONTEXT_PACK


# --------------------------------------------------------------------- #
# T19-3-12 .. T19-3-15  mixed basis: an excluded candidate never reaches
# the assembly, the serialized prompt, or the actual provider call
# --------------------------------------------------------------------- #
_A = CandidateContentProjection(
    document_id="CAND-A", content="ALPHA-CONTENT-9f31",
    title="ALPHA-TITLE-9f31", source_identity="ALPHA-SOURCE-9f31",
)
_B = CandidateContentProjection(
    document_id="CAND-B", content="BRAVO-CONTENT-2e77",
    title="BRAVO-TITLE-2e77", source_identity="BRAVO-SOURCE-2e77",
)
_C = CandidateContentProjection(
    document_id="CAND-C", content="CHARLIE-CONTENT-c410",
    title="CHARLIE-TITLE-c410", source_identity="CHARLIE-SOURCE-c410",
)
_B_SENTINELS = ("CAND-B", "BRAVO-CONTENT-2e77", "BRAVO-TITLE-2e77", "BRAVO-SOURCE-2e77")
_AC_SENTINELS = (
    "CAND-A", "ALPHA-CONTENT-9f31", "ALPHA-TITLE-9f31", "ALPHA-SOURCE-9f31",
    "CAND-C", "CHARLIE-CONTENT-c410", "CHARLIE-TITLE-c410", "CHARLIE-SOURCE-c410",
)


def _mixed_basis_assembly():
    governed_basis = SimpleNamespace(
        question_id="Q-MIXED", context_pack_id="CP-MIXED",
        admitted=(
            SimpleNamespace(candidate_id="CAND-A", disposition=DISPOSITION_ADMITTED),
            SimpleNamespace(candidate_id="CAND-C", disposition=DISPOSITION_ADMITTED),
        ),
    )
    return build_model_context(
        governed_basis=governed_basis, candidate_projections=[_A, _B, _C], question="mixed basis?",
    )


def test_t19_3_12_mixed_projections_admit_only_a_and_c():
    assembly = _mixed_basis_assembly()
    ids = tuple(item.candidate_id for item in assembly.evidence)
    assert ids == ("CAND-A", "CAND-C")


def test_t19_3_13_excluded_b_never_appears_in_the_serialized_prompt():
    assembly = _mixed_basis_assembly()
    prompt = ic.build_model_input_prompt(assembly)
    for sentinel in _B_SENTINELS:
        assert sentinel not in prompt


def test_t19_3_14_admitted_a_and_c_do_appear_in_the_serialized_prompt():
    assembly = _mixed_basis_assembly()
    prompt = ic.build_model_input_prompt(assembly)
    for sentinel in _AC_SENTINELS:
        assert sentinel in prompt


def test_t19_3_15_provider_invocation_receives_no_excluded_material():
    """Drives ModelContextAssembly -> real ModelGateway -> real GeminiIVE ->
    fake backend, with no network, and inspects the ACTUAL prompt the fake
    backend received -- stronger than inspecting the assembly alone."""
    from app.modules.model_gateway import ModelGateway

    assembly = _mixed_basis_assembly()
    backend = FakeBackend(make_ive_json())
    engine = GeminiIVE(backend, model="gemini-test")
    gateway = ModelGateway({"gemini": engine})

    gateway.execute("gemini", assembly)

    for sentinel in _B_SENTINELS:
        assert sentinel not in backend.last_prompt
    for sentinel in _AC_SENTINELS:
        assert sentinel in backend.last_prompt


# --------------------------------------------------------------------- #
# T19-3-16 / T19-3-17  byte-identical prompt; system prompt unchanged
# --------------------------------------------------------------------- #
def test_t19_3_16_old_and_new_serializers_produce_byte_identical_prompts():
    pack = ContextPack(
        context_pack_id="CP-BYTE",
        question="is money credit or debt?",
        documents=[
            ContextDocument(document_id="D1", title="Credit", content="money is credit",
                             source="src1", page=3, chunk_id="c1"),
            ContextDocument(document_id="D2", title="Debt", content="money is debt",
                             source="src2", page=None, chunk_id=None),
        ],
    )
    governed_basis = SimpleNamespace(
        question_id="Q-BYTE", context_pack_id=pack.context_pack_id,
        admitted=tuple(
            SimpleNamespace(candidate_id=d.document_id, disposition=DISPOSITION_ADMITTED)
            for d in pack.documents
        ),
    )
    assembly = build_model_context(
        governed_basis=governed_basis,
        candidate_projections=[
            CandidateContentProjection(
                document_id=d.document_id, content=d.content, title=d.title,
                source_identity=d.source, page=d.page, chunk_id=d.chunk_id,
            )
            for d in pack.documents
        ],
        question=pack.question,
    )

    old_prompt = ic.build_user_prompt(pack)
    new_prompt = ic.build_model_input_prompt(assembly)

    assert old_prompt == new_prompt  # exact Python string equality; no normalization


def test_t19_3_17_system_prompt_is_unchanged():
    assert ic.IVE_SYSTEM_PROMPT == (
        "You are an Intelligence Validation Engine (IVE). You interpret ONLY the "
        "provided Context Pack. Do not use outside knowledge. Ground every claim in "
        "the given documents by their document_id. Express uncertainty honestly; do "
        "not present confidence as proof. Return a single JSON object matching the "
        "requested schema and nothing else."
    )


# --------------------------------------------------------------------- #
# T19-3-18 .. T19-3-23  static ContextPack-bypass and wiring-site proofs
# --------------------------------------------------------------------- #
def _imported_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_t19_3_18_no_live_execution_interface_accepts_context_pack():
    gateway_src = (BACKEND_ROOT / "app" / "modules" / "model_gateway" / "gateway.py").read_text(
        encoding="utf-8"
    )
    gateway_tree = ast.parse(gateway_src)
    execute_node = next(
        n for n in ast.walk(gateway_tree) if isinstance(n, ast.FunctionDef) and n.name == "execute"
    )
    for arg in execute_node.args.args:
        if arg.arg in ("self", "engine_id"):
            continue
        text = ast.get_source_segment(gateway_src, arg.annotation) if arg.annotation else ""
        assert "ContextPack" not in (text or "")

    ports_src = (BACKEND_ROOT / "app" / "core" / "ports.py").read_text(encoding="utf-8")
    ports_tree = ast.parse(ports_src)
    ive_port = next(n for n in ast.walk(ports_tree) if isinstance(n, ast.ClassDef) and n.name == "IVEPort")
    run_node = next(n for n in ast.walk(ive_port) if isinstance(n, ast.FunctionDef) and n.name == "run")
    for arg in run_node.args.args:
        if arg.arg == "self":
            continue
        text = ast.get_source_segment(ports_src, arg.annotation) if arg.annotation else ""
        assert "ContextPack" not in (text or "")

    for provider_dir in ("gemini_ive", "openai_ive"):
        adapter_src = (
            BACKEND_ROOT / "app" / "modules" / provider_dir / "adapter.py"
        ).read_text(encoding="utf-8")
        adapter_tree = ast.parse(adapter_src)
        run_node = next(
            n for n in ast.walk(adapter_tree) if isinstance(n, ast.FunctionDef) and n.name == "run"
        )
        for arg in run_node.args.args:
            if arg.arg == "self":
                continue
            text = ast.get_source_segment(adapter_src, arg.annotation) if arg.annotation else ""
            assert "ContextPack" not in (text or "")


def test_t19_3_19_no_provider_adapter_imports_context_pack():
    for provider_dir in ("gemini_ive", "openai_ive"):
        adapter_path = BACKEND_ROOT / "app" / "modules" / provider_dir / "adapter.py"
        assert "ContextPack" not in _imported_names(adapter_path)


def test_t19_3_20_no_provider_adapter_invokes_the_legacy_shim():
    for provider_dir in ("gemini_ive", "openai_ive"):
        adapter_src = (
            BACKEND_ROOT / "app" / "modules" / provider_dir / "adapter.py"
        ).read_text(encoding="utf-8")
        assert "build_user_prompt(" not in adapter_src
        assert "build_model_input_prompt(" in adapter_src

    # control: the legacy shim really does still exist, for LIVE-1 (D19-16).
    assert hasattr(ic, "build_user_prompt")


def test_t19_3_21_exactly_one_production_call_site_invokes_build_model_context():
    orchestrator_src = (BACKEND_ROOT / "app" / "core" / "orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert orchestrator_src.count("build_model_context(") == 1


def test_t19_3_22_model_context_production_reference_allowlist_is_exact():
    module_dir = (BACKEND_ROOT / "app" / "modules" / "model_context").resolve()
    referring = []
    for path in sorted((BACKEND_ROOT / "app").rglob("*.py")):
        resolved = path.resolve()
        if resolved.parent == module_dir:
            continue
        if "model_context" in resolved.read_text(encoding="utf-8"):
            referring.append(str(resolved.relative_to(BACKEND_ROOT)))
    assert set(referring) == {"app/core/orchestrator.py", "app/core/ports.py"}


def test_t19_3_23_the_static_reference_proof_is_non_vacuous():
    module_dir = (BACKEND_ROOT / "app" / "modules" / "model_context").resolve()
    own_files = [p for p in module_dir.rglob("*.py")]
    assert own_files
    assert any("model_context" in p.read_text(encoding="utf-8") for p in own_files)
    unrelated = BACKEND_ROOT / "app" / "modules" / "mive" / "comparator.py"
    assert "model_context" not in unrelated.read_text(encoding="utf-8")


# --------------------------------------------------------------------- #
# T19-3-24 / T19-3-25  the Gateway stays payload-blind, policy-neutral,
# and still returns the exact IVEReport by identity
# --------------------------------------------------------------------- #
def test_t19_3_24_gateway_remains_payload_blind_and_policy_neutral():
    from app.modules.model_gateway import ModelGateway

    class _Opaque:
        def __getattr__(self, name):
            raise AssertionError(f"the Gateway inspected the model input: {name}")

    engine = _Engine("solo")
    gateway = ModelGateway({"solo": engine})
    gateway.execute("solo", _Opaque())
    assert isinstance(engine.calls[0], _Opaque)

    public = {name for name in dir(ModelGateway) if not name.startswith("_")}
    assert public == {"execute"}


def test_t19_3_25_ive_report_remains_the_canonical_execution_result():
    from app.modules.model_gateway import ModelGateway

    sentinel = object()

    class _ReportingEngine:
        engine_id = "solo"

        def run(self, model_input):
            return sentinel

    gateway = ModelGateway({"solo": _ReportingEngine()})
    assert gateway.execute("solo", object()) is sentinel


# --------------------------------------------------------------------- #
# T19-3-26  no TASK 17 wiring is introduced by this phase
# --------------------------------------------------------------------- #
def test_t19_3_26_no_task17_wiring_is_introduced():
    module_dir = Path(response_evidence.__file__).resolve().parent
    for path in sorted((BACKEND_ROOT / "app").rglob("*.py")):
        resolved = path.resolve()
        if resolved.parent == module_dir:
            continue
        assert "response_evidence" not in resolved.read_text(encoding="utf-8"), resolved
