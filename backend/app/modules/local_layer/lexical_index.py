"""Deterministic lexical retrieval over local fragments (conforms to RetrievalPort).

Chosen over any vector abstraction on purpose (mandate §8): the point of Phase 1
is to prove the architecture, not to optimise semantic search, and a lexical index
built from stdlib alone has no code path that could reach a cloud service. There is
no client, no URL, no credential and no SDK in this module.

Scoring is IDF-weighted, length-normalised term overlap. Ties break on `fragment_id`
so ordering is total and reproducible — a rebuilt index ranks identically to the
index it replaced.

The index is derived data: deletable, and rebuildable from the registry and the
source documents alone.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ...core.models import Evidence

INDEX_FORMAT_VERSION = "1"

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class LexicalIndex:
    """An in-memory lexical index that can persist itself to a single JSON file."""

    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        self._entries: list[dict[str, Any]] = entries or []
        self._idf: dict[str, float] = {}
        self._recompute_idf()

    # -- construction --------------------------------------------------- #
    @classmethod
    def build(cls, fragments) -> "LexicalIndex":
        entries: list[dict[str, Any]] = []
        for fragment in fragments:
            counts = Counter(tokenize(fragment["content"]))
            entries.append(
                {
                    "fragment_id": fragment["fragment_id"],
                    "material_id": fragment["material_id"],
                    "title": fragment["title"],
                    "source_file": fragment["source_file"],
                    "content": fragment["content"],
                    "provenance": dict(fragment["provenance"]),
                    "term_counts": dict(counts),
                    "length": sum(counts.values()),
                }
            )
        entries.sort(key=lambda e: e["fragment_id"])
        return cls(entries)

    def _recompute_idf(self) -> None:
        n = len(self._entries)
        if n == 0:
            self._idf = {}
            return
        df: Counter[str] = Counter()
        for entry in self._entries:
            df.update(entry["term_counts"].keys())
        # smoothed idf; always positive so a term shared by every fragment still
        # contributes a little rather than silently vanishing
        self._idf = {term: math.log(1.0 + n / (1.0 + count)) + 1.0 for term, count in df.items()}

    # -- properties ----------------------------------------------------- #
    def __len__(self) -> int:
        return len(self._entries)

    @property
    def material_ids(self) -> tuple[str, ...]:
        return tuple(sorted({e["material_id"] for e in self._entries}))

    def fingerprint(self) -> str:
        """Stable digest of index content — same fragments always give the same value."""
        payload = json.dumps(
            [
                {
                    "fragment_id": e["fragment_id"],
                    "content": e["content"],
                    "provenance": e["provenance"],
                }
                for e in self._entries
            ],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    # -- persistence ---------------------------------------------------- #
    def save(self, index_path: str | Path) -> Path:
        path = Path(index_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"index_format_version": INDEX_FORMAT_VERSION, "entries": self._entries},
                sort_keys=True,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, index_path: str | Path) -> "LexicalIndex":
        raw = json.loads(Path(index_path).read_text(encoding="utf-8"))
        return cls(list(raw["entries"]))

    @staticmethod
    def delete(index_path: str | Path) -> bool:
        """Remove the persisted index. Returns whether a file was actually removed."""
        path = Path(index_path)
        if path.is_file():
            path.unlink()
            return True
        return False

    # -- retrieval (RetrievalPort) -------------------------------------- #
    def _score(self, entry: dict[str, Any], query_terms: Counter[str]) -> float:
        counts: dict[str, int] = entry["term_counts"]
        length = entry["length"] or 1
        total = 0.0
        for term, q_count in query_terms.items():
            tf = counts.get(term, 0)
            if not tf:
                continue
            total += self._idf.get(term, 1.0) * q_count * (tf / (tf + 1.0))
        return total / math.sqrt(length)

    def retrieve(self, question: str, top_k: int) -> list[Evidence]:
        """Return the best-matching fragments as Evidence, provenance attached.

        Fragments with no term in common with the question score zero and are not
        returned: a non-match is reported as absence, never as a weak match.
        """
        query_terms = Counter(tokenize(question))
        if not query_terms or not self._entries:
            return []

        scored = [
            (self._score(entry, query_terms), entry["fragment_id"], entry)
            for entry in self._entries
        ]
        scored = [row for row in scored if row[0] > 0.0]
        scored.sort(key=lambda row: (-row[0], row[1]))

        return [
            Evidence(
                document_id=entry["fragment_id"],
                source_id=entry["material_id"],
                title=entry["title"],
                content=entry["content"],
                score=float(score),
                page=None,
                chunk_id=entry["fragment_id"],
                metadata={"provenance": dict(entry["provenance"])},
            )
            for score, _fragment_id, entry in scored[: max(1, top_k)]
        ]
