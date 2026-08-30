"""Adaptive Dialogue Decision Engine package (TASK 23 v0.1).

Frozen by `docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`. The export list
is deliberately closed to the approved public surface only: the frozen
vocabulary types (`models.py`) plus the stateless `AdaptiveDialogueEngine`
(`engine.py`). There is no `DialogueState` export — none exists (OD23-06).
This package is UNWIRED (OD23-01): nothing in this repository imports it yet.
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
