"""Thin synchronous HTTP client for the Voice of Emergence pilot transport.

Speaks only to POST /pilot/sessions, POST /pilot/sessions/{id}/turn and
POST /pilot/sessions/{id}/close. No reasoning, retrieval, model, MIVE, or
governance logic lives here — this module only shapes HTTP requests and
classifies their outcomes into a small set of safe, presentation-ready
results and exceptions. Raw backend error text, raw response bodies, and
raw requests.Response objects never leave this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests

# The real turn has measured ~47.6s end to end; this must safely exceed that.
_SESSION_TIMEOUT = (10, 20)
_TURN_TIMEOUT = (10, 150)
_CLOSE_TIMEOUT = (10, 20)

_BASE_URL_ENV_VAR = "VOICE_OF_EMERGENCE_API_BASE_URL"

# The exact public SINGLE-profile evidence fields (renderer.py's
# `_single_evidence_section`) — "source", never "source_id".
_ALLOWED_EVIDENCE_FIELDS = (
    "document_id",
    "title",
    "source",
    "page",
    "chunk_id",
    "excerpt",
    "claim_linkage",
)


class PilotClientError(Exception):
    """A controlled, safe-to-surface client error.

    Deliberately carries no backend message, response body, or URL —
    callers must not try to extract transport/backend detail from it.
    """


class ConfigurationError(PilotClientError):
    """The backend base URL is not configured in the environment."""


class SessionNotFoundError(PilotClientError):
    """The turn's pilot session is unknown to the backend (stale session)."""


@dataclass(frozen=True)
class AnswerTurn:
    primary_answer: str = ""
    disclaimer: str | None = None
    evidence: tuple[dict, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ClarifyTurn:
    pass


def _base_url() -> str:
    base = os.environ.get(_BASE_URL_ENV_VAR, "").strip()
    if not base:
        raise ConfigurationError("backend base URL is not configured")
    return base.rstrip("/")


def _safe_json(resp: "requests.Response"):
    try:
        return resp.json()
    except ValueError:
        return None


def _normalize_evidence(raw) -> tuple[dict, ...]:
    if not isinstance(raw, list):
        return ()
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append({k: item.get(k) for k in _ALLOWED_EVIDENCE_FIELDS if k in item})
    return tuple(rows)


class PilotClient:
    """One client instance per Streamlit run. Holds no conversation state."""

    def __init__(self) -> None:
        self._base = _base_url()

    def create_session(self) -> str:
        try:
            resp = requests.post(f"{self._base}/pilot/sessions", timeout=_SESSION_TIMEOUT)
        except requests.exceptions.RequestException:
            raise PilotClientError("transport failure creating session") from None

        if resp.status_code != 200:
            raise PilotClientError("unexpected status creating session")

        body = _safe_json(resp)
        session_id = body.get("session_id") if isinstance(body, dict) else None
        if not isinstance(session_id, str) or not session_id:
            raise PilotClientError("malformed session response")
        return session_id

    def run_turn(self, session_id: str, question: str) -> AnswerTurn | ClarifyTurn:
        try:
            resp = requests.post(
                f"{self._base}/pilot/sessions/{session_id}/turn",
                json={"question": question},
                timeout=_TURN_TIMEOUT,
            )
        except requests.exceptions.RequestException:
            raise PilotClientError("transport failure running turn") from None

        if resp.status_code == 404:
            body = _safe_json(resp)
            if isinstance(body, dict) and body.get("error_stage") == "not_found":
                raise SessionNotFoundError("pilot session not found") from None
            raise PilotClientError("turn request failed")

        if resp.status_code != 200:
            raise PilotClientError("unexpected status running turn")

        body = _safe_json(resp)
        if not isinstance(body, dict):
            raise PilotClientError("malformed turn response")

        kind = body.get("kind")
        if kind == "clarify":
            return ClarifyTurn()

        if kind == "answer":
            primary_answer = body.get("primary_answer")
            if not isinstance(primary_answer, str):
                raise PilotClientError("malformed turn response")
            disclaimer = body.get("disclaimer")
            if not isinstance(disclaimer, str):
                disclaimer = None
            return AnswerTurn(
                primary_answer=primary_answer,
                disclaimer=disclaimer,
                evidence=_normalize_evidence(body.get("evidence")),
            )

        raise PilotClientError("unrecognized turn response")

    def close_session(self, session_id: str) -> None:
        try:
            resp = requests.post(
                f"{self._base}/pilot/sessions/{session_id}/close",
                timeout=_CLOSE_TIMEOUT,
            )
        except requests.exceptions.RequestException:
            raise PilotClientError("transport failure closing session") from None

        if resp.status_code != 200:
            raise PilotClientError("unexpected status closing session")
