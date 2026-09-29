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


# --------------------------------------------------------------------- #
# G7: uncertainty.reported and presentation.composition_status
# --------------------------------------------------------------------- #
_APP_PATH = Path(__file__).resolve().parent.parent / "app.py"
_COMPOSED_LABEL = "Presented in the Voice of Emergence style from the verified interpretation."
_FALLBACK_LABEL = "Shown in standard form."

# Operational values a composed-turn backend response carries; none may
# ever reach AnswerTurn or the rendered page.
_OPERATIONAL_SENTINELS = (
    "gemini-3.8-flash-SENTINEL",
    "FINGERPRINT_SENTINEL_" + "f" * 40,
    "FALLBACK_PROVIDER_ERROR",
)


def _answer_body(**extra):
    body = {"kind": "answer", "primary_answer": "Money is a social technology.", "evidence": []}
    body.update(extra)
    return body


def _composed_backend_body():
    return _answer_body(
        disclaimer="composed-turn disclaimer",
        uncertainty={"reported": ["Historical origin is debated."]},
        presentation={"composition_status": "COMPOSED"},
        operational_metrics={
            "total_latency_ms": 19312.5,
            "total_estimated_cost": None,
            "providers": [{"provider": "gemini", "model": _OPERATIONAL_SENTINELS[0], "input_tokens": 5200}],
            "composition": {
                "status": _OPERATIONAL_SENTINELS[2],
                "model": _OPERATIONAL_SENTINELS[0],
                "input_tokens": 5200,
                "output_tokens": 300,
                "estimated_cost": 0.0123,
                "voe_runtime_behavioral_fingerprint_sha256": _OPERATIONAL_SENTINELS[1],
            },
        },
    )


class _TurnParsing:
    @staticmethod
    def run(body):
        resp = _FakeResponse(status_code=200, json_body=body)
        with mock.patch.dict("os.environ", {pc._BASE_URL_ENV_VAR: _BASE_URL}), \
             mock.patch.object(pc.requests, "post", return_value=resp):
            return pc.PilotClient().run_turn("sess-1", "What is money?")


class UncertaintyParsingTests(unittest.TestCase):
    def test_11_reported_uncertainty_is_parsed_verbatim(self):
        outcome = _TurnParsing.run(_answer_body(uncertainty={"reported": ["A is debated.", "B is unclear."]}))
        self.assertEqual(outcome.uncertainty, ("A is debated.", "B is unclear."))

    def test_12_non_string_entries_are_dropped(self):
        outcome = _TurnParsing.run(
            _answer_body(uncertainty={"reported": ["kept", 1, None, {"x": 1}, ["y"], True, "also kept"]})
        )
        self.assertEqual(outcome.uncertainty, ("kept", "also kept"))

    def test_13_missing_or_malformed_uncertainty_becomes_empty(self):
        shapes = {
            "missing": _answer_body(),
            "null": _answer_body(uncertainty=None),
            "list": _answer_body(uncertainty=["not", "a", "dict"]),
            "string": _answer_body(uncertainty="debated"),
            "reported_not_list": _answer_body(uncertainty={"reported": "debated"}),
            "reported_null": _answer_body(uncertainty={"reported": None}),
            "empty_dict": _answer_body(uncertainty={}),
            "mive_shape": _answer_body(uncertainty={"shared": ["x"], "per_engine": {"a": ["y"]}}),
        }
        for name, body in shapes.items():
            with self.subTest(shape=name):
                self.assertEqual(_TurnParsing.run(body).uncertainty, ())


class PresentationParsingTests(unittest.TestCase):
    def test_14_accepted_presentation_statuses(self):
        for status in ("COMPOSED", "FALLBACK"):
            with self.subTest(status=status):
                outcome = _TurnParsing.run(_answer_body(presentation={"composition_status": status}))
                self.assertEqual(outcome.presentation_status, status)

    def test_15_other_or_missing_presentation_is_none(self):
        shapes = {
            "missing": _answer_body(),
            "null": _answer_body(presentation=None),
            "string": _answer_body(presentation="COMPOSED"),
            "empty_dict": _answer_body(presentation={}),
            "lowercase": _answer_body(presentation={"composition_status": "composed"}),
            "internal_status": _answer_body(presentation={"composition_status": "FALLBACK_PROVIDER_ERROR"}),
            "padded": _answer_body(presentation={"composition_status": " COMPOSED"}),
            "non_string": _answer_body(presentation={"composition_status": 1}),
            "list": _answer_body(presentation={"composition_status": ["COMPOSED"]}),
        }
        for name, body in shapes.items():
            with self.subTest(shape=name):
                self.assertIsNone(_TurnParsing.run(body).presentation_status)


