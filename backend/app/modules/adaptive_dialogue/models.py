"""Adaptive Dialogue Decision Engine vocabulary (TASK 23 v0.1).

Frozen by `docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`. This module states
the pure, unwired, deterministic decision vocabulary for one dialogue turn: what
the engine may be asked (`DialogueTurnInput`) and what it may answer
(`DialogueDecision`). It implements no rule, no runtime wiring, and no session,
evidence, or model-output authority.

Structural absence (OD23-05, OD23-06). There is deliberately no field anywhere
in this module for `session_id`, `turn_ordinal`, a `Session` or
`SessionTurnEntry` reference, a `TurnRecord` reference, session history,
evidence identity, evidence content, retrieved candidates, a
`GovernedEvidenceSet`, a `ModelContext`, prior assistant output, a conversation
transcript, prior model output, provider output, a `DialogueProfile`, or
Content Pack content — not nullable, not optional, simply absent. There is
also no `DialogueState` type anywhere in this module.

This module imports the standard library only (`dataclasses`, `enum`). No
Core, orchestrator, session, turn_record, Model Context, model_gateway,
renderer, retrieval, provider, container, or transport entry point is
reachable from here, and nothing here can reach back into any of them.

No value in this module is derived from a wall clock, a UUID, or a random
source, and no instance identifier is minted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AdaptiveDialogueError(Exception):
    """Base of the Adaptive Dialogue error hierarchy (frozen contract §4.6).

    Distinct from any other module-local error in this repository: it
    introduces no transport stage and no mapping onto the core error
    taxonomy, because this module is unwired (OD23-01).
    """


class DialogueInputError(AdaptiveDialogueError):
    """Raised when a `DialogueTurnInput` cannot be constructed as contracted."""


class DialogueDecisionError(AdaptiveDialogueError):
    """Raised when a `DialogueDecision` cannot be constructed as contracted."""


class DialogueDecisionType(str, Enum):
    """The closed v0.1 decision vocabulary. Exactly two members exist.

    `PROCEED` means the dialogue layer has no clarification objection to
    handing the current request to the next application/runtime owner — it
    does not mean retrieve evidence, authorize retrieval, admit evidence,
    invoke Core, invoke a provider, or answer the question.

    `CLARIFY` means the current dialogue input does not satisfy a frozen
    deterministic dialogue-clarity rule — it does not mean `TurnRecord`
    closure, a session state transition, `WAITING_FOR_USER`, rendering, or
    sending text to the user. `CLARIFY` is declared vocabulary here, but see
    `DialogueDecision`'s pairing invariant for why it is implementation-
    unreachable in v0.1: no deterministic CLARIFY rule is authorized yet.

    Membership is closed. An unsupported or unknown value fails closed
    rather than being coerced to either member.
    """

    PROCEED = "PROCEED"
    CLARIFY = "CLARIFY"


class DialogueReasonCode(str, Enum):
    """The closed v0.1 reason-code vocabulary. Exactly one member exists.

    `NO_RULE_TRIGGERED` is the truthful code for every v0.1 evaluation,
    because v0.1 authorizes no CLARIFY rule: the engine reaches `PROCEED` by
    the ABSENCE of any triggered rule, not by evaluating and passing one. A
    future, separately authorized CLARIFY rule mints its own new closed
    member here; this module does not pre-declare a placeholder code for a
    rule that does not yet exist.
    """

    NO_RULE_TRIGGERED = "NO_RULE_TRIGGERED"


@dataclass(frozen=True, kw_only=True)
class DialogueTurnInput:
    """The complete, verbatim statement of what the engine was asked to
    evaluate for one dialogue turn.

    Exactly one field: `question`. It is input data only — never evidence,
    never a source of truth for anything beyond this one evaluation.

    `question` MUST be an actual `str` (OD23-09): a non-`str` value is
    refused outright, never coerced or converted (never `str(value)`). It
    must also be a non-empty string, and it must already satisfy STRIP
    normalization — no leading or trailing whitespace — the same convention
    the Model Context and Turn Record layers already use. This type verifies
    the convention; it never applies it, and never rewrites the question.
    """

    question: str

    def __post_init__(self) -> None:
        if not isinstance(self.question, str):
            raise DialogueInputError(
                "question must be a str, found "
                f"{type(self.question).__name__} ({self.question!r})"
            )
        if not self.question:
            raise DialogueInputError("question must be a non-empty string")
        if self.question != self.question.strip():
            raise DialogueInputError(
                "question must already be STRIP-normalized (no leading or "
                f"trailing whitespace), found {self.question!r}"
            )


@dataclass(frozen=True, kw_only=True)
class DialogueDecision:
    """The complete, closed statement of one engine evaluation's outcome.

    Exactly two fields: `decision_type` and `reason_code`. Nothing beyond
    them is part of the v0.1 result — there is deliberately no field for a
    `clarification_prompt`, a confidence, a score, an evidence id, provider
    metadata, model reasoning, chain-of-thought, free-form rationale, a
    timestamp, or any minted identifier.

    Beyond per-field membership, exactly one cross-field invariant is
    enforced: `decision_type = CLARIFY` may never pair with
    `reason_code = NO_RULE_TRIGGERED`. `NO_RULE_TRIGGERED` is definitionally
    the code for the no-rule-fired default — it states that no deterministic
    clarification rule fired, which only `PROCEED` can truthfully carry.
    This is the sole v0.1 cross-field pairing invariant required, and it is
    what makes CLARIFY's vocabulary-valid/implementation-unreachable status
    a structural property of construction, not a fact that merely happens
    to hold because no caller has constructed the invalid pair.
    """

    decision_type: DialogueDecisionType
    reason_code: DialogueReasonCode

    def __post_init__(self) -> None:
        if not isinstance(self.decision_type, DialogueDecisionType):
            raise DialogueDecisionError(
                "decision_type must be a DialogueDecisionType, found "
                f"{self.decision_type!r}"
            )
        if not isinstance(self.reason_code, DialogueReasonCode):
            raise DialogueDecisionError(
                "reason_code must be a DialogueReasonCode, found "
                f"{self.reason_code!r}"
            )
        if (
            self.decision_type is DialogueDecisionType.CLARIFY
            and self.reason_code is DialogueReasonCode.NO_RULE_TRIGGERED
        ):
            raise DialogueDecisionError(
                "CLARIFY may never pair with NO_RULE_TRIGGERED: that reason "
                "code states no deterministic rule fired, which only "
                "PROCEED can truthfully carry"
            )
