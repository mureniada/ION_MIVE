"""Voice of Emergence — thin Streamlit chat client over the E4 pilot API.

No reasoning, retrieval, model, MIVE, or governance logic here: this module
only drives POST /pilot/sessions[, /turn, /close] and renders the backend's
public response fields. Run: streamlit run app.py
(VOICE_OF_EMERGENCE_API_BASE_URL is read server-side, never displayed.)
"""

from __future__ import annotations

import streamlit as st

import pilot_client as pc

LOADING_TEXT = "Considering the evidence…"
SAFE_ERROR_TEXT = "Voice of Emergence could not complete this request. Please try again."
CLARIFY_TEXT = (
    "Could you say a bit more about what you're asking? "
    "That will help find the right evidence."
)

st.set_page_config(page_title="Voice of Emergence")


def _init_state() -> None:
    st.session_state.setdefault("pilot_session_id", None)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("request_in_flight", False)
    st.session_state.setdefault("last_error", None)
    st.session_state.setdefault("pending_question", None)


_init_state()

try:
    _CLIENT = pc.PilotClient()
except pc.ConfigurationError:
    st.title("Voice of Emergence")
    st.error(SAFE_ERROR_TEXT)
    st.stop()


def _new_conversation() -> None:
    session_id = st.session_state.pilot_session_id
    if session_id:
        try:
            _CLIENT.close_session(session_id)
        except pc.PilotClientError:
            pass
    st.session_state.messages = []
    st.session_state.pilot_session_id = None
    st.session_state.request_in_flight = False
    st.session_state.pending_question = None
    st.session_state.last_error = None
    st.rerun()


def _render_evidence_item(item: dict) -> None:
    source = item.get("source") or ""
    title = item.get("title") or source or "Source"
    st.markdown(f"**Source:** {title}")

    page = item.get("page")
    reference = page if page not in (None, "") else (item.get("chunk_id") or item.get("document_id"))
    st.markdown(f"**Reference:** {reference if reference not in (None, '') else '—'}")

    st.markdown(f"**Excerpt:** {item.get('excerpt') or ''}")

    claim_linkage = item.get("claim_linkage")
    if claim_linkage:
        st.markdown(f"**Linked claim:** {claim_linkage}")
    st.divider()


def _render_message(msg: dict) -> None:
    with st.chat_message(msg["role"]):
        kind = msg["kind"]
        if kind == "user":
            st.write(msg["content"])
        elif kind == "answer":
            st.write(msg["primary_answer"])
            if msg.get("disclaimer"):
                st.caption(msg["disclaimer"])
            evidence = msg.get("evidence") or []
            if evidence:
                with st.expander(f"Evidence ({len(evidence)})"):
                    for item in evidence:
                        _render_evidence_item(item)
        elif kind == "clarify":
            st.write(CLARIFY_TEXT)
        elif kind == "error":
            st.write(SAFE_ERROR_TEXT)


def _process_turn(question: str) -> None:
    try:
        if st.session_state.pilot_session_id is None:
            st.session_state.pilot_session_id = _CLIENT.create_session()
        try:
            outcome = _CLIENT.run_turn(st.session_state.pilot_session_id, question)
        except pc.SessionNotFoundError:
            # Stale in-memory pilot session: recover exactly once.
            st.session_state.pilot_session_id = _CLIENT.create_session()
            outcome = _CLIENT.run_turn(st.session_state.pilot_session_id, question)
    except pc.PilotClientError:
        st.session_state.messages.append({"role": "assistant", "kind": "error"})
        st.session_state.last_error = SAFE_ERROR_TEXT
        return

    st.session_state.last_error = None
    if isinstance(outcome, pc.ClarifyTurn):
        st.session_state.messages.append({"role": "assistant", "kind": "clarify"})
    else:
        st.session_state.messages.append({
            "role": "assistant",
            "kind": "answer",
            "primary_answer": outcome.primary_answer,
            "disclaimer": outcome.disclaimer,
            "evidence": list(outcome.evidence),
        })


title_col, action_col = st.columns([5, 1])
with title_col:
    st.title("Voice of Emergence")
with action_col:
    if st.button("New conversation", disabled=st.session_state.request_in_flight):
        _new_conversation()

for msg in st.session_state.messages:
    _render_message(msg)

prompt = st.chat_input("Ask a question", disabled=st.session_state.request_in_flight)

if prompt and not st.session_state.request_in_flight:
    st.session_state.messages.append({"role": "user", "kind": "user", "content": prompt})
    st.session_state.pending_question = prompt
    st.session_state.request_in_flight = True
    st.rerun()

if st.session_state.request_in_flight and st.session_state.pending_question:
    with st.chat_message("assistant"):
        with st.spinner(LOADING_TEXT):
            try:
                _process_turn(st.session_state.pending_question)
            finally:
                st.session_state.pending_question = None
                st.session_state.request_in_flight = False
    st.rerun()
