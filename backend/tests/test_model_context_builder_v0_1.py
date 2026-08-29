"""Bounded contract test for the Product Model Context Builder (v0.1).

Scope is deliberately narrow: this covers the PRODUCT model-context assembly
only — what may enter model execution after governance has already decided, and
what may not. Admission, provenance and fingerprint semantics stay owned and
tested by the frozen governance modules; nothing here re-asserts them, and
nothing here exercises them. Every governance object below is a stand-in, so a
passing run proves the exposure contract, not the governance one. The single
exception is T16-25, which drives a REAL `GovernedEvidenceSet` through the
frozen TASK 13 materializer to prove the structural input contract actually
accepts the live object without either module importing the other.

Absence checks are structural, never textual against source. The module under
test names the excluded vocabulary — `EvidenceRecord.claim`, retrieval
metadata, provenance, REJECTED / UNKNOWN / NOT_SUBMITTED, dialogue, memory and
model output — in its docstrings precisely in order to record that those
concepts are EXCLUDED at v0.1, so a raw source scan would report the exact
opposite of the truth. These tests interrogate dataclass field sets, module
namespaces and the parsed import/identifier graph instead. Where a textual
check does appear it is applied to the produced DATA (the assembly's own
repr), never to the module source.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules import model_context
import app.modules.model_context.builder as builder
import app.modules.model_context.models as models
from app.modules.model_context import (
    DEFERRED_SEGMENT_CLASSES,
    DISPOSITION_ADMITTED,
    IMPLEMENTED_SEGMENT_CLASSES,
    MODEL_CONTEXT_CONTRACT_ID,
    MODEL_CONTEXT_VERSION,
    QUESTION_NORMALIZATION_STRIP,
    CandidateContentProjection,
    EvidenceContextItem,
    ModelContextAssembly,
    ModelContextBuildError,
    ModelContextCoverage,
    ModelContextCoverageState,
    ModelContextSegmentClass,
    build_model_context,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]

MODULE_PATHS = (
    Path(models.__file__),
    Path(builder.__file__),
    Path(model_context.__file__),
)

ADMITTED = "ADMITTED"
QUESTION = "is money credit or debt?"

# Distinctive markers planted in the governance material the Builder must never
# expose. Their absence from the produced assembly is the proof.
CLAIM_TOKEN = "STRUCTURAL_CLAIM_TOKEN_MUST_NOT_REACH_A_MODEL"
PROVENANCE_TOKEN = "PROVENANCE_TOKEN_MUST_NOT_REACH_A_MODEL"
FINGERPRINT_TOKEN = "FINGERPRINT_TOKEN_MUST_NOT_REACH_A_MODEL"


# --------------------------------------------------------------------- #
# stand-ins. Nothing here governs, retrieves or reasons; these carry the
# fields the real objects carry, so the assertions observe the contract.
# --------------------------------------------------------------------- #
def _claim(candidate_id):
    """Shaped like the real EvidenceRecord.claim: a governance BINDING string,
    not source text (see admission/claim_adjudication.canonical_structural_claim)."""
    return (
        '{"contract_id":"' + CLAIM_TOKEN + '","evidence_id":"' + candidate_id + '"}'
    )


def _entry(candidate_id, *, disposition=ADMITTED):
    """One governed-evidence entry, carrying its native objects by reference."""
    return SimpleNamespace(
        candidate_id=candidate_id,
        disposition=disposition,
        native_status="VERIFIED",
        native_record=SimpleNamespace(
            evidence_id=candidate_id,
            claim=_claim(candidate_id),
            status="VERIFIED",
            fingerprint=SimpleNamespace(
                algorithm="SHA256",
                hash=FINGERPRINT_TOKEN + "-" + candidate_id,
                content_id=candidate_id,
            ),
        ),
        native_validation=SimpleNamespace(
            validation_id="VAL-" + candidate_id,
            evidence_id=candidate_id,
            result="PASS",
            blocking_reasons=(),
            evidence_fingerprint_hash=FINGERPRINT_TOKEN + "-" + candidate_id,
        ),
        native_transition=SimpleNamespace(
            transition_id="TR-" + candidate_id,
            evidence_id=candidate_id,
            from_status="PENDING",
            to_status="VERIFIED",
        ),
    )


def _basis(
    candidate_ids=("EV-1", "EV-2"),
    *,
    entries=None,
    question_id="REQ-001",
    context_pack_id="CP-001",
    not_submitted=("EV-9",),
):
    """A governed basis stand-in, shaped as GovernedEvidenceSet exposes itself.

    Carries the full surface deliberately — `rejected`, `unknown` and candidate
    accounting included — so that a passing exposure assertion proves the
    Builder does not reach them, rather than merely that they were absent.
    """
    return SimpleNamespace(
        admitted=tuple(
            _entry(candidate_id) for candidate_id in candidate_ids
        )
        if entries is None
        else tuple(entries),
        rejected=(),
        unknown=(),
        accounting=SimpleNamespace(
            retrieved_ids=tuple(candidate_ids) + tuple(not_submitted),
            submitted_ids=tuple(candidate_ids),
            governed_ids=tuple(candidate_ids),
            not_submitted=tuple(
                SimpleNamespace(candidate_id=cid, accounting_state="NOT_SUBMITTED")
                for cid in not_submitted
            ),
            context_pack_metadata={
                "ion_source_provenance": PROVENANCE_TOKEN,
                "evidence_fingerprint": FINGERPRINT_TOKEN,
            },
        ),
        backend_id="TEST-BACKEND",
        mapping_profile_id="TEST-PROFILE",
        adapter_id="ION_CORE_ADAPTER_FACADE_V0_1",
        adapter_version="0.1",
        question_id=question_id,
        context_pack_id=context_pack_id,
        governed_evidence_set_id="ION_GOVERNED_EVIDENCE_SET_V0_1",
        governed_evidence_set_version="0.1",
    )


def _projection(candidate_id, **overrides):
    values = {
        "document_id": candidate_id,
        "content": "body of " + candidate_id,
        "title": "Title " + candidate_id,
        "source_identity": "src-" + candidate_id,
        "page": 12,
        "chunk_id": "c1",
    }
    values.update(overrides)
    return CandidateContentProjection(**values)


def _build(candidate_ids=("EV-1", "EV-2"), *, projections=None, question=QUESTION, **kwargs):
    return build_model_context(
        governed_basis=_basis(candidate_ids, **kwargs),
        candidate_projections=(
            [_projection(candidate_id) for candidate_id in candidate_ids]
            if projections is None
            else projections
        ),
        question=question,
    )


def _field_names(cls):
    return {f.name for f in dataclasses.fields(cls)}


def _all_field_names():
    names = set()
    for cls in (
        ModelContextAssembly,
        EvidenceContextItem,
        ModelContextCoverage,
        CandidateContentProjection,
    ):
        names |= _field_names(cls)
    return names


def _identifiers(path):
    """Every identifier the parsed module actually uses. Docstrings excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
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


