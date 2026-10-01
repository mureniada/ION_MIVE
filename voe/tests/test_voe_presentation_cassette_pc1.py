"""Presentation Cassette PC1 (staging): file contract, generator and client wiring.

PC1 is presentation-only navigation/label metadata over the 63 objects whose
staging presentation scope is in force (OP-DEC-20261001-VOE-PC1-01 for 49,
OP-DEC-20260929-09 for the 14 TW-SRC-0003 objects). Streamlit AppTest with
PilotClient's HTTP methods stubbed — no network, no backend, no provider.
Generator tests that need the governed THE_WORKS inputs skip when they are absent.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_VOE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_VOE_DIR))
sys.path.insert(0, str(_VOE_DIR / "tools"))

import generate_presentation_cassette as gen  # noqa: E402
import pilot_client as pc  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

_APP_PATH = _VOE_DIR / "app.py"
_PC1_PATH = _VOE_DIR / "presentation_cassettes" / "pc1_staging.json"
_BASE_URL = "https://voe-backend.example.internal"
_WORKS_ROOT = Path(os.environ.get(
    "THE_WORKS_ROOT", r"C:\Users\murenia\Documents\Projects\ION_CLIENTS\THE_WORKS"))
_HAVE_WORKS = (_WORKS_ROOT / gen.WORKS_INPUTS["register"][0]).exists()

Q19, Q25 = "TW-OBJ-0043", "TW-OBJ-0049"
EXPECTED_COUNTS = {"TW-SRC-0001": 10, "TW-SRC-0002": 11, "TW-SRC-0003": 14, "TW-SRC-0004": 13, "TW-SRC-0005": 15}
PENDING_SOURCE = re.compile(r"TW-SRC-00(0[6-9]|1\d|2[0-7])")
CLIENT_LOADED = ("base_questions.json", "presentation_cassettes/pc1_staging.json")


def _pc1():
    return json.loads(_PC1_PATH.read_text(encoding="utf-8"))


def _row(oid, source="TW-SRC-0003"):
    return {"document_id": f"{oid}::c0", "chunk_id": f"{oid}::c0", "source": source, "title": "",
            "page": 1, "excerpt": f"Excerpt of {oid}.", "claim_linkage": "A linked claim."}


def _answer(evidence=(), suggestions=()):
    return pc.AnswerTurn(primary_answer="An answer.", disclaimer="", evidence=tuple(evidence),
                         uncertainty=(), presentation_status="COMPOSED", suggested_questions=tuple(suggestions))


class CassetteFileTests(unittest.TestCase):
    def setUp(self):
        self.c = _pc1()
        self.members = self.c["members"]
        self.by_id = {m["object_id"]: m for m in self.members}

    def test_contract_header(self):
        self.assertEqual(self.c["schema"], "VOE_PRESENTATION_CASSETTE_V1")
        self.assertEqual(self.c["environment"], "staging")
        self.assertEqual(self.c["opening"], "STARTER_ONLY")
        self.assertEqual(self.c["entry_questions"], [])
        self.assertEqual(self.c["production"], "NOT_AUTHORIZED")

    def test_exactly_63_members_with_the_expected_split(self):
        self.assertEqual(len(self.members), 63)
        self.assertEqual(len(self.by_id), 63)
        self.assertEqual(self.c["counts"], EXPECTED_COUNTS)

    def test_authorization_refs_per_source(self):
        for m in self.members:
            expected = "OP-DEC-20260929-09" if m["source_id"] == "TW-SRC-0003" else "OP-DEC-20261001-VOE-PC1-01"
            self.assertEqual(m["authorization_ref"], expected, m["object_id"])

    def test_q19_and_q25_are_never_navigable_and_their_wording_is_blocked(self):
        for oid in (Q19, Q25):
            self.assertFalse(self.by_id[oid]["navigable_after_answer"], oid)
            self.assertIn(self.by_id[oid]["question"], self.c["suggestion_blocklist"]["questions"])
        self.assertEqual({w["object_id"] for w in self.c["navigation_withheld"]}, {Q19, Q25})

    def test_only_objects_with_a_verbatim_question_are_navigable(self):
        for m in self.members:
            if m["navigable_after_answer"]:
                self.assertTrue(m.get("question"), m["object_id"])

    def test_no_knowledge_text_in_members(self):
        allowed = {"object_id", "object_sha256", "source_id", "fragment_id", "presentation_genre", "branch",
                   "catalogue_branch", "catalogue_sub_branch", "authorization_ref", "scope_end",
                   "presentation_cautions", "navigable_after_answer", "q_number", "question", "question_ref", "related"}
        for m in self.members:
            self.assertLessEqual(set(m), allowed, m["object_id"])

    def test_no_patent_or_product_member(self):
        for m in self.members:
            self.assertNotIn(m["presentation_genre"], ("PATENT_DISCLOSURE_CLAIM", "PRODUCT_DESCRIPTION"))

    def test_hold_phrases_are_blocked(self):
        phrases = self.c["suggestion_blocklist"]["phrases"]
        for p in ("rubicon", "cloud 9", "orpheus", "profit-sharing", "nature banking"):
            self.assertIn(p, phrases)

    def test_no_pending_source_or_placeholder_in_any_client_loaded_file(self):
        for rel in CLIENT_LOADED:
            text = (_VOE_DIR / rel).read_text(encoding="utf-8")
            self.assertIsNone(PENDING_SOURCE.search(text), rel)
            for word in ("PENDING_SLOT", "coming soon", "ALLOCATED"):
                self.assertNotIn(word.casefold(), text.casefold(), rel)

    def test_app_reads_the_cassette_and_not_the_v03_files(self):
        source = _APP_PATH.read_text(encoding="utf-8")
        self.assertIn('"presentation_cassettes" / "pc1_staging.json"', source)
        self.assertNotIn("works_navigation.json", source)
        self.assertNotIn("source_labels.json", source)
        self.assertNotIn("OPENING_QUESTIONS", source)


@unittest.skipUnless(_HAVE_WORKS, "governed THE_WORKS inputs not present")
class GeneratorTests(unittest.TestCase):
    def test_members_match_the_register_hashes(self):
        rel, _ = gen.WORKS_INPUTS["register"]
        rows = csv.DictReader(io.StringIO((_WORKS_ROOT / rel).read_text(encoding="utf-8"), newline=""))
        register = {r["object_id"]: r["object_sha256"] for r in rows}
        for m in _pc1()["members"]:
            self.assertEqual(m["object_sha256"], register[m["object_id"]], m["object_id"])

    def test_generation_is_deterministic_and_matches_the_file(self):
        cassette, _ = gen.build(_WORKS_ROOT)
        self.assertEqual(gen.render(cassette), _PC1_PATH.read_bytes())

    def _tampered_root(self, tmp: Path, key: str) -> Path:
        for rel, _ in gen.WORKS_INPUTS.values():
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_WORKS_ROOT / rel, dst)
        target = tmp / gen.WORKS_INPUTS[key][0]
        target.write_bytes(target.read_bytes() + b"\n")
        return tmp

    def test_generator_refuses_any_tampered_input_and_writes_nothing(self):
        for key in gen.WORKS_INPUTS:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as d:
                root = self._tampered_root(Path(d), key)
                out = Path(d) / "out" / "pc1.json"
                with self.assertRaises(gen.CassetteError):
                    gen.build(root)
                self.assertEqual(gen.main(["--works-root", str(root), "--out", str(out)]), 2)
                self.assertFalse(out.exists())

    def test_generator_refuses_a_missing_input(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(gen.main(["--works-root", d, "--out", str(Path(d) / "o.json")]), 2)
            self.assertFalse((Path(d) / "o.json").exists())


@mock.patch.dict("os.environ", {pc._BASE_URL_ENV_VAR: _BASE_URL})
class AppPc1Tests(unittest.TestCase):
    def setUp(self):
        self.answers = []
        mock.patch.object(pc.PilotClient, "create_session", return_value="s-1").start()
        mock.patch.object(pc.PilotClient, "run_turn", side_effect=lambda sid, q: self.answers.pop(0)).start()
        self.addCleanup(mock.patch.stopall)
        self.nav = {m["object_id"]: m for m in _pc1()["members"] if m.get("question")}

    def _ask(self, question="Q?"):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=30)
        at.run()
        at.chat_input[0].set_value(question).run()
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def _suggestions(self, at):
        return [b.label for b in at.button if (b.key or "").startswith("suggest-")]

    def test_opening_renders_exactly_the_starter(self):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=30)
        at.run()
        self.assertEqual([b.label for b in at.button if b.label != "New conversation"],
                         ["What is ION and how does it work?"])

    def test_q19_and_q25_are_never_offered_from_any_navigation_path(self):
        withheld = {self.nav[Q19]["question"], self.nav[Q25]["question"]}
        # Directly in the sources, as neighbours (Q20, Q23/Q26) and via composer suggestions.
        cases = [
            [_row(Q19), _row(Q25)],
            [_row("TW-OBJ-0044"), _row("TW-OBJ-0041")],
            [_row("TW-OBJ-0047"), _row("TW-OBJ-0050")],
        ]
        for evidence in cases:
            self.answers = [_answer(evidence=evidence, suggestions=tuple(withheld))]
            offered = self._suggestions(self._ask())
            self.assertFalse(withheld & set(offered), offered)

    def test_hold_topics_never_surface_as_suggestions(self):
        held = ("What is Rubicon?", "Tell me about Cloud 9.", "Who uses Orpheus?",
                "How does profit-sharing work?")
        self.answers = [_answer(suggestions=held + ("A fine question?",))]
        self.assertEqual(self._suggestions(self._ask()), ["A fine question?"])

    def test_no_generic_guarantee_block(self):
        # Q25 is withheld by object, not by a broad word block (operator, 2026-10-01).
        self.assertNotIn("guarantee", _pc1()["suggestion_blocklist"]["phrases"])
        self.answers = [_answer(suggestions=("What would a guarantee require?",))]
        self.assertEqual(self._suggestions(self._ask()), ["What would a guarantee require?"])

    def test_research_sources_get_readable_labels_from_the_cassette(self):
        self.answers = [_answer(evidence=[_row("TW-OBJ-0068", source="TW-SRC-0005")])]
        at = self._ask()
        texts = "\n".join(m.value for m in at.markdown)
        self.assertIn(f"**{_pc1()['source_labels']['TW-SRC-0005']}**", texts)

    def test_missing_cassette_fails_closed_to_starter_only(self):
        real_read = Path.read_text

        def read_text(self, *a, **k):
            if self.name == "pc1_staging.json":
                raise OSError("absent")
            return real_read(self, *a, **k)

        with mock.patch.object(Path, "read_text", read_text):
            at = AppTest.from_file(str(_APP_PATH), default_timeout=30)
            at.run()
            self.assertEqual([b.label for b in at.button if b.label != "New conversation"],
                             ["What is ION and how does it work?"])
            self.answers = [_answer(evidence=[_row("TW-OBJ-0036")], suggestions=())]
            at.chat_input[0].set_value("Q?").run()
            at.run()
            self.assertFalse(at.exception, at.exception)
            self.assertEqual(self._suggestions(at), [])


if __name__ == "__main__":
    unittest.main()
