"""LIVE-1 blinding support (v0.1).

Minimum data/config support for later human-blind evaluation: two answers
become a neutral X/Y pair carrying no provider/model/arm identity, plus a
provenance map kept separately so the mapping back to the real run/arm is
never exposed inside the blinded payload itself.

No GUI. A plain, file/config/CLI-compatible representation only.
"""

from __future__ import annotations

import hashlib
from typing import NamedTuple

from ...core.models import BlindedAnswer

LABELS = ("X", "Y")


class ProvenanceEntry(NamedTuple):
    run_id: str
    arm: str


def _hash_answer(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assign_blind_labels(
    answer_a: str,
    run_id_a: str,
    arm_a: str,
    answer_b: str,
    run_id_b: str,
    arm_b: str,
    *,
    label_order: tuple[str, str] = LABELS,
) -> tuple[tuple[BlindedAnswer, BlindedAnswer], dict[str, ProvenanceEntry]]:
    """Assign neutral labels to two answers.

    Returns (blinded_pair, provenance_map). `provenance_map` (label ->
    ProvenanceEntry(run_id, arm)) must be kept by the caller separately from
    the blinded pair -- nothing in `BlindedAnswer` can be traced back to
    run/arm/provider identity.
    """
    if len(set(label_order)) != 2:
        raise ValueError(f"label_order must contain exactly two distinct labels, got {label_order}")

    label_x, label_y = label_order
    blinded = (
        BlindedAnswer(label=label_x, text=answer_a, answer_hash=_hash_answer(answer_a)),
        BlindedAnswer(label=label_y, text=answer_b, answer_hash=_hash_answer(answer_b)),
    )
    provenance_map = {
        label_x: ProvenanceEntry(run_id=run_id_a, arm=arm_a),
        label_y: ProvenanceEntry(run_id=run_id_b, arm=arm_b),
    }
    return blinded, provenance_map


def resolve_provenance(label: str, provenance_map: dict[str, ProvenanceEntry]) -> ProvenanceEntry:
    """Recover the real run/arm for a blind label. Never called by anything
    that also has access to the blinded evaluation payload's own fields --
    this is the one deliberate seam where blinding is reversed, kept apart
    from the evaluator-facing objects."""
    if label not in provenance_map:
        raise KeyError(f"unknown blind label: {label!r}")
    return provenance_map[label]
