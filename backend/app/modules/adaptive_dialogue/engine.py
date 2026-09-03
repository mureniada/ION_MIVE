"""Adaptive Dialogue Decision Engine (TASK 23 v0.1).

Frozen by `docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`. `AdaptiveDialogueEngine`
is a decision instrument, not an orchestrator: it accepts one `DialogueTurnInput`
and returns one `DialogueDecision`, and does nothing else. It does not call
`Core.ask()`, does not call `SessionController`, does not call a provider, does
not render, and does not persist anything. As of E1 a caller exists —
`SessionController.run_turn()` evaluates this engine once per eligible
interaction — but the direction of that dependency is one-way: the caller
imports this module, and nothing here imports, names, or can reach the caller.
How that caller acts on a `DialogueDecision` remains entirely out of scope for
this module.

Pure, deterministic, model-free, and stateless between evaluations (OD23-03):
no network I/O, no filesystem I/O, no environment read, no provider call, no
retrieval call, no `Core.ask()` call, no session mutation, no persistence, no
global mutable state, no rendering, and no mutation of its input. No
timestamp, no UUID, no randomness. Identical valid inputs produce
semantically identical decisions.

Exactly ONE deterministic CLARIFY rule is authorized (E1), and it is the only
condition under which this engine returns anything but `PROCEED`: a question
carrying no alphanumeric character at all states nothing answerable, and
yields `CLARIFY` with `reason_code = QUESTION_HAS_NO_ANSWERABLE_CONTENT`.
Every other valid `DialogueTurnInput` yields `PROCEED` with
`NO_RULE_TRIGGERED`.

That rule is deliberately STRUCTURAL, not interpretive. This engine still
does not invent a semantic-ambiguity threshold, a length rule, a
question-mark rule, a pronoun rule, a keyword rule, a domain rule, or any
other heuristic about what a question MEANS: it observes only whether the
question string contains any alphanumeric character. Adding a second rule,
or widening this one, requires its own separate authorization and its own
reason code.

This module imports the standard library and this package's own vocabulary
only. No Core, session, turn_record, Model Context, model_gateway, renderer,
retrieval, provider, container, or transport entry point is reachable from
here.
"""

from __future__ import annotations

from .models import (
    DialogueDecision,
    DialogueDecisionType,
    DialogueReasonCode,
    DialogueTurnInput,
)


class AdaptiveDialogueEngine:
    """The sole crossing point between `DialogueTurnInput` and `DialogueDecision`.

    Stateless: this class carries no instance state, and `evaluate` reads
    only the `turn_input` it is given. No constructor argument exists —
    construction takes nothing, because this engine has no dependency on
    any runtime object.
    """

    def evaluate(self, turn_input: DialogueTurnInput) -> DialogueDecision:
        """Evaluate one dialogue turn.

        Exactly one rule is authorized. Its predicate is total and
        deterministic over the single field `DialogueTurnInput.question`
        (validity — `str`, non-empty, STRIP-normalized — already enforced by
        `DialogueTurnInput`'s own construction):

            no alphanumeric character in `question`
                -> CLARIFY / QUESTION_HAS_NO_ANSWERABLE_CONTENT
            otherwise
                -> PROCEED / NO_RULE_TRIGGERED

        `str.isalnum()` is evaluated per character, so the check reads the
        question only as a sequence of characters. It never lowercases,
        tokenizes, stems, parses, or otherwise interprets it, and never
        mutates the input.
        """
        if not any(character.isalnum() for character in turn_input.question):
            return DialogueDecision(
                decision_type=DialogueDecisionType.CLARIFY,
                reason_code=DialogueReasonCode.QUESTION_HAS_NO_ANSWERABLE_CONTENT,
            )
        return DialogueDecision(
            decision_type=DialogueDecisionType.PROCEED,
            reason_code=DialogueReasonCode.NO_RULE_TRIGGERED,
        )
