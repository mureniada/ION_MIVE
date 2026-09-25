"""Bounded contract test for the VOE Dialogue Profile runtime loader (Gate 2).

Scope: this covers the loader's own fail-closed identity/hash/fingerprint
validation and the VOE_PROFILE_ENABLED on/off law only. It does not exercise
any composer, ModelContext, or Core.ask() behavior — Gate 2 wires nothing
into any of those, so nothing here does either.

Two fixture strategies are used:

- Tests that must reproduce the exact pinned SHA-256/fingerprint values
  (B, D, G, H, I, K) read the REAL pinned runtime files committed with the
  loader under `app/modules/voe_profile/assets/` (see `tests/voe_pack.py`)
  — never write to them — so they run on any machine that has the
  repository.
- Tests that only need well-formed-but-wrong inputs (A, C, E, F, J) use
  synthetic `tmp_path` fixtures and do not depend on the external pack.

The immutable external source preparation pack the committed files were
taken from is used only by one optional cross-check that they are
byte-identical to it, skipped if that external workspace is not present on
the machine running this suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dataclasses

from app.modules.voe_profile import loader as loader_module
from app.modules.voe_profile.loader import (
    EXPECTED_PROFILE_ID,
    EXPECTED_PROFILE_VERSION,
    EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256,
    RUNTIME_BEHAVIORAL_FILES,
    VOEProfileLoadError,
    load_voe_profile_binding,
    load_voe_runtime_profile,
    resolve_voe_profile,
)
from app.modules.voe_profile.models import VOEProfileBinding, VOEProfileBindingError, VOERuntimeProfile
from tests.voe_pack import COMMITTED_VOE_PACK_DIR, EXTERNAL_SOURCE_PACK_DIR

REAL_PACK_DIR = COMMITTED_VOE_PACK_DIR

# The source preparation pack's OWN wider identity values (from
# 90-BUNDLE-MANIFEST.json and PROFILE_IDENTITY.txt) — pinned here as known
# constants distinct from EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256,
# for the negative tests proving neither is accepted as the runtime
# behavioral fingerprint.
_WHOLE_PACK_CANONICAL_PAYLOAD_FINGERPRINT_SHA256 = (
    "d49ef08cd9c1e9a63b548061ae699e00f3aad64f4c880205d6845f7daef89544"
)
_PACK_ZIP_SHA256 = "e7a0ab9800cbf7b494ad4a088989573f817f7068bfe0fa3726a1f9dfe79e0043"

requires_external_source_pack = pytest.mark.skipif(
    not EXTERNAL_SOURCE_PACK_DIR.is_dir(),
    reason="external source preparation workspace not present on this machine",
)


def _seed_bundle(tmp_path: Path, *, omit: str | None = None, mutate: dict[str, bytes] | None = None) -> Path:
    """Copy the four real runtime files into tmp_path, byte for byte, except
    for any filename named in `omit` (skipped) or `mutate` (replaced with
    the given bytes). Never writes to REAL_PACK_DIR."""
    mutate = mutate or {}
    for filename, _, _ in RUNTIME_BEHAVIORAL_FILES:
        if filename == omit:
            continue
        content = mutate.get(filename)
        if content is None:
            content = (REAL_PACK_DIR / filename).read_bytes()
        (tmp_path / filename).write_bytes(content)
    return tmp_path


# --------------------------------------------------------------------- #
# A: disabled -> exact baseline, no file access at all
# --------------------------------------------------------------------- #
def test_disabled_returns_none_and_touches_no_file():
    result = resolve_voe_profile(
        enabled=False, bundle_dir="C:/definitely/does/not/exist/anywhere"
    )
    assert result is None


def test_disabled_ignores_a_none_bundle_dir_too():
    assert resolve_voe_profile(enabled=False, bundle_dir=None) is None


# --------------------------------------------------------------------- #
# B: enabled + correct files -> READY / binding materialized
# --------------------------------------------------------------------- #
def test_enabled_with_real_pack_materializes_the_expected_runtime_profile():
    profile = resolve_voe_profile(enabled=True, bundle_dir=REAL_PACK_DIR)
    assert isinstance(profile, VOERuntimeProfile)
    assert profile.binding.profile_id == EXPECTED_PROFILE_ID
    assert profile.binding.profile_version == EXPECTED_PROFILE_VERSION
    assert (
        profile.binding.runtime_behavioral_fingerprint_sha256
        == EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256
    )


def test_load_voe_profile_binding_is_the_runtime_profiles_own_binding():
    via_resolve = resolve_voe_profile(enabled=True, bundle_dir=REAL_PACK_DIR)
    via_binding_only = load_voe_profile_binding(REAL_PACK_DIR)
    assert via_resolve.binding == via_binding_only


def test_load_voe_runtime_profile_direct_call_matches_resolve_voe_profile():
    via_resolve = resolve_voe_profile(enabled=True, bundle_dir=REAL_PACK_DIR)
    via_load = load_voe_runtime_profile(REAL_PACK_DIR)
    assert via_resolve == via_load


# --------------------------------------------------------------------- #
# C: missing runtime file -> fail closed
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("missing", [f for f, _, _ in RUNTIME_BEHAVIORAL_FILES])
def test_missing_runtime_file_fails_closed(tmp_path, missing):
    _seed_bundle(tmp_path, omit=missing)
    with pytest.raises(VOEProfileLoadError, match="missing"):
        load_voe_profile_binding(tmp_path)


def test_enabled_with_wholly_empty_directory_fails_closed(tmp_path):
    with pytest.raises(VOEProfileLoadError, match="missing"):
        load_voe_profile_binding(tmp_path)


# --------------------------------------------------------------------- #
# D: one-byte mutation in each behavioral file -> fail closed
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("target", [f for f, _, _ in RUNTIME_BEHAVIORAL_FILES])
def test_one_byte_mutation_fails_closed(tmp_path, target):
    original = (REAL_PACK_DIR / target).read_bytes()
    # Flip one byte in the middle, preserving length, so this specifically
    # exercises the SHA-256 mismatch path rather than the byte-count path.
    mid = len(original) // 2
    mutated_byte = (original[mid] + 1) % 256
    mutated = original[:mid] + bytes([mutated_byte]) + original[mid + 1 :]
    assert len(mutated) == len(original)

    _seed_bundle(tmp_path, mutate={target: mutated})
    with pytest.raises(VOEProfileLoadError, match="SHA-256 mismatch"):
        load_voe_profile_binding(tmp_path)


def test_truncated_file_fails_closed_on_byte_count(tmp_path):
    original = (REAL_PACK_DIR / "01-VOE-DIALOGUE-PROFILE-v0.2.md").read_bytes()
    _seed_bundle(
        tmp_path,
        mutate={"01-VOE-DIALOGUE-PROFILE-v0.2.md": original[:-1]},
    )
    with pytest.raises(VOEProfileLoadError, match="bytes, expected"):
        load_voe_profile_binding(tmp_path)


# --------------------------------------------------------------------- #
# E / F: wrong embedded profile_id / profile_version -> fail closed
#
# Tested directly against the identity-verification helper: the pinned
# per-file SHA-256 for 02-VOE-STYLE-PARAMETERS-v0.1.json is the real file's
# own hash, so a bundle-level end-to-end test cannot simultaneously satisfy
# that hash AND carry different embedded identity content. The helper is
# exactly where this check lives, so it is exercised directly (matching
# this suite's own convention of testing an inner boundary in isolation
# where the whole-pipeline path cannot construct the scenario).
# --------------------------------------------------------------------- #
def test_wrong_embedded_profile_id_fails_closed():
    payload = json.dumps({"profile_id": "SOME-OTHER-PROFILE", "profile_version": "0.2"}).encode()
    with pytest.raises(VOEProfileLoadError, match="profile identity mismatch"):
        loader_module._verify_embedded_identity(payload)


def test_wrong_embedded_profile_version_fails_closed():
    payload = json.dumps({"profile_id": "VOE-DIALOGUE-PROFILE", "profile_version": "0.9"}).encode()
    with pytest.raises(VOEProfileLoadError, match="profile version mismatch"):
        loader_module._verify_embedded_identity(payload)


def test_missing_embedded_identity_fields_fail_closed():
    payload = json.dumps({"style_parameters_version": "0.1"}).encode()
    with pytest.raises(VOEProfileLoadError, match="profile identity mismatch"):
        loader_module._verify_embedded_identity(payload)


def test_malformed_identity_source_json_fails_closed():
    with pytest.raises(VOEProfileLoadError, match="not valid UTF-8 JSON"):
        loader_module._verify_embedded_identity(b"{not json")


def test_real_style_parameters_file_passes_identity_verification():
    content = (REAL_PACK_DIR / "02-VOE-STYLE-PARAMETERS-v0.1.json").read_bytes()
    loader_module._verify_embedded_identity(content)  # must not raise


# --------------------------------------------------------------------- #
# G: wrong runtime behavioral fingerprint -> fail closed
# --------------------------------------------------------------------- #
def test_wrong_pinned_fingerprint_fails_closed(tmp_path, monkeypatch):
    _seed_bundle(tmp_path)
    monkeypatch.setattr(
        loader_module, "EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256", "0" * 64
    )
    with pytest.raises(VOEProfileLoadError, match="fingerprint mismatch"):
        load_voe_profile_binding(tmp_path)


# --------------------------------------------------------------------- #
# H: whole-pack canonical fingerprint is NOT accepted
# --------------------------------------------------------------------- #
def test_expected_fingerprint_is_not_the_whole_pack_fingerprint():
    assert (
        EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256
        != _WHOLE_PACK_CANONICAL_PAYLOAD_FINGERPRINT_SHA256
    )


def test_whole_pack_fingerprint_is_rejected_if_misconfigured(tmp_path, monkeypatch):
    _seed_bundle(tmp_path)
    monkeypatch.setattr(
        loader_module,
        "EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256",
        _WHOLE_PACK_CANONICAL_PAYLOAD_FINGERPRINT_SHA256,
    )
    with pytest.raises(VOEProfileLoadError, match="fingerprint mismatch"):
        load_voe_profile_binding(tmp_path)


# --------------------------------------------------------------------- #
# I: ZIP hash is NOT accepted
# --------------------------------------------------------------------- #
def test_expected_fingerprint_is_not_the_pack_zip_hash():
    assert EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256 != _PACK_ZIP_SHA256


def test_pack_zip_hash_is_rejected_if_misconfigured(tmp_path, monkeypatch):
    _seed_bundle(tmp_path)
    monkeypatch.setattr(
        loader_module, "EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256", _PACK_ZIP_SHA256
    )
    with pytest.raises(VOEProfileLoadError, match="fingerprint mismatch"):
        load_voe_profile_binding(tmp_path)


# --------------------------------------------------------------------- #
# J: excluded files are not runtime-loaded
# --------------------------------------------------------------------- #
def test_extra_excluded_named_files_present_do_not_affect_the_result(tmp_path):
    _seed_bundle(tmp_path)
    # Sibling files this loader must never open, even though they exist
    # right next to the four it does.
    (tmp_path / "07-VOE-CALIBRATION-SMOKE-v0.1.md").write_text("garbage, never read")
    (tmp_path / "90-BUNDLE-MANIFEST.json").write_text("{}")
    (tmp_path / "99-PREPARATION-RECEIPT.md").write_text("garbage, never read")

    with_extras = load_voe_profile_binding(tmp_path)

    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    _seed_bundle(clean_dir)
    without_extras = load_voe_profile_binding(clean_dir)

    assert with_extras == without_extras


def test_loader_source_never_lists_a_directory():
    """Structural proof, not behavioral inference: no call to a directory-
    listing operation (`iterdir`, `glob`, `rglob`, `listdir`, `scandir`)
    exists anywhere in loader.py's actual code, so it has no code path
    capable of discovering a file it was not explicitly given the name of.

    Parses the AST rather than scanning source text, so a docstring that
    merely NAMES these operations (to state they are absent, as this
    module's own docstring does) cannot trip a false positive the way a
    plain substring search would.
    """
    import ast

    source = Path(loader_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"iterdir", "glob", "rglob", "listdir", "scandir"}
    called_names = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    overlap = called_names & forbidden
    assert overlap == set(), f"loader.py calls forbidden directory-listing operation(s): {overlap}"


# --------------------------------------------------------------------- #
# K: deterministic four-file ordering produces the expected fingerprint
# --------------------------------------------------------------------- #
def test_pinned_file_order_reproduces_the_expected_fingerprint():
    """Pure function test on the pinned tuple alone — no file I/O, always
    runs regardless of the external pack's presence."""
    fingerprint = loader_module._runtime_behavioral_fingerprint(RUNTIME_BEHAVIORAL_FILES)
    assert fingerprint == EXPECTED_RUNTIME_BEHAVIORAL_FINGERPRINT_SHA256


def test_runtime_behavioral_files_tuple_is_already_path_sorted():
    paths = [f for f, _, _ in RUNTIME_BEHAVIORAL_FILES]
    assert paths == sorted(paths)
    assert len(paths) == 4


# --------------------------------------------------------------------- #
# Gate 2A: VOERuntimeProfile materialization
# --------------------------------------------------------------------- #
def test_voe_runtime_profile_is_immutable():
    profile = VOERuntimeProfile(
        binding=VOEProfileBinding(
            profile_id="X", profile_version="1", runtime_behavioral_fingerprint_sha256="a" * 64
        ),
        dialogue_profile_text="dialogue",
        style_parameters_text="{}",
        ethical_policy_text="ethics",
        illustrative_reasoning_policy_text="reasoning",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.dialogue_profile_text = "different"


def test_voe_runtime_profile_field_set_is_exactly_the_pinned_five():
    field_names = {f.name for f in dataclasses.fields(VOERuntimeProfile)}
    assert field_names == {
        "binding",
        "dialogue_profile_text",
        "style_parameters_text",
        "ethical_policy_text",
        "illustrative_reasoning_policy_text",
    }


_FORBIDDEN_RUNTIME_PROFILE_FIELD_NAMES = {
    "evidence",
    "authorized_evidence_basis",
    "retrieval",
    "retrieved_evidence",
    "model_context",
    "model_context_assembly",
    "governed_evidence",
    "governed_evidence_set",
    "session",
    "session_state",
    "conversation_memory",
    "provider",
    "model",
    "api_key",
    "credential",
    "settings",
    "bundle_dir",
    "path",
}


def test_voe_runtime_profile_has_no_evidence_retrieval_session_provider_settings_field():
    field_names = {f.name for f in dataclasses.fields(VOERuntimeProfile)}
    overlap = field_names & _FORBIDDEN_RUNTIME_PROFILE_FIELD_NAMES
    assert overlap == set(), f"VOERuntimeProfile carries forbidden field(s): {overlap}"


def test_voe_runtime_profile_rejects_wrong_binding_type():
    with pytest.raises(VOEProfileBindingError):
        VOERuntimeProfile(
            binding="not-a-binding",  # type: ignore[arg-type]
            dialogue_profile_text="dialogue",
            style_parameters_text="{}",
            ethical_policy_text="ethics",
            illustrative_reasoning_policy_text="reasoning",
        )


def test_voe_runtime_profile_rejects_empty_text_field():
    with pytest.raises(VOEProfileBindingError):
        VOERuntimeProfile(
            binding=VOEProfileBinding(
                profile_id="X", profile_version="1",
                runtime_behavioral_fingerprint_sha256="a" * 64,
            ),
            dialogue_profile_text="",
            style_parameters_text="{}",
            ethical_policy_text="ethics",
            illustrative_reasoning_policy_text="reasoning",
        )


def test_real_pack_load_returns_all_four_nonempty_behavioral_texts():
    profile = load_voe_runtime_profile(REAL_PACK_DIR)
    assert profile.dialogue_profile_text.strip() != ""
    assert profile.style_parameters_text.strip() != ""
    assert profile.ethical_policy_text.strip() != ""
    assert profile.illustrative_reasoning_policy_text.strip() != ""
    # Sanity: each text plausibly comes from its own named file, not a
    # cross-wired one.
    assert "Voice of Emergence" in profile.dialogue_profile_text or "VOE" in profile.dialogue_profile_text
    assert profile.style_parameters_text.lstrip().startswith("{")


@pytest.mark.parametrize(
    "filename,field_name",
    [
        ("01-VOE-DIALOGUE-PROFILE-v0.2.md", "dialogue_profile_text"),
        ("02-VOE-STYLE-PARAMETERS-v0.1.json", "style_parameters_text"),
        ("03-VOE-ETHICAL-INTERACTION-POLICY-v0.1.md", "ethical_policy_text"),
        ("04-VOE-ILLUSTRATIVE-REASONING-POLICY-v0.1.md", "illustrative_reasoning_policy_text"),
    ],
)
def test_runtime_text_is_byte_for_byte_the_verified_source_bytes(filename, field_name):
    """`runtime_text.encode("utf-8")` must equal the exact bytes that were
    hash-verified for this file — proving the text in VOERuntimeProfile is a
    decode of the verified bytes, never a re-read, a reconstruction, or a
    normalized/stripped variant."""
    source_bytes = (REAL_PACK_DIR / filename).read_bytes()
    profile = load_voe_runtime_profile(REAL_PACK_DIR)
    runtime_text = getattr(profile, field_name)
    assert runtime_text.encode("utf-8") == source_bytes


def test_no_second_filesystem_read_after_verification(tmp_path, monkeypatch):
    """Instrumented read boundary: patches `pathlib.Path.read_bytes` to
    count and record every call for the duration of one successful load.
    Exactly one read per of the four files, no duplicates, is the whole
    proof — nothing more elaborate is needed."""
    _seed_bundle(tmp_path)

    original_read_bytes = Path.read_bytes
    calls: list[Path] = []

    def counting_read_bytes(self, *args, **kwargs):
        calls.append(self)
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    load_voe_runtime_profile(tmp_path)

    read_names = sorted(p.name for p in calls)
    expected_names = sorted(f for f, _, _ in RUNTIME_BEHAVIORAL_FILES)
    assert read_names == expected_names, (
        f"expected exactly one read per runtime file, got reads for {read_names}"
    )


def test_utf8_decode_failure_fails_closed(monkeypatch):
    """A real pinned SHA-256 can never correspond to invalid-UTF-8 bytes
    (its source file is, by definition, valid UTF-8 already), so
    "hash-verified yet undecodable" cannot be constructed end-to-end against
    real files. This tests the decode-failure branch directly by making the
    already-hash-verified read step (`_read_and_check_file`) return invalid
    UTF-8 bytes that still satisfy its own return contract — proving
    `load_voe_runtime_profile` fails closed on the decode step itself,
    independent of the hash check that precedes it."""
    invalid_utf8 = b"\xff\xfe not valid utf-8 at all"

    def fake_read_and_check_file(bundle_dir, filename, expected_bytes, expected_sha256):
        return invalid_utf8

    monkeypatch.setattr(loader_module, "_read_and_check_file", fake_read_and_check_file)
    with pytest.raises(VOEProfileLoadError, match="not valid UTF-8"):
        load_voe_runtime_profile("irrelevant-path-not-touched")


# --------------------------------------------------------------------- #
# Optional cross-check: committed assets == external source pack
# --------------------------------------------------------------------- #
@requires_external_source_pack
@pytest.mark.parametrize("filename", [f for f, _, _ in RUNTIME_BEHAVIORAL_FILES])
def test_committed_asset_is_byte_identical_to_the_external_source_pack(filename):
    """The committed runtime file every test above reads must be byte for
    byte the file in the immutable source preparation pack it was taken
    from. Reads both sides, writes neither. This is the only test in the
    suite that depends on the external pack, and it skips where that pack
    is absent."""
    committed = (COMMITTED_VOE_PACK_DIR / filename).read_bytes()
    external = (EXTERNAL_SOURCE_PACK_DIR / filename).read_bytes()
    assert committed == external