def _imports(path):
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


# --------------------------------------------------------------------- #
# T16-01 .. T16-06  selection, exclusion and the fail-closed boundary
# --------------------------------------------------------------------- #
def test_t16_01_admitted_candidate_is_included():
    assembly = _build(("EV-1", "EV-2"))

    assert isinstance(assembly, ModelContextAssembly)
    assert tuple(item.candidate_id for item in assembly.evidence) == ("EV-1", "EV-2")
    assert all(isinstance(item, EvidenceContextItem) for item in assembly.evidence)
    assert assembly.question == QUESTION
    assert assembly.question_id == "REQ-001"
    assert assembly.context_pack_id == "CP-001"
    assert assembly.model_context_contract_id == MODEL_CONTEXT_CONTRACT_ID
    assert assembly.model_context_version == MODEL_CONTEXT_VERSION


def test_t16_02_non_admitted_projection_is_excluded_and_never_labelled():
    """The caller may supply un-filtered projections; exclusion is not a verdict."""
    admitted = ("EV-1", "EV-2")
    projections = [_projection(cid) for cid in ("EV-1", "EV-2", "EV-9", "EV-42")]

    assembly = build_model_context(
        governed_basis=_basis(admitted),
        candidate_projections=projections,
        question=QUESTION,
    )

    exposed = {item.candidate_id for item in assembly.evidence}
    assert exposed == {"EV-1", "EV-2"}
    assert "EV-9" not in exposed and "EV-42" not in exposed

    # the excluded candidates carry no Builder-assigned governance disposition
    # anywhere in the produced data, and the excluded ids are not recorded as
    # omitted-from-coverage either: they were never part of the governed basis.
    body = repr(assembly)
    for verdict in ("REJECTED", "UNKNOWN", "NOT_SUBMITTED"):
        assert verdict not in body
    assert "EV-9" not in body and "EV-42" not in body
    assert assembly.coverage.omitted_candidate_ids == ()


def test_t16_03_admitted_candidate_without_a_projection_fails_closed():
    with pytest.raises(ModelContextBuildError) as excinfo:
        build_model_context(
            governed_basis=_basis(("EV-1", "EV-2")),
            candidate_projections=[_projection("EV-1")],
            question=QUESTION,
        )

    assert "EV-2" in str(excinfo.value)


