"""ION / MIVE — thin Streamlit client over the FastAPI transport.

No provider calls, no MIVE/render logic here: it drives the backend's
GET /ask/stream (progress) and displays the backend's rendered result verbatim.
Run locally: streamlit run streamlit_app.py  (BACKEND_URL defaults to :8000)
"""

from __future__ import annotations

import client
import streamlit as st

STAGES = ["retrieval", "context_pack", "gemini", "openai", "mive", "answer"]

st.set_page_config(page_title="ION / MIVE", layout="wide")
st.title("ION / MIVE")
st.caption("Multi-Intelligence Validation — thin client. All reasoning runs in the backend.")

with st.sidebar:
    st.subheader("Backend")
    st.code(client.backend_url(), language="text")
    try:
        h = client.health()
        st.success(f"health: {h.get('status', 'unknown')}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"unreachable: {exc}")
    top_k = st.number_input("top_k", min_value=1, max_value=20, value=5, step=1)


def _pairs(entries: list[dict]) -> list[str]:
    out = []
    for e in entries or []:
        stmts = e.get("statements") or {}
        if stmts:
            out.append(" | ".join(f"**{k}**: {v}" for k, v in stmts.items()))
        elif "statement" in e:
            out.append(f"**{e.get('engine', '?')}**: {e['statement']}")
        else:
            out.append(str(e))
    return out


def render_result(result: dict) -> None:
    st.header("Primary answer")
    st.write(result.get("primary_answer", ""))

    mive = result.get("mive_assessment", {})
    st.header("MIVE assessment")
    st.metric("Overall status", mive.get("overall_status", "—"))

    def section(label: str, key: str, formatter=None):
        items = mive.get(key, [])
        with st.expander(f"{label} ({len(items)})", expanded=bool(items)):
            if not items:
                st.write("_none_")
            elif formatter:
                for line in formatter(items):
                    st.markdown(f"- {line}")
            else:
                st.json(items)

    section("Agreements", "agreements", _pairs)
    section("Partial agreements", "partial_agreements", _pairs)
    section("Disagreements", "disagreements", _pairs)
    section("Unique findings", "unique_findings",
            lambda items: [f"**{i.get('engine','?')}**: {i.get('statement','')}" for i in items])
    section("Weakly supported claims", "weakly_supported",
            lambda items: [f"**{i.get('engine','?')}**: {i.get('statement','')} "
                           f"({i.get('reason','')})" for i in items])

    unc = result.get("uncertainty", {})
    st.header("Uncertainty")
    shared = unc.get("shared", [])
    st.write("**Shared:** " + (", ".join(shared) if shared else "_none_"))
    per_engine = unc.get("per_engine", {})
    for engine, items in (per_engine or {}).items():
        st.write(f"**{engine}:** " + (", ".join(items) if items else "_none_"))

    st.header("Evidence")
    evidence = result.get("evidence", [])
    if not evidence:
        st.write("_no evidence linked_")
    for row in evidence:
        title = row.get("title", "")
        src = row.get("source", "")
        page = row.get("page")
        page_s = "" if page in (None, "") else f" · p{page}"
        with st.expander(f"[{row.get('document_id','?')}] {title} — {src}{page_s}"):
            st.caption(f"chunk: {row.get('chunk_id','')} · linked to: {row.get('claim_linkage','')}")
            st.write(row.get("excerpt", ""))

    st.header("Operational metrics")
    metrics = result.get("operational_metrics", {})
    providers = metrics.get("providers", [])
    cols = st.columns(max(1, len(providers)))
    for col, p in zip(cols, providers):
        with col:
            st.markdown(f"**{p.get('provider','?')}** · `{p.get('model','')}`")
            st.write(f"input tokens: {p.get('input_tokens')}")
            st.write(f"output tokens: {p.get('output_tokens')}")
            st.write(f"latency: {p.get('latency_ms')} ms")
            cost = p.get("estimated_cost")
            st.write(f"est. cost: {'—' if cost is None else f'${cost:.6f}'}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Retrieval latency", f"{metrics.get('retrieval_latency_ms','—')} ms")
    m2.metric("Total latency", f"{metrics.get('total_latency_ms','—')} ms")
    total_cost = metrics.get("total_estimated_cost")
    m3.metric("Total est. cost", "—" if total_cost is None else f"${total_cost:.6f}")

    if result.get("disclaimer"):
        st.divider()
        st.caption(result["disclaimer"])

    with st.expander("Raw result (JSON)"):
        st.json(result)


question = st.text_input("Question", value="What is money?")

if st.button("Ask", type="primary") and question.strip():
    result = None
    error = None
    with st.status("Running MIVE pipeline…", expanded=True) as status:
        seen = {s: st.empty() for s in STAGES}
        try:
            for event, data in client.stream_ask(question, top_k=int(top_k)):
                if event == "progress" and data:
                    stage, state = data.get("stage"), data.get("status")
                    if stage in seen:
                        mark = "✅" if state in ("done", "ready") else "⏳"
                        seen[stage].markdown(f"{mark} **{stage}** — {state}")
                elif event == "result":
                    result = data
                    status.update(label="Complete", state="complete")
                elif event == "error":
                    error = data
                    status.update(label="Failed", state="error")
        except Exception as exc:  # noqa: BLE001
            error = {"error_stage": "transport", "message": str(exc)}
            status.update(label="Transport error", state="error")

    if error:
        st.error(f"[{error.get('error_stage','error')}] {error.get('message','')}")
    elif result:
        render_result(result)
