"""Precise, stage-specific errors.

A failure must always name the stage that produced it (docs/07 failure output,
docs/15 error model). A single-provider failure is an *incomplete* MIVE state,
never a successful result (docs/06).
"""

from __future__ import annotations

# Canonical error stages (mirror docs/15 error model).
STAGE_CONFIGURATION = "configuration"
STAGE_RETRIEVAL = "retrieval"
STAGE_CONTEXT_PACK = "context_pack"
STAGE_GEMINI = "gemini"
STAGE_OPENAI = "openai"
STAGE_NORMALIZATION = "normalization"
STAGE_MIVE = "mive"

VALID_STAGES = frozenset(
    {
        STAGE_CONFIGURATION,
        STAGE_RETRIEVAL,
        STAGE_CONTEXT_PACK,
        STAGE_GEMINI,
        STAGE_OPENAI,
        STAGE_NORMALIZATION,
        STAGE_MIVE,
    }
)


class IonError(Exception):
    """Base class. Carries the stage so the API/renderer can report precisely."""

    stage: str = "unknown"

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        if stage is not None:
            self.stage = stage
        self.message = message


class ConfigurationError(IonError):
    stage = STAGE_CONFIGURATION


class RetrievalError(IonError):
    stage = STAGE_RETRIEVAL


class ContextPackError(IonError):
    stage = STAGE_CONTEXT_PACK


class ProviderError(IonError):
    """A provider path failed. `stage` is 'gemini' or 'openai'."""


class NormalizationError(IonError):
    stage = STAGE_NORMALIZATION


class MiveError(IonError):
    stage = STAGE_MIVE