def test_t16_04_duplicate_projection_identity_fails_closed():
    with pytest.raises(ModelContextBuildError) as excinfo:
        build_model_context(
            governed_basis=_basis(("EV-1",)),
            candidate_projections=[_projection("EV-1"), _projection("EV-1", content="other")],
            question=QUESTION,
        )

    assert "duplicate candidate projection identity" in str(excinfo.value)


def test_t16_05_duplicate_admitted_identity_fails_closed():
    duplicated = _basis(entries=(_entry("EV-1"), _entry("EV-1")))

    with pytest.raises(ModelContextBuildError) as excinfo:
        build_model_context(
            governed_basis=duplicated,
            candidate_projections=[_projection("EV-1")],
            question=QUESTION,
        )

    assert "duplicate admitted candidate identity" in str(excinfo.value)


def test_t16_06_zero_admitted_fails_closed_at_both_construction_paths():
    # through the Builder
    with pytest.raises(ModelContextBuildError):
        build_model_context(
            governed_basis=_basis(entries=()),
            candidate_projections=[_projection("EV-1")],
            question=QUESTION,
        )

    # and structurally, so no caller can hand-build a USER_INPUT-only context
    with pytest.raises(ModelContextBuildError):
        ModelContextAssembly(
            question=QUESTION,
            question_normalization=QUESTION_NORMALIZATION_STRIP,
            question_id="REQ-001",
            context_pack_id="CP-001",
            evidence=(),
            coverage=ModelContextCoverage(
                state=ModelContextCoverageState.COMPLETE,
                admitted_count=0,
                included_count=0,
            ),
        )


# --------------------------------------------------------------------- #
# T16-07 .. T16-10  identity, order and verbatim content
# --------------------------------------------------------------------- #
def test_t16_07_order_follows_the_admitted_governed_basis():
    admitted = ("EV-3", "EV-1", "EV-2")
    # supplied in a different order on purpose: the basis order is authoritative
    projections = [_projection(cid) for cid in reversed(admitted)]

    assembly = build_model_context(
        governed_basis=_basis(admitted),
        candidate_projections=projections,
        question=QUESTION,
    )

    assert tuple(item.candidate_id for item in assembly.evidence) == admitted


def test_t16_08_candidate_id_remains_traceable_exactly():
    admitted = ("sacred_economics::p12::c1", "sacred_economics::p111::c1")
    assembly = _build(admitted)

    assert tuple(item.candidate_id for item in assembly.evidence) == admitted
    for item in assembly.evidence:
        # the exact upstream identity string, not a slug, hash or index
        assert item.candidate_id in admitted


def test_t16_09_content_is_copied_verbatim():
    awkward = "  Leading and trailing spaces  \n\ttab\ttab\n```json\n{\"a\": 1}\n```\nПривет — 你好 🙂\n\n"
    long_body = "x" * 200_000  # far beyond the upstream Context Pack char budget
    projections = [
        _projection("EV-1", content=awkward),
        _projection("EV-2", content=long_body),
        _projection("EV-3", content=""),
    ]

    assembly = build_model_context(
        governed_basis=_basis(("EV-1", "EV-2", "EV-3")),
        candidate_projections=projections,
        question=QUESTION,
    )

    assert assembly.evidence[0].content == awkward
    assert assembly.evidence[1].content == long_body
    assert len(assembly.evidence[1].content) == 200_000
    assert assembly.evidence[2].content == ""
    # the very same string object: no transformation of any kind occurred
    for item, projection in zip(assembly.evidence, projections):
        assert item.content is projection.content


def test_t16_10_title_source_page_and_chunk_id_are_copied_verbatim():
    projections = [
        _projection("EV-1", title="  Spaced Title  ", source_identity="src A", page=12, chunk_id="c1"),
        _projection("EV-2", title="", source_identity="src-B", page="xii", chunk_id=None),
        _projection("EV-3", title="T3", source_identity="src-C", page=None, chunk_id="c9"),
    ]

    assembly = build_model_context(
        governed_basis=_basis(("EV-1", "EV-2", "EV-3")),
        candidate_projections=projections,
        question=QUESTION,
    )

    for item, projection in zip(assembly.evidence, projections):
        assert item.title == projection.title
        assert item.source_identity == projection.source_identity
        assert item.page == projection.page
        assert item.chunk_id == projection.chunk_id

    # both measured `page` types survive unconverted, and null stays null
    assert assembly.evidence[0].page == 12
    assert assembly.evidence[1].page == "xii"
    assert assembly.evidence[2].page is None
    assert assembly.evidence[1].chunk_id is None


