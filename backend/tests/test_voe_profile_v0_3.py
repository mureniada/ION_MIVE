"""VOE Dialogue Profile v0.3 (operator-approved 2026-09-29, client-experience refinement).

v0.3 is a NEW version next to v0.2: v0.2's files stay byte-identical, v0.3 has
its own identity/fingerprint, carries the approved voice, qualification,
two-context "layer" and default-length rules, and weakens nothing: the
composer's own preamble, schema and payload are unchanged. Also covers the
held-Works blocklist in the suggested-question filter. Offline; no provider.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from app.modules.response_composer import composer as composer_module
from app.modules.response_composer.composer import (
    build_composer_system_instruction,
    build_composer_user_payload,
    filter_suggested_questions,
)
from app.modules.voe_profile import loader as loader_module
from app.modules.voe_profile.loader import load_voe_runtime_profile
from tests.voe_pack import COMMITTED_VOE_PACK_DIR

V0_2_FILES = {  # historical v0.2 pins (loader before 2026-09-29) — must stay byte-identical
    "01-VOE-DIALOGUE-PROFILE-v0.2.md": (13140, "a5d96b9661d0ef6e6d752dd84e980e96461a957e5a9b82c9df55239a74484298"),
    "02-VOE-STYLE-PARAMETERS-v0.1.json": (1384, "389bee95e9a4932b09b724d369abe9771d48f45d8c5fc41e59030fc14b8df364"),
    "03-VOE-ETHICAL-INTERACTION-POLICY-v0.1.md": (2422, "538bf8bf8427aefd33aeac73e4659ac07f5f8c0fd3b2964efc93ffdf64cbadc5"),
    "04-VOE-ILLUSTRATIVE-REASONING-POLICY-v0.1.md": (1498, "8d56f1038b3bf2cee1eebe31e197bdc6493439f4fdce0e8ca324ce92e9001638"),
}
V0_2_FINGERPRINT = "432dd52a9e693e301eacd299e0253c0825dde9c364151c0b21391118efb370f5"
V0_3_FINGERPRINT = "e9966bd07fe723b68e6d10112ffa8651983649c255859fd95d55abd9a90fbbee"
V0_3_SYSTEM_INSTRUCTION_SHA256 = "46a5cd85f357b5ddddbfaef861c99cd754c9a9e4720c49d7c39a0618e7cad5de"
# Composer-owned preamble at e60b5cf (before v0.3) — must be unchanged.
PREAMBLE_SHA256_AT_E60B5CF = "c6632fca38a21d6ca0a21309ae17646aac0465aecb9db27d11446080982a5ca2"

# The only edits v0.3 makes to the v0.2 body before appending §25–§28.
V0_3_EDITS = (
    ("# VOE-DIALOGUE-PROFILE v0.2\n", "# VOE-DIALOGUE-PROFILE v0.3\n"),
    ("PROFILE_VERSION: 0.2  \n", "PROFILE_VERSION: 0.3  \n"),
    ("STATUS: CANDIDATE FROZEN FOR RUNTIME WIRING  \n",
     "STATUS: OPERATOR-APPROVED 2026-09-29 FOR STAGING REFINEMENT (supersedes v0.2 for runtime; v0.2 retained unchanged)  \n"),
    ("- “The evidence does not support certainty here.”\n", "- “The material does not support certainty here.”\n"),
)


def _read(name: str) -> bytes:
    return (COMMITTED_VOE_PACK_DIR / name).read_bytes()


def _v03_text() -> str:
    return _read("01-VOE-DIALOGUE-PROFILE-v0.3.md").decode("utf-8")


# --- D. Profile identity --------------------------------------------- #
@pytest.mark.parametrize("name", sorted(V0_2_FILES))
def test_v0_2_files_remain_byte_identical(name):
    size, sha = V0_2_FILES[name]
    content = _read(name)
    assert len(content) == size
    assert hashlib.sha256(content).hexdigest() == sha


def test_v0_2_fingerprint_is_unchanged_under_the_loader_rule():
    rows = tuple((n, *V0_2_FILES[n]) for n in sorted(V0_2_FILES))
    assert loader_module._runtime_behavioral_fingerprint(rows) == V0_2_FINGERPRINT


def test_v0_3_has_its_own_identity_and_fingerprint():
    profile = load_voe_runtime_profile(COMMITTED_VOE_PACK_DIR)
    assert profile.binding.profile_id == "VOE-DIALOGUE-PROFILE"
    assert profile.binding.profile_version == "0.3"
    assert profile.binding.runtime_behavioral_fingerprint_sha256 == V0_3_FINGERPRINT != V0_2_FINGERPRINT
    assert [f for f, _, _ in loader_module.RUNTIME_BEHAVIORAL_FILES] == [
        "01-VOE-DIALOGUE-PROFILE-v0.3.md", "02-VOE-STYLE-PARAMETERS-v0.2.json",
        "03-VOE-ETHICAL-INTERACTION-POLICY-v0.1.md", "04-VOE-ILLUSTRATIVE-REASONING-POLICY-v0.1.md",
    ]


def test_v0_3_is_v0_2_plus_only_the_recorded_edits_and_new_sections():
    base = _read("01-VOE-DIALOGUE-PROFILE-v0.2.md").decode("utf-8")
    for old, new in V0_3_EDITS:
        assert base.count(old) == 1
        base = base.replace(old, new)
    v03 = _v03_text()
    assert v03.startswith(base.rstrip("\n") + "\n\n## 25. Voice and Presence (v0.3)\n")
    appended = v03[len(base.rstrip("\n")):]
    assert [line for line in appended.splitlines() if line.startswith("## ")] == [
        "## 25. Voice and Presence (v0.3)",
        "## 26. Qualifications and Uncertainty in Conversation (v0.3)",
        "## 27. Two Meanings of \"Layer\" (v0.3)",
        "## 28. Default Length (v0.3)",
    ]
    assert "\r" not in v03


def test_style_parameters_v0_2_identity_and_unchanged_override_policy():
    new = json.loads(_read("02-VOE-STYLE-PARAMETERS-v0.2.json"))
    old = json.loads(_read("02-VOE-STYLE-PARAMETERS-v0.1.json"))
    assert (new["profile_id"], new["profile_version"], new["style_parameters_version"]) == ("VOE-DIALOGUE-PROFILE", "0.3", "0.2")
    assert new["user_override_policy"] == old["user_override_policy"]
    assert set(old["prohibited_style_drift"]) <= set(new["prohibited_style_drift"])
    assert {"persona_imitation", "self_description", "flirtation", "theatrical_femininity",
            "mystical_exaggeration", "institutional_audit_tone"} <= set(new["prohibited_style_drift"])
    assert new["defaults"]["verbosity"] == "concise_by_default"
    assert new["defaults"]["default_answer_length_words"] == "100-180"


# --- D. Required rules present ------------------------------------------ #
def test_no_imitation_and_no_self_description():
    t = _v03_text()
    assert "Voice of Emergence is not a simulation or imitation of Samina Vabo Ansari." in t  # §2 kept
    assert "Do not imitate Samina Vabo Ansari or any identifiable person" in t
    assert "Never describe yourself: do not state or imply your gender, appearance, body, age, beauty, feelings or nature" in t
    assert "do not claim to be human or to be nature" in t


def test_default_length_policy_is_a_target_not_a_limit():
    t = _v03_text()
    assert "aim for about 100–180 words" in t
    assert "two to four short paragraphs, one main idea per paragraph" in t
    assert "This is a default target, not a limit" in t
    assert "Never cut a qualification or an uncertainty to reach the range" in t


def test_two_context_layer_rule_is_present():
    t = _v03_text()
    assert "relative to Lyra and The Works' application architecture, ION may be described as a financial foundation or foundational layer" in t
    assert "relative to the wider monetary system, ION is a middle, transitional or tuning layer — not a replacement for sovereign money and not an end point" in t
    assert "Shortening an answer must never collapse these two contexts." in t


def test_qualification_rule_is_natural_but_never_weakening():
    t = _v03_text()
    assert "normally in one plain sentence" in t
    assert "Do not add a generic uncertainty sentence" in t
    assert "Never drop, soften or weaken a stated uncertainty" in t
    assert "never invent one" in t


def test_source_and_knowledge_authority_is_not_weakened():
    t = _v03_text()
    for kept in ("KNOWLEDGE AUTHORITY: NONE", "EVIDENCE AUTHORITY: NONE", "PROFILE != EVIDENCE",
                 "The Voice must never fabricate information", "Never name, describe or imply a source you were not given."):
        assert kept in t
    assert hashlib.sha256(composer_module._SYSTEM_INSTRUCTION_PREAMBLE.encode()).hexdigest() == PREAMBLE_SHA256_AT_E60B5CF


def test_system_instruction_is_pinned_for_v0_3():
    profile = load_voe_runtime_profile(COMMITTED_VOE_PACK_DIR)
    system = build_composer_system_instruction(profile)
    assert hashlib.sha256(system.encode("utf-8")).hexdigest() == V0_3_SYSTEM_INSTRUCTION_SHA256
    assert system.startswith(composer_module._SYSTEM_INSTRUCTION_PREAMBLE)


def test_response_depth_is_deliberately_not_sent_to_the_composer():
    """Documented decision (docs/VOE_PROFILE_v0.3_CLIENT_EXPERIENCE.md): length is a
    profile default; `response_depth` stays dormant, so the composer payload and
    schema are unchanged and no second call exists."""
    from app.modules.response_composer.models import ComposerInput
    profile = load_voe_runtime_profile(COMMITTED_VOE_PACK_DIR)
    payload = json.loads(build_composer_user_payload(ComposerInput(
        question="Q?", report_abstract="A.", report_highlights=(), report_claims=(),
        report_uncertainty=("U.",), report_confidence=0.5, voe_profile=profile, response_depth="BRIEF")))
    assert set(payload) == {"question", "abstract", "highlights", "claims", "uncertainty", "confidence"}


# --- C. Held Works material never surfaces as a suggestion --------------- #
def test_blocked_held_works_phrases_are_filtered():
    raw = ["What would Nature Banking mean?", "Could NATURE BANKING replace banks?",
           "Should money serve life, rather than life serving money?",
           "How does ION relate to money?", "What does Lyra do?"]
    assert filter_suggested_questions(raw, "What is ION?") == ("How does ION relate to money?", "What does Lyra do?")
