"""TASK 23.3B test: the Adaptive Dialogue model layer (decision vocabulary).

Scope is deliberately narrow: this proves ONLY `app/modules/adaptive_dialogue/
models.py` — construction, immutability, and the invariants
`DialogueTurnInput.__post_init__`/`DialogueDecision.__post_init__` enforce,
against the frozen contract `docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md`.
No `AdaptiveDialogueEngine` behavior is exercised here (see
`test_adaptive_dialogue_engine_v0_1.py`), no Core, no SessionController, and
no provider SDK is reachable from anything below.

Absence checks are structural, never textual against source: this module
interrogates the parsed import graph and dataclass field sets, matching the
convention `test_model_context_builder_v0_1.py` already establishes.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from app.modules.adaptive_dialogue import (
    AdaptiveDialogueError,
    DialogueDecision,
    DialogueDecisionError,
    DialogueDecisionType,
    DialogueInputError,
    DialogueReasonCode,
    DialogueTurnInput,
)
import app.modules.adaptive_dialogue as adaptive_dialogue_pkg
import app.modules.adaptive_dialogue.models as adaptive_dialogue_models

_MODELS_PATH = Path(adaptive_dialogue_models.__file__)

# The only modules this package's models layer may import from.
_ALLOWED_ABSOLUTE_IMPORTS = {"__future__", "dataclasses", "enum"}


def _imports(path: Path):
    """Every module named by an Import/ImportFrom node in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute, relative = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative.add((node.level, node.module or ""))
            else:
                absolute.add(node.module or "")
    return absolute, relative


# --------------------------------------------------------------------- #
# 1. DialogueDecisionType has exactly PROCEED and CLARIFY
# --------------------------------------------------------------------- #
def test_dialogue_decision_type_exact_members():
    assert {m.value for m in DialogueDecisionType} == {"PROCEED", "CLARIFY"}
    assert len(DialogueDecisionType) == 2


# --------------------------------------------------------------------- #
# 2. DialogueReasonCode has exactly NO_RULE_TRIGGERED
# --------------------------------------------------------------------- #
def test_dialogue_reason_code_exact_members():
    assert {m.value for m in DialogueReasonCode} == {
        "NO_RULE_TRIGGERED",
        "QUESTION_HAS_NO_ANSWERABLE_CONTENT",
    }
    assert len(DialogueReasonCode) == 2


# --------------------------------------------------------------------- #
# 3. DialogueTurnInput has exactly one field: question
# --------------------------------------------------------------------- #
def test_dialogue_turn_input_field_set():
    names = {f.name for f in dataclasses.fields(DialogueTurnInput)}
    assert names == {"question"}


# --------------------------------------------------------------------- #
# 4. DialogueTurnInput is frozen
# --------------------------------------------------------------------- #
def test_dialogue_turn_input_is_frozen():
    turn_input = DialogueTurnInput(question="What is the capital of France?")
    with pytest.raises(dataclasses.FrozenInstanceError):
        turn_input.question = "changed"  # type: ignore[misc]


# --------------------------------------------------------------------- #
# 5. valid question construction is stored verbatim
# --------------------------------------------------------------------- #
def test_dialogue_turn_input_valid_construction():
    turn_input = DialogueTurnInput(question="What is the capital of France?")
    assert turn_input.question == "What is the capital of France?"


# --------------------------------------------------------------------- #
# 6. empty question rejected
# --------------------------------------------------------------------- #
def test_dialogue_turn_input_rejects_empty_question():
    with pytest.raises(DialogueInputError):
        DialogueTurnInput(question="")


# --------------------------------------------------------------------- #
# 7. whitespace-only question rejected
# --------------------------------------------------------------------- #
def test_dialogue_turn_input_rejects_whitespace_only_question():
    with pytest.raises(DialogueInputError):
        DialogueTurnInput(question="   ")


# --------------------------------------------------------------------- #
# 8. non-str question rejected outright (OD23-09): no coercion
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_question", [None, 1, 3.14, [], {}, ("x",)])
def test_dialogue_turn_input_rejects_non_string_question(bad_question):
    with pytest.raises(DialogueInputError):
        DialogueTurnInput(question=bad_question)  # type: ignore[arg-type]


