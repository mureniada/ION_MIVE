"""Adaptive Dialogue Decision Engine package (TASK 23 v0.1).

Frozen by `docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`. The export list
is deliberately closed to the approved public surface only: the frozen
vocabulary types (`models.py`) plus the stateless `AdaptiveDialogueEngine`
(`engine.py`). There is no `DialogueState` export — none exists (OD23-06).

As of E1 this package is imported by `app.modules.session.controller`, which
evaluates the engine once per eligible interaction. That dependency is
strictly one-way: nothing in this package imports, names, or can reach the
session, core, turn_record, retrieval, governance, model, provider, renderer,
or transport layers.
"""

from .engine import AdaptiveDialogueEngine
from .models import (
    AdaptiveDialogueError,
    DialogueDecision,
    DialogueDecisionError,
    DialogueDecisionType,
    DialogueInputError,
    DialogueReasonCode,
    DialogueTurnInput,
)

__all__ = [
    "AdaptiveDialogueEngine",
    "AdaptiveDialogueError",
    "DialogueDecision",
    "DialogueDecisionError",
    "DialogueDecisionType",
    "DialogueInputError",
    "DialogueReasonCode",
    "DialogueTurnInput",
]
