"""TASK 23.3B test: the Adaptive Dialogue Decision Engine (`AdaptiveDialogueEngine`).

Scope is deliberately narrow: this proves ONLY `app/modules/adaptive_dialogue/
engine.py`'s `evaluate()` behavior against the frozen contract
`docs/ION_ADAPTIVE_DIALOGUE_ENGINE_CONTRACT_v1.md` — v0.1's unconditional
PROCEED/NO_RULE_TRIGGERED law, purity, determinism, and statelessness. No
Core, no SessionController, no provider SDK, and no network/filesystem
capability is reachable from anything below; this file proves that
structurally, not by convention.

Absence checks are structural, never textual against source, matching the
convention `test_model_context_builder_v0_1.py` and
`test_adaptive_dialogue_models_v0_1.py` already establish.
"""

from __future__ import annotations

import ast
import builtins
import inspect
import typing
from pathlib import Path

import pytest

from app.modules.adaptive_dialogue import (
    AdaptiveDialogueEngine,
    DialogueDecision,
    DialogueDecisionType,
    DialogueReasonCode,
    DialogueTurnInput,
)
import app.modules.adaptive_dialogue.engine as adaptive_dialogue_engine_module

_ENGINE_PATH = Path(adaptive_dialogue_engine_module.__file__)

# Everything this module's engine layer may import: the standard library
# names below, plus its own sibling `.models`.
_ALLOWED_ABSOLUTE_IMPORTS = {"__future__"}
_ALLOWED_RELATIVE_IMPORTS = {(1, "models")}

# Names a v0.1 engine must never be able to reach, structurally, from the
# adaptive_dialogue package namespace.
_FORBIDDEN_RUNTIME_NAMES = {
    "Core",
    "SessionController",
    "ModelGateway",
    "RetrievalPort",
    "CoreAdapter",
    "GovernedEvidenceSet",
    "ModelContextAssembly",
    "TurnRecord",
}


def _imports(path: Path):
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


def _question(text: str) -> DialogueTurnInput:
    return DialogueTurnInput(question=text)


# --------------------------------------------------------------------- #
# 14/15. valid input returns PROCEED / NO_RULE_TRIGGERED
# --------------------------------------------------------------------- #
def test_evaluate_valid_input_returns_proceed():
    engine = AdaptiveDialogueEngine()
    decision = engine.evaluate(_question("What is the capital of France?"))
    assert decision.decision_type is DialogueDecisionType.PROCEED


def test_evaluate_reason_code_is_no_rule_triggered():
    engine = AdaptiveDialogueEngine()
    decision = engine.evaluate(_question("What is the capital of France?"))
    assert decision.reason_code is DialogueReasonCode.NO_RULE_TRIGGERED


# --------------------------------------------------------------------- #
# 16. repeated identical evaluation gives semantically identical output
# --------------------------------------------------------------------- #
def test_evaluate_repeated_identical_input_gives_identical_output():
    engine = AdaptiveDialogueEngine()
    first = engine.evaluate(_question("What is the capital of France?"))
    second = engine.evaluate(_question("What is the capital of France?"))
    assert first == second


# --------------------------------------------------------------------- #
# 17. different valid questions all still follow the same authorized law
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "What is the capital of France?",
        "Summarize the retrieval contract.",
        "x",
        "Tell me everything about everything, right now, with no context at all.",
    ],
)
def test_evaluate_various_valid_questions_all_proceed(text):
    engine = AdaptiveDialogueEngine()
    decision = engine.evaluate(_question(text))
    assert decision.decision_type is DialogueDecisionType.PROCEED
    assert decision.reason_code is DialogueReasonCode.NO_RULE_TRIGGERED


# --------------------------------------------------------------------- #
# 18. engine never emits CLARIFY in v0.1
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "?",
        "what",
        "please clarify this for me",
        "ambiguous pronoun: it, they, that thing",
    ],
)
def test_evaluate_never_emits_clarify(text):
    engine = AdaptiveDialogueEngine()
    decision = engine.evaluate(_question(text))
    assert decision.decision_type is not DialogueDecisionType.CLARIFY


# --------------------------------------------------------------------- #
# 19. no external side effects: filesystem access during evaluate() fails
#     the test rather than passing silently
# --------------------------------------------------------------------- #
def test_evaluate_no_side_effects(monkeypatch):
    def _forbidden_open(*args, **kwargs):
        raise AssertionError("evaluate() must not perform filesystem I/O")

    monkeypatch.setattr(builtins, "open", _forbidden_open)
    engine = AdaptiveDialogueEngine()
    decision = engine.evaluate(_question("What is the capital of France?"))
    assert decision.decision_type is DialogueDecisionType.PROCEED


# --------------------------------------------------------------------- #
# 20. no state retained between evaluations
# --------------------------------------------------------------------- #
def test_engine_stateless_between_evaluations():
    engine = AdaptiveDialogueEngine()
    assert vars(engine) == {}
    engine.evaluate(_question("First question?"))
    assert vars(engine) == {}
    engine.evaluate(_question("A completely different second question?"))
    assert vars(engine) == {}


# --------------------------------------------------------------------- #
# 21. public interface accepts DialogueTurnInput only
# --------------------------------------------------------------------- #
def test_evaluate_signature_accepts_only_dialogue_turn_input():
    signature = inspect.signature(AdaptiveDialogueEngine.evaluate)
    params = [name for name in signature.parameters if name != "self"]
    assert params == ["turn_input"]

    # `from __future__ import annotations` (used throughout this repository)
    # makes every annotation a lazily-evaluated string at runtime, so the raw
    # `Parameter.annotation` above is the string "DialogueTurnInput", not the
    # class object. `typing.get_type_hints` resolves it against the engine
    # module's own globals back into the real class.
    hints = typing.get_type_hints(adaptive_dialogue_engine_module.AdaptiveDialogueEngine.evaluate)
    assert hints["turn_input"] is DialogueTurnInput
    assert hints["return"] is DialogueDecision


# --------------------------------------------------------------------- #
# 22. structural import-boundary check for engine.py
# --------------------------------------------------------------------- #
def test_engine_module_imports_only_allowed_names():
    absolute, relative = _imports(_ENGINE_PATH)
    assert absolute <= _ALLOWED_ABSOLUTE_IMPORTS
    assert relative <= _ALLOWED_RELATIVE_IMPORTS


# --------------------------------------------------------------------- #
# 23. no provider/retrieval/Core/session/runtime wiring reachable
# --------------------------------------------------------------------- #
def test_no_forbidden_runtime_names_reachable():
    import app.modules.adaptive_dialogue as adaptive_dialogue_pkg

    exported = set(adaptive_dialogue_pkg.__all__)
    assert exported.isdisjoint(_FORBIDDEN_RUNTIME_NAMES)
    for name in _FORBIDDEN_RUNTIME_NAMES:
        assert not hasattr(adaptive_dialogue_pkg, name)