# --------------------------------------------------------------------- #
# 8b. leading/trailing whitespace on non-empty content rejected
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_question", [" What is X?", "What is X? ", " What is X? ", "\tWhat is X?"]
)
def test_dialogue_turn_input_rejects_unstripped_question(bad_question):
    with pytest.raises(DialogueInputError):
        DialogueTurnInput(question=bad_question)


# --------------------------------------------------------------------- #
# 9. DialogueDecision has exactly two fields
# --------------------------------------------------------------------- #
def test_dialogue_decision_field_set():
    names = {f.name for f in dataclasses.fields(DialogueDecision)}
    assert names == {"decision_type", "reason_code"}


# --------------------------------------------------------------------- #
# 10. DialogueDecision is frozen
# --------------------------------------------------------------------- #
def test_dialogue_decision_is_frozen():
    decision = DialogueDecision(
        decision_type=DialogueDecisionType.PROCEED,
        reason_code=DialogueReasonCode.NO_RULE_TRIGGERED,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.decision_type = DialogueDecisionType.CLARIFY  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.reason_code = DialogueReasonCode.NO_RULE_TRIGGERED  # type: ignore[misc]


# --------------------------------------------------------------------- #
# 11. PROCEED + NO_RULE_TRIGGERED is valid
# --------------------------------------------------------------------- #
def test_dialogue_decision_proceed_no_rule_triggered_valid():
    decision = DialogueDecision(
        decision_type=DialogueDecisionType.PROCEED,
        reason_code=DialogueReasonCode.NO_RULE_TRIGGERED,
    )
    assert decision.decision_type is DialogueDecisionType.PROCEED
    assert decision.reason_code is DialogueReasonCode.NO_RULE_TRIGGERED


# --------------------------------------------------------------------- #
# 12. CLARIFY + NO_RULE_TRIGGERED is invalid: fails closed
# --------------------------------------------------------------------- #
def test_dialogue_decision_clarify_no_rule_triggered_rejected():
    with pytest.raises(DialogueDecisionError):
        DialogueDecision(
            decision_type=DialogueDecisionType.CLARIFY,
            reason_code=DialogueReasonCode.NO_RULE_TRIGGERED,
        )


# --------------------------------------------------------------------- #
# 12b. unsupported decision_type / reason_code values fail closed
# --------------------------------------------------------------------- #
def test_dialogue_decision_rejects_non_member_decision_type():
    with pytest.raises(DialogueDecisionError):
        DialogueDecision(
            decision_type="PROCEED",  # raw str, not a genuine enum member
            reason_code=DialogueReasonCode.NO_RULE_TRIGGERED,
        )


def test_dialogue_decision_rejects_non_member_reason_code():
    with pytest.raises(DialogueDecisionError):
        DialogueDecision(
            decision_type=DialogueDecisionType.PROCEED,
            reason_code="NO_RULE_TRIGGERED",  # raw str, not a genuine enum member
        )


# --------------------------------------------------------------------- #
# 13. no DialogueState exists anywhere in the package
# --------------------------------------------------------------------- #
def test_no_dialogue_state_export():
    assert "DialogueState" not in dir(adaptive_dialogue_pkg)
    assert "DialogueState" not in dir(adaptive_dialogue_models)
    assert not hasattr(adaptive_dialogue_pkg, "DialogueState")


# --------------------------------------------------------------------- #
# error hierarchy shape
# --------------------------------------------------------------------- #
def test_error_hierarchy_shape():
    assert issubclass(DialogueInputError, AdaptiveDialogueError)
    assert issubclass(DialogueDecisionError, AdaptiveDialogueError)
    assert issubclass(AdaptiveDialogueError, Exception)


# --------------------------------------------------------------------- #
# structural import-boundary check for models.py
# --------------------------------------------------------------------- #
def test_models_module_imports_only_allowed_names():
    absolute, relative = _imports(_MODELS_PATH)
    assert absolute <= _ALLOWED_ABSOLUTE_IMPORTS
    assert relative == set()
