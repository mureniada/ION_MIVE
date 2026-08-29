"""Model Gateway v0.1 — the provider-neutral model EXECUTION MECHANISM boundary.

One responsibility, stated exactly: resolve ONE explicitly requested engine
identity to ONE registered engine, execute that engine ONCE against the model
input the caller supplies, and return what the engine produced, unchanged.

    THE CALLER DECIDES WHICH TARGET RUNS.
    THE GATEWAY EXECUTES THE TARGET IT WAS GIVEN.

The two are never substituted. This module holds no notion of how many targets
a turn uses, in what order they run, or what should happen when one of them
raises. It has no field, method or branch in which such a decision could be
made, defaulted or recorded, and it never picks a target of its own. Those are
caller decisions today, and a later, separately authorized policy layer's
decisions afterwards.

Deliberately absent, with nowhere in this module to enter: a default target, an
implicit first target, a target inferred from a name, repeated execution,
substitute execution, target ordering, execution-policy identity, comparison,
measurement of what an execution consumed, event reporting, prompt
construction, response normalization, and every governance, admission,
sufficiency, provenance, retrieval, session and transport concern. This module
creates no epistemic authority of any kind: it decides nothing about whether
anything is true, admitted, sufficient or authoritative, and model output
leaves it exactly as model output.

It reaches for no vendor library and names no vendor. The engines it executes
are supplied to it already constructed, by the composition root, so the whole
module stays closed against concrete engine implementations: any object that
truthfully states its own `engine_id` and exposes `run()` satisfies this
boundary, which is what makes an engine replaceable without touching Product
orchestration.

The result object is the existing canonical `IVEReport`, returned BY IDENTITY.
This module introduces no second model-result authority: it does not wrap,
copy, re-shape, re-validate or annotate what an engine produced.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...core.errors import ConfigurationError
from ...core.models import IVEReport
from ...core.ports import IVEPort

MODEL_GATEWAY_CONTRACT_ID = "ION_MODEL_GATEWAY_V0_1"
MODEL_GATEWAY_VERSION = "0.1"


class ModelGateway:
    """Resolution and single execution for one explicitly requested target.

    The registry is supplied whole at construction and copied, so the mapping
    the caller passed in can never afterwards change what this Gateway
    resolves. Every registration is checked against the engine's OWN stated
    identity: a key that disagrees with the engine behind it would let a caller
    ask for one target and silently receive another, and that is refused rather
    than reconciled.

    A registry may legitimately be empty. Requiring some number of engines here
    would be a statement about how a turn is composed, which this boundary does
    not make.
    """

    def __init__(self, engines: Mapping[str, IVEPort]) -> None:
        if not isinstance(engines, Mapping):
            raise ConfigurationError(
                "Model Gateway engines must be supplied as a mapping of engine "
                f"id to engine, found {type(engines).__name__}."
            )

        # Copied, never referenced: this is the whole of the isolation. What the
        # caller does with its own mapping afterwards is not this Gateway's
        # resolution.
        registered: dict[str, IVEPort] = {}
        for engine_id, engine in engines.items():
            if not isinstance(engine_id, str) or not engine_id:
                raise ConfigurationError(
                    "Model Gateway engine id must be a non-empty string, found "
                    f"{engine_id!r}."
                )
            # The engine's own identity, read from the engine — never assumed
            # from the key it happens to be filed under.
            declared = getattr(engine, "engine_id", None)
            if not isinstance(declared, str) or not declared:
                raise ConfigurationError(
                    f"Engine registered as {engine_id!r} does not state a "
                    "non-empty engine_id of its own."
                )
            if declared != engine_id:
                raise ConfigurationError(
                    f"Model Gateway engine id {engine_id!r} disagrees with the "
                    f"engine's own identity {declared!r}."
                )
            if not callable(getattr(engine, "run", None)):
                raise ConfigurationError(
                    f"Engine registered as {engine_id!r} does not expose a "
                    "callable run()."
                )
            registered[engine_id] = engine

        self._engines = registered

    def execute(self, engine_id: str, context_pack: "ModelContextAssembly") -> IVEReport:
        """Execute the ONE engine the caller named, once, and return its report.

        The parameter keeps its ORIGINAL v0.1 name (`context_pack`) so the
        frozen TASK 19.2 Gateway suite pins it by name unchanged; the VALUE it
        carries is now the TASK 19.3 `ModelContextAssembly`, never a
        `ContextPack` — this Gateway forwards whatever the caller supplies and
        never inspects it, so the parameter's identifier is not itself part of
        the payload contract. `ModelContextAssembly` is named ONLY in this
        string forward reference, deliberately with no import anywhere in this
        module, so this boundary stays closed against the Product module that
        defines its own payload type, exactly as it already stays closed
        against every provider SDK. The Gateway remains payload-blind either
        way: it never reads a field of what it forwards.

        An unrecognized identity is refused deterministically, before any engine
        is reached: nothing is guessed, nothing near-matches, and no engine
        stands in for the one that was asked for. The refusal is the existing
        Product `ConfigurationError`, so no new failure stage enters the runtime
        error model.

        Whatever the engine raises travels outward untouched — the same
        exception object, with its own stage, cause and traceback. Reinterpreting
        it here would restate an engine's failure in this module's words and
        destroy the stage identity the runtime already reports.
        """
        if not isinstance(engine_id, str) or engine_id not in self._engines:
            raise ConfigurationError(f"Unknown model engine id: {engine_id!r}.")
        return self._engines[engine_id].run(context_pack)