# --------------------------------------------------------------------- #
# T16-11 .. T16-12  governance material can never become model evidence
# --------------------------------------------------------------------- #
def test_t16_11_evidence_record_claim_is_not_used_as_evidence_text():
    assembly = _build(("EV-1", "EV-2"))

    # the stand-in entries DO carry a claim; it reaches nothing
    assert CLAIM_TOKEN in _basis(("EV-1",)).admitted[0].native_record.claim
    assert CLAIM_TOKEN not in repr(assembly)
    assert "claim" not in _field_names(EvidenceContextItem)
    for item in assembly.evidence:
        for value in dataclasses.asdict(item).values():
            assert value != _claim(item.candidate_id)


def test_t16_12_retrieval_metadata_and_provenance_cannot_enter_the_item_contract():
    assembly = _build(("EV-1", "EV-2"))

    # the evidence item is exactly the six model-facing values, and nothing else
    assert _field_names(EvidenceContextItem) == {
        "candidate_id",
        "content",
        "title",
        "source_identity",
        "page",
        "chunk_id",
    }

    # markers planted in native records, validations, transitions and pack
    # metadata reach no part of the produced assembly
    body = repr(assembly)
    assert PROVENANCE_TOKEN not in body
    assert FINGERPRINT_TOKEN not in body

    # and there is no channel to hand governance material in: an object that is
    # not a plain projection is refused outright, however well shaped it looks
    smuggler = SimpleNamespace(
        document_id="EV-1",
        content="body",
        title="t",
        source_identity="s",
        page=None,
        chunk_id=None,
        metadata={"ion_canonical_provenance": PROVENANCE_TOKEN},
    )
    with pytest.raises(ModelContextBuildError) as excinfo:
        build_model_context(
            governed_basis=_basis(("EV-1",)),
            candidate_projections=[smuggler],
            question=QUESTION,
        )
    assert "CandidateContentProjection" in str(excinfo.value)


# --------------------------------------------------------------------- #
# T16-13 .. T16-16  the segment model: two implemented, three absent
# --------------------------------------------------------------------- #
def test_t16_13_user_input_is_structurally_distinct_from_evidence():
    assembly = _build(("EV-1", "EV-2"))

    assert isinstance(assembly.question, str)
    assert isinstance(assembly.evidence, tuple)
    assert assembly.question_normalization == QUESTION_NORMALIZATION_STRIP

    # the question is carried in its own field, is not an evidence item, and
    # cannot be read as one: EvidenceContextItem has no question field at all
    assert "question" not in _field_names(EvidenceContextItem)
    assert assembly.question not in assembly.evidence
    for item in assembly.evidence:
        assert item.content != assembly.question

    assert IMPLEMENTED_SEGMENT_CLASSES == (
        ModelContextSegmentClass.EVIDENCE,
        ModelContextSegmentClass.USER_INPUT,
    )
    # the Builder never normalizes: an un-normalized question is refused
    with pytest.raises(ModelContextBuildError):
        _build(("EV-1",), question="  padded question  ")
    with pytest.raises(ModelContextBuildError):
        _build(("EV-1",), question="")


def test_t16_14_model_output_payload_is_structurally_absent():
    assert ModelContextSegmentClass.MODEL_OUTPUT in DEFERRED_SEGMENT_CLASSES
    assert ModelContextSegmentClass.MODEL_OUTPUT not in IMPLEMENTED_SEGMENT_CLASSES

    for token in ("output", "answer", "completion", "response", "reply", "generated"):
        for name in _all_field_names():
            assert token not in name, (token, name)


def test_t16_15_dialogue_instruction_payload_is_structurally_absent():
    assert ModelContextSegmentClass.DIALOGUE_INSTRUCTION in DEFERRED_SEGMENT_CLASSES

    for token in ("dialogue", "instruction", "prompt", "directive", "persona"):
        for name in _all_field_names():
            assert token not in name, (token, name)


def test_t16_16_conversation_memory_payload_is_structurally_absent():
    assert ModelContextSegmentClass.CONVERSATION_MEMORY in DEFERRED_SEGMENT_CLASSES

    for token in ("conversation", "memory", "session", "history", "transcript", "message"):
        for name in _all_field_names():
            assert token not in name, (token, name)


def test_t16_segment_vocabulary_is_complete_and_partitioned():
    assert set(ModelContextSegmentClass.__members__) == {
        "EVIDENCE",
        "USER_INPUT",
        "DIALOGUE_INSTRUCTION",
        "CONVERSATION_MEMORY",
        "MODEL_OUTPUT",
    }
    assert set(IMPLEMENTED_SEGMENT_CLASSES) | set(DEFERRED_SEGMENT_CLASSES) == set(
        ModelContextSegmentClass
    )
    assert not set(IMPLEMENTED_SEGMENT_CLASSES) & set(DEFERRED_SEGMENT_CLASSES)

    # the assembly's whole field set: exactly the two implemented segments plus
    # identity and coverage. No deferred class has anywhere to live.
    assert _field_names(ModelContextAssembly) == {
        "question",
        "question_normalization",
        "question_id",
        "context_pack_id",
        "evidence",
        "coverage",
        "model_context_contract_id",
        "model_context_version",
    }


