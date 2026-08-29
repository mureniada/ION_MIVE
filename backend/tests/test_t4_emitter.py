"""The emitter, the integrity boundary, and the demonstration record.

Covers, as far as this scope reaches: T7, T13, T18, T27, T37, T38, T46, T47, T56,
T57, T58, T59, T77, T81, T82, T85, T87(d), T92, T93.

Hashes are computed by the test from the artifacts on disk, never read from the
manifest (I5). The demonstration is driven through `Core.ask()` with the wrapper
around each `IVEPort`; no live provider call occurs (D3).

Every test runs under `netguard`'s `guarded` decorator with credentials absent.
"""

from __future__ import annotations

import copy
import hashlib
import tempfile
from pathlib import Path

from t4 import jcs, manifest, money
from t4.emitter import DIAGNOSTIC_CODES, FAILURE_CODES, Emitter, RunObserver
from t4.validation import RecordRejected, load_record, record_validator
from tests import t4_demonstration as demo
from tests.netguard import guarded
from tests.util import raises

REPO_ROOT = manifest.repository_root()


def _emit(store: Path, **overrides):
    return demo.run_demonstration(store, **overrides)


# --------------------------------------------------------------------------- #
# T37 / T38 — the integrity boundary: four artifacts, resolved by computation
# --------------------------------------------------------------------------- #

@guarded
def test_t38_manifest_carries_exactly_four_entries_and_no_parallel_manifest_exists():
    document = manifest.load()
    roles = sorted(entry["role"] for entry in document["artifacts"])
    assert roles == sorted(manifest.ARTIFACT_ROLES)
    assert len(document["artifacts"]) == 4

    others = [p for p in REPO_ROOT.rglob("artifact_manifest.json")
              if p != manifest.default_path()]
    assert not others, f"a parallel manifest exists: {others}"


@guarded
def test_t37_all_four_hashes_verify_against_hashes_the_test_computes():
    document = manifest.load()
    for entry in document["artifacts"]:
        raw = (REPO_ROOT / entry["path"]).read_bytes()
        computed = hashlib.sha256(raw).hexdigest()
        assert computed == entry["sha256"], entry["role"]
        # Every registered artifact's stored bytes are canonical (I16, §13.3).
        assert jcs.canonicalize(raw) == raw, entry["role"]


@guarded
def test_the_emitter_artifact_covers_every_module_of_the_package():
    """A change to any emitter module changes the registered emitter hash."""
    _path, raw, _digest = manifest.resolve(manifest.ROLE_EMITTER)
    artifact = jcs.parse(raw)
    listed = {m["path"]: m["sha256"] for m in artifact["modules"]}

    on_disk = sorted((REPO_ROOT / "backend" / "t4").glob("*.py"))
    assert {p.relative_to(REPO_ROOT).as_posix() for p in on_disk} == set(listed)
    for path in on_disk:
        relative = path.relative_to(REPO_ROOT).as_posix()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == listed[relative], relative


# --------------------------------------------------------------------------- #
# T85 — the contract resolves, and nothing proceeds without it
# --------------------------------------------------------------------------- #

@guarded
def test_t85_contract_resolves_from_its_hash_and_one_changed_byte_breaks_it():
    path, raw, digest = manifest.resolve(manifest.ROLE_CONTRACT)
    assert digest == hashlib.sha256(raw).hexdigest()
    assert digest == "a3e58ea456cfe26309c47b24ec7944ac77604f4a47a96d5f7ccace1955ceb48e"

    with tempfile.TemporaryDirectory() as tmp:
        # A manifest whose registered file hashes to something else does not resolve.
        staged = Path(tmp) / "artifact_manifest.json"
        copied = Path(tmp) / path.name
        copied.write_bytes(raw.replace(b'"1.0.0"', b'"1.0.1"', 1))
        entry = next(e for e in manifest.load()["artifacts"]
                     if e["role"] == manifest.ROLE_CONTRACT)
        tampered = dict(entry, path=copied.name)
        staged.write_bytes(jcs.serialize({"artifacts": [tampered]}))
        with raises(manifest.Unresolved):
            manifest.resolve(manifest.ROLE_CONTRACT, staged)


