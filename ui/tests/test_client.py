"""Tests for ui/client.py's stream-to-POST fallback (I3).

Stdlib only (unittest + unittest.mock) — no new dependency, no network.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import client  # noqa: E402  (path insert above must run first)


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, raise_exc=None):
        self.status_code = status_code
        self._json_body = {} if json_body is None else json_body
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc

    def json(self):
        return self._json_body

    def iter_lines(self, decode_unicode=True):
        return iter(())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class StreamAskFallbackTests(unittest.TestCase):
    def test_stream_404_makes_exactly_one_stream_and_one_post_call(self):
        stream_resp = _FakeResponse(status_code=404)
        post_resp = _FakeResponse(status_code=200, json_body={"primary_answer": "ok"})
        with mock.patch.object(client.requests, "get", return_value=stream_resp) as get_mock, \
             mock.patch.object(client.requests, "post", return_value=post_resp) as post_mock:
            events = list(client.stream_ask("What is money?"))
        self.assertEqual(get_mock.call_count, 1)
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(len(events), 1)

    def test_fallback_yields_one_result_event_compatible_with_streamlit(self):
        stream_resp = _FakeResponse(status_code=404)
        body = {"primary_answer": "money is credit"}
        post_resp = _FakeResponse(status_code=200, json_body=body)
        with mock.patch.object(client.requests, "get", return_value=stream_resp), \
             mock.patch.object(client.requests, "post", return_value=post_resp):
            events = list(client.stream_ask("What is money?"))
        self.assertEqual(events, [("result", body)])

    def test_non_404_stream_error_propagates_without_post_fallback(self):
        error = client.requests.HTTPError("500 server error")
        stream_resp = _FakeResponse(status_code=500, raise_exc=error)
        with mock.patch.object(client.requests, "get", return_value=stream_resp), \
             mock.patch.object(client.requests, "post") as post_mock:
            with self.assertRaises(client.requests.HTTPError):
                list(client.stream_ask("What is money?"))
        post_mock.assert_not_called()

    def test_stream_connection_error_propagates_without_post_fallback(self):
        with mock.patch.object(
            client.requests, "get",
            side_effect=client.requests.ConnectionError("refused"),
        ) as get_mock, mock.patch.object(client.requests, "post") as post_mock:
            with self.assertRaises(client.requests.ConnectionError):
                list(client.stream_ask("What is money?"))
        get_mock.assert_called_once()
        post_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
