"""Deterministic text chunking. Pure function — unit-tested without I/O."""

from __future__ import annotations


def chunk_text(text: str, *, chunk_chars: int = 1200, overlap: int = 200) -> list[str]:
    """Split text into overlapping windows, preferring whitespace break points.

    Deterministic: same input always yields the same chunks.
    """
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be > 0")
    if overlap < 0 or overlap >= chunk_chars:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_chars")

    normalized = " ".join(text.split())
    if not normalized:
        return []
    if len(normalized) <= chunk_chars:
        return [normalized]

    chunks: list[str] = []
    start = 0
    n = len(normalized)
    step = chunk_chars - overlap
    while start < n:
        end = min(start + chunk_chars, n)
        if end < n:
            # try to break at the last space in the window for cleaner chunks
            space = normalized.rfind(" ", start + step, end)
            if space != -1 and space > start:
                end = space
        chunks.append(normalized[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]
