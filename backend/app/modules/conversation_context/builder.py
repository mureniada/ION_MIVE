"""Deterministic construction of a bounded Conversation Context (Phase 2, v0.1).

Pure: no I/O, no clock, no randomness, no network, no provider call, and no
summarization — a turn that no longer fits is DROPPED, never condensed.
Standard library and this package's own vocabulary only.

Two things happen here and nothing else:

- `prior_turn_from_ask_result` reads the ONE IVE report of a COMPLETED turn
  (its `abstract` and `uncertainty`) and caps each field deterministically.
  It never reads the composed or rendered answer, claims, relations, evidence
  identities or evidence content.
- `build_conversation_context` turns a session's remembered window into a
  `ConversationContext` (or `None` when there is nothing to remember),
  dropping the oldest turn while the total exceeds its cap.

`retrieval_query_for` states the one retrieval rule (RQ-A1, revised as
RQ-A1-R1): with context, the session's ROOT user question (its first
COMPLETED turn's question, capped), a newline, then the current question;
without context, the current question itself, unchanged. Prior model text
never reaches retrieval.
"""

from __future__ import annotations

from typing import Any, Iterable

from .models import (
    INTERPRETATION_CHAR_CAP,
    QUESTION_CHAR_CAP,
    TOTAL_CHAR_CAP,
    TRUNCATION_MARK,
    UNCERTAINTY_CHAR_CAP,
    UNCERTAINTY_ITEM_CAP,
    ConversationContext,
    PriorTurnContext,
    context_sha256,
    text_chars,
)


def cap_text(text: str, cap: int) -> str:
    """Strip, then cut to exactly `cap` code points with a trailing mark."""
    text = text.strip()
    if len(text) <= cap:
        return text
    return text[: cap - 1] + TRUNCATION_MARK


def prior_turn_from_ask_result(
    *, turn_id: str, question: str, ask_result: Any
) -> PriorTurnContext | None:
    """Remember one COMPLETED turn, or return None when it cannot be remembered.

    Reads `ask_result.ive_reports` only, and requires exactly one report (the
    SINGLE profile) with a non-empty `abstract`. Anything else yields None:
    the turn itself is never failed because it cannot be remembered.
    """
    reports = getattr(ask_result, "ive_reports", None)
    if not isinstance(reports, list) or len(reports) != 1:
        return None
    report = reports[0]
    if not isinstance(report, dict):
        return None
    abstract = report.get("abstract")
    if not isinstance(abstract, str) or not abstract.strip():
        return None
    if not isinstance(question, str) or not question.strip():
        return None
    if not isinstance(turn_id, str) or not turn_id:
        return None

    raw_uncertainty = report.get("uncertainty")
    items: list[str] = []
    if isinstance(raw_uncertainty, list):
        for item in raw_uncertainty:
            if len(items) == UNCERTAINTY_ITEM_CAP:
                break
            if isinstance(item, str) and item.strip():
                items.append(cap_text(item, UNCERTAINTY_CHAR_CAP))

    return PriorTurnContext(
        turn_id=turn_id,
        question=cap_text(question, QUESTION_CHAR_CAP),
        interpretation=cap_text(abstract, INTERPRETATION_CHAR_CAP),
        uncertainty=tuple(items),
    )


def root_question_for(question: str) -> str:
    """The session root (RQ-A1-R1): the normalized question, capped like any
    remembered question."""
    return cap_text(question, QUESTION_CHAR_CAP)


def build_conversation_context(
    window: Iterable[PriorTurnContext], *, root_question: str | None,
) -> ConversationContext | None:
    """The context for the next turn, oldest first, or None when empty.

    `root_question` is the session's established root; with no root there is
    no follow-up context (the turn runs exactly as a first turn).
    """
    turns = list(window)
    while turns and sum(text_chars(turn) for turn in turns) > TOTAL_CHAR_CAP:
        turns.pop(0)
    if not turns or root_question is None:
        return None
    prior_turns = tuple(turns)
    return ConversationContext(
        prior_turns=prior_turns,
        context_sha256=context_sha256(prior_turns),
        root_question=root_question,
    )


def retrieval_query_for(question: str, context: ConversationContext | None) -> str:
    if context is None:
        return question
    return context.root_question + "\n" + question
