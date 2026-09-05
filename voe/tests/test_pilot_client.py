"""Tests for voe/pilot_client.py.

Stdlib only (unittest + unittest.mock) — no new dependency, no network, no
real backend, no provider calls. `requests.post` is mocked throughout.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pilot_client as pc  # noqa: E402  (path insert above must run first)

_SECRET_BACKEND_TEXT = "SECRET_INTERNAL_DIAGNOSTIC_DETAIL_DO_NOT_LEAK"
_BASE_URL = "https://voe-backend.example.internal"


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, json_raises=False, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self._json_raises = json_raises
        self.text = text

    def json(self):
        if self._json_raises:
            raise ValueError("not json")
        return self._json_body


def _with_base_url(test_method):
    return mock.patch.dict("os.environ", {pc._BASE_URL_ENV_VAR: _BASE_URL})(test_method)


class ConfigurationTests(unittest.TestCase):
    def test_missing_base_url_raises_configuration_error(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(pc.ConfigurationError):
                pc.PilotClient()


class CreateSessionTests(unittest.TestCase):
    @_with_base_url
    def test_1_create_session_success(self):
        resp = _FakeResponse(status_code=200, json_body={"session_id": "sess-1", "status": "ACTIVE"})
        with mock.patch.object(pc.requests, "post", return_value=resp) as post_mock:
            client = pc.PilotClient()
            session_id = client.create_session()
        self.assertEqual(session_id, "sess-1")
        self.assertTrue(post_mock.call_args.args[0].endswith("/pilot/sessions"))

    @_with_base_url
    def test_9a_create_session_malformed_payload_fails_closed(self):
        resp = _FakeResponse(status_code=200, json_body={"status": "ACTIVE"})  # no session_id
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError):
                client.create_session()

    @_with_base_url
    def test_10a_create_session_error_message_never_leaks(self):
        resp = _FakeResponse(status_code=500, json_body={"message": _SECRET_BACKEND_TEXT}, text=_SECRET_BACKEND_TEXT)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError) as ctx:
                client.create_session()
        self.assertNotIn(_SECRET_BACKEND_TEXT, str(ctx.exception))


class RunTurnTests(unittest.TestCase):
    @_with_base_url
    def test_2_answer_turn_success(self):
        body = {
            "kind": "answer",
            "primary_answer": "Money is a social technology.",
            "disclaimer": "single-model disclaimer",
            "evidence": [
                {
                    "document_id": "doc-1",
                    "title": "Sacred Economics",
                    "source": "sacred_economics_book_text",
                    "page": 12,
                    "chunk_id": "c1",
                    "excerpt": "an excerpt",
                    "claim_linkage": "money is credit",
                }
            ],
        }
        resp = _FakeResponse(status_code=200, json_body=body)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            outcome = client.run_turn("sess-1", "What is money?")
        self.assertIsInstance(outcome, pc.AnswerTurn)
        self.assertEqual(outcome.primary_answer, "Money is a social technology.")
        self.assertEqual(outcome.disclaimer, "single-model disclaimer")
        self.assertEqual(len(outcome.evidence), 1)
        self.assertEqual(outcome.evidence[0]["source"], "sacred_economics_book_text")
        self.assertNotIn("source_id", outcome.evidence[0])

    @_with_base_url
    def test_3_clarify_turn_success(self):
        body = {"kind": "clarify", "session_id": "sess-1", "turn_ordinal": 1, "reason_code": "AMBIGUOUS"}
        resp = _FakeResponse(status_code=200, json_body=body)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            outcome = client.run_turn("sess-1", "what about it")
        self.assertIsInstance(outcome, pc.ClarifyTurn)

    @_with_base_url
    def test_4_stale_session_404_classified_separately(self):
        body = {"status": "error", "error_stage": "not_found", "message": _SECRET_BACKEND_TEXT}
        resp = _FakeResponse(status_code=404, json_body=body)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.SessionNotFoundError) as ctx:
                client.run_turn("stale-sess", "What is money?")
        self.assertNotIn(_SECRET_BACKEND_TEXT, str(ctx.exception))

    @_with_base_url
    def test_5_representative_controlled_non_404_failure(self):
        body = {"status": "error", "error_stage": "session_closed", "message": _SECRET_BACKEND_TEXT}
        resp = _FakeResponse(status_code=409, json_body=body)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError) as ctx:
                client.run_turn("sess-1", "What is money?")
        self.assertNotIsInstance(ctx.exception, pc.SessionNotFoundError)
        self.assertNotIn(_SECRET_BACKEND_TEXT, str(ctx.exception))

    @_with_base_url
    def test_6_transport_exception(self):
        with mock.patch.object(
            pc.requests, "post", side_effect=pc.requests.exceptions.ConnectionError("refused: 10.0.0.5:8000")
        ):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError) as ctx:
                client.run_turn("sess-1", "What is money?")
        self.assertNotIn("10.0.0.5", str(ctx.exception))

    @_with_base_url
    def test_9b_malformed_answer_payload_fails_closed(self):
        body = {"kind": "answer"}  # missing primary_answer
        resp = _FakeResponse(status_code=200, json_body=body)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError):
                client.run_turn("sess-1", "What is money?")

    @_with_base_url
    def test_9c_unrecognized_kind_fails_closed(self):
        body = {"kind": "something_new", "primary_answer": "x"}
        resp = _FakeResponse(status_code=200, json_body=body)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError):
                client.run_turn("sess-1", "What is money?")

    @_with_base_url
    def test_9d_non_json_body_fails_closed(self):
        resp = _FakeResponse(status_code=200, json_raises=True)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError):
                client.run_turn("sess-1", "What is money?")


class CloseSessionTests(unittest.TestCase):
    @_with_base_url
    def test_7_close_success(self):
        resp = _FakeResponse(status_code=200, json_body={"status": "CLOSED"})
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            client.close_session("sess-1")  # must not raise

    @_with_base_url
    def test_8a_close_404_safely_containable(self):
        body = {"status": "error", "error_stage": "not_found", "message": _SECRET_BACKEND_TEXT}
        resp = _FakeResponse(status_code=404, json_body=body)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError) as ctx:
                client.close_session("sess-1")
        self.assertNotIn(_SECRET_BACKEND_TEXT, str(ctx.exception))

    @_with_base_url
    def test_8b_close_409_safely_containable(self):
        body = {"status": "error", "error_stage": "concurrent_turn", "message": _SECRET_BACKEND_TEXT}
        resp = _FakeResponse(status_code=409, json_body=body)
        with mock.patch.object(pc.requests, "post", return_value=resp):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError) as ctx:
                client.close_session("sess-1")
        self.assertNotIn(_SECRET_BACKEND_TEXT, str(ctx.exception))

    @_with_base_url
    def test_10b_close_transport_exception_never_leaks(self):
        with mock.patch.object(
            pc.requests, "post", side_effect=pc.requests.exceptions.Timeout(_SECRET_BACKEND_TEXT)
        ):
            client = pc.PilotClient()
            with self.assertRaises(pc.PilotClientError) as ctx:
                client.close_session("sess-1")
        self.assertNotIn(_SECRET_BACKEND_TEXT, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