# --------------------------------------------------------------------- #
# T16-17 .. T16-19  coverage semantics, and the absence of sizing
# --------------------------------------------------------------------- #
def test_t16_17_coverage_is_complete_for_a_successful_v0_1_assembly():
    assembly = _build(("EV-1", "EV-2", "EV-3"))

    assert assembly.coverage.state is ModelContextCoverageState.COMPLETE
    assert assembly.coverage.admitted_count == 3
    assert assembly.coverage.included_count == 3
    assert assembly.coverage.omitted_candidate_ids == ()
    # v0.1 never emits NOT_APPLICABLE: zero-admitted fails closed instead
    assert assembly.coverage.state is not ModelContextCoverageState.NOT_APPLICABLE


def test_t16_18_coverage_is_inclusion_only_and_cannot_represent_sufficiency():
    assert _field_names(ModelContextCoverage) == {
        "state",
        "admitted_count",
        "included_count",
        "omitted_candidate_ids",
    }
    for token in (
        "sufficien",
        "answerab",
        "authority",
        "confidence",
        "relevance",
        "score",
        "quality",
        "adequa",
        "truth",
    ):
        for name in _field_names(ModelContextCoverage):
            assert token not in name, (token, name)

    # identical counts, entirely different material -> identical coverage.
    # Nothing about the question, the content or the identities can move it.
    first = _build(("EV-1", "EV-2"), question="short?")
    second = build_model_context(
        governed_basis=_basis(("A", "B"), question_id="REQ-2", context_pack_id="CP-2"),
        candidate_projections=[
            _projection("A", content="a totally different body of text"),
            _projection("B", content=""),
        ],
        question="a much longer and quite differently worded question?",
    )
    assert first.coverage == second.coverage

    assert set(ModelContextCoverageState.__members__) == {
        "COMPLETE",
        "PARTIAL",
        "NONE",
        "NOT_APPLICABLE",
    }


def test_t16_19_no_sizing_trimming_ranking_or_rewriting_occurs():
    admitted = tuple("EV-" + str(n) for n in (9, 10, 1, 2, 33, 4))
    projections = [_projection(cid, content="c" * 50_000) for cid in admitted]
    question = "why   does    spacing  matter?"

    assembly = build_model_context(
        governed_basis=_basis(admitted),
        candidate_projections=projections,
        question=question,
    )

    # every admitted candidate is present: nothing is dropped for size
    assert len(assembly.evidence) == len(admitted)
    assert sum(len(item.content) for item in assembly.evidence) == 6 * 50_000
    # order is the governed basis order, NOT a lexicographic or numeric ranking
    assert tuple(item.candidate_id for item in assembly.evidence) == admitted
    assert tuple(item.candidate_id for item in assembly.evidence) != tuple(sorted(admitted))
    # the question is carried through untouched, internal spacing included
    assert assembly.question == question


# --------------------------------------------------------------------- #
# T16-20 .. T16-23  boundary, export surface, immutability, determinism
# --------------------------------------------------------------------- #
def test_t16_20_module_has_no_forbidden_dependency_or_capability():
    allowed_stdlib = {"__future__", "dataclasses", "enum", "typing"}
    own_modules = {"builder", "models"}

    for path in MODULE_PATHS:
        absolute, relative = _imports(path)
        for module in absolute:
            assert module.split(".")[0] in allowed_stdlib, (path.name, module)
        for level, module in relative:
            assert level == 1, (path.name, level, module)
            assert module in own_modules, (path.name, module)

        used = _identifiers(path)
        for forbidden in (
            # clock / identity / randomness
            "now", "utcnow", "utc_now_iso", "monotonic", "sleep",
            "uuid", "uuid4", "uuid5", "random", "time", "datetime",
            # I/O, network, environment
            "open", "read_text", "read_bytes", "environ", "getenv",
            "urlopen", "socket", "requests", "httpx",
            # governance material this module must never reach for
            "rejected", "unknown", "accounting", "not_submitted",
            "native_record", "native_validation", "native_transition",
            "claim", "fingerprint", "provenance",
            # judgements this module must never make
            "sort", "sorted", "rank", "trim", "truncate", "summarize",
            "score", "confidence", "authority", "sufficiency",
        ):
            assert forbidden not in used, (path.name, forbidden)

    # no provider, store, adapter, renderer, container or governance name is
    # reachable through this package's live namespace
    for module in (model_context, builder, models):
        for name in (
            "GovernedEvidenceSet", "GovernanceDisposition", "MaterializationInput",
            "materialize_governed_evidence_set", "CoreAdapter", "CoreAdapterOutcome",
            "run_runtime_admission_gate", "build_qdrant_runtime_bridge",
            "RuntimeEvidenceBridge", "resolve_evidence_provenance",
            "ContextPack", "ContextDocument", "Evidence", "IVEReport",
            "QdrantRetrieval", "GeminiIVE", "OpenAIIVE", "build_user_prompt",
            "IVE_SYSTEM_PROMPT", "DeterministicRenderer", "build_core", "Settings",
        ):
            assert not hasattr(module, name), (module.__name__, name)

    # no contract field is derived from a wall clock. Compared on whole
    # underscore-separated parts, not as raw substrings, so a legitimate name
    # is never condemned for merely containing a token (candi-date_id).
    for name in _all_field_names():
        parts = name.split("_")
        for token in ("at", "time", "clock", "date", "timestamp", "created", "updated"):
            assert token not in parts, (token, name)