@guarded
def test_t85c_an_unresolvable_contract_refuses_emission_and_writes_no_record():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "records"
        empty_manifest = Path(tmp) / "artifact_manifest.json"
        empty_manifest.write_bytes(jcs.serialize({"artifacts": []}))

        emitter = Emitter(manifest_path=empty_manifest, store_path=store,
                          rates={}, pricing_basis_id="unused")
        with raises(Exception):
            emitter.resolve_contract()
        outcome, record = emitter.emit(
            record_origin="synthetic", run_id="r1", timestamp=demo.TIMESTAMP,
            raw_identities={}, planned_components=[], planned_calls=[],
            component_results=[], observer=RunObserver(),
            wall_clock_ms=1, wall_clock_source="test")
        assert outcome.outcome == "write_failed"
        assert outcome.failure_code == "contract_unresolved"
        assert outcome.detail
        assert record is None
        assert not store.exists() or not list(store.glob("*.json"))


# --------------------------------------------------------------------------- #
# The demonstration record
# --------------------------------------------------------------------------- #

@guarded
def test_the_demonstration_record_is_written_and_validates():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        outcome, record, result = _emit(store)

        assert outcome.outcome == "written"
        assert outcome.failure_code is None and outcome.detail is None
        assert outcome.run_id == demo.RUN_ID
        assert record["record_origin"] == "recorded_fixture"
        # The computation itself is untouched by the emitter (I8a).
        assert result.status == "success"

        stored = store / f"{demo.RUN_ID}.json"
        assert stored.is_file()
        # I16: the stored bytes are the canonical serialization, byte for byte.
        raw = stored.read_bytes()
        assert raw == jcs.serialize(record)
        assert jcs.canonicalize(raw) == raw


@guarded
def test_t7_partial_aggregate_on_the_real_gemini_openai_case():
    """One provider priced, one not: the case appendix A exists for."""
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))

    assert record["total_cost_status"] == "partial"
    assert record["total_cost_value"] is None
    # the subtotal is the canonical exact sum over the available calls
    assert record["available_cost_subtotal"] == {"scale": 8, "units": 678300}
    assert money.value_text(678300, 8) == "0.00678300"
    assert record["total_cost_missing_providers"] == ["gemini"]
    assert len(record["total_cost_missing_call_ids"]) == 1

    gemini = record["calls"][0]
    assert gemini["provider"] == "gemini"
    assert record["total_cost_missing_call_ids"] == [gemini["call_id"]]
    assert gemini["cost_status"] == "unavailable"
    assert gemini["cost_value"] is None and gemini["cost_kind"] is None
    assert "no pricing entry" in gemini["cost_unavailable_reason"]

    openai = record["calls"][1]
    assert openai["cost_status"] == "available"
    assert openai["cost_kind"] == "estimated"
    assert openai["cost_currency"] == "USD"
    assert openai["pricing_basis_id"]


@guarded
def test_the_cost_is_computed_exactly_and_not_through_the_rounding_helper():
    """PricingTable.estimate_cost rounds (pricing.py:39); the emitter must not use it."""
    from app.modules.telemetry.pricing import PricingTable

    rounded = PricingTable().estimate_cost("gpt-5.4-mini", *demo.OPENAI_TOKENS)
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))
    exact = record["calls"][1]["cost_value"]

    # Same value here, reached two ways — but only one of them is exact integer
    # arithmetic, and only one of them keeps its scale.
    assert exact == {"scale": 8, "units": 678300}
    assert abs(rounded - 0.006783) < 1e-12
    assert isinstance(exact["units"], int) and isinstance(exact["scale"], int)

    source = (REPO_ROOT / "backend" / "t4" / "emitter.py").read_text(encoding="utf-8")
    assert "estimate_cost" not in source.split("**What it does not do.**")[1].split('"""')[0] \
        or True  # the prose names it; what matters is the call graph below
    assert ".estimate_cost(" not in source


@guarded
def test_b4_reported_model_is_null_with_a_reason_on_every_call():
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))
    for call in record["calls"]:
        assert call["reported_model"] is None
        assert call["reported_model_unavailable_reason"]
        # never substituted with the requested model
        assert call["reported_model"] != call["requested_model"]


@guarded
def test_t47_a_locally_derived_total_is_arithmetically_correct():
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))
    for call in record["calls"]:
        assert call["total_tokens"]["source"] == "locally_derived"
        assert call["total_tokens"]["value"] == \
            call["input_tokens"]["value"] + call["output_tokens"]["value"]
        assert call["token_consistency_status"] == "consistent"
        # a sum-of-parts field alongside a locally derived total would be redundant
        assert call["token_sum_of_parts"] is None


@guarded
def test_i1_no_measurement_is_zero_where_it_is_absent():
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))
    for call in record["calls"]:
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            measurement = call[field]
            if measurement["status"] == "unavailable":
                assert measurement["value"] is None
                assert measurement["unavailable_reason"]
    assert record["emission_result"]["emission_status"] == "incomplete"
    assert record["emission_result"]["unavailable_measurements"] == ["calls[0].cost_value"]


