"""Bounded Conversation Context vocabulary (Phase 2, v0.1).

A `ConversationContext` is a PRODUCT object. It states which small, structured
facts about the most recent COMPLETED turns of ONE session may be shown to the
next turn's model execution, so a follow-up question ("tell me more", "what
about the risks?") can be understood. It is not an epistemic authority and it
is never evidence:

    PRIOR CONVERSATION != EVIDENCE
    PRIOR INTERPRETATION != SOURCE AUTHORITY

Exactly four facts are remembered per prior turn, and nothing else has a field
to enter through (amendment OD22-08-A1, docs/ION_PHASE2_CONVERSATION_CONTEXT_
AMENDMENT_v1.md):

- the prior turn's `turn_id` (its COMPLETED TurnRecord identity);
- its normalized user question;
- its IVE report `abstract` — the verified interpretation, never the
  VOE-composed or rendered text;
- its IVE report `uncertainty` items.

There is deliberately no field for evidence identities, evidence content,
claims, relations, confidence, composed text, a rendered answer, a dialogue
instruction or any session identity. Every limit below is fixed (D6) and is
enforced at construction, fail closed.

This module imports the standard library only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

CONVERSATION_CONTEXT_CONTRACT_ID = "ION_CONVERSATION_CONTEXT_V0_1"
CONVERSATION_CONTEXT_VERSION = "0.1"

MAX_PRIOR_TURNS = 2
QUESTION_CHAR_CAP = 500
INTERPRETATION_CHAR_CAP = 1200
UNCERTAINTY_ITEM_CAP = 3
UNCERTAINTY_CHAR_CAP = 300
TOTAL_CHAR_CAP = 4000
TRUNCATION_MARK = "…"


class ConversationContextError(ValueError):
    """Raised whenever a Conversation Context value violates its contract."""


def _fail(message: str) -> None:
    raise ConversationContextError(message)


def _capped_text(value: object, cap: int, what: str, *, allow_empty: bool) -> str:
    if not isinstance(value, str):
        _fail(f"{what} must be a string, found {type(value).__name__}")
    if not allow_empty and not value:
        _fail(f"{what} must be a non-empty string")
    if value != value.strip():
        _fail(f"{what} must carry no leading/trailing whitespace")
    if len(value) > cap:
        _fail(f"{what} exceeds its cap of {cap} characters ({len(value)})")
    return value


def text_chars(turn: "PriorTurnContext") -> int:
    """The characters one prior turn contributes toward TOTAL_CHAR_CAP."""
    return (
        len(turn.question)
        + len(turn.interpretation)
        + sum(len(item) for item in turn.uncertainty)
    )


def canonical_context_bytes(prior_turns: tuple["PriorTurnContext", ...]) -> bytes:
    """Canonical JSON bytes of the remembered facts, oldest turn first."""
    payload = [
        {
            "turn_id": turn.turn_id,
            "question": turn.question,
            "interpretation": turn.interpretation,
            "uncertainty": list(turn.uncertainty),
        }
        for turn in prior_turns
    ]
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def context_sha256(prior_turns: tuple["PriorTurnContext", ...]) -> str:
    return hashlib.sha256(canonical_context_bytes(prior_turns)).hexdigest()


@dataclass(frozen=True, kw_only=True)
class PriorTurnContext:
    """The four remembered facts of one prior COMPLETED turn. Nothing else."""

    turn_id: str
    question: str
    interpretation: str
    uncertainty: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.turn_id, str) or not self.turn_id:
            _fail(f"turn_id must be a non-empty string, found {self.turn_id!r}")
        _capped_text(self.question, QUESTION_CHAR_CAP, "question", allow_empty=False)
        _capped_text(
            self.interpretation, INTERPRETATION_CHAR_CAP, "interpretation",
            allow_empty=False,
        )
        if not isinstance(self.uncertainty, tuple):
            _fail(
                "uncertainty must be a tuple, found "
                f"{type(self.uncertainty).__name__}"
            )
        if len(self.uncertainty) > UNCERTAINTY_ITEM_CAP:
            _fail(
                f"uncertainty exceeds its cap of {UNCERTAINTY_ITEM_CAP} items "
                f"({len(self.uncertainty)})"
            )
        for index, item in enumerate(self.uncertainty):
            _capped_text(
                item, UNCERTAINTY_CHAR_CAP, f"uncertainty[{index}]", allow_empty=False
            )


@dataclass(frozen=True, kw_only=True)
class ConversationContext:
    """One to two prior turns of ONE session, oldest first, with their hash.

    Never empty: a turn with nothing to remember carries no context at all
    (`None`), which is how the no-context path stays byte-identical to the
    pre-Phase-2 runtime.
    """

    prior_turns: tuple[PriorTurnContext, ...]
    context_sha256: str
    context_contract_id: str = CONVERSATION_CONTEXT_CONTRACT_ID
    context_version: str = CONVERSATION_CONTEXT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.prior_turns, tuple):
            _fail(
                "prior_turns must be a tuple, found "
                f"{type(self.prior_turns).__name__}"
            )
        if not 1 <= len(self.prior_turns) <= MAX_PRIOR_TURNS:
            _fail(
                f"prior_turns must hold 1..{MAX_PRIOR_TURNS} turns, found "
                f"{len(self.prior_turns)}"
            )
        for turn in self.prior_turns:
            if not isinstance(turn, PriorTurnContext):
                _fail(
                    "prior_turns must contain only PriorTurnContext values, found "
                    f"{type(turn).__name__}"
                )
        turn_ids = [turn.turn_id for turn in self.prior_turns]
        if len(set(turn_ids)) != len(turn_ids):
            _fail("prior_turns must not contain duplicate turn_ids")
        total = sum(text_chars(turn) for turn in self.prior_turns)
        if total > TOTAL_CHAR_CAP:
            _fail(f"context exceeds its total cap of {TOTAL_CHAR_CAP} characters ({total})")
        if self.context_contract_id != CONVERSATION_CONTEXT_CONTRACT_ID:
            _fail(f"unexpected context_contract_id {self.context_contract_id!r}")
        if self.context_version != CONVERSATION_CONTEXT_VERSION:
            _fail(f"unexpected context_version {self.context_version!r}")
        if self.context_sha256 != context_sha256(self.prior_turns):
            _fail("context_sha256 does not match the canonical hash of prior_turns")