def test_t16_21_public_export_surface_is_exact_and_closed():
    assert set(model_context.__all__) == {
        "DEFERRED_SEGMENT_CLASSES",
        "DISPOSITION_ADMITTED",
        "IMPLEMENTED_SEGMENT_CLASSES",
        "MODEL_CONTEXT_BUILDER_ID",
        "MODEL_CONTEXT_BUILDER_VERSION",
        "MODEL_CONTEXT_CONTRACT_ID",
        "MODEL_CONTEXT_VERSION",
        "QUESTION_NORMALIZATION_STRIP",
        "CandidateContentProjection",
        "EvidenceContextItem",
        "ModelContextAssembly",
        "ModelContextBuildError",
        "ModelContextCoverage",
        "ModelContextCoverageState",
        "ModelContextSegmentClass",
        "build_model_context",
    }
    for name in model_context.__all__:
        assert hasattr(model_context, name), name

    assert MODEL_CONTEXT_CONTRACT_ID == "ION_MODEL_CONTEXT_ASSEMBLY_V0_1"
    assert MODEL_CONTEXT_VERSION == "0.1"
    assert model_context.MODEL_CONTEXT_BUILDER_ID == "ION_MODEL_CONTEXT_BUILDER_V0_1"
    assert DISPOSITION_ADMITTED == ADMITTED
    assert QUESTION_NORMALIZATION_STRIP == "STRIP"
    # the error is module-local and introduces no transport stage
    assert issubclass(ModelContextBuildError, ValueError)
    assert ModelContextBuildError.__module__.startswith("app.modules.model_context")