# --------------------------------------------------------------------------- #
# T58 / T59 / T13 / T56 / T93 — the fingerprint
# --------------------------------------------------------------------------- #

@guarded
def test_t58_fingerprint_is_recomputable_from_the_record_alone():
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))
    recomputed = hashlib.sha256(
        jcs.serialize(record["run_configuration"])).hexdigest()
    assert recomputed == record["run_fingerprint"]


@guarded
def test_t13_two_runs_of_one_configuration_share_a_fingerprint_and_not_an_id():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        _o1, first, _ = _emit(store, run_id="run-a")
        _o2, second, _ = _emit(store, run_id="run-b")
    assert first["run_id"] != second["run_id"]
    assert first["run_fingerprint"] == second["run_fingerprint"]
    assert first["run_configuration"] == second["run_configuration"]


@guarded
def test_t93_the_profile_label_is_pinned_and_a_resolution_state_change_moves_it():
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))
    assert record["run_configuration"]["configuration_profile"] == "ion-t4-runcfg-5"

    # Mutating a resolution_state through the stored configuration changes the
    # fingerprint, because resolution_state sits inside run_configuration.
    mutated = copy.deepcopy(record["run_configuration"])
    mutated["execution_policy"]["retry_policy_identity"]["resolution_state"] = \
        "verified_sdk_default"
    assert hashlib.sha256(jcs.serialize(mutated)).hexdigest() != record["run_fingerprint"]


@guarded
def test_provenance_hashes_cannot_move_the_fingerprint():
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))
    mutated = copy.deepcopy(record)
    mutated["provenance"]["emitter_sha256"] = "0" * 64
    assert hashlib.sha256(
        jcs.serialize(mutated["run_configuration"])).hexdigest() == record["run_fingerprint"]


# --------------------------------------------------------------------------- #
# T92 — comparability is derived, never carried
# --------------------------------------------------------------------------- #

@guarded
def test_t92_strict_comparability_is_derived_and_is_false_for_this_record():
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))

    configuration = record["run_configuration"]
    identities = [configuration[k] for k in
                  ("workload_identity", "prompt_identity", "context_identity")]
    identities += list(configuration["execution_policy"].values())
    identities += [c["decoding_identity"] for c in configuration["planned_calls"]]
    identities += [c["implementation_identity"] for c in configuration["planned_components"]]

    unobservable = sorted({i["dimension"] for i in identities
                           if i["resolution_state"] == "provider_managed_unobservable"})
    assert unobservable == ["decoding", "retry", "termination", "timeout"]
    strict_comparability = not unobservable
    assert strict_comparability is False

    # The derivable fact is never stored where it could contradict its source.
    assert "strict_comparability" not in jcs.to_canonical_text(record)


@guarded
def test_t92a_a_record_carrying_a_strict_comparability_field_is_rejected():
    validate = record_validator()
    with tempfile.TemporaryDirectory() as tmp:
        _outcome, record, _ = _emit(Path(tmp))
    assert validate(record) is None

    mutated = copy.deepcopy(record)
    mutated["run_configuration"]["strict_comparability"] = True
    assert validate(mutated) is not None


# --------------------------------------------------------------------------- #
# T18 / T82 — append-only, and canonical bytes on read
# --------------------------------------------------------------------------- #

@guarded
def test_t18_a_duplicate_run_id_is_rejected_and_leaves_the_first_record_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        _outcome, first, _ = _emit(store)
        before = (store / f"{demo.RUN_ID}.json").read_bytes()

        outcome, record = _emit(store)[:2]
        assert outcome.outcome == "write_failed"
        assert outcome.failure_code == "duplicate_run_id"
        assert record is None
        assert (store / f"{demo.RUN_ID}.json").read_bytes() == before
        assert not list(store.glob("*.partial"))


@guarded
def test_t82c_a_hand_edited_non_canonical_record_is_rejected_on_read():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        _outcome, record, _ = _emit(store)
        stored = store / f"{demo.RUN_ID}.json"

        assert load_record(stored) == record

        # Equivalent data, non-canonical bytes: reordered keys and whitespace.
        import json
        stored.write_bytes(json.dumps(record, indent=2).encode("utf-8"))
        with raises(RecordRejected):
            load_record(stored)


@guarded
def test_a_record_written_under_another_contract_is_unverifiable():
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        _outcome, record, _ = _emit(store)
        stored = store / f"{demo.RUN_ID}.json"
        mutated = copy.deepcopy(record)
        mutated["run_configuration"]["identity_contract_sha256"] = "0" * 64
        stored.write_bytes(jcs.serialize(mutated))
        with raises(RecordRejected):
            load_record(stored)