class BackwardCompatibilityAndBoundaryTests(unittest.TestCase):
    def test_16_older_backend_response_still_parses(self):
        """A pre-G7 SINGLE response: no presentation key, uncertainty present."""
        body = _answer_body(disclaimer="single-model disclaimer", uncertainty={"reported": []})
        outcome = _TurnParsing.run(body)
        self.assertEqual(outcome.primary_answer, "Money is a social technology.")
        self.assertEqual(outcome.disclaimer, "single-model disclaimer")
        self.assertEqual(outcome.uncertainty, ())
        self.assertIsNone(outcome.presentation_status)

    def test_17_answer_turn_carries_no_operational_field_or_value(self):
        outcome = _TurnParsing.run(_composed_backend_body())
        # + suggested_questions (composer v0.2): navigation only, not operational.
        self.assertEqual(
            set(outcome.__dataclass_fields__),
            {"primary_answer", "disclaimer", "evidence", "uncertainty", "presentation_status",
             "suggested_questions"},
        )
        self.assertEqual(outcome.uncertainty, ("Historical origin is debated.",))
        self.assertEqual(outcome.presentation_status, "COMPOSED")
        rendered = repr(outcome)
        for sentinel in _OPERATIONAL_SENTINELS:
            self.assertNotIn(sentinel, rendered)


class AppSourceTests(unittest.TestCase):
    SOURCE = _APP_PATH.read_text(encoding="utf-8")

    def test_18_app_uses_the_approved_wording(self):
        self.assertIn('"What remains uncertain"', self.SOURCE)
        self.assertIn(_COMPOSED_LABEL, self.SOURCE)
        self.assertIn(_FALLBACK_LABEL, self.SOURCE)

    def test_19_app_never_reads_operational_fields(self):
        for name in ("operational_metrics", "composition", "estimated_cost", "tokens", "fingerprint", "latency"):
            with self.subTest(name=name):
                self.assertNotIn(name, self.SOURCE)


try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover - streamlit is a voe/requirements.txt dependency
    AppTest = None


@unittest.skipIf(AppTest is None, "streamlit.testing is not available")
class AppRenderTests(unittest.TestCase):
    """Drives the real app.py through one turn with requests.post mocked."""

    def _render(self, answer_body):
        responses = iter([
            _FakeResponse(status_code=200, json_body={"session_id": "sess-1", "status": "ACTIVE"}),
            _FakeResponse(status_code=200, json_body=answer_body),
        ])
        with mock.patch.dict("os.environ", {pc._BASE_URL_ENV_VAR: _BASE_URL}), \
             mock.patch.object(pc.requests, "post", side_effect=lambda *a, **k: next(responses)):
            at = AppTest.from_file(str(_APP_PATH), default_timeout=30)
            at.run()
            at.chat_input[0].set_value("What is money?").run()
        self.assertFalse(at.exception)
        texts = [m.value for m in at.markdown] + [c.value for c in at.caption]
        return texts

    def test_20_composed_turn_shows_uncertainty_and_label_but_no_operational_data(self):
        texts = self._render(_composed_backend_body())
        self.assertIn("**What remains uncertain**", texts)
        self.assertIn("- Historical origin is debated.", texts)
        self.assertIn(_COMPOSED_LABEL, texts)
        self.assertNotIn(_FALLBACK_LABEL, texts)
        joined = "\n".join(texts)
        for sentinel in _OPERATIONAL_SENTINELS:
            self.assertNotIn(sentinel, joined)

    def test_21_fallback_turn_shows_the_fallback_label(self):
        texts = self._render(_answer_body(presentation={"composition_status": "FALLBACK"}))
        self.assertIn(_FALLBACK_LABEL, texts)
        self.assertNotIn(_COMPOSED_LABEL, texts)

    def test_22_older_backend_response_shows_neither_heading_nor_label(self):
        texts = self._render(_answer_body(disclaimer="single-model disclaimer", uncertainty={"reported": []}))
        self.assertIn("single-model disclaimer", texts)
        self.assertNotIn("**What remains uncertain**", texts)
        self.assertNotIn(_COMPOSED_LABEL, texts)
        self.assertNotIn(_FALLBACK_LABEL, texts)


if __name__ == "__main__":
    unittest.main()