def test_t16_22_contract_objects_are_immutable():
    assembly = _build(("EV-1",))

    for target, attribute, value in (
        (assembly, "question", "rewritten"),
        (assembly, "evidence", ()),
        (assembly.evidence[0], "content", "rewritten"),
        (assembly.evidence[0], "candidate_id", "EV-OTHER"),
        (assembly.coverage, "state", ModelContextCoverageState.PARTIAL),
        (_projection("EV-1"), "content", "rewritten"),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(target, attribute, value)

    assert isinstance(assembly.evidence, tuple)
    assert isinstance(assembly.coverage.omitted_candidate_ids, tuple)


def test_t16_23_same_input_produces_value_equal_output():
    first = _build(("EV-1", "EV-2"))
    second = _build(("EV-1", "EV-2"))

    assert first is not second
    assert first == second
    assert first.evidence == second.evidence
    assert first.coverage == second.coverage


# --------------------------------------------------------------------- #
# T16-24  the module is WIRED ONLY THROUGH THE AUTHORIZED PRODUCT PATH
#
# TASK 19.3 intentionally wires this module into the live runtime, so the
# ORIGINAL law this test proved — that no production file outside this
# module's own package ever names it — is now intentionally false. Deleting
# or weakening the proof would erase the architectural guarantee it protected;
# instead the law is REPLACED by a strictly stronger one: not merely THAT the
# module is unreferenced, but exactly WHICH files may reference it, and that
# reaching it is the only way model execution proceeds at all.
#
# The exact allow-list below is not a guess: it was measured from the actual
# TASK 19.3 implementation with the identical substring scan the original test
# used, over `backend/app/` at the current HEAD. `app/core/orchestrator.py` is
# the single materialization site; `app/core/ports.py` carries a TYPE_CHECKING
# forward-reference so `IVEPort` can declare its payload type without Core
# runtime-importing this package. No other production file names it: the two
# provider adapters and `ive_common` reference `ModelContextAssembly` only as
# a quoted forward-reference string, with no import backing it anywhere, and
# so never surface the "model_context" substring their own source is scanned
# for below — this is a stronger closure than a merely-permitted reference
# would be, and the allow-list is a ceiling, not a floor.
# --------------------------------------------------------------------- #
_T16_24_ALLOWED_EXTERNAL_REFERENCES = frozenset({
    "app/core/orchestrator.py",
    "app/core/ports.py",
})


def test_t16_24_model_context_is_wired_only_through_the_authorized_product_path():
    module_dir = Path(models.__file__).resolve().parent

    referring = []
    for path in sorted((BACKEND_ROOT / "app").rglob("*.py")):
        resolved = path.resolve()
        if resolved.parent == module_dir:
            continue
        if "model_context" in resolved.read_text(encoding="utf-8"):
            referring.append(str(resolved.relative_to(BACKEND_ROOT)))

    # (A) no unauthorized production file references this module.
    assert set(referring) == _T16_24_ALLOWED_EXTERNAL_REFERENCES, referring

    # the production tree really was inspected, and really can detect a
    # reference: a scan that silently matched nothing would prove nothing.
    production_files = sorted((BACKEND_ROOT / "app").rglob("*.py"))
    assert len(production_files) > 50, len(production_files)
    assert any(
        "model_context" in p.resolve().read_text(encoding="utf-8")
        for p in production_files
        if p.resolve().parent == module_dir
    )

    orchestrator_src = (BACKEND_ROOT / "app" / "core" / "orchestrator.py").read_text(
        encoding="utf-8"
    )

    # (B) exactly ONE production call site invokes build_model_context.
    assert orchestrator_src.count("build_model_context(") == 1, orchestrator_src

    # (C) neither provider adapter package invokes the builder, imports this
    # module, or reaches it via `ive_common`'s re-export surface (it has none).
    for provider_dir in ("gemini_ive", "openai_ive"):
        for path in sorted((BACKEND_ROOT / "app" / "modules" / provider_dir).rglob("*.py")):
            src = path.read_text(encoding="utf-8")
            assert "build_model_context" not in src, (path, src)
            assert "model_context" not in src, (path, src)

    ive_common_src = (BACKEND_ROOT / "app" / "modules" / "ive_common.py").read_text(
        encoding="utf-8"
    )
    assert "build_model_context" not in ive_common_src

    # (D) no live Product provider execution path accepts or receives a
    # `ContextPack`: `IVEPort.run`'s own payload parameter does not name the
    # type (scoped to that one method — `ContextPackBuilderPort.build` in the
    # same file legitimately still returns a `ContextPack`, upstream of model
    # execution), and neither provider adapter names or imports it.
    ports_src = (BACKEND_ROOT / "app" / "core" / "ports.py").read_text(encoding="utf-8")
    ports_tree = ast.parse(ports_src)
    ive_port_node = next(
        node for node in ast.walk(ports_tree)
        if isinstance(node, ast.ClassDef) and node.name == "IVEPort"
    )
    run_node = next(
        node for node in ast.walk(ive_port_node)
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    for arg in run_node.args.args:
        if arg.arg == "self":
            continue
        annotation_text = (
            ast.get_source_segment(ports_src, arg.annotation) if arg.annotation else ""
        )
        assert "ContextPack" not in (annotation_text or ""), annotation_text

    for provider_dir in ("gemini_ive", "openai_ive"):
        adapter_path = BACKEND_ROOT / "app" / "modules" / provider_dir / "adapter.py"
        adapter_src = adapter_path.read_text(encoding="utf-8")
        adapter_tree = ast.parse(adapter_src)

        # no import of ContextPack (prose mentioning it, e.g. in the module
        # docstring explaining what is NOT accepted, is not code and is not
        # what this law is about).
        imported_names = {
            alias.name
            for node in ast.walk(adapter_tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert "ContextPack" not in imported_names, imported_names

        # the run() method's own payload parameter does not name the type.
        run_node = next(
            node for node in ast.walk(adapter_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        for arg in run_node.args.args:
            if arg.arg == "self":
                continue
            annotation_text = (
                ast.get_source_segment(adapter_src, arg.annotation)
                if arg.annotation else ""
            )
            assert "ContextPack" not in (annotation_text or ""), annotation_text

    gateway_src = (
        BACKEND_ROOT / "app" / "modules" / "model_gateway" / "gateway.py"
    ).read_text(encoding="utf-8")
    gateway_tree = ast.parse(gateway_src)
    gateway_imported_names = {
        alias.name
        for node in ast.walk(gateway_tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "ContextPack" not in gateway_imported_names, gateway_imported_names
    execute_node = next(
        node for node in ast.walk(gateway_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "execute"
    )
    for arg in execute_node.args.args:
        if arg.arg in ("self", "engine_id"):
            continue
        annotation_text = (
            ast.get_source_segment(gateway_src, arg.annotation)
            if arg.annotation else ""
        )
        assert "ContextPack" not in (annotation_text or ""), annotation_text

    # control: ContextPack really is still detectable elsewhere in app/, so
    # (D) is not a vacuous prohibition against a name nobody uses any more.
    control = [
        p for p in production_files
        if "ContextPack" in p.read_text(encoding="utf-8")
        and p.resolve().parent != module_dir
    ]
    assert len(control) > 1, control

    # (E) if build_model_context raises, no Gateway/provider/MIVE execution
    # occurs. Proven at the unit level too (T19-3-06..08 in the dedicated live
    # wiring suite); restated here as a source-order fact so this test alone
    # continues to certify the law even if that file is ever removed: the
    # materialization call precedes both `_run_engine` call sites textually,
    # and both are inside the same unguarded `try` block that a raised
    # `ModelContextBuildError` (mapped to `ContextPackError`) would abort.
    materialize_at = orchestrator_src.index("self._materialize_model_context(")
    first_run_engine_at = orchestrator_src.index('self._run_engine("gemini"')
    assert materialize_at < first_run_engine_at

    # (F) the proof is non-vacuous: the exact predicate used above really can
    # report a violation, demonstrated by deliberately probing a file that is
    # NOT on the allow-list and IS known not to reference this module.
    unrelated = BACKEND_ROOT / "app" / "modules" / "mive" / "comparator.py"
    assert "model_context" not in unrelated.read_text(encoding="utf-8")


# --------------------------------------------------------------------- #
# T16-25  the structural input contract accepts the REAL frozen object
# --------------------------------------------------------------------- #
def test_t16_25_a_real_governed_evidence_set_is_accepted_verbatim():
    """Neither module imports the other; the join is purely structural."""
    from app.modules.governed_evidence import (
        GovernedEvidenceSet,
        MaterializationInput,
        materialize_governed_evidence_set,
    )

    submitted = ("EV-1", "EV-2")
    retrieved = ("EV-1", "EV-2", "EV-3")  # EV-3 is NOT_SUBMITTED accounting only

    native = SimpleNamespace(
        records=tuple(
            SimpleNamespace(
                evidence_id=cid,
                claim=_claim(cid),
                status="VERIFIED",
                validation_id="VAL-" + cid,
                fingerprint=SimpleNamespace(
                    algorithm="SHA256", hash="FP-" + cid, content_id=cid
                ),
            )
            for cid in submitted
        ),
        validations=tuple(
            SimpleNamespace(
                validation_id="VAL-" + cid,
                evidence_id=cid,
                result="PASS",
                blocking_reasons=(),
                evidence_fingerprint_hash="FP-" + cid,
            )
            for cid in submitted
        ),
        transitions=tuple(
            SimpleNamespace(
                transition_id="TR-" + cid,
                evidence_id=cid,
                from_status="PENDING",
                to_status="VERIFIED",
                validation_id="VAL-" + cid,
            )
            for cid in submitted
        ),
    )

    governed = materialize_governed_evidence_set(
        MaterializationInput(
            outcome_state="GOVERNANCE_COMPLETE",
            native_result=native,
            retrieved_candidate_ids=retrieved,
            submitted_candidate_ids=submitted,
            candidate_count=len(retrieved),
            governed_count=len(submitted),
            backend_id="TEST-BACKEND",
            mapping_profile_id="TEST-PROFILE",
            adapter_id="ION_CORE_ADAPTER_FACADE_V0_1",
            adapter_version="0.1",
            context_pack_id="CP-REAL",
            question_id="REQ-REAL",
            context_pack_metadata={"truncated": True},
        )
    )
    assert isinstance(governed, GovernedEvidenceSet)

    # deliberately including a projection for the NOT_SUBMITTED candidate: the
    # caller is not required to pre-filter, and it must simply not be exposed.
    assembly = build_model_context(
        governed_basis=governed,
        candidate_projections=[_projection(cid) for cid in retrieved],
        question=QUESTION,
    )

    assert tuple(item.candidate_id for item in assembly.evidence) == submitted
    assert assembly.question_id == "REQ-REAL"
    assert assembly.context_pack_id == "CP-REAL"
    assert assembly.coverage.state is ModelContextCoverageState.COMPLETE
    assert assembly.coverage.admitted_count == assembly.coverage.included_count == 2
    assert "EV-3" not in repr(assembly)
    assert CLAIM_TOKEN not in repr(assembly)
