"""VOE client-experience refinement v0.3 (operator-approved 2026-09-29).

Natural answer on the main surface; Sources and "About this answer" collapsed;
every technical disclosure kept verbatim; bounded, allowlisted Works navigation
after answers. Since PC1 the app reads navigation from the presentation cassette
and the opening is the starter only; works_navigation.json remains the pinned
generator input and is still checked here as a file. Streamlit AppTest with
PilotClient's HTTP methods stubbed — no network, no backend, no provider.
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_VOE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_VOE_DIR))

import pilot_client as pc  # noqa: E402  (path insert above must run first)
from streamlit.testing.v1 import AppTest  # noqa: E402

_APP_PATH = _VOE_DIR / "app.py"
_NAV_PATH = _VOE_DIR / "works_navigation.json"
_LABELS_PATH = _VOE_DIR / "source_labels.json"
_BASE_URL = "https://voe-backend.example.internal"
_COMPOSED_LABEL = "Presented in the Voice of Emergence style from the verified interpretation."
_DISCLAIMER = "The interpretation in this response was produced by a single configured model execution (gemini)."

# The 14 TW-SRC-0003 objects authorized by OP-DEC-20260929-09 — nothing else.
AUTHORIZED = {
    "TW-OBJ-0025", "TW-OBJ-0033", "TW-OBJ-0036", "TW-OBJ-0037", "TW-OBJ-0040", "TW-OBJ-0041", "TW-OBJ-0043",
    "TW-OBJ-0044", "TW-OBJ-0045", "TW-OBJ-0046", "TW-OBJ-0047", "TW-OBJ-0049", "TW-OBJ-0050", "TW-OBJ-0051",
}
HELD_FRAGMENTS = {
    "TW-PROP-0026", "TW-PROP-0027", "TW-PROP-0028", "TW-PROP-0029", "TW-PROP-0030", "TW-PROP-0031", "TW-PROP-0032",
    "TW-PROP-0034", "TW-PROP-0035", "TW-PROP-0038", "TW-PROP-0039", "TW-PROP-0042", "TW-PROP-0048", "TW-PROP-0052",
}
OPENINGS = [
    ("TW-OBJ-0036", "How does ION relate to money?"),
    ("TW-OBJ-0037", "What problem is ION trying to resolve?"),
    ("TW-OBJ-0047", "What makes ION a wavelet?"),
]
NOT_AFTER_ANSWER = {"TW-OBJ-0033", "TW-OBJ-0040", "TW-OBJ-0041", "TW-OBJ-0051"}  # Q9, Q16, Q17, Q27
Q9_WORDING = "What would be needed to correct this?"
Q24_WORDING = "What would Nature Banking mean?"
AUDIT_WORDS = ("evidence", "verified interpretation", "configured model", "cross-model",
               "consensus", "what remains uncertain", "model execution")


def _nav():
    return json.loads(_NAV_PATH.read_text(encoding="utf-8"))


def _row(oid, n=0, source="TW-SRC-0003", page=2, claim="A linked claim."):
    return {"document_id": f"{oid}::c{n}", "chunk_id": f"{oid}::c{n}", "source": source, "title": "",
            "page": page, "excerpt": f"Excerpt of {oid}.", "claim_linkage": claim}


def _answer(evidence=(), suggestions=(), status="COMPOSED", uncertainty=("Implementation is not yet specified.",),
            text="A calm, natural answer."):
    return pc.AnswerTurn(primary_answer=text, disclaimer=_DISCLAIMER, evidence=tuple(evidence),
                         uncertainty=tuple(uncertainty), presentation_status=status,
                         suggested_questions=tuple(suggestions))


def _walk(node):
    yield node
    kids = getattr(node, "children", None)
    if isinstance(kids, dict):
        for k in sorted(kids):
            yield from _walk(kids[k])


def _surface_texts(chat_message):
    """Text shown directly in the answer bubble — everything outside the expanders."""
    out = []
    for k in sorted(chat_message.children):
        node = chat_message.children[k]
        if type(node).__name__ == "Expander":
            continue
        for n in _walk(node):
            if isinstance(getattr(n, "value", None), str):
                out.append(n.value)
    return out


def _expander_texts(expander):
    return [n.value for n in _walk(expander) if isinstance(getattr(n, "value", None), str)]


class WorksNavigationFileTests(unittest.TestCase):
    def setUp(self):
        self.nav = _nav()
        self.items = self.nav["items"]

    def test_bound_to_exactly_the_14_authorized_objects(self):
        self.assertEqual({i["object_id"] for i in self.items}, AUTHORIZED)
        self.assertEqual(self.nav["authority"]["decision"], "OP-DEC-20260929-09")
        self.assertEqual(self.nav["authority"]["source_id"], "TW-SRC-0003")

    def test_no_held_fragment_is_an_item(self):
        self.assertFalse({i["fragment_id"] for i in self.items} & HELD_FRAGMENTS)
        self.assertTrue(HELD_FRAGMENTS <= set(self.nav["blocked"]["fragments"]))

    def test_openings_are_exactly_the_three_approved(self):
        self.assertEqual([(i["object_id"], i["question"]) for i in self.items if i["opening"]], OPENINGS)

    def test_root_anchor_problem_questions_are_never_offered_after_an_answer(self):
        for i in self.items:
            if i["object_id"] in NOT_AFTER_ANSWER:
                self.assertFalse(i["navigable_after_answer"], i["object_id"])
                self.assertFalse(i["opening"], i["object_id"])
        for i in self.items:
            if i["navigable_after_answer"]:
                rank = i["retrieval_probe_2026_09_29"]["anchored_after_starter_rank"]
                self.assertIsNotNone(rank)
                self.assertLessEqual(rank, 3)

    def test_q9_current_wording_cannot_surface(self):
        q9 = next(i for i in self.items if i["object_id"] == "TW-OBJ-0033")
        self.assertFalse(q9["opening"] or q9["navigable_after_answer"])
        self.assertEqual(q9["source_reference_label"], "Q9")
        self.assertIn(Q9_WORDING, self.nav["blocked"]["questions"])

    def test_blocked_material_includes_nature_banking_and_the_closing_block(self):
        self.assertIn(Q24_WORDING, self.nav["blocked"]["questions"])
        self.assertIn("nature banking", self.nav["blocked"]["phrases"])
        self.assertIn("rather than life serving money", self.nav["blocked"]["phrases"])
        for i in self.items:
            if i["opening"] or i["navigable_after_answer"]:
                self.assertNotIn(i["question"], self.nav["blocked"]["questions"])
                self.assertNotIn("nature banking", i["question"].casefold())

    def test_source_labels_cover_only_known_ids(self):
        labels = json.loads(_LABELS_PATH.read_text(encoding="utf-8"))["labels"]
        self.assertEqual(set(labels), {"TW-SRC-0001", "TW-SRC-0002", "TW-SRC-0003", "TW-SRC-0004", "TW-SRC-0005"})


class SourceWordingTests(unittest.TestCase):
    SOURCE = _APP_PATH.read_text(encoding="utf-8")

    def _const(self, name):
        for node in ast.parse(self.SOURCE).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
                return ast.literal_eval(node.value)
        raise AssertionError(name)

    def test_loading_welcome_and_clarify_texts_are_natural(self):
        for name in ("LOADING_TEXT", "WELCOME_TEXT", "CLARIFY_TEXT"):
            self.assertNotIn("evidence", self._const(name).casefold(), name)

    def test_no_evidence_heading_remains(self):
        self.assertNotIn('f"Evidence (', self.SOURCE)
        self.assertEqual(self._const("SOURCES_HEADING"), "Sources")
        self.assertEqual(self._const("ABOUT_HEADING"), "About this answer")


@mock.patch.dict("os.environ", {pc._BASE_URL_ENV_VAR: _BASE_URL})
class AppSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.answers = []
        self.create_session = mock.patch.object(pc.PilotClient, "create_session", return_value="s-1").start()
        self.run_turn = mock.patch.object(pc.PilotClient, "run_turn",
                                          side_effect=lambda sid, q: self.answers.pop(0)).start()
        self.addCleanup(mock.patch.stopall)

    def _app(self):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def _ask(self, at, question):
        at.chat_input[0].set_value(question).run()
        at.run()  # settle: AppTest keeps pre-rerun elements until the next run
        self.assertFalse(at.exception, at.exception)
        return at

    def _suggestions(self, at):
        return [b.label for b in at.button if (b.key or "").startswith("suggest-")]

    # --- A. UI ---------------------------------------------------------- #
    def test_main_surface_is_natural_and_sections_are_collapsed(self):
        self.answers = [_answer(evidence=[_row("TW-OBJ-0036"), _row("TW-OBJ-0021", source="TW-SRC-0002", page=3)])]
        at = self._ask(self._app(), "What is ION and how does it work?")
        bubble = at.chat_message[1]
        surface = "\n".join(_surface_texts(bubble)).casefold()
        self.assertIn("a calm, natural answer.", surface)
        for word in AUDIT_WORDS + ("presented in the voice", "open points", "implementation is not yet specified"):
            self.assertNotIn(word, surface)
        self.assertEqual([(e.label, e.proto.expanded) for e in at.expander],
                         [("Sources (2)", False), ("About this answer", False)])

    def test_about_holds_every_disclosure_verbatim(self):
        self.answers = [_answer(evidence=[_row("TW-OBJ-0036", claim="ION can sit alongside existing money.")],
                                uncertainty=("First open point.", "Second open point."))]
        at = self._ask(self._app(), "Q?")
        about = next(e for e in at.expander if e.label == "About this answer")
        texts = _expander_texts(about)
        self.assertIn(_COMPOSED_LABEL, texts)
        self.assertIn(_DISCLAIMER, texts)
        self.assertIn("**Open points**", texts)
        self.assertIn("- First open point.\n- Second open point.", texts)
        self.assertTrue(any("ION can sit alongside existing money." in t for t in texts))

    def test_sources_keep_every_excerpt_with_readable_names(self):
        rows = [_row("TW-OBJ-0047", page=4), _row("TW-OBJ-0033", page=2),
                {"document_id": "broken_money::pall::c12", "chunk_id": "broken_money::pall::c12",
                 "source": "broken_money", "title": "broken_money", "page": 12, "excerpt": "Book excerpt."}]
        self.answers = [_answer(evidence=rows)]
        at = self._ask(self._app(), "Q?")
        texts = _expander_texts(next(e for e in at.expander if e.label.startswith("Sources")))
        for r in rows:
            self.assertIn(r["excerpt"], texts)
        joined = "\n".join(texts)
        self.assertIn("The Works — 27 questions about money, nature and the next economic system", joined)
        self.assertIn("Q23 · What makes ION a wavelet?", joined)
        self.assertIn("· Q9", joined)
        self.assertNotIn(Q9_WORDING, joined.replace("Excerpt of TW-OBJ-0033.", ""))
        self.assertIn("**broken_money** · p. 12", joined)

    def test_fallback_keeps_uncertainty_visible_on_the_surface(self):
        self.answers = [_answer(status="FALLBACK", uncertainty=("Open A.", "Open B."))]
        at = self._ask(self._app(), "Q?")
        surface = _surface_texts(at.chat_message[1])
        self.assertIn("Still open: Open A. · Open B.", surface)
        about = _expander_texts(next(e for e in at.expander if e.label == "About this answer"))
        self.assertIn("Shown in standard form.", about)
        self.assertIn("- Open A.\n- Open B.", about)

    def test_composed_answer_has_no_uncertainty_block_on_the_surface(self):
        self.answers = [_answer(uncertainty=("Open A.",))]
        at = self._ask(self._app(), "Q?")
        self.assertFalse([t for t in _surface_texts(at.chat_message[1]) if "Open A." in t])

    # --- B. Opening navigation ----------------------------------------- #
    # PC1 (design v2.1 O-3): the opening is STARTER ONLY; the v0.3 Q12/Q13/Q23
    # entry buttons are not carried over.
    def test_opening_is_the_starter_only(self):
        at = self._app()
        buttons = [(b.key, b.label) for b in at.button if (b.key or "").startswith(("starter-", "opening-"))]
        self.assertEqual(buttons, [("starter-what-is-ion", "What is ION and how does it work?")])

    def test_opening_uses_the_normal_submit_path_and_session(self):
        self.answers = [_answer(), _answer()]
        at = self._app()
        next(b for b in at.button if b.key == "starter-what-is-ion").click().run()
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(self.run_turn.call_args_list, [mock.call("s-1", "What is ION and how does it work?")])
        users = [m["content"] for m in at.session_state.messages if m["kind"] == "user"]
        self.assertEqual(users, ["What is ION and how does it work?"])
        self._ask(at, "Tell me more.")
        self.create_session.assert_called_once()
        self.assertEqual(self.run_turn.call_args_list[-1], mock.call("s-1", "Tell me more."))
        self.assertFalse([b for b in at.button if (b.key or "").startswith(("starter-", "opening-"))])

    # --- C. Works navigation -------------------------------------------- #
    def test_works_questions_follow_the_answer_sources(self):
        self.answers = [_answer(evidence=[_row("TW-OBJ-0036"), _row("TW-OBJ-0046")], suggestions=("Composer one?", "Composer two?"))]
        at = self._ask(self._app(), "What is ION and how does it work?")
        self.assertEqual(self._suggestions(at),
                         ["How does ION relate to money?", "What problem is ION trying to resolve?", "Composer one?"])

    def test_root_anchor_problem_and_q9_items_are_never_offered(self):
        rows = [_row(o) for o in ("TW-OBJ-0040", "TW-OBJ-0041", "TW-OBJ-0051", "TW-OBJ-0033", "TW-OBJ-0025")]
        self.answers = [_answer(evidence=rows, suggestions=())]
        at = self._ask(self._app(), "Q?")
        offered = self._suggestions(at)
        nav = {i["object_id"]: i["question"] for i in _nav()["items"]}
        for oid in NOT_AFTER_ANSWER | {"TW-OBJ-0025"}:
            self.assertNotIn(nav[oid], offered)
        self.assertNotIn(Q9_WORDING, offered)
        self.assertLessEqual(len(offered), 2)

    def test_held_and_nature_banking_suggestions_never_surface(self):
        held = ("What is the digital euro?", Q24_WORDING, "Does money serve life, rather than life serving money?",
                "what changed after 1971?", Q9_WORDING)
        self.answers = [_answer(suggestions=held + ("A fine question?",))]
        at = self._ask(self._app(), "Q?")
        self.assertEqual(self._suggestions(at), ["A fine question?"])

    def test_at_most_three_and_already_asked_questions_are_skipped(self):
        self.answers = [_answer(evidence=[_row("TW-OBJ-0037"), _row("TW-OBJ-0047")],
                                suggestions=("One?", "Two?", "Three?"))]
        at = self._ask(self._app(), "What problem is ION trying to resolve?")
        offered = self._suggestions(at)
        self.assertLessEqual(len(offered), 3)
        self.assertNotIn("What problem is ION trying to resolve?", offered)
        works = [q for q in offered if q in {i["question"] for i in _nav()["items"]}]
        self.assertLessEqual(len(works), 2)

    def test_book_only_answer_gets_no_works_questions(self):
        self.answers = [_answer(evidence=[{"document_id": "kybalion::p81::c0", "source": "kybalion", "title": "kybalion",
                                           "page": 81, "excerpt": "x"}], suggestions=())]
        at = self._ask(self._app(), "Q?")
        self.assertEqual(self._suggestions(at), [])

    def test_navigation_click_is_an_ordinary_question(self):
        self.answers = [_answer(evidence=[_row("TW-OBJ-0036")], suggestions=()), _answer()]
        at = self._ask(self._app(), "What is ION and how does it work?")
        next(b for b in at.button if b.label == "What problem is ION trying to resolve?").click().run()
        at.run()
        self.assertEqual(self.run_turn.call_args_list[-1], mock.call("s-1", "What problem is ION trying to resolve?"))
        self.create_session.assert_called_once()


if __name__ == "__main__":
    unittest.main()
