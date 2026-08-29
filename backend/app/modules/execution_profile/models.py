"""Model Execution Profile contract vocabulary (v0.1).

An `ExecutionProfile` is a PRODUCT POLICY object. It states, for one turn,
which engines a Model Execution Profile authorizes, in what mode. It is data,
not a mechanism:

    IT DESCRIBES EXECUTION POLICY.
    IT DOES NOT EXECUTE A MODEL.

It does not resolve engines, call the Model Gateway, call a provider, call
MIVE, render a response, perform governance, build a Model Context, inspect
evidence, load an environment variable, choose a credential, estimate
pricing, emit progress, or implement retry, fallback or routing. None of
those has a field, method or branch anywhere in this module in which it
could be expressed — this module has no notion any of them exist.

This module imports the standard library only. No Model Gateway, provider
adapter, MIVE, Model Context, GovernedEvidenceSet, Core, container, Settings,
telemetry, renderer or Turn Record entry point is reachable from here, so no
execution mechanism, credential, or comparison semantic can be reached
through Product code by way of this package, and this package cannot reach
back into any of them. How a policy this module can express is actually
carried out is a later, separately authorized layer's concern (TASK 20.3),
not this contract's.

No value in this module is derived from a wall clock, a UUID, a random
source, an environment variable or the filesystem, and no instance
identifier is minted: the identity fields below are either fixed contract
literals or values the caller supplies verbatim, validated for shape only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

EXECUTION_PROFILE_CONTRACT_ID = "ION_MODEL_EXECUTION_PROFILE_V0_1"
EXECUTION_PROFILE_CONTRACT_VERSION = "0.1"


class ExecutionProfileError(ValueError):
    """Raised whenever an ExecutionProfile cannot be constructed as contracted.

    Every failure is closed. A missing, malformed, blank, whitespace-padded,
    or duplicated value raises here; none is ever silently trimmed, defaulted
    or coerced into a legal-looking value.

    This is a module-local error on purpose. It introduces no transport stage
    and no mapping onto the core error taxonomy; how a caller responds to a
    profile that fails to construct is a later wiring decision, not this
    contract's business.
    """


class ExecutionMode(str, Enum):
    """How a Model Execution Profile turn is carried out.

    Exactly one member exists at v0.1: SINGLE. Deliberately absent, with
    nowhere in this enum to enter: DUAL, VERIFY, MIVE, FALLBACK, AUTO, ROUTED,
    ADAPTIVE, or any other mode this Product does not yet implement. Declaring
    an unimplemented mode here would assert a capability the system does not
    have; a later, separately authorized phase adds a member only once its
    semantics actually exist.
    """

    SINGLE = "SINGLE"


def _shape_checked_text(value: object, what: str) -> str:
    """Require a non-empty string carrying no leading/trailing whitespace.

    Taken verbatim otherwise: nothing is trimmed, cased or rewritten. A value
    that fails either check is refused rather than repaired, so a caller can
    never observe a "corrected" identity that differs from what it supplied.
    """
    if not isinstance(value, str) or not value:
        raise ExecutionProfileError(f"{what} must be a non-empty string, found {value!r}")
    if value != value.strip():
        raise ExecutionProfileError(
            f"{what} must carry no leading/trailing whitespace, found {value!r}"
        )
    return value


@dataclass(frozen=True, kw_only=True)
class ExecutionProfile:
    """One immutable, deterministic Model Execution Profile.

    Minimum field set only. Deliberately absent, with no field to carry them:
    a comparison mode, a provider, a requested model, a retry policy, a
    fallback policy, a timeout, a generation-control surface, a system
    prompt, a pricing binding, a credential or API key, a content or dialogue
    profile, a session id, and a turn id. This object states execution-policy
    SHAPE only — nothing about how a turn will run, what it will cost, or
    which secret it uses.

    `engine_ids` names the engines this profile AUTHORIZES. It carries no
    epistemic authority: no admitted/rejected/unknown state, no evidence, no
    provenance, no confidence, no sufficiency judgement, no retrieval score,
    no content-activation decision. Whether a named engine is actually
    registered and reachable is a composition/runtime concern this contract
    does not check — it validates policy shape only, never provider
    existence.

    `mode == SINGLE` requires `len(engine_ids) == 1`: a SINGLE profile that
    named more than one engine, or named none, would misstate its own mode.
    """

    profile_id: str
    profile_version: str
    mode: ExecutionMode
    engine_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _shape_checked_text(self.profile_id, "profile_id")
        _shape_checked_text(self.profile_version, "profile_version")

        if not isinstance(self.mode, ExecutionMode):
            raise ExecutionProfileError(
                f"mode must be a supported ExecutionMode member, found {self.mode!r}"
            )

        if not isinstance(self.engine_ids, tuple):
            raise ExecutionProfileError(
                "engine_ids must be supplied as a tuple, found "
                f"{type(self.engine_ids).__name__}"
            )
        if not self.engine_ids:
            raise ExecutionProfileError(
                "engine_ids must be non-empty: a profile that authorizes no "
                "engine describes no executable policy"
            )

        seen: set[str] = set()
        for engine_id in self.engine_ids:
            _shape_checked_text(engine_id, "engine_ids entry")
            if engine_id in seen:
                raise ExecutionProfileError(
                    f"duplicate engine id in engine_ids: {engine_id!r}"
                )
            seen.add(engine_id)

        if self.mode is ExecutionMode.SINGLE and len(self.engine_ids) != 1:
            raise ExecutionProfileError(
                "SINGLE execution mode requires exactly one engine id, found "
                f"{len(self.engine_ids)}: {self.engine_ids!r}"
            )
