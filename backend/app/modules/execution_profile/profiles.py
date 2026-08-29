"""The one canonical Model Execution Profile v0.1 defines: STANDARD_GEMINI.

This module states, and states only, that STANDARD_GEMINI is a SINGLE
execution profile whose requested engine identity is "gemini". It does NOT
claim that Core uses it, that Gemini actually executes, that OpenAI is
skipped at runtime, that MIVE is bypassed, that the renderer supports SINGLE,
that Turn Record supports SINGLE, that configuration selects it, or that a
pilot deployment can run without OpenAI credentials. Every one of those is a
runtime-wiring claim that belongs to a later, separately authorized phase
(TASK 20.3) — none of them is true merely because this module exists.

`STANDARD_GEMINI` is a plain, pre-constructed `ExecutionProfile` instance: no
factory, no environment lookup, no registry, and no hidden behaviour. TASK
20.2 defines exactly this one profile; a general profile registry or
resolver is explicitly out of this phase's scope.
"""

from __future__ import annotations

from .models import ExecutionMode, ExecutionProfile

STANDARD_GEMINI = ExecutionProfile(
    profile_id="STANDARD_GEMINI",
    profile_version="0.1",
    mode=ExecutionMode.SINGLE,
    engine_ids=("gemini",),
)
