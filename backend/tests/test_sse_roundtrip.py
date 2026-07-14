"""SSE format round-trip — the contract the Streamlit client consumes.

No live provider calls. Verifies that frames produced by the backend's
`format_sse` parse back to the same events in order (via `parse_sse_stream`),
and that a real (mocked) pipeline stream preserves canonical progress order.
"""

from __future__ import annotations

from app.api.service import format_sse, parse_sse_stream, sse_events


def test_format_then_parse_is_identity():
    events = [
        ("progress", {"stage": "retrieval", "status": "started"}),
        ("progress", {"stage": "retrieval", "status": "done"}),
        ("result", {"primary_answer": "money is credit"}),
    ]
    text = "".join(format_sse(e, d) for e, d in events)
    parsed = list(parse_sse_stream(text.split("\n")))
    assert parsed == events


def test_mocked_pipeline_stream_preserves_progress_order():
    from tests.test_transport_service import _core  # reuse the mocked core wiring

    frames = "".join(format_sse(e, d) for e, d in sse_events(_core(), "is money credit?"))
    parsed = list(parse_sse_stream(frames.split("\n")))
    stages = [d["stage"] for e, d in parsed if e == "progress"]
    assert stages.index("retrieval") < stages.index("gemini") < stages.index("mive")
    assert parsed[-1][0] == "result"
    assert "primary_answer" in parsed[-1][1]