# --------------------------------------------------------------------------- #
# T77 / T87(d) / T46 — refusal paths
# --------------------------------------------------------------------------- #

def _observer_with_one_call(tokens=(1000, 1000)):
    observer = RunObserver()
    observer.record(
        call_id="c1", sequence=1, attempt=observer.next_attempt(1),
        provider="openai", requested_model="expensive-model",
        reported_model=None, reported_model_reason="not reported",
        input_tokens=tokens[0], output_tokens=tokens[1], token_reason=None,
        latency_ms=1, latency_reason=None, latency_source="test")
    return observer


@guarded
def test_t77_a_known_exact_value_the_domain_cannot_hold_refuses_the_write():
    """Not rounded, not written at reduced precision, not recorded as unavailable."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        emitter = Emitter(
            manifest_path=manifest.default_path(), store_path=store,
            # a price that drives the per-call amount past its bound of 1000
            rates={"expensive-model": (999_999.0, 999_999.0)},
            pricing_basis_id="test", validator=record_validator())
        outcome, record = emitter.emit(
            record_origin="synthetic", run_id="over-bound", timestamp=demo.TIMESTAMP,
            raw_identities=_demo_identities(), planned_components=demo.COMPONENTS,
            planned_calls=[{"sequence": 1, "provider": "openai",
                            "requested_model": "expensive-model"}],
            component_results=[{"component": c["component"], "outcome": "completed",
                                "incomplete_reason": None} for c in demo.COMPONENTS],
            observer=_observer_with_one_call((10 ** 9, 10 ** 9)),
            wall_clock_ms=1, wall_clock_source="test")

        assert outcome.outcome == "write_failed"
        assert outcome.failure_code == "domain_violation"
        assert "exceeds the role bound" in outcome.detail
        assert record is None
        assert not list(store.glob("*.json"))
        assert not list(store.glob("*.partial"))


@guarded
def test_t87d_a_security_material_value_refuses_the_write_rather_than_omitting_it():
    import base64 as b64
    contract_path = REPO_ROOT / "backend" / "t4" / "contract" / \
        "ion_t4_identity_contract_v1.json"
    contract = jcs.parse(contract_path.read_bytes())
    entry = next(d for d in contract["dimensions"] if d["dimension"] == "implementation")
    variant = entry["variants"][0]
    variant["keys"][0]["key"] = "openai_api_key"
    variant["keys"].sort(key=lambda k: k["key"].encode("utf-16-be"))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        staged_contract = tmp_path / "contract.json"
        staged_contract.write_bytes(jcs.serialize(contract))
        staged_manifest = tmp_path / "artifact_manifest.json"
        entries = []
        for original in manifest.load()["artifacts"]:
            if original["role"] == manifest.ROLE_CONTRACT:
                entries.append(dict(original, path="contract.json",
                                    sha256=hashlib.sha256(
                                        staged_contract.read_bytes()).hexdigest()))
            else:
                source = REPO_ROOT / original["path"]
                copied = tmp_path / Path(original["path"]).name
                copied.write_bytes(source.read_bytes())
                entries.append(dict(original, path=copied.name))
        staged_manifest.write_bytes(jcs.serialize({"artifacts": entries}))

        identities = _demo_identities()
        raw = dict(identities["implementation"][1])
        distributions = dict(raw["distributions"])
        distributions["openai_api_key"] = distributions.pop("google_genai_version")
        identities["implementation"] = ("implementation",
                                        {"distributions": distributions,
                                         "python": raw["python"]})

        store = tmp_path / "records"
        emitter = Emitter(manifest_path=staged_manifest, store_path=store,
                          rates={}, pricing_basis_id="test")
        outcome, record = emitter.emit(
            record_origin="synthetic", run_id="secret", timestamp=demo.TIMESTAMP,
            raw_identities=identities, planned_components=demo.COMPONENTS,
            planned_calls=[{"sequence": 1, "provider": "openai",
                            "requested_model": "m"}],
            component_results=[{"component": c["component"], "outcome": "completed",
                                "incomplete_reason": None} for c in demo.COMPONENTS],
            observer=RunObserver(), wall_clock_ms=1, wall_clock_source="test")

        assert outcome.outcome == "write_failed"
        assert outcome.failure_code == "secret_boundary"
        assert record is None
        assert not store.exists() or not list(store.glob("*.json"))
        # the refusal names the key, never a value
        assert "openai_api_key" in outcome.detail
        del b64


def _demo_identities():
    import base64 as b64
    payload = b64.b64encode(b"demo").decode()
    return {
        "workload": ("workload", {"bytes_b64": payload, "present": True}),
        "prompt": ("prompt", {"bytes_b64": payload, "present": True}),
        "context": ("context", {"bytes_b64": payload, "present": True}),
        "decoding": ("decoding", {"locally_set": False}),
        "retry": ("retry", {"locally_set": False}),
        "timeout": ("timeout", {"locally_set": False}),
        "termination": ("termination", {"locally_set": False}),
        "dispatch": ("dispatch", {"configurable": False, "mode": "sequential",
                                  "order": ["gemini", "openai"]}),
        "fallback": ("fallback", {"enabled": False, "on_provider_error": "propagate"}),
        "implementation": ("implementation", demo.RECORDED_ENVIRONMENT),
    }


@guarded
def test_t46_the_emission_outcome_payload_is_closed_and_complete_on_both_branches():
    with tempfile.TemporaryDirectory() as tmp:
        outcome, _record, _ = _emit(Path(tmp))
    payload = outcome.to_dict()
    assert set(payload) == {"detail", "emitter_name", "emitter_version",
                            "failure_code", "outcome", "run_id", "timestamp"}
    assert payload["outcome"] == "written"
    assert payload["failure_code"] is None and payload["detail"] is None
    assert payload["run_id"] and payload["emitter_name"] and payload["emitter_version"]
    assert payload["timestamp"]


@guarded
def test_every_failure_code_the_emitter_can_return_is_documented():
    assert len(set(FAILURE_CODES)) == len(FAILURE_CODES)
    assert len(set(DIAGNOSTIC_CODES)) == len(DIAGNOSTIC_CODES)
    for required in ("canonicalization_input_invalid", "domain_violation",
                     "contract_unresolved", "secret_boundary"):
        assert required in FAILURE_CODES


# --------------------------------------------------------------------------- #
# I8a — the emitter does not corrupt what it measures
# --------------------------------------------------------------------------- #

@guarded
def test_i8a_a_failing_provider_still_yields_an_observed_attempt_and_the_error_propagates():
    """This is why the wrapper sits at IVEPort: `_run_engine` re-raises."""
    from types import SimpleNamespace

    from app.core.errors import ProviderError
    from app.modules.context_pack import ContextPackBuilder
    from app.modules.gemini_ive import GeminiIVE
    from app.modules.model_context import (
        DISPOSITION_ADMITTED,
        CandidateContentProjection,
        build_model_context,
    )
    from app.modules.retrieval.embeddings import HashingEmbedder
    from app.modules.retrieval.memory_index import InMemoryRetrieval
    from t4.emitter import ObservingIVE

    class Exploding:
        def generate(self, *, system, user, schema):
            raise RuntimeError("gemini 503")

    retrieval = InMemoryRetrieval(HashingEmbedder(dimension=512))
    retrieval.index(demo.DOCS)
    pack = ContextPackBuilder(char_budget=20_000).build(
        demo.QUESTION, retrieval.retrieve(demo.QUESTION, 3))

    # HARNESS FIDELITY (TASK 19.3): the live IVEPort payload is the governed
    # `ModelContextAssembly`, not the `ContextPack`. Built through the real,
    # frozen `build_model_context` -- the identical production path
    # `Core.ask()` uses -- admitting every document the pack submitted, over a
    # structural governed-basis stand-in.
    model_input = build_model_context(
        governed_basis=SimpleNamespace(
            question_id="Q-T4-I8A",
            context_pack_id=pack.context_pack_id,
            admitted=tuple(
                SimpleNamespace(candidate_id=d.document_id, disposition=DISPOSITION_ADMITTED)
                for d in pack.documents
            ),
        ),
        candidate_projections=[
            CandidateContentProjection(
                document_id=d.document_id, content=d.content, title=d.title,
                source_identity=d.source, page=d.page, chunk_id=d.chunk_id,
            )
            for d in pack.documents
        ],
        question=pack.question,
    )

    observer = RunObserver()
    wrapped = ObservingIVE(
        GeminiIVE(Exploding(), model="gemini-2.5-pro"), observer=observer,
        sequence=1, provider="gemini", requested_model="gemini-2.5-pro",
        clock=lambda: 0, latency_source="test")

    with raises(ProviderError):
        wrapped.run(model_input)

    assert len(observer.calls) == 1
    attempt = observer.calls[0]
    assert attempt["attempt"] == 1 and attempt["sequence"] == 1
    # B4: the attempt that yielded nothing carries reasoned absences, not zeros.
    assert attempt["input_tokens"] is None and attempt["latency_ms"] is None
    assert attempt["token_reason"] and attempt["latency_reason"]
