"""Runtime configuration.

Reading this module never reads secrets or opens connections. `Settings.load()`
reads environment variables when explicitly called (at runtime, in factories).
Secret *presence* is exposed as booleans only — values are never returned or
logged (docs/11).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# The conventional spellings this project already uses for `_as_bool`
# (DEBUG and friends), reused verbatim so the accepted true/false vocabulary
# stays one vocabulary — not a second, competing convention.
_VOE_PROFILE_ENABLED_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_VOE_PROFILE_ENABLED_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


class SettingsError(ValueError):
    """Raised by `Settings.load()` for a value that must fail loudly rather
    than silently coerce.

    Currently raised only for a malformed `VOE_PROFILE_ENABLED`: this is a
    governed profile-activation switch, not an ordinary feature flag like
    `DEBUG`, and a typo in it must never be silently reinterpreted as a
    deliberate "disabled" — see `_strict_voe_profile_enabled` below.

    Module-local on purpose: mapping this onto a transport-facing readiness
    failure is a later, separately authorized composition-time concern, not
    this module's business — this file reads no secrets and opens no
    connections, and stays that way whether it raises or not.
    """


def _strict_voe_profile_enabled(value: str | None) -> bool:
    """The VOE profile activation law: malformed operator intent is never
    silently treated as disabled.

        unset, or empty after stripping         -> False
        an explicit accepted FALSE spelling      -> False
        an explicit accepted TRUE spelling       -> True
        any other non-empty value                -> SettingsError, loud

    Deliberately stricter than `_as_bool`, and deliberately not a change to
    `_as_bool` itself: `DEBUG` and any other ordinary feature flag keep their
    existing permissive-with-default behavior unchanged. Only this one
    governed activation switch refuses to guess.
    """
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized == "":
        return False
    if normalized in _VOE_PROFILE_ENABLED_FALSE_VALUES:
        return False
    if normalized in _VOE_PROFILE_ENABLED_TRUE_VALUES:
        return True
    accepted = sorted(_VOE_PROFILE_ENABLED_TRUE_VALUES | _VOE_PROFILE_ENABLED_FALSE_VALUES)
    raise SettingsError(
        f"VOE_PROFILE_ENABLED={value!r} is not a recognized value. "
        f"Unset or one of {accepted} is required; a malformed value is "
        "never silently treated as disabled."
    )


@dataclass(frozen=True)
class Settings:
    debug: bool
    default_top_k: int
    openai_model: str
    gemini_model: str
    embedding_backend: str          # "fake" | "local" | "openai"
    embedding_model: str
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    qdrant_upsert_batch_size: int   # points per Qdrant upsert request
    context_char_budget: int        # explicit truncation budget (docs/04)
    # The requested Model Execution Profile identity (TASK 20). "" is an
    # INVALID CONFIGURATION MARKER, never a default execution profile: no
    # policy may be silently selected. Composition (app/container.py) fails
    # closed on "", exactly as it does on an unknown identity — see docs/14.
    execution_profile_id: str = ""
    # VOE Dialogue Profile on/off switch (Gate 2 / Gate 2A). Defaults OFF:
    # absent or unset means the profile never loads and the runtime behaves
    # exactly as it did before this switch existed. Parsed STRICTLY, not by
    # the shared permissive `_as_bool`: a malformed value raises
    # `SettingsError` rather than silently resolving to False — see
    # `_strict_voe_profile_enabled`. This field is not yet read by
    # `app.container` or `Core.ask()` — it exists so `app.modules.voe_profile`
    # can be tested against real configuration values ahead of that later,
    # separately authorized wiring.
    voe_profile_enabled: bool = False
    # Directory expected to contain exactly the four files
    # `app.modules.voe_profile.loader.RUNTIME_BEHAVIORAL_FILES` names, by
    # fixed filename. "" is an INVALID CONFIGURATION MARKER, never a default
    # location: `resolve_voe_profile()` refuses to guess one. Unused when
    # `voe_profile_enabled` is False.
    voe_profile_bundle_dir: str = ""

    @staticmethod
    def load(env: dict[str, str] | None = None) -> "Settings":
        e = env if env is not None else os.environ
        return Settings(
            debug=_as_bool(e.get("DEBUG"), False),
            default_top_k=int(e.get("DEFAULT_TOP_K", "5")),
            openai_model=e.get("OPENAI_MODEL", ""),
            gemini_model=e.get("GEMINI_MODEL", ""),
            embedding_backend=e.get("EMBEDDING_BACKEND", "local"),
            embedding_model=e.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            qdrant_url=e.get("VECTOR_STORE_URL", "http://localhost:6333"),
            qdrant_api_key=e.get("VECTOR_STORE_API_KEY", ""),
            qdrant_collection=e.get("VECTOR_COLLECTION", "ion_corpus_v1"),
            qdrant_upsert_batch_size=int(e.get("QDRANT_UPSERT_BATCH_SIZE", "128")),
            context_char_budget=int(e.get("CONTEXT_CHAR_BUDGET", "60000")),
            # Missing EXECUTION_PROFILE becomes "", the invalid marker above —
            # never a silently chosen profile.
            execution_profile_id=e.get("EXECUTION_PROFILE", ""),
            voe_profile_enabled=_strict_voe_profile_enabled(e.get("VOE_PROFILE_ENABLED")),
            voe_profile_bundle_dir=e.get("VOE_PROFILE_BUNDLE_DIR", ""),
        )


def secret_presence(env: dict[str, str] | None = None) -> dict[str, bool]:
    """Booleans only — never the values (docs/11)."""
    e = env if env is not None else os.environ

    def present(name: str) -> bool:
        v = e.get(name)
        return bool(v and v.strip())

    return {
        "OPENAI_API_KEY": present("OPENAI_API_KEY"),
        "GEMINI_API_KEY": present("GEMINI_API_KEY"),
    }
