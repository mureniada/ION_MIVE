from __future__ import annotations

from app.modules.retrieval.chunker import chunk_text
from tests.util import raises


def test_short_text_single_chunk():
    assert chunk_text("hello world") == ["hello world"]


def test_empty_text_no_chunks():
    assert chunk_text("   ") == []


def test_long_text_is_windowed_with_overlap_and_deterministic():
    text = " ".join(f"word{i}" for i in range(400))
    a = chunk_text(text, chunk_chars=200, overlap=40)
    b = chunk_text(text, chunk_chars=200, overlap=40)
    assert a == b                      # deterministic
    assert len(a) > 1                  # windowed
    assert all(len(c) <= 200 for c in a)


def test_invalid_overlap_rejected():
    with raises(ValueError):
        chunk_text("x y z", chunk_chars=10, overlap=10)
