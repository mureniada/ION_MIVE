"""Entity lexical fallback — detector, matching, ordering and runtime cache.

Implements the selection policy adopted by OP-DEC-20261004-TW2-51. Pure and
deterministic: no network, no clock, no randomness, and no Qdrant client. The
adapter (`qdrant_store.QdrantRetrieval`) supplies the cache loader and
materializes selected candidates by point id; nothing here ever reaches a
vector store, so this module has no write path of any kind.

What this module does NOT do: it never interprets, admits or ranks evidence
for truth, never builds `Evidence`, and never supplies content to a model.
The runtime cache only NOMINATES point ids (CONTENT AUTHORITY != RETRIEVAL
STRUCTURE).

Phase-1 detector: an initial plus a capitalized surname in the CURRENT
question ("P. Oomen"). No surname-only, capitalized-pair or multi-token name
detection — those need a separate labeled test set and decision.

Matching. A detected entity is ACTIVE only if its exact full form (tier 1,
e.g. `P.\\s*Oomen`) occurs in the cache; an entity whose full form does not
occur yields nothing, so a stray capitalized word cannot pull in every unit
containing it. For an active entity, units match by full form (tier 1) or by
the whole-word surname (tier 2).

Ordering (TW2-51 §5 as amended by OP-DEC-20261004-TW2-52): tier 1 before tier 2,
then the retrieval-ordering role priority, then earliest occurrence, then
document_id. The role priority reads the stored
`ion_content_pack_lineage.epistemic_role` VERBATIM (sentinel
`__NO_EPISTEMIC_ROLE__` when absent) and is used ONLY to choose the limited
lexical additions: DATA_DESCRIPTION first, SOURCE_AUTHOR_CLAIM last, every
other value in between. It never states authority, never reclassifies
evidence and never describes a person (RETRIEVAL ORDER != EVIDENCE AUTHORITY;
EPISTEMIC ROLE != PERSON ROLE). No role is ever inferred from free text.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from typing import Callable, Iterable

ENTITY_LEXICAL_POLICY_ID = "OP-DEC-20261004-TW2-51"
ENTITY_LEXICAL_AMENDMENT_ID = "OP-DEC-20261004-TW2-52"

# TW2-52 §3: the fixed sentinel for a unit with no usable stored role.
NO_EPISTEMIC_ROLE = "__NO_EPISTEMIC_ROLE__"
_ROLE_FIRST = "DATA_DESCRIPTION"
_ROLE_LAST = "SOURCE_AUTHOR_CLAIM"

# An initial (one letter, not glued to a preceding word or abbreviation such as
# "U.S."), a full stop, optional whitespace, then a surname candidate. Case is
# checked in code, so the pattern stays Unicode-aware without \p classes.
_ENTITY_PATTERN = re.compile(r"(?<![\w.])([^\W\d_])\.\s*([^\W\d_][^\W\d_'\-]*)")
_LETTER_BEFORE = r"(?<![^\W\d_])"
_LETTER_AFTER = r"(?![^\W\d_])"


@dataclass(frozen=True)
class EntityTerm:
    initial: str
    surname: str

    @property
    def full_form(self) -> str:
        return f"{self.initial}. {self.surname}"


def detect_entities(question: str) -> tuple[EntityTerm, ...]:
    """Phase-1 detection over the CURRENT question only. Order-preserving, unique."""
    found: list[EntityTerm] = []
    for match in _ENTITY_PATTERN.finditer(question or ""):
        initial, surname = match.group(1), match.group(2).rstrip("-'")
        if not initial.isupper():
            continue
        if len(surname) < 2 or not surname[0].isupper():
            continue
        if not any(ch.islower() for ch in surname[1:]):
            continue
        term = EntityTerm(initial=initial, surname=surname)
        if term not in found:
            found.append(term)
    return tuple(found)


def _full_form_pattern(term: EntityTerm) -> re.Pattern[str]:
    return re.compile(
        _LETTER_BEFORE + re.escape(term.initial) + r"\.\s*" + re.escape(term.surname) + _LETTER_AFTER
    )


def _surname_pattern(term: EntityTerm) -> re.Pattern[str]:
    return re.compile(_LETTER_BEFORE + re.escape(term.surname) + _LETTER_AFTER)


def normalize_epistemic_role(payload: object) -> str:
    """TW2-52 §3: the stored role verbatim, or the sentinel. Never inferred.

    Reads `payload["ion_content_pack_lineage"]["epistemic_role"]` only. A
    non-empty string is returned exactly as stored (no trim, no case folding);
    absent lineage, absent role, a non-string or an empty string all yield
    `NO_EPISTEMIC_ROLE`. No other field — source_location, content, title,
    chunk position — is ever consulted.
    """
    lineage = payload.get("ion_content_pack_lineage") if isinstance(payload, dict) else None
    role = lineage.get("epistemic_role") if isinstance(lineage, dict) else None
    return role if isinstance(role, str) and role != "" else NO_EPISTEMIC_ROLE


def role_priority(epistemic_role: str) -> int:
    """Retrieval-ordering proxy only (TW2-52 §1): 0 first, 1 middle, 2 last."""
    if epistemic_role == _ROLE_FIRST:
        return 0
    if epistemic_role == _ROLE_LAST:
        return 2
    return 1


@dataclass(frozen=True)
class CacheEntry:
    """One point of the active collection (TW2-52 §2 projection).

    Identity, content and the stored epistemic role (or the sentinel) — the
    role is carried only to order lexical candidates, never as authority.
    """

    point_id: str
    document_id: str
    content: str
    epistemic_role: str


@dataclass(frozen=True)
class LexicalMatch:
    point_id: str
    document_id: str
    tier: int
    role_priority: int
    offset: int


def rank_matches(
    entries: Iterable[CacheEntry], terms: tuple[EntityTerm, ...]
) -> tuple[LexicalMatch, ...]:
    """Every matching unit, in the adopted deterministic order (TW2-52 §1).

    FULL-FORM GATING (TW2-52 §4): an entity whose exact full form occurs in no
    cached unit is dropped before any surname-tier expansion is attempted.
    """
    entries = tuple(entries)
    patterns = [(_full_form_pattern(t), _surname_pattern(t)) for t in terms]
    active = [
        (full, surname)
        for full, surname in patterns
        if any(full.search(e.content) for e in entries)  # full form must occur
    ]
    matches: list[LexicalMatch] = []
    for entry in entries:
        best: tuple[int, int] | None = None
        for full, surname in active:
            hit = full.search(entry.content)
            key = (1, hit.start()) if hit else None
            if key is None:
                hit = surname.search(entry.content)
                key = (2, hit.start()) if hit else None
            if key is not None and (best is None or key < best):
                best = key
        if best is not None:
            matches.append(LexicalMatch(
                entry.point_id, entry.document_id, best[0],
                role_priority(entry.epistemic_role), best[1],
            ))
    matches.sort(key=lambda m: (m.tier, m.role_priority, m.offset, m.document_id))
    return tuple(matches)


def select_matches(
    matches: tuple[LexicalMatch, ...], *, exclude_document_ids: Iterable[str], limit: int
) -> tuple[LexicalMatch, ...]:
    """Drop matches already retrieved densely, then keep at most `limit`."""
    excluded = set(exclude_document_ids)
    return tuple(m for m in matches if m.document_id not in excluded)[: max(0, limit)]


def cache_fingerprint(entries: Iterable[CacheEntry]) -> str:
    """TW2-52 §3: SHA-256 over the sorted
    (point_id, SHA-256(content), normalized_epistemic_role) tuples."""
    lines = sorted(
        (e.point_id, hashlib.sha256(e.content.encode("utf-8")).hexdigest(), e.epistemic_role)
        for e in entries
    )
    body = "".join(f"{pid}\t{sha}\t{role}\n" for pid, sha, role in lines).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


class LexicalCacheError(RuntimeError):
    """The cache could not be built or verified. Never escapes the adapter."""


@dataclass(frozen=True)
class LexicalCacheSnapshot:
    collection: str
    entries: tuple[CacheEntry, ...]
    fingerprint: str
    point_count: int


# loader() -> (point count before, entries, point count after)
CacheLoader = Callable[[], tuple[int, list[CacheEntry], int]]


class LexicalRuntimeCache:
    """RUNTIME_CACHE (TW2-51): process-local, read-only, never persisted.

    Bound to exactly one collection at construction. Built lazily on the first
    request and never rebuilt once built: a successful snapshot lives until the
    process ends. A failed build is not cached, so a later triggered turn may
    attempt the build again; no built snapshot is ever replaced.
    """

    def __init__(self, collection: str, loader: CacheLoader) -> None:
        if not isinstance(collection, str) or not collection:
            raise ValueError("a lexical runtime cache is bound to one named collection")
        self._collection = collection
        self._loader = loader
        self._snapshot: LexicalCacheSnapshot | None = None
        self._lock = threading.Lock()

    @property
    def collection(self) -> str:
        return self._collection

    def snapshot(self) -> LexicalCacheSnapshot:
        """The verified snapshot, building it once. Raises LexicalCacheError."""
        with self._lock:
            if self._snapshot is None:
                self._snapshot = self._build()
            return self._snapshot

    def _build(self) -> LexicalCacheSnapshot:
        try:
            before, entries, after = self._loader()
        except Exception as exc:
            raise LexicalCacheError(f"lexical cache load failed: {type(exc).__name__}") from exc
        entries = tuple(entries)
        if before != after:
            raise LexicalCacheError(
                f"collection point count changed during the build ({before} -> {after})"
            )
        if len(entries) != before:
            raise LexicalCacheError(
                f"scrolled {len(entries)} points but the collection reports {before}"
            )
        if len({e.point_id for e in entries}) != len(entries):
            raise LexicalCacheError("duplicate point ids in the scrolled collection")
        for e in entries:
            if (not isinstance(e, CacheEntry) or not e.point_id
                    or not isinstance(e.content, str)
                    or not isinstance(e.epistemic_role, str) or e.epistemic_role == ""):
                raise LexicalCacheError("malformed cache entry")
        return LexicalCacheSnapshot(
            collection=self._collection,
            entries=entries,
            fingerprint=cache_fingerprint(entries),
            point_count=before,
        )
