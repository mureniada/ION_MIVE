"""Bounded contract test for the Product Response Evidence Projection (v0.1).

Scope is deliberately narrow: this covers the PRODUCT presentation contract
only — what a response may present after model execution, and what it may not.
Admission, provenance and fingerprint semantics stay owned and tested by the
frozen governance modules; exposure semantics stay owned and tested by the
frozen Model Context module. Nothing here re-asserts or exercises either. Every
authorized basis below is a stand-in, so a passing run proves the presentation
contract, not the exposure or governance ones.

The single exception is T17-25, which drives a REAL `ModelContextAssembly`
built by the frozen TASK 16 builder — and its real `EvidenceContextItem`
evidence tuple — straight into the projector, to prove the structural input
contract actually accepts the live objects without adaptation and without
either production module importing the other.

Absence checks are structural, never textual against source. The module under
test names the excluded vocabulary — REJECTED / UNKNOWN / NOT_SUBMITTED,
disposition, authority, sufficiency, provenance, fingerprint, and the MIVE
comparison categories — in its docstrings precisely in order to record that
those concepts are EXCLUDED at v0.1, so a raw source scan would report the exact
opposite of the truth. These tests interrogate dataclass field sets, module
namespaces and the parsed import/identifier graph instead. Where a textual check
does appear it is applied to the produced DATA (the projection's own repr),
never to the module source.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules import response_evidence
import app.modules.response_evidence.models as models
import app.modules.response_evidence.projector as projector
from app.modules.response_evidence import (
    EXCERPT_PREFIX_CHARS,
    EXCERPT_RULE_PREFIX_CHARS_240_V0_1,
    RESPONSE_EVIDENCE_CONTRACT_ID,
    RESPONSE_EVIDENCE_PROJECTOR_ID,
    RESPONSE_EVIDENCE_PROJECTOR_VERSION,
    RESPONSE_EVIDENCE_VERSION,
    UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS,
    EvidenceReferenceRequest,
    RenderedEvidenceItem,
    ResponseEvidenceProjection,
    ResponseEvidenceProjectionError,
    UnresolvedReference,
    project_response_evidence,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]

MODULE_PATHS = (
    Path(models.__file__),
    Path(projector.__file__),
    Path(response_evidence.__file__),
)

LINKAGE = "money is a medium of exchange"
OTHER_LINKAGE = "money is a store of value"


# --------------------------------------------------------------------- #
# stand-ins. Nothing here governs, exposes, retrieves or compares; these
# carry the six fields a real Model Context evidence item carries, so the
# assertions observe the structural contract.
# --------------------------------------------------------------------- #
def _exposed(
    candidate_id, *, content="exposed body", title="Title", source="src", page=7,
    chunk_id="c1",
):
    """Shaped exactly like the frozen EvidenceContextItem, by attribute."""
    return SimpleNamespace(
        candidate_id=candidate_id,
        content=content,
        title=title,
        source_identity=source,
        page=page,
        chunk_id=chunk_id,
    )


def _ref(candidate_id, claim_linkage=LINKAGE):
    return EvidenceReferenceRequest(
        candidate_id=candidate_id, claim_linkage=claim_linkage
    )


def _field_names(cls):
    return {f.name for f in dataclasses.fields(cls)}


def _all_field_names():
    names = set()
    for cls in (
        EvidenceReferenceRequest,
        RenderedEvidenceItem,
        UnresolvedReference,
        ResponseEvidenceProjection,
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
# T17-01 .. T17-05  presentation eligibility and the unknown-reference rule
# --------------------------------------------------------------------- #
def test_t17_01_authorized_candidate_reference_produces_one_evidence_item():
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1")],
        reference_requests=[_ref("EV-1")],
    )

    assert isinstance(result, ResponseEvidenceProjection)
    assert len(result.evidence) == 1
    assert result.unresolved_references == ()

    item = result.evidence[0]
    assert isinstance(item, RenderedEvidenceItem)
    assert item.candidate_id == "EV-1"
    assert item.claim_linkage == LINKAGE
    assert result.response_evidence_contract_id == RESPONSE_EVIDENCE_CONTRACT_ID
    assert result.response_evidence_version == RESPONSE_EVIDENCE_VERSION


def test_t17_02_candidate_outside_authorized_basis_never_produces_evidence():
    """The whole point of the contract: only exposed material may be presented."""
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1", content="EXPOSED")],
        reference_requests=[_ref("EV-NEVER-EXPOSED")],
    )

    assert result.evidence == ()
    assert [u.candidate_id for u in result.unresolved_references] == [
        "EV-NEVER-EXPOSED"
    ]
    # nothing was fabricated to stand in for it
    assert "EV-NEVER-EXPOSED" not in repr(result.evidence)


def test_t17_03_unknown_reference_is_recorded_explicitly():
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1")],
        reference_requests=[_ref("EV-9", claim_linkage=OTHER_LINKAGE)],
    )

    assert len(result.unresolved_references) == 1
    unresolved = result.unresolved_references[0]
    assert isinstance(unresolved, UnresolvedReference)
    assert unresolved.candidate_id == "EV-9"
    assert unresolved.claim_linkage == OTHER_LINKAGE
    assert unresolved.reason == UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS
    assert unresolved.reason == "NOT_IN_AUTHORIZED_MODEL_CONTEXT_BASIS"


def test_t17_04_unknown_reference_does_not_fail_the_complete_projection():
    """One unresolvable reference must not decide the fate of the response."""
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1"), _exposed("EV-2")],
        reference_requests=[_ref("EV-1"), _ref("EV-MISSING"), _ref("EV-2")],
    )

    assert [e.candidate_id for e in result.evidence] == ["EV-1", "EV-2"]
    assert [u.candidate_id for u in result.unresolved_references] == ["EV-MISSING"]


def test_t17_05_unknown_reference_is_never_labelled_with_a_governance_verdict():
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1")],
        reference_requests=[_ref("EV-MISSING")],
    )
    unresolved = result.unresolved_references[0]

    # no governance or accounting field exists to carry a verdict ...
    assert _field_names(UnresolvedReference) == {
        "candidate_id",
        "claim_linkage",
        "reason",
    }
    for absent in ("disposition", "status", "native_status", "accounting_state"):
        assert not hasattr(unresolved, absent)

    # ... and no governance or accounting word appears in the produced data
    blob = repr(result)
    for forbidden in (
        "REJECTED", "UNKNOWN", "NOT_SUBMITTED", "UNADMITTED", "ADMITTED",
        "GOVERN", "PENDING", "VERIFIED",
    ):
        assert forbidden not in blob, forbidden


# --------------------------------------------------------------------- #
# T17-06 .. T17-07  the identity join
# --------------------------------------------------------------------- #
def test_t17_06_duplicate_authorized_basis_candidate_id_fails_closed():
    with pytest.raises(ResponseEvidenceProjectionError) as exc:
        project_response_evidence(
            authorized_basis=[
                _exposed("EV-1", content="first body"),
                _exposed("EV-1", content="second body"),
            ],
            reference_requests=[_ref("EV-1")],
        )
    assert "duplicate authorized basis identity" in str(exc.value)

    # malformed basis identity and malformed request identity are equally closed
    for basis, requests in (
        ([_exposed("")], [_ref("EV-1")]),
        ([_exposed(None)], [_ref("EV-1")]),
        ([SimpleNamespace(content="x")], [_ref("EV-1")]),
        ([_exposed("EV-1")], [SimpleNamespace(candidate_id="EV-1", claim_linkage="x")]),
        ([_exposed("EV-1")], [{"candidate_id": "EV-1"}]),
        ("not-a-sequence", [_ref("EV-1")]),
    ):
        with pytest.raises(ResponseEvidenceProjectionError):
            project_response_evidence(
                authorized_basis=basis, reference_requests=requests
            )


def test_t17_07_identity_join_is_by_value_never_by_position():
    """Basis order and request order deliberately disagree."""
    result = project_response_evidence(
        authorized_basis=[
            _exposed("EV-A", content="BODY-A", title="A", source="sa", page=1),
            _exposed("EV-B", content="BODY-B", title="B", source="sb", page=2),
        ],
        reference_requests=[_ref("EV-B"), _ref("EV-A")],
    )

    # a positional join would put BODY-A first; a value join puts BODY-B first
    assert [e.candidate_id for e in result.evidence] == ["EV-B", "EV-A"]
    assert result.evidence[0].source_content == "BODY-B"
    assert result.evidence[0].title == "B"
    assert result.evidence[1].source_content == "BODY-A"
    assert result.evidence[1].title == "A"


# --------------------------------------------------------------------- #
# T17-08 .. T17-09  verbatim copying from the authorized basis
# --------------------------------------------------------------------- #
def test_t17_08_source_content_is_copied_verbatim():
    body = "  Leading and trailing space, a\ttab, a\nnewline, and Ünïcode.  "
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1", content=body)],
        reference_requests=[_ref("EV-1")],
    )
    item = result.evidence[0]

    # byte-for-byte: nothing stripped, normalized, summarized or re-cased
    assert item.source_content == body
    assert item.source_content is body


def test_t17_09_title_source_page_and_chunk_id_are_copied_verbatim():
    result = project_response_evidence(
        authorized_basis=[
            _exposed(
                "EV-1", title="  Sacred Economics  ", source="sacred_economics",
                page="xii", chunk_id="p12::c1",
            )
        ],
        reference_requests=[_ref("EV-1")],
    )
    item = result.evidence[0]

    assert item.title == "  Sacred Economics  "
    assert item.source_identity == "sacred_economics"
    assert item.page == "xii"
    assert item.chunk_id == "p12::c1"

    # the full page/chunk domain survives unconverted: str | int | None
    for page, chunk_id in ((12, "c1"), (None, None), ("xii", None)):
        one = project_response_evidence(
            authorized_basis=[_exposed("EV-1", page=page, chunk_id=chunk_id)],
            reference_requests=[_ref("EV-1")],
        ).evidence[0]
        assert one.page == page and one.chunk_id == chunk_id


# --------------------------------------------------------------------- #
# T17-10 .. T17-13  excerpting is marked presentation, never governance
# --------------------------------------------------------------------- #
def test_t17_10_excerpt_uses_the_deterministic_declared_prefix_rule():
    body = "x" * 500
    item = project_response_evidence(
        authorized_basis=[_exposed("EV-1", content=body)],
        reference_requests=[_ref("EV-1")],
    ).evidence[0]

    assert EXCERPT_PREFIX_CHARS == 240
    assert EXCERPT_RULE_PREFIX_CHARS_240_V0_1 == "PREFIX_CHARS_240_V0_1"
    assert item.excerpt_rule == EXCERPT_RULE_PREFIX_CHARS_240_V0_1
    assert item.excerpt == body[:240]
    assert len(item.excerpt) == 240

    # a prefix, not a rewrite: no ellipsis, no strip, no invented text
    padded = "   " + "y" * 10 + "   "
    short = project_response_evidence(
        authorized_basis=[_exposed("EV-1", content=padded)],
        reference_requests=[_ref("EV-1")],
    ).evidence[0]
    assert short.excerpt == padded
    assert "..." not in short.excerpt and "…" not in short.excerpt


def test_t17_11_truncated_flag_is_correct():
    for length, expected in ((0, False), (239, False), (240, False), (241, True)):
        item = project_response_evidence(
            authorized_basis=[_exposed("EV-1", content="z" * length)],
            reference_requests=[_ref("EV-1")],
        ).evidence[0]
        assert item.truncated is expected, length

    # and a false flag cannot be constructed by hand either
    with pytest.raises(ResponseEvidenceProjectionError):
        RenderedEvidenceItem(
            candidate_id="EV-1", title="t", source_identity="s",
            source_content="z" * 300, excerpt=("z" * 300)[:240],
            excerpt_rule=EXCERPT_RULE_PREFIX_CHARS_240_V0_1,
            truncated=False, source_length=300, claim_linkage=LINKAGE,
        )


def test_t17_12_source_length_is_correct():
    for length in (0, 1, 240, 241, 5000):
        item = project_response_evidence(
            authorized_basis=[_exposed("EV-1", content="z" * length)],
            reference_requests=[_ref("EV-1")],
        ).evidence[0]
        assert item.source_length == length
        assert item.source_length == len(item.source_content)

    # a rewritten excerpt or a wrong length cannot be constructed by hand
    for kwargs in (
        {"excerpt": "SUMMARISED BY A MODEL", "source_length": 300},
        {"excerpt": ("z" * 300)[:240], "source_length": 240},
        {"excerpt": ("z" * 300)[:240], "source_length": 300,
         "excerpt_rule": "SOME_OTHER_RULE"},
    ):
        base = {
            "candidate_id": "EV-1", "title": "t", "source_identity": "s",
            "source_content": "z" * 300,
            "excerpt_rule": EXCERPT_RULE_PREFIX_CHARS_240_V0_1,
            "truncated": True, "claim_linkage": LINKAGE,
        }
        with pytest.raises(ResponseEvidenceProjectionError):
            RenderedEvidenceItem(**{**base, **kwargs})


def test_t17_13_short_source_content_is_visibly_non_truncated():
    body = "a short exposed body"
    item = project_response_evidence(
        authorized_basis=[_exposed("EV-1", content=body)],
        reference_requests=[_ref("EV-1")],
    ).evidence[0]

    assert item.truncated is False
    assert item.excerpt == body == item.source_content
    assert item.source_length == len(body)


# --------------------------------------------------------------------- #
# T17-14 .. T17-15  MODEL OUTPUT IS NOT EVIDENCE
# --------------------------------------------------------------------- #
def test_t17_14_claim_linkage_is_structurally_separate_from_source_content():
    linkage = "MODEL_TEXT_MUST_NOT_BECOME_SOURCE_MATERIAL"
    body = "SOURCE_BODY"
    item = project_response_evidence(
        authorized_basis=[_exposed("EV-1", content=body, title="T", source="S")],
        reference_requests=[_ref("EV-1", claim_linkage=linkage)],
    ).evidence[0]

    assert item.claim_linkage == linkage
    # separate fields of the same object; the model text reaches none of the
    # fields that carry authorized source material
    assert item.source_content == body
    for field in ("source_content", "excerpt", "title", "source_identity"):
        assert linkage not in getattr(item, field)


def test_t17_15_claim_linkage_cannot_create_an_evidence_identity():
    """Naming an exposed candidate inside model text does not summon it."""
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1", content="EXPOSED BODY")],
        # the linkage text names EV-1, but the reference itself asks for EV-999
        reference_requests=[_ref("EV-999", claim_linkage="as shown in EV-1")],
    )

    assert result.evidence == ()
    assert len(result.unresolved_references) == 1
    assert result.unresolved_references[0].candidate_id == "EV-999"

    # and a resolved item's identity is the BASIS's, not the request's
    resolved = project_response_evidence(
        authorized_basis=[_exposed("EV-1")],
        reference_requests=[_ref("EV-1", claim_linkage="EV-1 is not an identity")],
    ).evidence[0]
    basis_identity = _exposed("EV-1").candidate_id
    assert resolved.candidate_id == basis_identity


# --------------------------------------------------------------------- #
# T17-16 .. T17-17  the deterministic (candidate_id, claim_linkage) row rule
# --------------------------------------------------------------------- #
def test_t17_16_same_candidate_with_different_linkage_is_represented_separately():
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1", content="BODY")],
        reference_requests=[
            _ref("EV-1", claim_linkage=LINKAGE),
            _ref("EV-1", claim_linkage=OTHER_LINKAGE),
        ],
    )

    assert len(result.evidence) == 2
    assert [e.claim_linkage for e in result.evidence] == [LINKAGE, OTHER_LINKAGE]
    assert {e.candidate_id for e in result.evidence} == {"EV-1"}
    # the same exposed body legitimately supports both linkages
    assert {e.source_content for e in result.evidence} == {"BODY"}


def test_t17_17_exact_duplicate_reference_request_handling_is_deterministic():
    """The documented rule: rows are keyed on (candidate_id, claim_linkage);
    an exact repeat collapses to its first occurrence, order preserved."""
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1"), _exposed("EV-2")],
        reference_requests=[
            _ref("EV-1"), _ref("EV-2"), _ref("EV-1"), _ref("EV-1"),
        ],
    )
    assert [e.candidate_id for e in result.evidence] == ["EV-1", "EV-2"]

    # the same collapsing applies to repeated unresolvable references
    unresolved = project_response_evidence(
        authorized_basis=[_exposed("EV-1")],
        reference_requests=[_ref("EV-X"), _ref("EV-X"), _ref("EV-X", OTHER_LINKAGE)],
    ).unresolved_references
    assert [(u.candidate_id, u.claim_linkage) for u in unresolved] == [
        ("EV-X", LINKAGE),
        ("EV-X", OTHER_LINKAGE),
    ]


# --------------------------------------------------------------------- #
# T17-18 .. T17-20  the authority, dependency and capability boundaries
# --------------------------------------------------------------------- #
def test_t17_18_no_admission_authority_or_sufficiency_field_exists():
    assert _field_names(RenderedEvidenceItem) == {
        "candidate_id",
        "title",
        "source_identity",
        "source_content",
        "excerpt",
        "excerpt_rule",
        "truncated",
        "source_length",
        "claim_linkage",
        "page",
        "chunk_id",
    }
    assert _field_names(EvidenceReferenceRequest) == {"candidate_id", "claim_linkage"}
    assert _field_names(ResponseEvidenceProjection) == {
        "evidence",
        "unresolved_references",
        "response_evidence_contract_id",
        "response_evidence_version",
    }

    for forbidden in (
        "disposition", "admission", "admitted", "rejected", "unknown",
        "not_submitted", "accounting", "accounting_state", "authority",
        "authoritative", "sufficiency", "sufficient", "confidence", "score",
        "relevance", "provenance", "fingerprint", "native_status",
        "native_record", "native_validation", "native_transition", "verdict",
        "governance", "coverage", "status",
    ):
        assert forbidden not in _all_field_names(), forbidden


def test_t17_19_module_has_no_forbidden_dependency():
    allowed_stdlib = {"__future__", "dataclasses", "typing"}
    own_modules = {"models", "projector"}

    for path in MODULE_PATHS:
        absolute, relative = _imports(path)
        for module in absolute:
            assert module.split(".")[0] in allowed_stdlib, (path.name, module)
        for level, module in relative:
            assert level == 1, (path.name, level, module)
            assert module in own_modules, (path.name, module)

    # no provider, store, adapter, renderer, container, transport, governance,
    # model-context or comparison name is reachable through this package's
    # live namespace
    for module in (response_evidence, projector, models):
        for name in (
            "GovernedEvidenceSet", "GovernanceDisposition", "MaterializationInput",
            "materialize_governed_evidence_set", "CoreAdapter",
            "ModelContextAssembly", "EvidenceContextItem", "build_model_context",
            "CandidateContentProjection", "ModelContextCoverage",
            "run_runtime_admission_gate", "RuntimeEvidenceBridge",
            "resolve_evidence_provenance", "ContextPack", "ContextDocument",
            "Evidence", "IVEReport", "MIVEResult", "Claim", "MIVEComparator",
            "QdrantRetrieval", "GeminiIVE", "OpenAIIVE", "build_user_prompt",
            "IVE_SYSTEM_PROMPT", "DeterministicRenderer", "RendererPort",
            "AskResult", "Core", "build_core", "Settings", "FastAPI",
        ):
            assert not hasattr(module, name), (module.__name__, name)


def test_t17_20_module_uses_no_clock_identity_io_or_judgement_capability():
    for path in MODULE_PATHS:
        used = _identifiers(path)
        for forbidden in (
            # clock / identity / randomness
            "now", "utcnow", "utc_now_iso", "monotonic", "sleep",
            "uuid", "uuid1", "uuid4", "uuid5", "random", "time", "datetime",
            # filesystem, network, environment
            "open", "read_text", "read_bytes", "write_text", "write_bytes",
            "Path", "environ", "getenv", "urlopen", "socket", "requests",
            "httpx", "connect", "session",
            # governance / exposure material this module must never reach for
            "disposition", "admitted", "rejected", "accounting",
            "native_record", "native_validation", "native_transition",
            "claim", "fingerprint", "provenance", "coverage",
            # judgements this module must never make
            "sort", "sorted", "rank", "ranked", "trim", "summarize", "rewrite",
            "score", "confidence", "authority", "sufficiency", "relevance",
            # comparison categories: GAP-RENDER-01 stays out of this contract
            "mive", "agreements", "partial_agreements", "conflicts",
            "unique_findings", "combined_evidence", "evidence_overlap",
            "evidence_document_ids", "engine_id", "engines",
        ):
            assert forbidden not in used, (path.name, forbidden)

    # no contract field is derived from a wall clock. Compared on whole
    # underscore-separated parts, not as raw substrings, so a legitimate name
    # is never condemned for merely containing a token (candi-date_id).
    for name in _all_field_names():
        parts = name.split("_")
        for token in ("at", "time", "clock", "date", "timestamp", "created", "updated"):
            assert token not in parts, (token, name)


# --------------------------------------------------------------------- #
# T17-21 .. T17-23  the public surface, immutability and determinism
# --------------------------------------------------------------------- #
def test_t17_21_public_export_surface_is_exact_and_closed():
    assert set(response_evidence.__all__) == {
        "EXCERPT_PREFIX_CHARS",
        "EXCERPT_RULE_PREFIX_CHARS_240_V0_1",
        "RESPONSE_EVIDENCE_CONTRACT_ID",
        "RESPONSE_EVIDENCE_PROJECTOR_ID",
        "RESPONSE_EVIDENCE_PROJECTOR_VERSION",
        "RESPONSE_EVIDENCE_VERSION",
        "UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS",
        "EvidenceReferenceRequest",
        "RenderedEvidenceItem",
        "ResponseEvidenceProjection",
        "ResponseEvidenceProjectionError",
        "UnresolvedReference",
        "project_response_evidence",
    }
    for name in response_evidence.__all__:
        assert hasattr(response_evidence, name), name

    assert RESPONSE_EVIDENCE_CONTRACT_ID == "ION_RESPONSE_EVIDENCE_PROJECTION_V0_1"
    assert RESPONSE_EVIDENCE_VERSION == "0.1"
    assert RESPONSE_EVIDENCE_PROJECTOR_ID == "ION_RESPONSE_EVIDENCE_PROJECTOR_V0_1"
    assert RESPONSE_EVIDENCE_PROJECTOR_VERSION == "0.1"


def test_t17_22_contract_objects_are_immutable():
    result = project_response_evidence(
        authorized_basis=[_exposed("EV-1")],
        reference_requests=[_ref("EV-1"), _ref("EV-MISSING")],
    )

    assert isinstance(result.evidence, tuple)
    assert isinstance(result.unresolved_references, tuple)

    for obj, field, value in (
        (result, "evidence", ()),
        (result.evidence[0], "source_content", "REWRITTEN"),
        (result.evidence[0], "candidate_id", "EV-OTHER"),
        (result.unresolved_references[0], "reason", "REJECTED"),
        (_ref("EV-1"), "candidate_id", "EV-OTHER"),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, field, value)


def test_t17_23_same_input_produces_value_equal_output():
    def build():
        return project_response_evidence(
            authorized_basis=[
                _exposed("EV-1", content="b" * 400),
                _exposed("EV-2", content="short"),
            ],
            reference_requests=[
                _ref("EV-2", OTHER_LINKAGE), _ref("EV-MISSING"), _ref("EV-1"),
            ],
        )

    first, second = build(), build()
    assert first == second
    assert first.evidence == second.evidence
    assert first.unresolved_references == second.unresolved_references


# --------------------------------------------------------------------- #
# T17-24  the module is unwired: nothing existing refers to it
# --------------------------------------------------------------------- #
def test_t17_24_no_existing_production_or_test_file_references_this_module():
    this_test = Path(__file__).resolve()
    module_dir = Path(models.__file__).resolve().parent

    referring = []
    for path in sorted((BACKEND_ROOT / "app").rglob("*.py")) + sorted(
        (BACKEND_ROOT / "tests").glob("*.py")
    ):
        resolved = path.resolve()
        if resolved == this_test or resolved.parent == module_dir:
            continue
        if "response_evidence" in resolved.read_text(encoding="utf-8"):
            referring.append(str(resolved.relative_to(BACKEND_ROOT)))

    assert referring == [], referring


# --------------------------------------------------------------------- #
# T17-25  the REAL frozen TASK 16 objects are accepted without adaptation
#
# This is a contract-compatibility proof, not a shape-similarity one. The
# basis below is a genuine `ModelContextAssembly` produced by the frozen TASK
# 16 builder through its public entry point, and its `evidence` tuple —
# genuine `EvidenceContextItem` objects — is handed to the TASK 17 projector
# exactly as the builder returned it: no conversion, no repacking, no adapter,
# no field renaming, no reconstruction. Neither production module imports the
# other; the join is purely structural, and that is what makes this work.
#
# Importing the TASK 16 public contract here is verification, not wiring. The
# corrected TASK 16 T16-24 proves unwiredness against `backend/app/`, which
# this test does not touch.
# --------------------------------------------------------------------- #
def test_t17_25_a_real_model_context_assembly_is_accepted_verbatim():
    """A REAL TASK 16 assembly forms the authorized basis, unmodified."""
    from app.modules.model_context import (
        CandidateContentProjection,
        EvidenceContextItem,
        ModelContextAssembly,
        build_model_context,
    )

    admitted = ("EV-1", "EV-2")
    long_body = "exposed body for EV-1 " + "w" * 300
    short_body = "short exposed body for EV-2"
    bodies = {"EV-1": long_body, "EV-2": short_body}

    # a governed basis stand-in: TASK 13 semantics are not under test here,
    # only the TASK 16 -> TASK 17 contract seam.
    governed_basis = SimpleNamespace(
        question_id="Q-1",
        context_pack_id="cp_abc",
        admitted=tuple(
            SimpleNamespace(candidate_id=cid, disposition="ADMITTED")
            for cid in admitted
        ),
    )
    projections = (
        CandidateContentProjection(
            document_id="EV-1", content=long_body, title="Title EV-1",
            source_identity="sacred_economics", page=12, chunk_id="EV-1::c1",
        ),
        CandidateContentProjection(
            document_id="EV-2", content=short_body, title="Title EV-2",
            source_identity="sacred_economics", page="xii", chunk_id=None,
        ),
        # submitted but not admitted: legitimate TASK 16 input that never
        # reaches the assembly, so it is never exposed to a model either
        CandidateContentProjection(
            document_id="EV-NOT-ADMITTED", content="never exposed",
            title="Excluded", source_identity="sacred_economics",
            page=99, chunk_id="EV-NOT-ADMITTED::c1",
        ),
    )

    assembly = build_model_context(
        governed_basis=governed_basis,
        candidate_projections=projections,
        question="is money credit or debt?",
    )

    # the real objects, confirmed as such before anything is asserted on them
    assert isinstance(assembly, ModelContextAssembly)
    assert assembly.evidence and all(
        isinstance(item, EvidenceContextItem) for item in assembly.evidence
    )
    assert [e.candidate_id for e in assembly.evidence] == ["EV-1", "EV-2"]

    # THE SEAM: the assembly's own evidence tuple, passed straight through.
    # No conversion, no repacking, no adaptation of any kind.
    authorized_basis = assembly.evidence
    result = project_response_evidence(
        authorized_basis=authorized_basis,
        reference_requests=[
            _ref("EV-2"),
            # admitted upstream but never placed in the real model context:
            # unresolvable here, and that is the whole contract
            _ref("EV-NOT-ADMITTED"),
            _ref("EV-1"),
        ],
    )

    # identity is preserved exactly, and the request order is honoured
    assert [e.candidate_id for e in result.evidence] == ["EV-2", "EV-1"]

    # a reference outside the REAL basis resolves ONLY to an unresolved record
    assert [u.candidate_id for u in result.unresolved_references] == [
        "EV-NOT-ADMITTED"
    ]
    assert result.unresolved_references[0].reason == (
        UNRESOLVED_REASON_NOT_IN_AUTHORIZED_BASIS
    )
    assert "EV-NOT-ADMITTED" not in repr(result.evidence)
    # ... even though TASK 16 was handed its content: being submitted, or even
    # admitted, is not being exposed, and only exposure permits presentation
    assert "never exposed" not in repr(result)

    # every field survives the seam exactly, against the REAL items
    exposed_by_id = {e.candidate_id: e for e in assembly.evidence}
    for item in result.evidence:
        source = exposed_by_id[item.candidate_id]
        assert isinstance(source, EvidenceContextItem)
        assert item.candidate_id == source.candidate_id
        assert item.source_content == source.content
        assert item.title == source.title
        assert item.source_identity == source.source_identity
        assert item.page == source.page
        assert item.chunk_id == source.chunk_id
        assert item.excerpt == source.content[:EXCERPT_PREFIX_CHARS]
        assert item.truncated is (len(source.content) > EXCERPT_PREFIX_CHARS)
        assert item.source_length == len(source.content)

    # both branches of the excerpt rule are exercised against real content
    by_id = {e.candidate_id: e for e in result.evidence}
    assert by_id["EV-1"].truncated is True
    assert by_id["EV-2"].truncated is False
    assert by_id["EV-1"].source_content == bodies["EV-1"]
    assert by_id["EV-2"].source_content == bodies["EV-2"]
    # the full page/chunk_id domain crossed the seam unconverted
    assert by_id["EV-1"].page == 12 and by_id["EV-1"].chunk_id == "EV-1::c1"
    assert by_id["EV-2"].page == "xii" and by_id["EV-2"].chunk_id is None

    # RESPONSE-CITED is a subset of the REAL MODEL-CONTEXT-INCLUDED basis
    cited = {e.candidate_id for e in result.evidence}
    included = {e.candidate_id for e in assembly.evidence}
    assert cited <= included
    assert cited == {"EV-1", "EV-2"}

    # TASK 16 Product code is untouched by the seam: the assembly it returned
    # is unchanged and still immutable after being consumed.
    assert assembly.evidence is authorized_basis
    assert [e.candidate_id for e in assembly.evidence] == ["EV-1", "EV-2"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        assembly.evidence[0].content = "REWRITTEN BY THE CONSUMER"
