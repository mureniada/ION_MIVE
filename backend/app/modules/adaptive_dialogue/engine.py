"""Adaptive Dialogue Decision Engine (TASK 23 v0.1).

Frozen by `docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`. `AdaptiveDialogueEngine`
is a decision instrument, not an orchestrator: it accepts one `DialogueTurnInput`
and returns one `DialogueDecision`, and does nothing else. It is UNWIRED
(OD23-01) — it does not call `Core.ask()`, does not call `SessionController`,
does not call a provider, does not render, and does not persist anything.
Whether, and how, some future caller acts on a `DialogueDecision` is out of
scope for this module.

Pure, deterministic, model-free, and stateless between evaluations (OD23-03):
no network I/O, no filesystem I/O, no environment read, no provider call, no
retrieval call, no `Core.ask()` call, no session mutation, no persistence, no
global mutable state, no rendering, and no mutation of its input. No
timestamp, no UUID, no randomness. Identical valid inputs produce
semantically identical decisions.

No deterministic CLARIFY rule is authorized yet (frozen contract §7): this
engine returns `PROCEED`, with `reason_code = NO_RULE_TRIGGERED`, for every
valid `DialogueTurnInput`, unconditionally. It does not invent a semantic-
ambiguity threshold, a length rule, a question-mark rule, a pronoun rule, a
keyword rule, or any other heuristic. `CLARIFY` remains part of the closed
decision vocabulary but is structurally unreachable from this code path —
`DialogueDecision`'s own construction invariant forbids CLARIFY paired with
the only reason code this module ever supplies — until a future, separately
authorized rule and its own reason code are added.

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

        v0.1 law: no CLARIFY rule is authorized, so every valid
        `turn_input` — validity already enforced by `DialogueTurnInput`'s
        own construction — returns `PROCEED` with `NO_RULE_TRIGGERED`.
        """
        return DialogueDecision(
            decision_type=DialogueDecisionType.PROCEED,
            reason_code=DialogueReasonCode.NO_RULE_TRIGGERED,
        )
