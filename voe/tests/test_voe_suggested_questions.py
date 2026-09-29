"""Suggested next questions in the VOE client (composer contract v0.2).

pilot_client parses `presentation.suggested_questions` defensively; app.py
shows them as buttons under the LATEST answer only, never while a request is
in flight, and a click goes through the one existing `_submit` path. Streamlit
AppTest with PilotClient's HTTP methods stubbed — no network, no backend.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_VOE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_VOE_DIR))

import pilot_client as pc  # noqa: E402  (path insert above must run first)
from streamlit.testing.v1 import AppTest  # noqa: E402

_APP_PATH = _VOE_DIR / "app.py"
_BASE_URL = "https://voe-backend.example.internal"
S1 = "How does ION work in practice?"
S2 = "What are the risks of ION?"
S3 = "How does ION relate to money?"


class ParsingTests(unittest.TestCase):
    def parse(self, presentation):
        return pc._normalize_suggested_questions(presentation)

    def test_valid_list_is_kept(self):
        self.assertEqual(self.parse({"suggested_questions": [S1, S2]}), (S1, S2))

    def test_at_most_three(self):
        self.assertEqual(self.parse({"suggested_questions": [S1, S2, S3, "Four?"]}), (S1, S2, S3))

    def test_missing_or_malformed_gives_empty(self):
        for presentation in (None, "x", {}, {"suggested_questions": None},
                             {"suggested_questions": "S1"}, {"suggested_questions": {"a": 1}}):
            with self.subTest(presentation=presentation):
                self.assertEqual(self.parse(presentation), ())

    def test_non_strings_and_blanks_are_dropped(self):
        self.assertEqual(self.parse({"suggested_questions": [1, None, "  ", S1]}), (S1,))

    def test_run_turn_carries_suggestions_onto_the_answer(self):
        body = {"kind": "answer", "primary_answer": "A.", "evidence": [],
                "presentation": {"composition_status": "COMPOSED", "suggested_questions": [S1, S2]}}
        resp = mock.Mock(status_code=200, json=lambda: body)
        with mock.patch.dict("os.environ", {pc._BASE_URL_ENV_VAR: _BASE_URL}), \
                mock.patch.object(pc.requests, "post", return_value=resp):
            outcome = pc.PilotClient().run_turn("s-1", "Q?")
        self.assertEqual(outcome.suggested_questions, (S1, S2))


def _answer(n, suggestions=(S1, S2)):
    return pc.AnswerTurn(
        primary_answer=f"Answer {n}.", uncertainty=("Open point.",),
        presentation_status="COMPOSED", suggested_questions=tuple(suggestions),
    )


@mock.patch.dict("os.environ", {pc._BASE_URL_ENV_VAR: _BASE_URL})
class AppTests(unittest.TestCase):
    def setUp(self):
        self.answers = []
        self.create_session = mock.patch.object(
            pc.PilotClient, "create_session", return_value="s-1").start()
        self.run_turn = mock.patch.object(
            pc.PilotClient, "run_turn",
            side_effect=lambda sid, q: self.answers.pop(0)).start()
        self.addCleanup(mock.patch.stopall)

    def _app(self):
        at = AppTest.from_file(str(_APP_PATH), default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def _suggestion_buttons(self, at):
        return [b for b in at.button if (b.key or "").startswith("suggest-")]

    def test_buttons_render_under_the_latest_answer_only(self):
        self.answers = [_answer(1, (S1, S2)), _answer(2, (S2, S3))]
        at = self._app()
        at.chat_input[0].set_value("First question?").run()
        self.assertEqual([b.label for b in self._suggestion_buttons(at)], [S1, S2])
        self.assertTrue(all(b.key.startswith("suggest-1-") for b in self._suggestion_buttons(at)))
        at.chat_input[0].set_value("Second question?").run()
        buttons = self._suggestion_buttons(at)
        self.assertEqual([b.label for b in buttons], [S2, S3])          # older buttons gone
        self.assertTrue(all(b.key.startswith("suggest-3-") for b in buttons))

    def test_click_uses_the_normal_submit_path_in_the_same_session(self):
        self.answers = [_answer(1, (S1, S2)), _answer(2, ())]
        at = self._app()
        at.chat_input[0].set_value("First question?").run()
        self._suggestion_buttons(at)[0].click().run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(self.run_turn.call_args_list,
                         [mock.call("s-1", "First question?"), mock.call("s-1", S1)])
        self.create_session.assert_called_once()
        users = [m["content"] for m in at.session_state.messages if m["kind"] == "user"]
        self.assertEqual(users, ["First question?", S1])
        self.assertFalse(at.session_state.request_in_flight)
        self.assertEqual(self._suggestion_buttons(at), [])              # answer 2 had none

    def test_typed_input_still_works_after_suggestions(self):
        self.answers = [_answer(1, (S1, S2)), _answer(2)]
        at = self._app()
        at.chat_input[0].set_value("First question?").run()
        at.chat_input[0].set_value("Something else?").run()
        self.assertEqual(self.run_turn.call_args_list[-1], mock.call("s-1", "Something else?"))

    def test_no_buttons_while_a_request_is_in_flight(self):
        self.answers = [_answer(1, (S1, S2))]
        at = self._app()
        at.chat_input[0].set_value("First question?").run()
        self.assertEqual(len(self._suggestion_buttons(at)), 2)
        at.session_state["request_in_flight"] = True
        at.run()
        self.assertEqual(self._suggestion_buttons(at), [])

    def test_no_buttons_for_fallback_clarify_or_empty(self):
        self.answers = [pc.AnswerTurn(primary_answer="Plain.", presentation_status="FALLBACK"),
                        pc.ClarifyTurn()]
        at = self._app()
        at.chat_input[0].set_value("First question?").run()
        self.assertEqual(self._suggestion_buttons(at), [])
        at.chat_input[0].set_value("???").run()
        self.assertEqual(self._suggestion_buttons(at), [])

    def test_unclicked_suggestions_leave_no_state_behind(self):
        self.answers = [_answer(1, (S1, S2)), _answer(2, ())]
        at = self._app()
        at.chat_input[0].set_value("First question?").run()
        at.chat_input[0].set_value("Typed follow-up?").run()
        self.assertEqual([c.args[1] for c in self.run_turn.call_args_list],
                         ["First question?", "Typed follow-up?"])
        self.assertIsNone(at.session_state.pending_question)


if __name__ == "__main__":
    unittest.main()
