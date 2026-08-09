"""Pre-freeze validation of the identity contract — mandate section 13.6, items 1-11.

The contract under test is the operator-supplied byte image, copied unchanged into
`t4/contract/`. It is **not frozen and not registered**: see that directory's
STATUS.md. These tests establish what the mission's step 4.4 asks and stop exactly
where it says to stop — before the freeze.

The independent-implementation check is the point of
`test_this_canonicalizer_reproduces_the_contract_bytes_and_every_vector_digest`: the
contract's stated digest and its fifteen vector digests were produced by a separate
canonicalizer, so agreement here is two implementations agreeing. That is strong
evidence and it is still not conformance (T61a).

Every test runs under `netguard`'s `guarded` decorator with credentials absent.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from t4 import contract_check, jcs
from tests.netguard import guarded
from tests.util import raises

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "t4" / "contract" / \
    "ion_t4_identity_contract_v1.json"

# The digest of the byte image the operator supplied with the closing mission.
SUPPLIED_SHA256 = "a3e58ea456cfe26309c47b24ec7944ac77604f4a47a96d5f7ccace1955ceb48e"
SUPPLIED_BYTE_COUNT = 29978
EXPECTED_VECTOR_COUNT = 15


def _raw() -> bytes:
    return CONTRACT_PATH.read_bytes()


@guarded
def test_the_contract_byte_image_is_the_one_that_was_supplied():
    raw = _raw()
    assert len(raw) == SUPPLIED_BYTE_COUNT
    assert hashlib.sha256(raw).hexdigest() == SUPPLIED_SHA256


@guarded
def test_this_canonicalizer_reproduces_the_contract_bytes_and_every_vector_digest():
    """Two independent implementations agreeing — necessary, not sufficient (T61a)."""
    raw = _raw()
    contract = jcs.parse(raw)

    # (a) the contract's own canonical bytes
    assert jcs.serialize(contract) == raw
    assert hashlib.sha256(jcs.serialize(contract)).hexdigest() == SUPPLIED_SHA256

    # (b) every builder vector, all three stages, computed rather than read
    seen = 0
    for dimension in contract["dimensions"]:
        for vector in dimension["vectors"]:
            seen += 1
            where = vector["vector_id"]
            basis_bytes = base64.b64decode(vector["expected_basis_bytes_b64"], validate=True)
            assert jcs.serialize(vector["expected_identity"]["basis"]) == basis_bytes, where
            digest = hashlib.sha256(basis_bytes).hexdigest()
            assert digest == vector["expected_digest"], where
            assert digest == vector["expected_identity"]["digest"], where
            raw_input = base64.b64decode(vector["raw_input_b64"], validate=True)
            assert jcs.canonicalize(raw_input) == raw_input, where
    assert seen == EXPECTED_VECTOR_COUNT


@guarded
def test_stored_contract_bytes_are_canonical():
    """Section 13.6 item 11 / I16: a non-canonical stored artifact is rejected on read."""
    assert contract_check.stored_bytes_are_canonical(_raw())


@guarded
def test_contract_passes_section_13_6_items_1_to_10():
    """Item 1 runs against the registered meta-schema artifact, not only structurally."""
    from t4 import manifest

    _path, meta_raw, _digest = manifest.resolve(manifest.ROLE_CONTRACT_SCHEMA)
    result = contract_check.check_contract(jcs.parse(_raw()), jcs.parse(meta_raw))
    assert result.passed, "findings:\n" + "\n".join(result.findings)
    # Every checklist item was actually exercised, not merely not-failed.
    for item in ("1", "2", "3", "4", "4a", "4b", "5", "6", "7", "8", "9", "10"):
        assert item in result.checks_run, f"checklist item {item} never ran"


@guarded
def test_the_ten_dimensions_are_present_unique_and_sorted():
    contract = jcs.parse(_raw())
    names = [d["dimension"] for d in contract["dimensions"]]
    assert len(names) == 10
    assert set(names) == set(contract_check.DIMENSIONS)
    assert names == sorted(names, key=lambda n: n.encode("utf-16-be"))


@guarded
def test_the_validator_rejects_a_contract_that_violates_each_checked_rule():
    """The checks are enforced, not decorative — one mutation per rule family.

    Mutations are made on the parsed document; nothing on disk is touched.
    """
    import copy

    def broken(mutate):
        contract = jcs.parse(_raw())
        mutate(contract)
        return contract_check.check_contract(contract)

    def dimension(contract, name):
        return next(d for d in contract["dimensions"] if d["dimension"] == name)

    # item 2 — a pinned value moved off its pin
    assert not broken(lambda c: c.__setitem__("profile_label", "ion-t4-runcfg-4")).passed
    assert not broken(lambda c: c.__setitem__("canonicalization", "jcs")).passed

    # item 1 — an unknown key anywhere
    assert not broken(lambda c: c.__setitem__("extra", 1)).passed
    assert not broken(lambda c: dimension(c, "prompt").__setitem__("extra", 1)).passed

    # item 3 — a missing dimension, and an unsorted one
    assert not broken(lambda c: c["dimensions"].pop()).passed
    assert not broken(lambda c: c["dimensions"].reverse()).passed

    # item 4 — a content dimension with no content_rule
    assert not broken(lambda c: dimension(c, "context").__setitem__("content_rule", None)).passed
    # item 4 — a parameter_set variant with an empty key set
    assert not broken(
        lambda c: dimension(c, "dispatch")["variants"][0].__setitem__("keys", [])).passed

    # item 4a — an unobservable dimension stripped of its declaration
    assert not broken(
        lambda c: dimension(c, "retry").__setitem__("unobservable_declaration", None)).passed
    # ... and one whose declaration carries an empty evidence field
    assert not broken(
        lambda c: dimension(c, "retry")["unobservable_declaration"]
        .__setitem__("evidence", "")).passed

    # item 4b — library_default named first with no verification entry
    def name_library_default(contract):
        key = dimension(contract, "dispatch")["variants"][0]["keys"][0]
        key["default_resolution"]["sources"] = ["library_default"]
    assert not broken(name_library_default).passed

    # item 5 — a discriminator outside the dimension's admitted subset
    assert not broken(
        lambda c: dimension(c, "dispatch").__setitem__("discriminators", ["provider"])).passed

    # item 6 — two selectors in one dimension that can both match
    def duplicate_variant(contract):
        entry = dimension(contract, "dispatch")
        clone = copy.deepcopy(entry["variants"][0])
        clone["variant_id"] = "zz-clone"          # keeps the sort order valid
        entry["variants"].append(clone)
    assert not broken(duplicate_variant).passed

    # item 7 — a dimension with no vector
    assert not broken(lambda c: dimension(c, "workload").__setitem__("vectors", [])).passed

    # item 8 — a digest that does not match its basis
    def break_digest(contract):
        vector = dimension(contract, "workload")["vectors"][0]
        vector["expected_digest"] = "0" * 64
    assert not broken(break_digest).passed

    # item 8 — a basis whose bytes disagree with expected_basis_bytes_b64
    def break_basis_bytes(contract):
        vector = dimension(contract, "prompt")["vectors"][0]
        vector["expected_identity"]["basis"]["content"]["byte_length"] = 80.0
    assert not broken(break_basis_bytes).passed

    # item 8 — an inadmissible (presence, basis_kind, resolution_state) triple
    def break_coupling(contract):
        vector = dimension(contract, "context")["vectors"][2]  # the absent vector
        vector["expected_identity"]["resolution_state"] = "explicit_value"
    assert not broken(break_coupling).passed

    # item 8 — a content_reference basis made to carry a parameter
    def break_truth_table(contract):
        vector = dimension(contract, "workload")["vectors"][0]
        vector["expected_identity"]["basis"]["parameters"] = [
            {"key": "k", "value": "1", "value_type": "integer"}]
    assert not broken(break_truth_table).passed

    # item 9 — readable_at_emission false
    def break_readability(contract):
        key = dimension(contract, "implementation")["variants"][0]["keys"][0]
        key["default_resolution"]["readable_at_emission"] = False
    assert not broken(break_readability).passed

    # item 10 — a key name that reads as credential-bearing
    def break_secret_boundary(contract):
        key = dimension(contract, "implementation")["variants"][0]["keys"][0]
        key["key"] = "openai_api_key"
    assert not broken(break_secret_boundary).passed


@guarded
def test_a_hand_edited_non_canonical_contract_is_rejected_on_read():
    """I16 / T82c, for the contract: equivalent but non-canonical bytes do not pass."""
    raw = _raw()
    reordered = b'{"contract_version":"1.0.0","canonicalization":"rfc8785"}'
    assert not contract_check.stored_bytes_are_canonical(reordered)
    whitespaced = b'{"a": 1}'
    assert not contract_check.stored_bytes_are_canonical(whitespaced)
    assert contract_check.stored_bytes_are_canonical(raw)


@guarded
def test_the_registered_schemas_are_exactly_what_their_source_derives():
    """The artifact and its source cannot drift: the bytes are re-derived and compared."""
    from t4 import build_schemas, manifest

    for role, filename in (
        (manifest.ROLE_CONTRACT_SCHEMA, build_schemas.CONTRACT_SCHEMA_FILENAME),
        (manifest.ROLE_RUN_RECORD_SCHEMA, build_schemas.RUN_RECORD_SCHEMA_FILENAME),
    ):
        _path, raw, _digest = manifest.resolve(role)
        assert raw == build_schemas.canonical_bytes(filename), filename
        assert jcs.canonicalize(raw) == raw, filename


@guarded
def test_a_contract_with_a_duplicate_property_name_never_parses():
    with raises(jcs.DuplicatePropertyName):
        jcs.parse('{"contract_kind":"a","contract_kind":"b"}')


@guarded
def test_no_dimension_declares_a_key_whose_effective_value_is_unreadable():
    """Section 13.2: an unreadable value's honest home is an `unobservable` dimension.

    Four dimensions in this contract take that home: they carry no keys at all.
    """
    contract = jcs.parse(_raw())
    unobservable = sorted(d["dimension"] for d in contract["dimensions"]
                          if d["basis_kind"] == "unobservable")
    assert unobservable == ["decoding", "retry", "termination", "timeout"]
    for entry in contract["dimensions"]:
        for variant in entry["variants"] or []:
            for key in variant["keys"]:
                assert key["default_resolution"]["readable_at_emission"] is True
